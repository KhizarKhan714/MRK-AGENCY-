"""
MRK AI Assistant — Flask Blueprint
════════════════════════════════════════════════════════════════════════
Self-contained AI division for MRK Agency. Registered onto the main
app with `app.register_blueprint(ai_bp)` — does not touch, import from,
or depend on any existing route in app.py. If this file has a bug, it
breaks /ai/* routes only — the rest of the site (hiring page included)
stays fully online.

WHAT THIS FILE DOES
- Client-facing chat: answers business questions + recommends the
  best-fit package, using a fixed knowledge-base prompt (edit
  KNOWLEDGE_BASE below whenever pricing/services change).
- Every exchange is saved to its own table (ai_conversations).
- A lightweight heuristic scores each exchange as a lead (high/medium/low).
- On a high-intent lead, sends the CEO an SMS via Twilio so no lead
  is missed even when away from the dashboard.
- Access is enforced by which ROUTES exist, not by asking the AI to
  behave — clients can only ever hit /ai/chat, which is hard-locked
  to the business-Q&A-and-recommendation system prompt below. There is
  no client route that reaches image generation, marketing tools, or
  anything else — those simply are not defined here.

ENV VARS REQUIRED (set these in Railway):
  GROQ_API_KEY        - free API key from console.groq.com, no card required
  TWILIO_ACCOUNT_SID  - from twilio.com console
  TWILIO_AUTH_TOKEN   - from twilio.com console
  TWILIO_FROM_NUMBER  - the Twilio number that sends the SMS (e.g. +1415...)
  CEO_PHONE_NUMBER    - your phone number to receive lead alerts (e.g. +923184467807)
DATABASE_URL is reused from the environment exactly like app.py does.
════════════════════════════════════════════════════════════════════════
"""

from flask import Blueprint, request, jsonify, session
import psycopg2
import os
import uuid
import requests

ai_bp = Blueprint('mrk_ai', __name__, url_prefix='/ai')

DATABASE_URL = os.environ.get('DATABASE_URL', '').replace('postgres://', 'postgresql://')
GROQ_API_KEY = os.environ.get('GROQ_API_KEY', '')
TWILIO_ACCOUNT_SID = os.environ.get('TWILIO_ACCOUNT_SID', '')
TWILIO_AUTH_TOKEN = os.environ.get('TWILIO_AUTH_TOKEN', '')
TWILIO_FROM_NUMBER = os.environ.get('TWILIO_FROM_NUMBER', '')
CEO_PHONE_NUMBER = os.environ.get('CEO_PHONE_NUMBER', '')


def get_db():
    return psycopg2.connect(DATABASE_URL)


