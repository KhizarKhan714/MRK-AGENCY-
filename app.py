from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, abort
from psycopg2.extras import RealDictCursor
from werkzeug.utils import secure_filename
from functools import wraps
from datetime import datetime, timedelta
import psycopg2
import bcrypt
import os
import base64
import random
import cloudinary
import cloudinary.uploader

app = Flask(__name__)
app.secret_key = 'mrk_ultra_secure_2026_khizar'
DATABASE_URL = os.environ.get('DATABASE_URL', '').replace('postgres://', 'postgresql://')

# MRK AI — self-contained blueprint, see ai_assistant.py. Registering it
# here does not add, remove, or alter any route below.
from ai_assistant import ai_bp, init_ai_db
app.register_blueprint(ai_bp)


def get_db():
    conn = psycopg2.connect(DATABASE_URL)
    return conn


def get_dict_db():
    conn = psycopg2.connect(DATABASE_URL)
    return conn, conn.cursor(cursor_factory=RealDictCursor)


cloudinary.config(
    cloud_name=os.environ.get('CLOUDINARY_CLOUD_NAME'),
    api_key=os.environ.get('CLOUDINARY_API_KEY'),
    api_secret=os.environ.get('CLOUDINARY_API_SECRET'),
    secure=True
)

def upload_image(file_storage, folder="mrk_agency"):
    if not file_storage or file_storage.filename == "":
        return None
    result = cloudinary.uploader.upload(file_storage, folder=folder)
    return result.get("secure_url")

def upload_multiple_images(file_list, folder="mrk_agency"):
    urls = []
    for f in file_list:
        u = upload_image(f, folder=folder)
        if u:
            urls.append(u)
    return urls


app.config['UPLOAD_FOLDER'] = 'uploads'
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'pdf', 'doc', 'docx'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def log_audit(actor_type, actor_id, actor_name, action, target_type=None, target_id=None):
    pass

def send_notification(recipient_type, recipient_id, title, message, link=None):
    pass


def ceo_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get('ceo'):
            return redirect(url_for('ceo_portal'))
        return f(*args, **kwargs)
    return wrapper


def get_site_settings():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT portfolio_visible, team_visible FROM site_settings WHERE id=1")
    row = c.fetchone()
    conn.close()
    return {'portfolio_section_visible': row[0], 'team_section_visible': row[1]}


def get_site_copy():
    conn = get_db()
    c = conn.cursor()
    c.execute('''SELECT hero_tagline, hero_subtext, agency_bio, contact_email,
                        contact_phone, contact_whatsapp, payoneer_email,
                        payoneer_account_name, payment_instructions,
                        linkedin_url, facebook_url, instagram_url, twitter_url
                 FROM site_settings WHERE id=1''')
    row = c.fetchone()
    conn.close()
    keys = ['hero_tagline', 'hero_subtext', 'agency_bio', 'contact_email',
            'contact_phone', 'contact_whatsapp', 'payoneer_email',
            'payoneer_account_name', 'payment_instructions',
            'linkedin_url', 'facebook_url', 'instagram_url', 'twitter_url']
    return dict(zip(keys, row))


@app.context_processor
def inject_globals():
    return {'site_settings': get_site_settings(), 'current_year': datetime.utcnow().year}


PACKAGE_INFO = {
    'Bronze':   {'price': 1499, 'weeks': 2,  'phases': [(1.00, 'Full payment')], 'category': 'package'},
    'Consular': {'price': 2999, 'weeks': 3,  'phases': [(0.50, 'Upfront'), (0.50, 'On delivery')], 'category': 'package'},
    'Gold':     {'price': 4999, 'weeks': 5,  'phases': [(0.30, 'Upfront'), (0.20, 'Midpoint review'), (0.50, 'On delivery')], 'category': 'package'},
    'Diamond':  {'price': 8499, 'weeks': 10, 'phases': [(0.30, 'Upfront'), (0.20, 'Midpoint review'), (0.50, 'On delivery')], 'category': 'package'},
    'Web Design (Service)':        {'price': 799,  'weeks': 1, 'phases': [(1.00, 'Full payment')], 'category': 'service', 'desc': 'Design only — no build. Ideal if you already have a developer or platform and just need the look done right.'},
    'UI/UX Design (Service)':      {'price': 999,  'weeks': 1, 'phases': [(1.00, 'Full payment')], 'category': 'service', 'desc': 'Audit and redesign of an existing product or site\u2019s user experience — flows, usability, and interface polish.'},
    'Graphic Design (Service)':    {'price': 499,  'weeks': 1, 'phases': [(1.00, 'Full payment')], 'category': 'service', 'desc': 'Logo and brand asset design — for a new identity or refreshing what you already have.'},
    'SEO (Service)':                {'price': 599,  'weeks': 1, 'phases': [(1.00, 'Full payment')], 'category': 'service', 'desc': 'One-time technical SEO setup — the foundation done right. Ongoing ranking work is a separate, recurring engagement.'},
    'Web Development (Service)':   {'price': 1299, 'weeks': 2, 'phases': [(1.00, 'Full payment')], 'category': 'service', 'desc': 'Add functionality to a site you already have — no need to rebuild everything from scratch.'},
}
CUSTOM_EXECUTIVE_PHASES = [(0.30, 'Upfront'), (0.20, 'Midpoint review'), (0.50, 'On delivery')]

# The 6-stage project timeline shown to clients. Order matters — index
# position is used everywhere progress is computed.
PROJECT_STAGES = ['Submitted', 'Planning', 'Design', 'Development', 'Testing', 'Delivered']


def create_payment_phases(conn_cursor, project_id, total_amount, phases):
    for i, (pct, label) in enumerate(phases, start=1):
        conn_cursor.execute(
            '''INSERT INTO project_payments (project_id, phase_number, phase_label, amount)
               VALUES (%s,%s,%s,%s)''',
            (project_id, i, label, round(float(total_amount) * pct, 2))
    )
