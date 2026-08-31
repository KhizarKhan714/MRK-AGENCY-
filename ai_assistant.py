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
    # ─── ADDED: MRK AI — Contractor Intelligence & Assistance System.
    #     Separate table from ai_conversations (client chat) since these
    #     are scoped per contractor + per project, not per anonymous visitor.
    c.execute('''CREATE TABLE IF NOT EXISTS contractor_ai_conversations (
        id SERIAL PRIMARY KEY,
        contractor_id INTEGER NOT NULL,
        project_id INTEGER,
        message TEXT NOT NULL,
        response TEXT NOT NULL,
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


def call_groq(system_prompt, user_message, history):
    messages = [{"role": "system", "content": system_prompt}] + history + [{"role": "user", "content": user_message}]
    resp = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": "llama-3.3-70b-versatile",
            "max_tokens": 700,
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
        reply = call_groq(KNOWLEDGE_BASE, user_message, history)
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
  

# ═══════════════════════════════════════════════════════════════════════
# MRK AI — CONTRACTOR INTELLIGENCE & ASSISTANCE SYSTEM
# ═══════════════════════════════════════════════════════════════════════
# Advisory/operationally-supportive only. Unlike the client chat above
# (one static KNOWLEDGE_BASE for everyone), this builds a fresh system
# prompt per request from the authenticated contractor's own authorized
# project data — so it can never leak one contractor's project into
# another's conversation, and it never has to be manually edited when
# assignments change.

CONTRACTOR_AI_RULES = """
You are MRK AI, the internal assistant inside the MRK Agency Contractor Portal.
You are speaking with an authenticated, assigned contractor about their own
assigned work. You are NOT the client-facing sales assistant.

WHO YOU ARE TALKING TO: the contractor named {contractor_name}, viewing the
project context provided below. Use it to give specific, grounded answers —
never ask them to re-explain what project or role they're asking about if it's
already in the context below.

SOURCE-OF-TRUTH HIERARCHY — when multiple things could answer a question, prefer
information in this order and say so if it matters:
1. CEO-approved instructions (labeled "CEO DIRECTION" below)
2. Official project requirements (labeled "REQUIREMENTS" below)
3. Authorized client requirements included in the project description/objective
4. The contractor's own assigned role/task (labeled "YOUR ROLE" / "CURRENT TASK")
5. Other project/system data below (stage, deadline, deliverable status, files)
6. General technical knowledge (frameworks, tools, best practices — clearly
   your own knowledge, not project-specific fact)
7. Your own recommendations — ALWAYS label these explicitly as your suggestion,
   never phrase a recommendation as if it were a CEO or client instruction.

WHAT YOU MUST NEVER DO:
- Never invent or guess a deadline, requirement, client instruction, project
  status, approval, payment amount, assignment, CEO decision, credential, or
  deliverable that isn't in the context below. If it's not there, say plainly
  that this hasn't been specified and the contractor should ask the CEO.
- Never assign or reassign projects, change status/stage/deadlines, modify
  requirements or client info, modify contractor compensation, approve or
  reject work, override CEO instructions, or publish anything client-visible.
  You have no authority to do any of this — you can only explain, advise,
  and help the contractor do their own work better.
- Never present your own suggestion (a tool choice, an approach, a priority
  order) as if the CEO or client specifically asked for it.

WHAT YOU SHOULD DO WELL:
- When asked "what am I working on" / "explain my project" / "what's next",
  organize the context below into a clear, logical briefing — not a raw dump.
- Break tasks into concrete steps or checklists when helpful.
- Identify required vs. recommended vs. optional tools for a task, and explain
  why each matters — always distinguishing official requirements from your
  own suggestions.
- Proactively flag missing information that could block progress: say what's
  missing, why it's needed, what should be requested from the CEO or client,
  and whether work can reasonably continue without it in the meantime.
- Help debug, review work-in-progress against the stated requirements, explain
  APIs/frameworks, and help prepare a checklist before submission.
- If asked for a "today's work" briefing, summarize: top priority, secondary
  tasks, deadline, anything pending/blocked, tools needed, and a suggested
  order — grounded only in the context below.

Keep replies focused and practical — a working assistant, not a wall of text.
"""


def build_contractor_context(project, phases, client_files):
    """project is the explicit-column row from get_contractor_project();
    phases is a list of dicts from project_payments; client_files is a
    list of filenames. Builds the per-project context block injected
    into CONTRACTOR_AI_RULES for this one conversation."""
    lines = [f"PROJECT: {project['title']}"]
    if project['main_objective']:
        obj = project['main_objective']
        if project['main_objective_other']:
            obj += f" ({project['main_objective_other']})"
        lines.append(f"OBJECTIVE: {obj}")
    if project['description']:
        lines.append(f"DESCRIPTION: {project['description']}")
    if project['contractor_role']:
        lines.append(f"YOUR ROLE: {project['contractor_role']}")
    if project['current_task']:
        lines.append(f"CURRENT TASK: {project['current_task']}")
    if project['ceo_instructions']:
        lines.append(f"CEO DIRECTION: {project['ceo_instructions']}")
    if project['specific_requirements']:
        lines.append(f"REQUIREMENTS: {project['specific_requirements']}")
    if project['reference_sites']:
        lines.append(f"REFERENCE SITES PROVIDED: {project['reference_sites']}")
    lines.append(f"DEADLINE: {project['deadline'] or 'Not specified — ask the CEO if this matters for your planning.'}")
    lines.append(f"CLIENT-VISIBLE STAGE: {project['client_visible_stage'] or 'Not yet set'}")
    lines.append(f"PROJECT STATUS: {project['status']}")

    if phases:
        lines.append("MILESTONE STATUS:")
        for ph in phases:
            if ph['client_approved']:
                st = "Completed and approved by the client"
            elif ph['ceo_review_status'] == 'approved':
                st = "Approved by the CEO, now visible to the client for their review"
            elif ph['ceo_review_status'] == 'pending':
                st = "Submitted by you, awaiting CEO review"
            elif ph['ceo_review_status'] == 'revision_requested':
                st = f"CEO requested a revision: {ph['ceo_feedback'] or 'no detail given'}"
            else:
                st = "Not yet submitted"
            lines.append(f"  - Phase {ph['phase_number']} ({ph['phase_label']}): {st}")
    else:
        lines.append("MILESTONE STATUS: No payment phases found for this project.")

    if client_files:
        lines.append("CLIENT-PROVIDED FILES/ASSETS: " + ", ".join(client_files))
    else:
        lines.append("CLIENT-PROVIDED FILES/ASSETS: none uploaded yet.")

    return "\n".join(lines)


def get_contractor_projects(c, contractor_id):
    """All projects currently or recently assigned to this contractor,
    explicit columns only — never SELECT * across files, tuple drift
    between app.py and this file is exactly how the earlier bug happened."""
    c.execute('''SELECT id, title, status FROM projects
                 WHERE accepted_by=%s AND status IN ('approved','suspended','completed')
                 ORDER BY updated_at DESC''', (contractor_id,))
    return [{'id': r[0], 'title': r[1], 'status': r[2]} for r in c.fetchall()]


def get_contractor_project(c, contractor_id, project_id):
    """Single project, explicit columns, ownership-checked."""
    c.execute('''SELECT id, title, description, deadline, status, main_objective,
                        main_objective_other, contractor_role, current_task,
                        ceo_instructions, specific_requirements, reference_sites,
                        client_visible_stage
                 FROM projects WHERE id=%s AND accepted_by=%s''', (project_id, contractor_id))
    r = c.fetchone()
    if not r:
        return None
    return {'id': r[0], 'title': r[1], 'description': r[2], 'deadline': r[3], 'status': r[4],
            'main_objective': r[5], 'main_objective_other': r[6], 'contractor_role': r[7],
            'current_task': r[8], 'ceo_instructions': r[9], 'specific_requirements': r[10],
            'reference_sites': r[11], 'client_visible_stage': r[12]}


def get_project_phases(c, project_id):
    c.execute('''SELECT phase_number, phase_label, client_approved, ceo_review_status, ceo_feedback
                 FROM project_payments WHERE project_id=%s ORDER BY phase_number''', (project_id,))
    return [{'phase_number': r[0], 'phase_label': r[1], 'client_approved': r[2],
             'ceo_review_status': r[3], 'ceo_feedback': r[4]} for r in c.fetchall()]


def get_project_client_files(c, project_id):
    c.execute('''SELECT filename FROM files WHERE project_id=%s AND uploaded_by='client'
                 ORDER BY uploaded_at DESC''', (project_id,))
    return [r[0] for r in c.fetchall()]


@ai_bp.route('/contractor/projects')
def contractor_ai_projects():
    """Lightweight list for the widget's project picker — id/title/status
    only, so a contractor with multiple assignments can pick which one
    they're asking about."""
    if 'contractor_id' not in session:
        return jsonify({'error': 'not authenticated'}), 401
    conn = get_db()
    c = conn.cursor()
    projects = get_contractor_projects(c, session['contractor_id'])
    conn.close()
    return jsonify({'projects': projects})


@ai_bp.route('/contractor/history')
def contractor_ai_history():
    """Last exchanges for one project, so reopening the widget doesn't
    lose context — mirrors the client chat's history pull, but scoped
    per contractor+project instead of per anonymous visitor_session."""
    if 'contractor_id' not in session:
        return jsonify({'error': 'not authenticated'}), 401
    project_id = request.args.get('project_id', type=int)
    if not project_id:
        return jsonify({'error': 'project_id is required'}), 400
    conn = get_db()
    c = conn.cursor()
    c.execute('''SELECT message, response, created_at FROM contractor_ai_conversations
                 WHERE contractor_id=%s AND project_id=%s ORDER BY id DESC LIMIT 12''',
              (session['contractor_id'], project_id))
    rows = list(reversed(c.fetchall()))
    conn.close()
    return jsonify({'history': [{'message': r[0], 'response': r[1]} for r in rows]})


@ai_bp.route('/contractor/chat', methods=['POST'])
def contractor_chat():
    """The contractor-facing counterpart to /ai/chat. Gated by an actual
    session check (the client route intentionally has none — this one
    must, since it exposes per-project CEO instructions and client data)."""
    if 'contractor_id' not in session:
        return jsonify({'error': 'not authenticated'}), 401

    data = request.get_json(silent=True) or {}
    user_message = (data.get('message') or '').strip()
    project_id = data.get('project_id')
    if not user_message:
        return jsonify({'error': 'message is required'}), 400

    contractor_id = session['contractor_id']
    contractor_name = session.get('contractor_name', 'Contractor')

    conn = get_db()
    c = conn.cursor()

    projects = get_contractor_projects(c, contractor_id)
    if not projects:
        conn.close()
        return jsonify({'reply': "You don't have any assigned projects yet — once the CEO assigns you one, I'll be able to help with it."})

    if not project_id:
        if len(projects) == 1:
            project_id = projects[0]['id']
        else:
            conn.close()
            options = "\n".join(f"- {p['title']} (#{p['id']}, {p['status']})" for p in projects)
            return jsonify({
                'reply': f"You have {len(projects)} assigned projects — which one is this about?\n{options}",
                'projects': projects
            })

    project = get_contractor_project(c, contractor_id, project_id)
    if not project:
        conn.close()
        return jsonify({'error': 'That project is not assigned to you.'}), 403

    phases = get_project_phases(c, project_id)
    client_files = get_project_client_files(c, project_id)
    context_block = build_contractor_context(project, phases, client_files)
    system_prompt = CONTRACTOR_AI_RULES.format(contractor_name=contractor_name) + "\n\nCURRENT PROJECT CONTEXT:\n" + context_block

    c.execute('''SELECT message, response FROM contractor_ai_conversations
                 WHERE contractor_id=%s AND project_id=%s ORDER BY id DESC LIMIT 6''',
              (contractor_id, project_id))
    rows = c.fetchall()
    history = []
    for msg, resp in reversed(rows):
        history.append({"role": "user", "content": msg})
        history.append({"role": "assistant", "content": resp})

    try:
        reply = call_groq(system_prompt, user_message, history)
    except Exception:
        conn.close()
        return jsonify({'error': 'AI is temporarily unavailable, please try again shortly.'}), 503

    c.execute('''INSERT INTO contractor_ai_conversations (contractor_id, project_id, message, response)
                 VALUES (%s,%s,%s,%s)''', (contractor_id, project_id, user_message, reply))
    conn.commit()
    conn.close()

    return jsonify({'reply': reply, 'project_id': project_id})
  