def init_ai_db():
    """Call once at startup, same pattern as app.py's init_db()."""
    conn = get_db()
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS ai_conversations (
        id SERIAL PRIMARY KEY,
        client_id INTEGER,
        visitor_session TEXT NOT NULL,
        message TEXT NOT NULL,
        response TEXT NOT NULL,
        lead_score TEXT DEFAULT 'low',
        notified BOOLEAN DEFAULT FALSE,
        created_at TIMESTAMP DEFAULT NOW()
    )''')
    conn.commit()
    conn.close()


# ─── KNOWLEDGE BASE ─────────────────────────────────────────────────
# This is the ONLY place the AI's business knowledge lives. Edit this
# text whenever pricing/services/policy changes — no retraining, no
# redeploy of any model, it's just live text sent with every request.
KNOWLEDGE_BASE = """
You are the MRK AI Assistant for MRK Agency ("Where your brand achieves glory").
MRK Agency was founded on October 23, 2023, by Khizar Khan, who is the Founder & CEO.
MRK Agency offers: Web Development, SEO, Web Design, Graphic Design, UI/UX Design,
and Software Engineering. No ecommerce or marketing services are offered.

CONTACT: MRK Agency currently operates with the CEO as the sole point of contact for
new business. Clients should reach out via WhatsApp at +923184467807, or by email at
ceo@mrkagency.com, or by using the "Start a Project" flow on the site. There is no
other contact channel or team member to reach — all new project inquiries go to the
CEO directly.

PACKAGES (full builds):
- Bronze — $1,499 — 5 pages — 2 weeks — 100% upfront
- Consular — $2,999 — 10 pages — 3 weeks — 50% upfront / 50% on delivery
- Gold — $4,999 — 20 pages — 5 weeks — 30% upfront / 20% midpoint / 50% on delivery
- Diamond — $8,499 — unlimited pages — 10 weeks — 30% upfront / 20% midpoint / 50% on delivery
- Custom Executive — $10,000+ — everything in Diamond plus custom software and a
  dedicated point of contact — timeline and budget discussed individually
All packages include the same core services at greater depth as the tier increases.
There are no revision limits on any package.

À LA CARTE SERVICES (standalone, no full package needed):
- Web Design — $799 — design only, no build
- UI/UX Design — $999 — audit and redesign of an existing product's UX
- Graphic Design — $499 — logo and brand assets
- SEO — $599 — one-time technical setup (ongoing ranking work is separate)
- Web Development — $1,299 — add functionality to an existing site

YOUR JOB in every reply:
1. Answer the client's question using ONLY the information above.
2. If they describe a need or budget, recommend the single best-fit package
   or service and make the case for it — don't just list options and leave
   the decision to them. Sell it: point out what's included that they'd
   otherwise pay extra for elsewhere (no revision limits, full package
   scope vs piecemeal à la carte pricing), and frame it as the smart use
   of their budget, not just "the plan we recommend."
3. When a client's stated budget covers a higher tier than what they first
   asked about, mention the upgrade and what it unlocks — but never
   pressure them past their stated budget, and never invent a discount
   or price that isn't listed above.
4. If asked who runs MRK Agency, who founded it, when it was founded, or
   how to contact the company, answer using the CONTACT and founder info above.
5. Never invent pricing, timelines, or services not listed above.
6. Never discuss or reveal the company's technology stack, programming
   languages, databases, internal tools, how the CEO manages operations day
   to day, or any other internal/technical detail — none of that is listed
   above on purpose, and none of it should be guessed at or disclosed.
7. Never mention image generation, marketing asset creation, business
   reports, or any other internal/CEO tool — those do not exist for clients.
8. Keep replies short and conversational, not a wall of text.
9. If the client wants to proceed, tell them to use the "Get Started"
   flow on the site or the WhatsApp/email contact above.
"""


def call_groq(user_message, history):
    messages = [{"role": "system", "content": KNOWLEDGE_BASE}] + history + [{"role": "user", "content": user_message}]
    resp = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": "llama-3.3-70b-versatile",
            "max_tokens": 500,
            "messages": messages,
        },
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    return data["choices"][0]["message"]["content"]


# ─── LEAD SCORING ───────────────────────────────────────────────────
# Simple, fast, and easy for you to tune — no extra API call needed.
# Add/remove words any time to adjust sensitivity.
HIGH_INTENT_WORDS = [
    'ready to start', 'sign up', 'hire you', 'get started', 'how do i pay',
    'my budget is', 'when can we start', 'move forward', 'book a call',
    'contact number', 'whatsapp number', 'let\'s do it', 'i want to proceed',
]
MEDIUM_INTENT_WORDS = [
    'price', 'pricing', 'cost', 'package', 'quote', 'timeline', 'how long',
]

def score_lead(message):
    text = message.lower()
    if any(p in text for p in HIGH_INTENT_WORDS):
        return 'high'
    if any(p in text for p in MEDIUM_INTENT_WORDS):
        return 'medium'
    return 'low'


def notify_ceo_sms(visitor_session, message):
    if not (TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN and TWILIO_FROM_NUMBER and CEO_PHONE_NUMBER):
        return  # Twilio not configured yet — silently skip, don't crash the chat
    try:
        requests.post(
            f"https://api.twilio.com/2010-04-01/Accounts/{TWILIO_ACCOUNT_SID}/Messages.json",
            auth=(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN),
            data={
                "From": TWILIO_FROM_NUMBER,
                "To": CEO_PHONE_NUMBER,
                "Body": f"🔥 High-intent MRK lead ({visitor_session[:8]}): \"{message[:120]}\"",
            },
            timeout=10,
        )
    except Exception:
        pass  # never let a notification failure break the chat response


# ─── ROUTES ─────────────────────────────────────────────────────────

@ai_bp.route('/chat', methods=['POST'])
def chat():
    """
    The ONLY client-facing AI route. Deliberately does one thing:
    business Q&A + package recommendation. No other capability is
    reachable through this endpoint, by design.
    """
    data = request.get_json(silent=True) or {}
    user_message = (data.get('message') or '').strip()
    visitor_session = data.get('visitor_session') or str(uuid.uuid4())

    if not user_message:
        return jsonify({'error': 'message is required'}), 400

    client_id = session.get('customer_id')  # None for anonymous visitors

    conn = get_db()
    c = conn.cursor()

    # Pull last 6 exchanges for this visitor so Claude has context
    c.execute('''SELECT message, response FROM ai_conversations
                 WHERE visitor_session=%s ORDER BY id DESC LIMIT 6''', (visitor_session,))
    rows = c.fetchall()
    history = []
    for msg, resp in reversed(rows):
        history.append({"role": "user", "content": msg})
        history.append({"role": "assistant", "content": resp})

    try:
        reply = call_groq(user_message, history)
    except Exception:
        conn.close()
        return jsonify({'error': 'AI is temporarily unavailable, please try again shortly.'}), 503

    lead_score = score_lead(user_message)

    c.execute('''INSERT INTO ai_conversations
                 (client_id, visitor_session, message, response, lead_score)
                 VALUES (%s,%s,%s,%s,%s)''',
              (client_id, visitor_session, user_message, reply, lead_score))
    conn.commit()

    if lead_score == 'high':
        # avoid spamming the CEO — only notify if this visitor hasn't
        # triggered a high-intent alert in their last 5 messages
        c.execute('''SELECT COUNT(*) FROM ai_conversations
                     WHERE visitor_session=%s AND lead_score='high' AND notified=TRUE''',
                  (visitor_session,))
        already = c.fetchone()[0]
        if already == 0:
            notify_ceo_sms(visitor_session, user_message)
            c.execute('''UPDATE ai_conversations SET notified=TRUE
                         WHERE visitor_session=%s AND lead_score='high' ''',
                      (visitor_session,))
            conn.commit()

    conn.close()
    return jsonify({'reply': reply, 'visitor_session': visitor_session})


@ai_bp.route('/ceo/leads')
def ceo_leads():
    """
    CEO-only view of every AI conversation, grouped by visitor, newest
    first. Guarded the same way every other CEO route in app.py is —
    if there's no ceo session, bounce to login. This route (and this
    file) is the ONLY place that reads ai_conversations; clients never
    get access to this data through /ai/chat.
    """
    from flask import render_template, redirect, url_for

    if not session.get('ceo'):
        return redirect(url_for('ceo_login'))

    filter_score = request.args.get('filter', 'all')

    conn = get_db()
    c = conn.cursor()
    if filter_score in ('high', 'medium', 'low'):
        c.execute('''SELECT visitor_session, client_id, message, response,
                            lead_score, created_at
                     FROM ai_conversations
                     WHERE lead_score=%s
                     ORDER BY created_at DESC LIMIT 200''', (filter_score,))
    else:
        c.execute('''SELECT visitor_session, client_id, message, response,
                            lead_score, created_at
                     FROM ai_conversations
                     ORDER BY created_at DESC LIMIT 200''')
    rows = c.fetchall()

    c.execute('''SELECT lead_score, COUNT(*) FROM ai_conversations GROUP BY lead_score''')
    counts = {row[0]: row[1] for row in c.fetchall()}
    conn.close()

    conversations = [{
        'visitor_session': r[0],
        'client_id': r[1],
        'message': r[2],
        'response': r[3],
        'lead_score': r[4],
        'created_at': r[5],
    } for r in rows]

    return render_template('ceo_ai_leads.html',
                            conversations=conversations,
                            counts=counts,
                            active_filter=filter_score)