def init_db():
    conn = get_db()
    c = conn.cursor()

    c.execute('''CREATE TABLE IF NOT EXISTS customers (
        id SERIAL PRIMARY KEY,
        first_name TEXT, last_name TEXT,
        email TEXT UNIQUE, password TEXT,
        photo TEXT,
        suspended BOOLEAN DEFAULT FALSE,
        phone TEXT,
        whatsapp TEXT)''')
    try: c.execute('ALTER TABLE customers ADD COLUMN IF NOT EXISTS photo TEXT')
    except: conn.rollback()
    try: c.execute('ALTER TABLE customers ADD COLUMN IF NOT EXISTS suspended BOOLEAN DEFAULT FALSE')
    except: conn.rollback()
    try: c.execute('ALTER TABLE customers ADD COLUMN IF NOT EXISTS phone TEXT')
    except: conn.rollback()
    try: c.execute('ALTER TABLE customers ADD COLUMN IF NOT EXISTS whatsapp TEXT')
    except: conn.rollback()

    c.execute('''CREATE TABLE IF NOT EXISTS contractors (
        id SERIAL PRIMARY KEY,
        name TEXT, password TEXT, expertise TEXT,
        experience TEXT, note TEXT, cin TEXT,
        status TEXT DEFAULT 'pending',
        email TEXT, phone TEXT, whatsapp TEXT,
        cnic TEXT, cnic_image TEXT, cv TEXT,
        specialties TEXT, suspended BOOLEAN DEFAULT FALSE,
        badge TEXT)''')
    try: c.execute('ALTER TABLE contractors ADD COLUMN IF NOT EXISTS email TEXT')
    except: conn.rollback()
    try: c.execute('ALTER TABLE contractors ADD COLUMN IF NOT EXISTS phone TEXT')
    except: conn.rollback()
    try: c.execute('ALTER TABLE contractors ADD COLUMN IF NOT EXISTS whatsapp TEXT')
    except: conn.rollback()
    try: c.execute('ALTER TABLE contractors ADD COLUMN IF NOT EXISTS cnic TEXT')
    except: conn.rollback()
    try: c.execute('ALTER TABLE contractors ADD COLUMN IF NOT EXISTS cnic_image TEXT')
    except: conn.rollback()
    try: c.execute('ALTER TABLE contractors ADD COLUMN IF NOT EXISTS cv TEXT')
    except: conn.rollback()
    try: c.execute('ALTER TABLE contractors ADD COLUMN IF NOT EXISTS specialties TEXT')
    except: conn.rollback()
    try: c.execute('ALTER TABLE contractors ADD COLUMN IF NOT EXISTS suspended BOOLEAN DEFAULT FALSE')
    except: conn.rollback()
    try: c.execute('ALTER TABLE contractors ADD COLUMN IF NOT EXISTS badge TEXT')
    except: conn.rollback()
    try: c.execute("ALTER TABLE contractors ADD COLUMN IF NOT EXISTS country TEXT")
    except: conn.rollback()
    try: c.execute("ALTER TABLE contractors ADD COLUMN IF NOT EXISTS national_id TEXT")
    except: conn.rollback()

    c.execute('''CREATE TABLE IF NOT EXISTS projects (
        id SERIAL PRIMARY KEY,
        customer_id INTEGER, title TEXT, description TEXT,
        website_type TEXT, budget TEXT, deadline TEXT,
        package TEXT, status TEXT DEFAULT 'pending',
        assigned_contractor_id INTEGER,
        contractor_pay TEXT,
        accepted_by INTEGER,
        rejection_reason TEXT,
        invoice_ref TEXT,
        completed BOOLEAN DEFAULT FALSE)''')
    try: c.execute('ALTER TABLE projects ADD COLUMN IF NOT EXISTS contractor_pay TEXT')
    except: conn.rollback()
    try: c.execute('ALTER TABLE projects ADD COLUMN IF NOT EXISTS accepted_by INTEGER')
    except: conn.rollback()
    try: c.execute('ALTER TABLE projects ADD COLUMN IF NOT EXISTS rejection_reason TEXT')
    except: conn.rollback()
    try: c.execute('ALTER TABLE projects ADD COLUMN IF NOT EXISTS invoice_ref TEXT')
    except: conn.rollback()
    try: c.execute('ALTER TABLE projects ADD COLUMN IF NOT EXISTS completed BOOLEAN DEFAULT FALSE')
    except: conn.rollback()

    # ─── ADDED (consolidated pass): timestamps + the contractor→CEO→client
    #     stage flow. client_visible_stage is the ONLY one ever shown to
    #     the client; contractor_stage_pending + stage_pending_approval
    #     hold the contractor's proposed change until the CEO approves it.
    for col, ddl in [
        ('created_at', 'TIMESTAMP DEFAULT NOW()'),
        ('updated_at', 'TIMESTAMP DEFAULT NOW()'),
        ('contractor_stage_pending', 'TEXT'),
        ('stage_pending_approval', 'BOOLEAN DEFAULT FALSE'),
        ('client_visible_stage', "TEXT DEFAULT 'Submitted'"),
    ]:
        try: c.execute(f'ALTER TABLE projects ADD COLUMN IF NOT EXISTS {col} {ddl}')
        except: conn.rollback()

    # ─── ADDED (consolidated pass): contractor availability (CEO-controlled,
    #     shown on the contractor's own Overview tab) + last login tracking.
    for col, ddl in [
        ('availability_status', "TEXT DEFAULT 'Available'"),
        ('last_login', 'TIMESTAMP'),
    ]:
        try: c.execute(f'ALTER TABLE contractors ADD COLUMN IF NOT EXISTS {col} {ddl}')
        except: conn.rollback()

    # ─── ADDED (consolidated pass): company announcements (CEO posts,
    #     every contractor sees them on their Overview tab).
    c.execute('''CREATE TABLE IF NOT EXISTS announcements (
        id SERIAL PRIMARY KEY,
        message TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT NOW())''')

    # ─── ADDED (consolidated pass): activity feeds — one per side, merged
    #     together for the CEO's Recent Activity / Activity Center.
    c.execute('''CREATE TABLE IF NOT EXISTS contractor_activity (
        id SERIAL PRIMARY KEY,
        contractor_id INTEGER REFERENCES contractors(id) ON DELETE CASCADE,
        action TEXT,
        created_at TIMESTAMP DEFAULT NOW())''')
    c.execute('''CREATE TABLE IF NOT EXISTS client_activity (
        id SERIAL PRIMARY KEY,
        customer_id INTEGER REFERENCES customers(id) ON DELETE CASCADE,
        action TEXT,
        created_at TIMESTAMP DEFAULT NOW())''')

    # ─── ADDED (consolidated pass): CEO login hardening — every attempt is
    #     logged; repeated failures from the same IP get locked out.
    c.execute('''CREATE TABLE IF NOT EXISTS ceo_login_attempts (
        id SERIAL PRIMARY KEY,
        ip TEXT,
        success BOOLEAN,
        attempted_at TIMESTAMP DEFAULT NOW())''')

    c.execute('''CREATE TABLE IF NOT EXISTS ceo (
        id SERIAL PRIMARY KEY,
        name TEXT, password TEXT, secret_key TEXT,
        security_answer TEXT)''')
    c.execute("SELECT COUNT(*) FROM ceo")
    if c.fetchone()[0] == 0:
        c.execute("INSERT INTO ceo (name, password, secret_key, security_answer) VALUES (%s,%s,%s,%s)",
             ('Khizar Khan', 'CEOMRKAgencyKhizarKhan', 'KhizarKhanCEOMRK7', 'Kiran'))

    # ─── ADDED: CEO Account page fields — runs every startup (IF NOT EXISTS
    #     makes re-runs safe), unconditional so it always applies regardless
    #     of whether the ceo row already existed.
    for col, ddl in [
        ('photo', 'TEXT'),
        ('email', 'TEXT'),
        ('backup_email', 'TEXT'),
        ('phone', 'TEXT'),
        ('whatsapp', 'TEXT'),
    ]:
        try: c.execute(f'ALTER TABLE ceo ADD COLUMN IF NOT EXISTS {col} {ddl}')
        except: conn.rollback()

    c.execute('''CREATE TABLE IF NOT EXISTS team_members (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    role TEXT,
    specialties TEXT,
    bio TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    projects_count INTEGER DEFAULT 0,
    photo TEXT
)''')
    try: c.execute('ALTER TABLE team_members ADD COLUMN IF NOT EXISTS is_published BOOLEAN DEFAULT FALSE')
    except: conn.rollback()
    try: c.execute('ALTER TABLE team_members ADD COLUMN IF NOT EXISTS display_order INTEGER DEFAULT 0')
    except: conn.rollback()

    c.execute('''CREATE TABLE IF NOT EXISTS portfolio_projects (
        id SERIAL PRIMARY KEY,
        title TEXT NOT NULL,
        category TEXT NOT NULL,
        package_tier TEXT,
        short_summary TEXT,
        full_description TEXT,
        tech_stack TEXT,
        client_name TEXT,
        is_confidential BOOLEAN DEFAULT FALSE,
        live_url TEXT,
        cover_image TEXT,
        gallery_images TEXT,
        is_published BOOLEAN DEFAULT FALSE,
        is_featured BOOLEAN DEFAULT FALSE,
        display_order INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT NOW())''')

    c.execute('''CREATE TABLE IF NOT EXISTS team_project_links (
        id SERIAL PRIMARY KEY,
        team_member_id INTEGER REFERENCES team_members(id) ON DELETE CASCADE,
        portfolio_project_id INTEGER REFERENCES portfolio_projects(id) ON DELETE CASCADE)''')

    c.execute('''CREATE TABLE IF NOT EXISTS site_settings (
        id SERIAL PRIMARY KEY,
        portfolio_visible BOOLEAN DEFAULT FALSE,
        team_visible BOOLEAN DEFAULT FALSE)''')
    c.execute("SELECT COUNT(*) FROM site_settings")
    if c.fetchone()[0] == 0:
        c.execute("INSERT INTO site_settings (portfolio_visible, team_visible) VALUES (FALSE, FALSE)")

    for col, ddl in [
        ('hero_tagline', "TEXT DEFAULT 'Where Your Brand Achieves Glory'"),
        ('hero_subtext', 'TEXT'),
        ('agency_bio', 'TEXT'),
        ('contact_email', "TEXT DEFAULT 'ceo@mrkagency.com'"),
        ('contact_phone', 'TEXT'),
        ('contact_whatsapp', 'TEXT'),
        ('payoneer_email', 'TEXT'),
        ('payoneer_account_name', 'TEXT'),
        ('payment_instructions', 'TEXT'),
    ]:
        try: c.execute(f'ALTER TABLE site_settings ADD COLUMN IF NOT EXISTS {col} {ddl}')
        except: conn.rollback()

    c.execute('''CREATE TABLE IF NOT EXISTS project_payments (
        id SERIAL PRIMARY KEY,
        project_id INTEGER REFERENCES projects(id) ON DELETE CASCADE,
        phase_number INTEGER,
        phase_label TEXT,
        amount NUMERIC(10,2),
        is_paid BOOLEAN DEFAULT FALSE,
        paid_at TIMESTAMP,
        payment_method TEXT DEFAULT 'Payoneer')''')

    for col, ddl in [
        ('bank_account_title', 'TEXT'),
        ('bank_account_number', 'TEXT'),
        ('bank_name', 'TEXT'),
        ('bank_swift_iban', 'TEXT'),
        ('photo', 'TEXT'),
    ]:
        try: c.execute(f'ALTER TABLE contractors ADD COLUMN IF NOT EXISTS {col} {ddl}')
        except: conn.rollback()

    c.execute('''CREATE TABLE IF NOT EXISTS bank_edit_requests (
        id SERIAL PRIMARY KEY,
        contractor_id INTEGER REFERENCES contractors(id) ON DELETE CASCADE,
        new_bank_account_title TEXT,
        new_bank_account_number TEXT,
        new_bank_name TEXT,
        new_bank_swift_iban TEXT,
        status TEXT DEFAULT 'pending',
        requested_at TIMESTAMP DEFAULT NOW(),
        decided_at TIMESTAMP)''')

    for col, ddl in [
        ('contractor_proof', 'TEXT'),
        ('contractor_submitted_at', 'TIMESTAMP'),
        ('client_approved', 'BOOLEAN DEFAULT FALSE'),
        ('client_approved_at', 'TIMESTAMP'),
        ('client_notes', 'TEXT'),
    ]:
        try: c.execute(f'ALTER TABLE project_payments ADD COLUMN IF NOT EXISTS {col} {ddl}')
        except: conn.rollback()

    c.execute('''CREATE TABLE IF NOT EXISTS contractor_payouts (
        id SERIAL PRIMARY KEY,
        project_id INTEGER REFERENCES projects(id) ON DELETE CASCADE,
        contractor_id INTEGER REFERENCES contractors(id) ON DELETE CASCADE,
        payout_type TEXT,
        amount NUMERIC(10,2),
        status TEXT DEFAULT 'pending',
        paid_at TIMESTAMP,
        created_at TIMESTAMP DEFAULT NOW())''')

    c.execute('''CREATE TABLE IF NOT EXISTS advance_requests (
        id SERIAL PRIMARY KEY,
        project_id INTEGER REFERENCES projects(id) ON DELETE CASCADE,
        contractor_id INTEGER REFERENCES contractors(id) ON DELETE CASCADE,
        amount_requested NUMERIC(10,2),
        reason TEXT,
        status TEXT DEFAULT 'pending',
        requested_at TIMESTAMP DEFAULT NOW(),
        decided_at TIMESTAMP)''')

    c.execute('''CREATE TABLE IF NOT EXISTS testimonials (
        id SERIAL PRIMARY KEY,
        customer_id INTEGER REFERENCES customers(id) ON DELETE CASCADE,
        rating INTEGER,
        review_text TEXT,
        is_published BOOLEAN DEFAULT TRUE,
        created_at TIMESTAMP DEFAULT NOW())''')

    for col, ddl in [
        ('linkedin_url', 'TEXT'),
        ('facebook_url', 'TEXT'),
        ('instagram_url', 'TEXT'),
        ('twitter_url', 'TEXT'),
    ]:
        try: c.execute(f'ALTER TABLE site_settings ADD COLUMN IF NOT EXISTS {col} {ddl}')
        except: conn.rollback()

    conn.commit()
    conn.close()

