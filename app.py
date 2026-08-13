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