# ═══════════════════════════════════════════════════════════════════════
# ADDED (consolidated pass) — shared helpers for activity logging,
# notifications, business health, and the contractor→CEO→client stage flow.
# ════════════════════════════════════════════════════════════════  

def log_contractor_activity(c, contractor_id, action):
    c.execute("INSERT INTO contractor_activity (contractor_id, action) VALUES (%s,%s)", (contractor_id, action))

def log_client_activity(c, customer_id, action):
    c.execute("INSERT INTO client_activity (customer_id, action) VALUES (%s,%s)", (customer_id, action))

def touch_project(c, project_id):
    c.execute("UPDATE projects SET updated_at=NOW() WHERE id=%s", (project_id,))


def get_next_review_phase(c, project_id):
    c.execute('''SELECT phase_number, phase_label, contractor_proof, contractor_submitted_at,
                        client_approved, client_notes
                 FROM project_payments
                 WHERE project_id=%s AND client_approved=FALSE
                 ORDER BY phase_number LIMIT 1''', (project_id,))
    return c.fetchone()


def get_project_stage_info(c, project_ids=None):
    if project_ids is not None and not project_ids:
        return {}
    if project_ids is None:
        c.execute("SELECT id, client_visible_stage, contractor_stage_pending, stage_pending_approval FROM projects")
    else:
        c.execute("""SELECT id, client_visible_stage, contractor_stage_pending, stage_pending_approval
                     FROM projects WHERE id = ANY(%s)""", (list(project_ids),))
    info = {}
    for row in c.fetchall():
        info[row[0]] = {'current': row[1] or 'Submitted', 'pending': row[2] if row[3] else None}
    return info


def get_merged_activity(c, limit=None):
    c.execute('''SELECT action, created_at, 'contractor' AS src FROM contractor_activity
                 UNION ALL
                 SELECT action, created_at, 'client' AS src FROM client_activity
                 ORDER BY created_at DESC''' + (f' LIMIT {int(limit)}' if limit else ''))
    return c.fetchall()


def get_ceo_notifications(c, limit=None):
    notifs = []

    c.execute("SELECT COUNT(*) FROM contractors WHERE status='pending'")
    n = c.fetchone()[0]
    if n > 0:
        notifs.append({'dot': '🔴', 'text': f'{n} new contractor application(s) waiting', 'sub': 'Review and approve or reject', 'link': '/ceo/contractors'})

    c.execute("SELECT COUNT(*) FROM projects WHERE status='pending'")
    n = c.fetchone()[0]
    if n > 0:
        notifs.append({'dot': '🔴', 'text': f'{n} new project submission(s) waiting', 'sub': 'Review and approve or reject', 'link': '/ceo/projects'})

    c.execute('''SELECT COUNT(*) FROM project_payments
                 WHERE contractor_proof IS NOT NULL AND client_approved=FALSE''')
    n = c.fetchone()[0]
    if n > 0:
        notifs.append({'dot': '🔵', 'text': f'{n} milestone submission(s) awaiting client review', 'sub': 'Contractor has submitted proof', 'link': '/ceo/projects'})

    c.execute("SELECT COUNT(*) FROM bank_edit_requests WHERE status='pending'")
    n = c.fetchone()[0]
    if n > 0:
        notifs.append({'dot': '🟡', 'text': f'{n} bank detail change request(s) pending', 'sub': 'Contractor payout details', 'link': '/ceo/contractors'})

    c.execute("SELECT COUNT(*) FROM advance_requests WHERE status='pending'")
    n = c.fetchone()[0]
    if n > 0:
        notifs.append({'dot': '🟡', 'text': f'{n} advance payment request(s) pending', 'sub': 'Contractor requesting funds', 'link': '/ceo/finance'})

    c.execute("SELECT COUNT(*) FROM projects WHERE stage_pending_approval=TRUE")
    n = c.fetchone()[0]
    if n > 0:
        notifs.append({'dot': '🔵', 'text': f'{n} project stage update(s) proposed by contractors', 'sub': 'Awaiting your approval', 'link': '/ceo/projects'})

    c.execute("SELECT COUNT(*) FROM projects WHERE status='completed'")
    n = c.fetchone()[0]
    if n > 0:
        notifs.append({'dot': '🟢', 'text': f'{n} project(s) completed', 'sub': 'All-time', 'link': '/ceo/projects'})

    return notifs[:limit] if limit else notifs


def get_pending_approvals(c, limit=None):
    approvals = []
    c.execute("SELECT id, name, expertise FROM contractors WHERE status='pending' ORDER BY id DESC")
    for row in c.fetchall():
        approvals.append({'text': f'Contractor application — {row[1]}', 'sub': row[2] or 'General', 'link': '/ceo/contractors'})
    c.execute("SELECT id, title FROM projects WHERE status='pending' ORDER BY id DESC")
    for row in c.fetchall():
        approvals.append({'text': f'Project submission — {row[1]}', 'sub': f'Project #{row[0]}', 'link': '/ceo/projects'})
    return approvals[:limit] if limit else approvals


def get_monthly_revenue(months=6):
    conn = get_db(); c = conn.cursor()
    c.execute('''SELECT TO_CHAR(paid_at, 'Mon YYYY') AS month, SUM(amount)
                 FROM project_payments WHERE is_paid=TRUE AND paid_at IS NOT NULL
                 GROUP BY TO_CHAR(paid_at, 'Mon YYYY'), DATE_TRUNC('month', paid_at)
                 ORDER BY DATE_TRUNC('month', paid_at) DESC LIMIT %s''', (months,))
    rows = c.fetchall()
    conn.close()
    return [{'month': r[0], 'amount': float(r[1])} for r in reversed(rows)]


def get_business_health():
    conn = get_db(); c = conn.cursor()

    c.execute("SELECT COUNT(*) FROM projects WHERE status IN ('approved','completed')")
    total_started = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM projects WHERE status='completed'")
    completed = c.fetchone()[0]
    completion_rate = f"{round(completed/total_started*100)}%" if total_started else "No Data Yet"

    c.execute('''SELECT COALESCE(SUM(amount),0) FROM project_payments
                 WHERE is_paid=TRUE AND paid_at >= DATE_TRUNC('month', NOW())''')
    this_month = float(c.fetchone()[0])
    c.execute('''SELECT COALESCE(SUM(amount),0) FROM project_payments
                 WHERE is_paid=TRUE AND paid_at >= DATE_TRUNC('month', NOW() - INTERVAL '1 month')
                 AND paid_at < DATE_TRUNC('month', NOW())''')
    last_month = float(c.fetchone()[0])
    if this_month == 0 and last_month == 0:
        revenue_trend = "No Data Yet"
    elif this_month > last_month:
        revenue_trend = "Growing"
    elif this_month < last_month:
        revenue_trend = "Declining"
    else:
        revenue_trend = "Stable"

    c.execute("SELECT AVG(rating) FROM testimonials WHERE is_published=TRUE")
    avg_rating = c.fetchone()[0]
    satisfaction = f"{round(float(avg_rating),1)} / 5" if avg_rating else "No Data Yet"

    c.execute('''SELECT AVG(EXTRACT(EPOCH FROM (updated_at - created_at))/86400.0)
                 FROM projects WHERE status='completed' AND created_at IS NOT NULL''')
    avg_days = c.fetchone()[0]
    avg_delivery = f"{round(float(avg_days),1)} Days" if avg_days else "No Data Yet"

    try:
        c.execute('''SELECT COUNT(*) FROM projects p
                     WHERE p.status='approved' AND p.deadline IS NOT NULL
                     AND p.deadline != '' AND p.deadline::date < CURRENT_DATE''')
        overdue = c.fetchone()[0]
    except Exception:
        conn.rollback()
        overdue = 0
    status = "Healthy" if overdue == 0 else "Needs Attention"

    conn.close()
    return {'status': status, 'revenue_trend': revenue_trend, 'completion_rate': completion_rate,
            'satisfaction': satisfaction, 'avg_delivery': avg_delivery}


def get_morning_brief():
    conn = get_db(); c = conn.cursor()
    # ─── FIXED: server runs in UTC, but the CEO is in Pakistan (UTC+5) —
    #     using raw UTC hour was producing wrong greetings (e.g. "Good
    #     Afternoon" at night). Offset to local time for the greeting only.
    local_hour = (datetime.utcnow() + timedelta(hours=5)).hour
    time_of_day = 'Morning' if local_hour < 12 else ('Afternoon' if local_hour < 18 else 'Evening')

    summary = []
    c.execute("SELECT COUNT(*) FROM contractors WHERE status='pending'")
    n = c.fetchone()[0]
    if n: summary.append(f"{n} contractor(s) awaiting approval")

    try:
        c.execute('''SELECT COUNT(*) FROM projects WHERE status='approved' AND deadline IS NOT NULL
                     AND deadline != '' AND deadline::date BETWEEN CURRENT_DATE AND CURRENT_DATE + INTERVAL '3 days' ''')
        n = c.fetchone()[0]
    except Exception:
        conn.rollback(); n = 0
    if n: summary.append(f"{n} project(s) nearing deadline")

    c.execute('''SELECT COUNT(*) FROM project_payments WHERE is_paid=FALSE''')
    n = c.fetchone()[0]
    summary.append(f"{n} invoice(s) still unpaid" if n else "No overdue invoices")

    c.execute('''SELECT COALESCE(SUM(amount),0) FROM project_payments
                 WHERE is_paid=TRUE AND paid_at >= DATE_TRUNC('month', NOW())''')
    month_rev = float(c.fetchone()[0])
    summary.append(f"Revenue this month: ${month_rev:,.2f}")

    c.execute("SELECT COUNT(*) FROM contractors WHERE status='pending'")
    pending_ct = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM projects WHERE status='pending'")
    pending_pr = c.fetchone()[0]
    if pending_ct:
        focus = "Approve contractor applications."
    elif pending_pr:
        focus = "Review pending project submissions."
    else:
        focus = "You're all caught up — great time to plan ahead."

    conn.close()
    return time_of_day, summary, focus


# ═══════════════════════════════════════════════════════════════════════
# MRK AI — implemented in ai_assistant.py (Blueprint, url_prefix='/ai').
# Client-facing chat lives at POST /ai/chat. /ceo/ai-center below still
# shows "Coming Soon" cards — swap those for real links whenever ready.
# ═══════════════════════════════════════════════════════════════════════


# ─── HOME ───────────────────────────────────────────────
@app.route('/')
def home():
    conn, c = get_dict_db()
    c.execute("SELECT * FROM portfolio_projects WHERE is_published=TRUE AND is_featured=TRUE ORDER BY display_order LIMIT 3")
    featured_projects = c.fetchall()
    c.execute("SELECT * FROM team_members WHERE is_published=TRUE ORDER BY display_order LIMIT 3")
    featured_team = c.fetchall()
    c.execute('''SELECT t.rating, t.review_text, t.created_at, cu.first_name, cu.last_name
                 FROM testimonials t JOIN customers cu ON cu.id = t.customer_id
                 WHERE t.is_published=TRUE ORDER BY t.created_at DESC LIMIT 12''')
    testimonials = c.fetchall()
    conn.close()
    return render_template('index.html', featured_projects=featured_projects,
                           featured_team=featured_team, testimonials=testimonials)


# ─── CUSTOMER AUTH ──────────────────────────────────────
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        try:
            fn = request.form['first_name'].strip()
            ln = request.form['last_name'].strip()
            email = request.form['email'].strip()
            phone = request.form.get('phone', '').strip()
            whatsapp = request.form.get('whatsapp', '').strip()
            pw = bcrypt.hashpw(request.form['password'].encode(), bcrypt.gensalt())
            conn = get_db()
            c = conn.cursor()
            c.execute('INSERT INTO customers (first_name,last_name,email,password,phone,whatsapp) VALUES (%s,%s,%s,%s,%s,%s)',
                      (fn, ln, email, pw.decode(), phone, whatsapp))
            conn.commit()
            conn.close()
            return redirect(url_for('login'))
        except:
            return render_template('register.html', error='Email already exists or invalid data.')
    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email'].strip()
        pw = request.form['password'].encode()
        conn = get_db()
        c = conn.cursor()
        c.execute('SELECT * FROM customers WHERE email=%s', (email,))
        user = c.fetchone()
        conn.close()
        if user and bcrypt.checkpw(pw, user[4].encode()):
            if user[6]:
                return render_template('login.html', error='Your account has been suspended. Contact MRK Agency.')
            session['customer_id'] = user[0]
            session['customer_name'] = user[1]
            return redirect(url_for('dashboard'))
        return render_template('login.html', error='Invalid email or password.')
    return render_template('login.html')


@app.route('/logout')
def logout():
    session.pop('customer_id', None)
    session.pop('customer_name', None)
    return redirect(url_for('login'))


# ─── CLIENT DASHBOARD (Workplace home) ──────────────────
@app.route('/dashboard')
def dashboard():
    if 'customer_id' not in session:
        return redirect(url_for('login'))
    cid = session['customer_id']
    conn = get_db()
    c = conn.cursor()

    c.execute('SELECT * FROM projects WHERE customer_id=%s ORDER BY updated_at DESC', (cid,))
    projects = c.fetchall()
    total_project_count = len(projects)

    active_count = sum(1 for p in projects if p[8] == 'approved')
    completed_count = sum(1 for p in projects if p[8] == 'completed')

    pending_payments_total = 0.0
    open_requests_count = 0
    latest_project_id = projects[0][0] if projects else None

    stage_info = get_project_stage_info(c, [p[0] for p in projects]) if projects else {}

    recent_projects = []
    project_health = None
    timeline_project = None

    for p in projects:
        c.execute('''SELECT COALESCE(SUM(amount),0) FROM project_payments
                     WHERE project_id=%s AND is_paid=FALSE''', (p[0],))
        due = float(c.fetchone()[0])
        pending_payments_total += due

        rv = get_next_review_phase(c, p[0])
        if rv and rv[3]:
            open_requests_count += 1

        info = stage_info.get(p[0], {'current': 'Submitted', 'pending': None})
        try:
            stage_idx = PROJECT_STAGES.index(info['current'])
        except ValueError:
            stage_idx = 0
        progress_pct = round((stage_idx / (len(PROJECT_STAGES) - 1)) * 100)

        status_map = {'pending': 'pending', 'approved': 'approved', 'completed': 'completed', 'rejected': 'rejected'}
        status_label_map = {'pending': '⏳ Pending', 'approved': '🟢 In Progress', 'completed': '🏁 Completed', 'rejected': '❌ Rejected'}

        if len(recent_projects) < 3:
            recent_projects.append({
                'title': p[2],
                'status': status_map.get(p[8], p[8]),
                'status_label': status_label_map.get(p[8], p[8]),
                'progress_pct': progress_pct,
                'last_updated': p[16].strftime('%b %d') if len(p) > 16 and p[16] else 'Recently'
            })

        if p[8] == 'approved' and timeline_project is None:
            timeline_project = {'title': p[2], 'stage_index': stage_idx}

        if p[8] == 'approved' and project_health is None:
            rv_notes = rv[5] if rv else None
            overdue = False
            if p[6]:
                try:
                    overdue = datetime.strptime(p[6], '%Y-%m-%d').date() < datetime.utcnow().date()
                except Exception:
                    overdue = False
            if rv_notes:
                project_health = {'status': 'warn', 'message': 'Delivery has been extended.', 'reason': 'Client requested additional revisions.'}
            elif overdue:
                project_health = {'status': 'warn', 'message': 'This project has passed its original deadline.', 'reason': 'Timeline extended — check in with your account manager.'}
            else:
                project_health = {'status': 'good', 'message': 'Everything is on schedule.', 'expected_delivery': p[6] or 'TBD'}

    c.execute("SELECT action, created_at FROM client_activity WHERE customer_id=%s ORDER BY created_at DESC LIMIT 6", (cid,))
    recent_activity = [{'time': r[1].strftime('%b %d, %-I:%M %p') if r[1] else '', 'text': r[0]} for r in c.fetchall()]

    c.execute("SELECT action FROM client_activity WHERE customer_id=%s ORDER BY created_at DESC LIMIT 4", (cid,))
    notifications = [r[0] for r in c.fetchall()]

    site_copy = get_site_copy()
    conn.close()

    return render_template('dashboard.html', name=session['customer_name'],
        total_project_count=total_project_count, active_count=active_count, completed_count=completed_count,
        pending_payments_total=pending_payments_total, open_requests_count=open_requests_count,
        recent_projects=recent_projects, project_health=project_health, timeline_project=timeline_project,
        recent_activity=recent_activity, notifications=notifications,
        contact_whatsapp=site_copy.get('contact_whatsapp'), latest_project_id=latest_project_id)


# ─── CUSTOMER PROFILE ───────────────────────────────────
@app.route('/profile')
def profile():
    if 'customer_id' not in session:
        return redirect(url_for('login'))
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT id, first_name, last_name, email, photo, phone, whatsapp FROM customers WHERE id=%s', (session['customer_id'],))
    row = c.fetchone()
    conn.close()
    customer = {'id': row[0], 'first_name': row[1], 'last_name': row[2], 'email': row[3], 'photo': row[4], 'phone': row[5], 'whatsapp': row[6]}
    return render_template('profile.html', customer=customer)


@app.route('/update-profile', methods=['POST'])
def update_profile():
    if 'customer_id' not in session:
        return redirect(url_for('login'))
    action = request.form.get('action')
    conn = get_db()
    c = conn.cursor()

    def get_customer():
        c.execute('SELECT id, first_name, last_name, email, photo FROM customers WHERE id=%s', (session['customer_id'],))
        row = c.fetchone()
        return {'id': row[0], 'first_name': row[1], 'last_name': row[2], 'email': row[3], 'photo': row[4]}

    if action == 'update_info':
        fn = request.form['first_name'].strip()
        ln = request.form['last_name'].strip()
        email = request.form['email'].strip()
        try:
            c.execute('UPDATE customers SET first_name=%s, last_name=%s, email=%s WHERE id=%s',
                      (fn, ln, email, session['customer_id']))
            conn.commit()
            session['customer_name'] = fn
            customer = get_customer()
            conn.close()
            return render_template('profile.html', customer=customer, success='Profile updated successfully.')
        except:
            conn.close()
            conn2 = get_db(); c2 = conn2.cursor()
            c2.execute('SELECT id, first_name, last_name, email, photo FROM customers WHERE id=%s', (session['customer_id'],))
            row = c2.fetchone()
            customer = {'id': row[0], 'first_name': row[1], 'last_name': row[2], 'email': row[3], 'photo': row[4]}
            conn2.close()
            return render_template('profile.html', customer=customer, error='Email already in use.')

    elif action == 'change_password':
        current_pw = request.form['current_password'].encode()
        new_pw = request.form['new_password']
        confirm_pw = request.form['confirm_password']
        c.execute('SELECT password FROM customers WHERE id=%s', (session['customer_id'],))
        row = c.fetchone()
        customer = get_customer()
        if not bcrypt.checkpw(current_pw, row[0].encode()):
            conn.close()
            return render_template('profile.html', customer=customer, error='Current password is incorrect.')
        if new_pw != confirm_pw:
            conn.close()
            return render_template('profile.html', customer=customer, error='New passwords do not match.')
        if len(new_pw) < 6:
            conn.close()
            return render_template('profile.html', customer=customer, error='Password must be at least 6 characters.')
        hashed = bcrypt.hashpw(new_pw.encode(), bcrypt.gensalt()).decode()
        c.execute('UPDATE customers SET password=%s WHERE id=%s', (hashed, session['customer_id']))
        conn.commit()
        conn.close()
        return render_template('profile.html', customer=customer, success='Password changed successfully.')

    elif action == 'update_photo':
        photo_file = request.files.get('photo')
        if photo_file and photo_file.filename:
            photo_data = photo_file.read()
            b64 = base64.b64encode(photo_data).decode()
            mime = photo_file.content_type
            data_url = f'data:{mime};base64,{b64}'
            c.execute('UPDATE customers SET photo=%s WHERE id=%s', (data_url, session['customer_id']))
            conn.commit()
        customer = get_customer()
        conn.close()
        return render_template('profile.html', customer=customer, success='Profile photo updated.')

    conn.close()
    return redirect(url_for('profile'))


# ─── PROJECTS ─────────────────────────────────
@app.route('/submit-project', methods=['GET', 'POST'])
def submit_project():
    if 'customer_id' not in session:
        return redirect(url_for('login'))
    if request.method == 'POST':
        try:
            package = request.form['package']
            title = request.form['title']
            description = request.form['description']
            pages_needed = request.form.get('pages_needed', '')
            tech_preference = request.form.get('tech_preference', '')
            reference_sites = request.form.get('reference_sites', '')
            must_have_features = request.form.get('must_have_features', '')

            extra_lines = []
            if pages_needed: extra_lines.append(f"Pages/sections wanted: {pages_needed}")
            if tech_preference: extra_lines.append(f"Language/tech preference: {tech_preference}")
            if reference_sites: extra_lines.append(f"Reference sites: {reference_sites}")
            if must_have_features: extra_lines.append(f"Must-have features: {must_have_features}")
            if extra_lines:
                description = description + "\n\n---\n" + "\n".join(extra_lines)

            if package == 'Custom Executive':
                budget = request.form.get('budget', '0') or '0'
                deadline = request.form.get('deadline', '')
                custom_scope = request.form.get('custom_scope', '')
                if custom_scope:
                    description = description + f"\n\nCustom software scope: {custom_scope}"
                phases = CUSTOM_EXECUTIVE_PHASES
            elif package in PACKAGE_INFO:
                info = PACKAGE_INFO[package]
                budget = str(info['price'])
                deadline = (datetime.utcnow() + timedelta(weeks=info['weeks'])).strftime('%Y-%m-%d')
                phases = info['phases']
            else:
                raise ValueError('Unknown package selected.')

            conn = get_db()
            c = conn.cursor()
            c.execute('''INSERT INTO projects
                (customer_id,title,description,website_type,budget,deadline,package)
                VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id''',
                (session['customer_id'], title, description, package, budget, deadline, package))
            new_id = c.fetchone()[0]

            create_payment_phases(c, new_id, budget, phases)
            log_client_activity(c, session['customer_id'], f'Project submitted: {title}')

            conn.commit()
            conn.close()
            return redirect(url_for('invoice', project_id=new_id))
        except Exception as e:
            return render_template('submit_project.html', error=str(e))
    return render_template('submit_project.html')


@app.route('/my-projects')
def my_projects():
    if 'customer_id' not in session:
        return redirect(url_for('login'))
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT * FROM projects WHERE customer_id=%s', (session['customer_id'],))
    projects = c.fetchall()

    amount_due = {}
    for p in projects:
        c.execute('''SELECT COALESCE(SUM(amount),0) FROM project_payments
                     WHERE project_id=%s AND is_paid=FALSE''', (p[0],))
        amount_due[p[0]] = float(c.fetchone()[0])

    review_status = {}
    for p in projects:
        phase = get_next_review_phase(c, p[0])
        if phase and phase[3]:
            review_status[p[0]] = {
                'phase_number': phase[0], 'phase_label': phase[1],
                'proof': phase[2], 'submitted_at': phase[3]
            }

    conn.close()
    return render_template('my_projects.html', projects=projects, amount_due=amount_due, review_status=review_status)


# ─── INVOICE ────────────────────────────────────────────
@app.route('/invoice/<int:project_id>')
def invoice(project_id):
    if 'customer_id' not in session:
        return redirect(url_for('login'))
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT * FROM projects WHERE id=%s AND customer_id=%s', (project_id, session['customer_id']))
    project = c.fetchone()
    if not project:
        conn.close()
        return redirect(url_for('my_projects'))

    c.execute('''SELECT phase_number, phase_label, amount, is_paid, paid_at
                 FROM project_payments WHERE project_id=%s ORDER BY phase_number''', (project_id,))
    phase_rows = c.fetchall()
    conn.close()

    phases = [{'number': r[0], 'label': r[1], 'amount': float(r[2]), 'is_paid': r[3], 'paid_at': r[4]} for r in phase_rows]
    total_amount = sum(p['amount'] for p in phases)
    total_paid = sum(p['amount'] for p in phases if p['is_paid'])
    amount_due_now = sum(p['amount'] for p in phases if not p['is_paid'])
    fully_paid = amount_due_now == 0 and len(phases) > 0
    next_due_phase = next((p for p in phases if not p['is_paid']), None)

    settings = get_site_copy()

    return render_template('invoice.html', project=project, phases=phases,
                           total_amount=total_amount, total_paid=total_paid,
                           amount_due_now=amount_due_now, fully_paid=fully_paid,
                           next_due_phase=next_due_phase, settings=settings)


# ─── CONTRACTOR APPLY ───────────────────────────────────
@app.route('/contractor-apply', methods=['GET', 'POST'])
@app.route('/contractor/apply', methods=['GET', 'POST'])
def contractor_apply():
    if request.method == 'POST':
        name        = request.form['name'].strip()
        email       = request.form['email'].strip().lower()
        country     = request.form.get('country', '').strip()
        phone       = request.form.get('phone', '').strip()
        whatsapp    = request.form.get('whatsapp', '').strip()
        national_id = request.form.get('national_id', '').strip()
        expertise   = request.form['expertise']
        experience  = request.form.get('experience', '')
        specialties = request.form.get('specialties', '')
        note        = request.form.get('note', '')
        password    = request.form['password']
        hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

        bank_account_title  = request.form.get('bank_account_title', '').strip()
        bank_account_number = request.form.get('bank_account_number', '').strip()
        bank_name            = request.form.get('bank_name', '').strip()
        bank_swift_iban      = request.form.get('bank_swift_iban', '').strip()

        cnic_image_name = None
        cv_name = None

        if 'cnic_image' in request.files:
            f = request.files['cnic_image']
            if f and allowed_file(f.filename):
                cnic_image_name = secure_filename(f'id_{name}_{f.filename}')
                f.save(os.path.join(app.config['UPLOAD_FOLDER'], cnic_image_name))

        if 'cv' in request.files:
            f = request.files['cv']
            if f and allowed_file(f.filename):
                cv_name = secure_filename(f'cv_{name}_{f.filename}')
                f.save(os.path.join(app.config['UPLOAD_FOLDER'], cv_name))

        conn = get_db()
        c = conn.cursor()
        c.execute('''INSERT INTO contractors
            (name, email, phone, whatsapp, cnic, cnic_image, cv,
             expertise, experience, specialties, note, password, status,
             country, national_id, bank_account_title, bank_account_number,
             bank_name, bank_swift_iban)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'pending',%s,%s,%s,%s,%s,%s)
            RETURNING id''',
            (name, email, phone, whatsapp, national_id, cnic_image_name, cv_name,
             expertise, experience, specialties, note, hashed,
             country, national_id, bank_account_title, bank_account_number,
             bank_name, bank_swift_iban))
        new_id = c.fetchone()[0]
        conn.commit()
        conn.close()

        log_audit('contractor', new_id, name, 'CONTRACTOR_APPLIED',
                  target_type='contractor', target_id=new_id)
        send_notification('ceo', 1, f'New Contractor Application: {name}',
                          f'{expertise} specialist from {country} applied.',
                          '/mrkceokhan7/dashboard')
        flash('Application submitted! You will receive your CIN upon approval.', 'success')
        return redirect(url_for('contractor_login'))
    return render_template('contractor_apply.html')


# ─── CONTRACTOR LOGIN ────────────────────────────────────
@app.route('/contractor-login', methods=['GET', 'POST'])
def contractor_login():
    if request.method == 'POST':
        cin = request.form['cin'].strip()
        pw = request.form['password'].encode()
        conn = get_db()
        c = conn.cursor()
        c.execute('SELECT * FROM contractors WHERE cin=%s', (cin,))
        contractor = c.fetchone()
        if contractor and bcrypt.checkpw(pw, contractor[2].encode()):
            if contractor[15]:
                conn.close()
                return render_template('contractor_login.html', error='Your account has been suspended. Contact MRK Agency.')
            session['contractor_id'] = contractor[0]
            session['contractor_name'] = contractor[1]
            c.execute("UPDATE contractors SET last_login=NOW() WHERE id=%s", (contractor[0],))
            log_contractor_activity(c, contractor[0], 'Logged in')
            conn.commit()
            conn.close()
            return redirect(url_for('contractor_dashboard'))
        conn.close()
        return render_template('contractor_login.html', error='Invalid CIN or password.')
    return render_template('contractor_login.html')


@app.route('/contractor-logout')
def contractor_logout():
    session.pop('contractor_id', None)
    session.pop('contractor_name', None)
    return redirect(url_for('contractor_login'))


# ─── CONTRACTOR DASHBOARD (Workplace) ───────────────────
@app.route('/contractor-dashboard')
def contractor_dashboard():
    if 'contractor_id' not in session:
        return redirect(url_for('contractor_login'))
    cid = session['contractor_id']
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT * FROM contractors WHERE id=%s', (cid,))
    contractor = c.fetchone()

    c.execute('SELECT availability_status, last_login FROM contractors WHERE id=%s', (cid,))
    avail_row = c.fetchone()
    availability_status = avail_row[0] or 'Available'
    last_login = avail_row[1]

    c.execute("""SELECT * FROM projects
                 WHERE status='approved' AND contractor_pay IS NOT NULL
                 AND (accepted_by IS NULL OR accepted_by=%s)
                 AND (completed IS NULL OR completed=FALSE)""", (cid,))
    projects = c.fetchall()

    review_status = {}
    for p in projects:
        if p[11] == cid:
            phase = get_next_review_phase(c, p[0])
            if phase:
                review_status[p[0]] = {
                    'phase_number': phase[0], 'phase_label': phase[1],
                    'proof': phase[2], 'submitted_at': phase[3],
                    'client_approved': phase[4], 'client_notes': phase[5]
                }

    c.execute('''SELECT project_id, payout_type, amount, status, paid_at
                 FROM contractor_payouts WHERE contractor_id=%s
                 ORDER BY project_id, created_at''', (cid,))
    payouts = {}
    for row in c.fetchall():
        payouts.setdefault(row[0], []).append(
            {'payout_type': row[1], 'amount': row[2], 'status': row[3], 'paid_at': row[4]})

    project_stage_info = get_project_stage_info(c, [p[0] for p in projects]) if projects else {}

    c.execute("SELECT COUNT(*) FROM projects WHERE accepted_by=%s AND (completed IS NULL OR completed=FALSE)", (cid,))
    assigned_count = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM projects WHERE accepted_by=%s AND completed=TRUE", (cid,))
    completed_count = c.fetchone()[0]
    c.execute("SELECT COALESCE(SUM(amount),0) FROM contractor_payouts WHERE contractor_id=%s AND status='paid'", (cid,))
    current_earnings = float(c.fetchone()[0])
    performance_rating = 'New' if completed_count == 0 else 'Good Standing'

    c.execute("SELECT message, created_at FROM announcements ORDER BY created_at DESC LIMIT 10")
    announcements = c.fetchall()
    c.execute("SELECT action, created_at FROM contractor_activity WHERE contractor_id=%s ORDER BY created_at DESC LIMIT 6", (cid,))
    recent_activity = c.fetchall()

    site_copy = get_site_copy()
    conn.close()

    return render_template('contractor_dashboard.html',
        contractor=contractor, projects=projects, review_status=review_status, payouts=payouts,
        availability_status=availability_status, last_login=last_login,
        assigned_count=assigned_count, completed_count=completed_count,
        current_earnings=current_earnings, performance_rating=performance_rating,
        announcements=announcements, recent_activity=recent_activity,
        contact_whatsapp=site_copy.get('contact_whatsapp'), project_stage_info=project_stage_info)


@app.route('/contractor-change-password', methods=['POST'])
def contractor_change_password():
    if 'contractor_id' not in session:
        return redirect(url_for('contractor_login'))
    cid = session['contractor_id']
    current_pw = request.form['current_password'].encode()
    new_pw = request.form['new_password']
    confirm_pw = request.form['confirm_password']
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT * FROM contractors WHERE id=%s', (cid,))
    contractor = c.fetchone()
    if not bcrypt.checkpw(current_pw, contractor[2].encode()):
        conn.close(); flash('Current password is incorrect.'); return redirect(url_for('contractor_dashboard'))
    if new_pw != confirm_pw:
        conn.close(); flash('New passwords do not match.'); return redirect(url_for('contractor_dashboard'))
    if len(new_pw) < 6:
        conn.close(); flash('Password must be at least 6 characters.'); return redirect(url_for('contractor_dashboard'))
    hashed = bcrypt.hashpw(new_pw.encode(), bcrypt.gensalt()).decode()
    c.execute('UPDATE contractors SET password=%s WHERE id=%s', (hashed, cid))
    log_contractor_activity(c, cid, 'Password changed')
    conn.commit(); conn.close()
    flash('Password changed successfully.')
    return redirect(url_for('contractor_dashboard'))


@app.route('/accept-project/<int:id>')
def accept_project(id):
    if 'contractor_id' not in session:
        return redirect(url_for('contractor_login'))
    conn = get_db()
    c = conn.cursor()
    c.execute('UPDATE projects SET accepted_by=%s, assigned_contractor_id=%s WHERE id=%s',
              (session['contractor_id'], session['contractor_id'], id))
    c.execute('SELECT contractor_pay FROM projects WHERE id=%s', (id,))
    pay_row = c.fetchone()
    if pay_row and pay_row[0]:
        create_contractor_payouts(c, id, session['contractor_id'], pay_row[0])
    conn.commit()
    conn.close()
    return redirect(url_for('contractor_dashboard'))


@app.route('/mark-complete/<int:id>')
def mark_complete(id):
    if 'contractor_id' not in session:
        return redirect(url_for('contractor_login'))
    conn = get_db()
    c = conn.cursor()
    invoice_ref = 'INV-MRK-' + str(random.randint(100000, 999999))
    c.execute("""UPDATE projects SET completed=TRUE, status='completed', invoice_ref=%s, updated_at=NOW()
                 WHERE id=%s AND accepted_by=%s""",
              (invoice_ref, id, session['contractor_id']))
    conn.commit()
    conn.close()
    return redirect(url_for('contractor_dashboard'))


# ═══════════════════════════════════════════════════════════════════════
# ADDED (consolidated pass) — contractor availability, announcements,
# and the project stage flow (contractor proposes → CEO approves → client sees)
# ═══════════════════════════════════════════════════════════════════════

@app.route('/contractor/update-stage/<int:project_id>', methods=['POST'])
def contractor_update_stage(project_id):
    if 'contractor_id' not in session:
        return redirect(url_for('contractor_login'))
    new_stage = request.form.get('new_stage', '').strip()
    if new_stage not in PROJECT_STAGES:
        flash('Invalid stage.')
        return redirect(url_for('contractor_dashboard'))
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT accepted_by FROM projects WHERE id=%s', (project_id,))
    row = c.fetchone()
    if not row or row[0] != session['contractor_id']:
        conn.close()
        return redirect(url_for('contractor_dashboard'))
    c.execute('''UPDATE projects SET contractor_stage_pending=%s, stage_pending_approval=TRUE
                 WHERE id=%s''', (new_stage, project_id))
    conn.commit()
    conn.close()
    flash('Stage update submitted for CEO approval.')
    return redirect(url_for('contractor_dashboard'))


# ─── CEO PORTAL ─────────────────────────────────────────
@app.route('/mrkceokhan7')
def ceo_portal():
    return render_template('ceo_login.html')


@app.route('/ceo-login', methods=['POST'])
def ceo_login():
    name = request.form['name'].strip()
    pw = request.form['password'].strip()
    sk = request.form['secret_key'].strip()
    sa = request.form['security_answer'].strip()
    ip = request.remote_addr or 'unknown'

    conn = get_db()
    c = conn.cursor()

    c.execute('''SELECT COUNT(*) FROM ceo_login_attempts
                 WHERE ip=%s AND success=FALSE AND attempted_at > NOW() - INTERVAL '15 minutes' ''', (ip,))
    recent_failures = c.fetchone()[0]
    if recent_failures >= 5:
        conn.close()
        return render_template('ceo_login.html', error='Too many failed attempts. Try again in 15 minutes.')

    c.execute('SELECT * FROM ceo WHERE name=%s', (name,))
    ceo = c.fetchone()
    success = bool(ceo and ceo[2] == pw and ceo[3] == sk and ceo[4] == sa)
    c.execute('INSERT INTO ceo_login_attempts (ip, success) VALUES (%s,%s)', (ip, success))
    conn.commit()
    conn.close()

    if success:
        session['ceo'] = True
        return redirect(url_for('ceo_dashboard'))
    return render_template('ceo_login.html', error='Invalid credentials. Access denied.')


@app.route('/ceo-logout')
def ceo_logout():
    session.pop('ceo', None)
    return redirect(url_for('ceo_portal'))


# ═══════════════════════════════════════════════════════════════════════
# ADDED — CEO ACCOUNT: identity, contact info, and separately-verified
# password / secret key / security answer changes. Never assumes the ceo
# row has id=1 — always looks it up, so this can't silently target the
# wrong row if the table's history ever drifted.
# ═══════════════════════════════════════════════════════════════════════

def get_ceo_id(c):
    c.execute("SELECT id FROM ceo ORDER BY id LIMIT 1")
    row = c.fetchone()
    return row[0] if row else None


@app.route('/ceo/account')
@ceo_required
def ceo_account():
    conn, c = get_dict_db()
    c.execute("SELECT * FROM ceo ORDER BY id LIMIT 1")
    ceo = c.fetchone()
    conn.close()
    return render_template('ceo_profile.html', active_page='account', ceo=ceo)


@app.route('/ceo/account/update-contact', methods=['POST'])
@ceo_required
def ceo_update_contact():
    conn = get_db(); c = conn.cursor()
    ceo_id = get_ceo_id(c)
    c.execute('''UPDATE ceo SET email=%s, backup_email=%s, phone=%s, whatsapp=%s WHERE id=%s''',
              (request.form.get('email'), request.form.get('backup_email'),
               request.form.get('phone'), request.form.get('whatsapp'), ceo_id))
    conn.commit(); conn.close()
    flash('Contact info updated.')
    return redirect(url_for('ceo_account'))


@app.route('/ceo/account/update-photo', methods=['POST'])
@ceo_required
def ceo_update_photo():
    photo_file = request.files.get('photo')
    if not photo_file or not photo_file.filename:
        flash('No photo was received — please try selecting the file again.')
        return redirect(url_for('ceo_account'))
    try:
        photo_url = upload_image(photo_file, folder="mrk_agency/ceo")
    except Exception as e:
        flash(f'Photo upload failed: {e}')
        return redirect(url_for('ceo_account'))
    if not photo_url:
        flash('Photo upload failed — no URL returned. Check Cloudinary configuration.')
        return redirect(url_for('ceo_account'))
    conn = get_db(); c = conn.cursor()
    ceo_id = get_ceo_id(c)
    c.execute('UPDATE ceo SET photo=%s WHERE id=%s', (photo_url, ceo_id))
    conn.commit(); conn.close()
    flash('Photo updated.')
    return redirect(url_for('ceo_account'))


@app.route('/ceo/account/change-password', methods=['POST'])
@ceo_required
def ceo_change_password():
    conn = get_db(); c = conn.cursor()
    ceo_id = get_ceo_id(c)
    c.execute('SELECT password FROM ceo WHERE id=%s', (ceo_id,))
    row = c.fetchone()
    if row[0] != request.form.get('current_password', '').strip():
        conn.close(); flash('Current password is incorrect.'); return redirect(url_for('ceo_account'))
    c.execute('UPDATE ceo SET password=%s WHERE id=%s', (request.form.get('new_password', '').strip(), ceo_id))
    conn.commit(); conn.close()
    flash('Password updated.')
    return redirect(url_for('ceo_account'))


@app.route('/ceo/account/change-secret-key', methods=['POST'])
@ceo_required
def ceo_change_secret_key():
    conn = get_db(); c = conn.cursor()
    ceo_id = get_ceo_id(c)
    c.execute('SELECT secret_key FROM ceo WHERE id=%s', (ceo_id,))
    row = c.fetchone()
    if row[0] != request.form.get('current_secret_key', '').strip():
        conn.close(); flash('Current secret key is incorrect.'); return redirect(url_for('ceo_account'))
    c.execute('UPDATE ceo SET secret_key=%s WHERE id=%s', (request.form.get('new_secret_key', '').strip(), ceo_id))
    conn.commit(); conn.close()
    flash('Secret key updated.')
    return redirect(url_for('ceo_account'))


@app.route('/ceo/account/change-security-answer', methods=['POST'])
@ceo_required
def ceo_change_security_answer():
    conn = get_db(); c = conn.cursor()
    ceo_id = get_ceo_id(c)
    c.execute('SELECT security_answer FROM ceo WHERE id=%s', (ceo_id,))
    row = c.fetchone()
    if row[0] != request.form.get('current_security_answer', '').strip():
        conn.close(); flash('Current answer is incorrect.'); return redirect(url_for('ceo_account'))
    c.execute('UPDATE ceo SET security_answer=%s WHERE id=%s', (request.form.get('new_security_answer', '').strip(), ceo_id))
    conn.commit(); conn.close()
    flash('Security answer updated.')
    return redirect(url_for('ceo_account'))


# ─── CEO: DASHBOARD (home page) ──────────────────────────
@app.route('/ceo-dashboard')
@ceo_required
def ceo_dashboard():
    conn = get_db()
    c = conn.cursor()

    c.execute("SELECT COUNT(*) FROM contractors WHERE status='pending'")
    pending_contractors_count = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM contractors WHERE status='approved' AND (suspended IS NULL OR suspended=FALSE)")
    active_contractors_count = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM projects WHERE status='pending'")
    pending_projects_count = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM projects WHERE status='approved'")
    active_projects_count = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM projects WHERE status='completed'")
    completed_count = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM customers WHERE suspended=FALSE OR suspended IS NULL")
    active_customers_count = c.fetchone()[0]

    c.execute("SELECT COALESCE(SUM(amount),0) FROM project_payments WHERE is_paid=TRUE")
    total_revenue = float(c.fetchone()[0])

    time_of_day, brief_summary, focus_today = get_morning_brief()
    business_health = get_business_health()
    pending_approvals = get_pending_approvals(c, limit=5)
    notifications = get_ceo_notifications(c, limit=5)
    recent_activity_rows = get_merged_activity(c, limit=6)
    recent_activity = [{'time': r[1].strftime('%-I:%M %p') if r[1] else '', 'text': r[0]} for r in recent_activity_rows]

    conn.close()
    return render_template('ceo_dashboard.html', active_page='dashboard',
        time_of_day=time_of_day, brief_summary=brief_summary, focus_today=focus_today,
        business_health=business_health, total_revenue=total_revenue, completed_count=completed_count,
        pending_contractors_count=pending_contractors_count, active_contractors_count=active_contractors_count,
        pending_projects_count=pending_projects_count, active_projects_count=active_projects_count,
        active_customers_count=active_customers_count,
        pending_approvals=pending_approvals, notifications=notifications, recent_activity=recent_activity)


# ─── CEO: CONTRACTORS PAGE ─────────────────
