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
        try: c.execute(f'ALTER TABLE ceo ADD COLUMN IF NOT EXISTS {col} {ddl}')
        except: conn.rollback()    
        c.execute("INSERT INTO ceo (name, password, secret_key, security_answer) VALUES (%s,%s,%s,%s)",
             ('Khizar Khan', 'CEOMRKAgencyKhizarKhan', 'KhizarKhanCEOMRK7', 'Kiran'))
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
# ═══════════════════════════════════════════════════════════════════════

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
# RESERVED — MRK AI (future division). Not implemented yet.
# When the AI product is ready, build it as its own Flask Blueprint
# (e.g. ai_bp = Blueprint('mrk_ai', __name__, url_prefix='/ai'),
# registered with app.register_blueprint(ai_bp)) so it shares this same
# database connection and CEO session without touching any route above
# or below. /ceo/ai-center already exists as the UI placeholder — swap
# its "Coming Soon" cards for real links into the blueprint's routes
# once it exists.
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


# ─── PROJECTS ───────────────────────────────────────────
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


# ─── CEO: CONTRACTORS PAGE ───────────────────────────────
@app.route('/ceo/contractors')
@ceo_required
def ceo_contractors():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM contractors WHERE status='pending'")
    pending_contractors = c.fetchall()
    c.execute("SELECT * FROM contractors WHERE status='approved' AND (suspended IS NULL OR suspended=FALSE)")
    approved_contractors = c.fetchall()
    c.execute("SELECT * FROM contractors WHERE status='rejected' OR suspended=TRUE")
    rejected_contractors = c.fetchall()
    c.execute("SELECT * FROM contractors WHERE status='banned'")
    banned_contractors = c.fetchall()

    c.execute("SELECT id, availability_status FROM contractors")
    contractor_availability = {row[0]: (row[1] or 'Available') for row in c.fetchall()}

    c.execute('''SELECT id, title, package, contractor_pay FROM projects
                 WHERE status='approved' AND accepted_by IS NULL''')
    unassigned_projects = [{'id': r[0], 'title': r[1], 'package': r[2], 'contractor_pay': r[3]} for r in c.fetchall()]

    c.execute("SELECT id, message FROM announcements ORDER BY created_at DESC LIMIT 20")
    announcements = c.fetchall()

    conn.close()
    return render_template('ceo_contractors.html', active_page='contractors',
        pending_contractors=pending_contractors, approved_contractors=approved_contractors,
        rejected_contractors=rejected_contractors, banned_contractors=banned_contractors,
        contractor_availability=contractor_availability, unassigned_projects=unassigned_projects,
        announcements=announcements)


@app.route('/ceo/contractor/<int:id>/set-availability', methods=['POST'])
@ceo_required
def set_contractor_availability(id):
    status = request.form.get('availability_status', 'Available')
    if status not in ('Available', 'Busy', 'Offline'):
        status = 'Available'
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE contractors SET availability_status=%s WHERE id=%s", (status, id))
    conn.commit()
    conn.close()
    flash('Contractor availability updated.')
    return redirect(url_for('ceo_contractors'))


@app.route('/ceo/announcements/add', methods=['POST'])
@ceo_required
def add_announcement():
    message = request.form.get('message', '').strip()
    if message:
        conn = get_db()
        c = conn.cursor()
        c.execute("INSERT INTO announcements (message) VALUES (%s)", (message,))
        conn.commit()
        conn.close()
        flash('Announcement posted.')
    return redirect(url_for('ceo_contractors'))


@app.route('/ceo/announcements/<int:id>/delete', methods=['POST'])
@ceo_required
def delete_announcement(id):
    conn = get_db()
    c = conn.cursor()
    c.execute("DELETE FROM announcements WHERE id=%s", (id,))
    conn.commit()
    conn.close()
    flash('Announcement removed.')
    return redirect(url_for('ceo_contractors'))


# ─── CEO: PROJECTS PAGE ───────────────────────────────────
@app.route('/ceo/projects')
@ceo_required
def ceo_projects():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM projects WHERE status='pending'")
    pending_projects = c.fetchall()
    c.execute("SELECT * FROM projects WHERE status='approved'")
    approved_projects = c.fetchall()
    c.execute("SELECT * FROM projects WHERE status='completed'")
    completed_projects = c.fetchall()
    c.execute("SELECT * FROM projects WHERE status='rejected'")
    rejected_projects = c.fetchall()
    c.execute("SELECT * FROM contractors WHERE status='approved' AND (suspended IS NULL OR suspended=FALSE)")
    approved_contractors = c.fetchall()

    c.execute('''SELECT project_id, phase_number, phase_label, amount, is_paid
                 FROM project_payments ORDER BY project_id, phase_number''')
    payment_phases = {}
    for row in c.fetchall():
        payment_phases.setdefault(row[0], []).append(
            {'phase_number': row[1], 'phase_label': row[2], 'amount': row[3], 'is_paid': row[4]})

    c.execute('''SELECT project_id, phase_number, phase_label, contractor_proof,
                        contractor_submitted_at, client_approved
                 FROM project_payments WHERE contractor_proof IS NOT NULL
                 ORDER BY project_id, phase_number''')
    milestone_submissions = {}
    for row in c.fetchall():
        milestone_submissions.setdefault(row[0], []).append(
            {'phase_number': row[1], 'phase_label': row[2], 'proof': row[3],
             'submitted_at': row[4], 'client_approved': row[5]})

    c.execute('''SELECT project_id, id, payout_type, amount, status, paid_at
                 FROM contractor_payouts ORDER BY project_id, created_at''')
    contractor_payouts = {}
    for row in c.fetchall():
        contractor_payouts.setdefault(row[0], []).append(
            {'id': row[1], 'payout_type': row[2], 'amount': row[3], 'status': row[4], 'paid_at': row[5]})

    all_project_ids = [p[0] for p in (pending_projects + approved_projects + completed_projects + rejected_projects)]
    project_stage_info = get_project_stage_info(c, all_project_ids) if all_project_ids else {}

    conn.close()
    return render_template('ceo_projects.html', active_page='projects',
        pending_projects=pending_projects, approved_projects=approved_projects,
        completed_projects=completed_projects, rejected_projects=rejected_projects,
        approved_contractors=approved_contractors, payment_phases=payment_phases,
        milestone_submissions=milestone_submissions, contractor_payouts=contractor_payouts,
        project_stage_info=project_stage_info)


@app.route('/ceo/project/<int:id>/assign-contractor', methods=['POST'])
@ceo_required
def assign_contractor(id):
    contractor_id = request.form.get('contractor_id')
    if not contractor_id:
        flash('Please select a contractor.')
        return redirect(request.referrer or url_for('ceo_projects'))
    conn = get_db()
    c = conn.cursor()
    c.execute('UPDATE projects SET assigned_contractor_id=%s, accepted_by=%s, updated_at=NOW() WHERE id=%s',
              (contractor_id, contractor_id, id))
    c.execute('SELECT contractor_pay FROM projects WHERE id=%s', (id,))
    pay_row = c.fetchone()
    if pay_row and pay_row[0]:
        create_contractor_payouts(c, id, contractor_id, pay_row[0])
    conn.commit()
    conn.close()
    flash('Contractor assigned.')
    return redirect(request.referrer or url_for('ceo_projects'))


@app.route('/ceo/project/<int:id>/approve-stage', methods=['POST'])
@ceo_required
def approve_stage(id):
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT contractor_stage_pending FROM projects WHERE id=%s', (id,))
    row = c.fetchone()
    if row and row[0]:
        c.execute('''UPDATE projects SET client_visible_stage=%s, stage_pending_approval=FALSE,
                     contractor_stage_pending=NULL, updated_at=NOW() WHERE id=%s''', (row[0], id))
        c.execute('SELECT customer_id FROM projects WHERE id=%s', (id,))
        cust_row = c.fetchone()
        if cust_row:
            log_client_activity(c, cust_row[0], f'Project stage updated: {row[0]}')
        conn.commit()
        flash(f'Stage approved — now visible to the client as "{row[0]}".')
    conn.close()
    return redirect(request.referrer or url_for('ceo_projects'))


@app.route('/ceo/project/<int:id>/reject-stage', methods=['POST'])
@ceo_required
def reject_stage(id):
    conn = get_db()
    c = conn.cursor()
    c.execute('UPDATE projects SET stage_pending_approval=FALSE, contractor_stage_pending=NULL WHERE id=%s', (id,))
    conn.commit()
    conn.close()
    flash('Stage update rejected.')
    return redirect(request.referrer or url_for('ceo_projects'))


# ─── CEO: CLIENTS PAGE ───────────────────────────────────
@app.route('/ceo/clients')
@ceo_required
def ceo_clients():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM customers WHERE suspended=FALSE OR suspended IS NULL")
    customers = c.fetchall()
    c.execute("SELECT * FROM customers WHERE suspended=TRUE")
    suspended_customers = c.fetchall()

    c.execute("SELECT customer_id, COUNT(*) FROM projects GROUP BY customer_id")
    project_counts = {row[0]: row[1] for row in c.fetchall()}

    client_totals_paid = {}
    client_totals_due = {}
    client_projects = {}
    for cu in (customers + suspended_customers):
        c.execute('''SELECT p.id, p.title, p.status, COALESCE(SUM(pp.amount) FILTER (WHERE pp.is_paid), 0),
                            COALESCE(SUM(pp.amount) FILTER (WHERE NOT pp.is_paid), 0)
                     FROM projects p LEFT JOIN project_payments pp ON pp.project_id = p.id
                     WHERE p.customer_id=%s GROUP BY p.id, p.title, p.status''', (cu[0],))
        rows = c.fetchall()
        client_totals_paid[cu[0]] = sum(float(r[3]) for r in rows)
        client_totals_due[cu[0]] = sum(float(r[4]) for r in rows)
        client_projects[cu[0]] = [{'title': r[1], 'status': r[2]} for r in rows]

    conn.close()
    return render_template('ceo_clients.html', active_page='clients',
        customers=customers, suspended_customers=suspended_customers, project_counts=project_counts,
        client_totals_paid=client_totals_paid, client_totals_due=client_totals_due, client_projects=client_projects)


# ─── CEO: FINANCE PAGE ───────────────────────────────────
@app.route('/ceo/finance')
@ceo_required
def ceo_finance():
    conn = get_db()
    c = conn.cursor()

    c.execute("SELECT COALESCE(SUM(amount),0) FROM project_payments WHERE is_paid=TRUE")
    total_revenue = float(c.fetchone()[0])
    c.execute("SELECT COALESCE(SUM(amount),0) FROM project_payments WHERE is_paid=FALSE")
    pending_payments_total = float(c.fetchone()[0])
    c.execute("SELECT COALESCE(SUM(amount),0) FROM contractor_payouts WHERE status='paid'")
    payouts_paid_total = float(c.fetchone()[0])
    c.execute("SELECT COALESCE(SUM(amount),0) FROM contractor_payouts WHERE status='pending'")
    payouts_pending_total = float(c.fetchone()[0])
    net_profit = total_revenue - payouts_paid_total

    c.execute('''SELECT pp.project_id, p.title, p.customer_id, pp.phase_number, pp.phase_label, pp.amount, pp.is_paid
                 FROM project_payments pp JOIN projects p ON p.id = pp.project_id
                 ORDER BY pp.is_paid ASC, p.id DESC''')
    payment_phases_list = [{'project_id': r[0], 'project_title': r[1], 'customer_id': r[2],
                             'phase_number': r[3], 'phase_label': r[4], 'amount': float(r[5]), 'is_paid': r[6]}
                            for r in c.fetchall()]

    c.execute('''SELECT co.id, con.name, p.title, co.payout_type, co.amount, co.status
                 FROM contractor_payouts co
                 JOIN contractors con ON con.id = co.contractor_id
                 JOIN projects p ON p.id = co.project_id
                 ORDER BY co.status ASC, co.id DESC''')
    contractor_payouts_list = [{'id': r[0], 'contractor_name': r[1], 'project_title': r[2],
                                 'payout_type': r[3], 'amount': float(r[4]), 'status': r[5]}
                                for r in c.fetchall()]

    conn.close()
    monthly_revenue = get_monthly_revenue()

    return render_template('ceo_finance.html', active_page='finance',
        total_revenue=total_revenue, pending_payments_total=pending_payments_total,
        payouts_paid_total=payouts_paid_total, payouts_pending_total=payouts_pending_total,
        net_profit=net_profit, payment_phases_list=payment_phases_list,
        contractor_payouts_list=contractor_payouts_list, monthly_revenue=monthly_revenue)


# ─── CEO: WEBSITE SETTINGS PAGE ──────────────────────────
@app.route('/ceo/website-settings')
@ceo_required
def ceo_website_settings():
    settings = get_site_copy()
    return render_template('ceo_website_settings.html', active_page='website', settings=settings)


@app.route('/ceo/site-settings', methods=['POST'])
@ceo_required
def ceo_site_settings():
    conn = get_db()
    c = conn.cursor()
    c.execute('''UPDATE site_settings SET
        hero_tagline=%s, hero_subtext=%s, agency_bio=%s,
        contact_email=%s, contact_phone=%s, contact_whatsapp=%s,
        payoneer_email=%s, payoneer_account_name=%s, payment_instructions=%s,
        linkedin_url=%s, facebook_url=%s, instagram_url=%s, twitter_url=%s
        WHERE id=1''',
        (request.form.get('hero_tagline'), request.form.get('hero_subtext'), request.form.get('agency_bio'),
         request.form.get('contact_email'), request.form.get('contact_phone'), request.form.get('contact_whatsapp'),
         request.form.get('payoneer_email'), request.form.get('payoneer_account_name'),
         request.form.get('payment_instructions'),
         request.form.get('linkedin_url'), request.form.get('facebook_url'),
         request.form.get('instagram_url'), request.form.get('twitter_url')))
    conn.commit()
    conn.close()
    flash('Settings updated.')
    return redirect(url_for('ceo_website_settings'))


@app.route('/ceo/project/<int:project_id>/mark-phase-paid/<int:phase_number>', methods=['POST'])
@ceo_required
def mark_phase_paid(project_id, phase_number):
    conn = get_db()
    c = conn.cursor()
    c.execute('''UPDATE project_payments SET is_paid=TRUE, paid_at=NOW()
                 WHERE project_id=%s AND phase_number=%s''', (project_id, phase_number))
    c.execute('SELECT customer_id FROM projects WHERE id=%s', (project_id,))
    row = c.fetchone()
    if row:
        log_client_activity(c, row[0], 'Invoice paid')
    touch_project(c, project_id)
    conn.commit()
    conn.close()
    flash('Payment marked as received.')
    return redirect(request.referrer or url_for('ceo_finance'))


@app.route('/ceo/project/<int:project_id>/unmark-phase-paid/<int:phase_number>', methods=['POST'])
@ceo_required
def unmark_phase_paid(project_id, phase_number):
    conn = get_db()
    c = conn.cursor()
    c.execute('''UPDATE project_payments SET is_paid=FALSE, paid_at=NULL
                 WHERE project_id=%s AND phase_number=%s''', (project_id, phase_number))
    conn.commit()
    conn.close()
    flash('Payment marking undone.')
    return redirect(request.referrer or url_for('ceo_finance'))


# ─── CEO: ANALYTICS PAGE ─────────────────────────────────
@app.route('/ceo/analytics')
@ceo_required
def ceo_analytics():
    conn = get_db()
    c = conn.cursor()

    c.execute('''SELECT status, COUNT(*) FROM projects GROUP BY status''')
    status_rows = c.fetchall()
    status_labels = {'pending': 'Pending', 'approved': 'Active', 'completed': 'Completed', 'rejected': 'Rejected'}
    project_status_breakdown = [{'label': status_labels.get(r[0], r[0]), 'count': r[1]} for r in status_rows]

    c.execute("SELECT COUNT(*) FROM customers")
    total_clients = c.fetchone()[0]
    new_clients_this_month = None

    c.execute("SELECT COUNT(*) FROM projects")
    total_submitted = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM projects WHERE status IN ('approved','completed')")
    total_approved = c.fetchone()[0]
    conversion_rate = f"{round(total_approved/total_submitted*100)}%" if total_submitted else "No Data Yet"

    c.execute('''SELECT TO_CHAR(created_at, 'Mon YYYY') AS month, COUNT(*)
                 FROM projects WHERE status IN ('approved','completed') AND created_at IS NOT NULL
                 GROUP BY TO_CHAR(created_at, 'Mon YYYY'), DATE_TRUNC('month', created_at)
                 ORDER BY DATE_TRUNC('month', created_at) DESC LIMIT 6''')
    monthly_sales = [{'month': r[0], 'count': r[1]} for r in reversed(c.fetchall())]

    conn.close()
    monthly_revenue = get_monthly_revenue()

    return render_template('ceo_analytics.html', active_page='analytics',
        monthly_revenue=monthly_revenue, project_status_breakdown=project_status_breakdown,
        total_clients=total_clients, new_clients_this_month=new_clients_this_month,
        conversion_rate=conversion_rate, monthly_sales=monthly_sales)


# ─── CEO: NOTIFICATIONS CENTER ───────────────────────────
@app.route('/ceo/notifications')
@ceo_required
def ceo_notifications():
    conn = get_db()
    c = conn.cursor()
    notifications = get_ceo_notifications(c)
    conn.close()
    return render_template('ceo_notifications.html', active_page='notifications', notifications=notifications)


# ─── CEO: ACTIVITY CENTER ────────────────────────────────
@app.route('/ceo/activity')
@ceo_required
def ceo_activity():
    conn = get_db()
    c = conn.cursor()
    rows = get_merged_activity(c, limit=200)
    conn.close()
    activity_feed = [{'day': r[1].strftime('%B %d, %Y') if r[1] else '', 'time': r[1].strftime('%-I:%M %p') if r[1] else '', 'text': r[0]} for r in rows]
    return render_template('ceo_activity.html', active_page='activity', activity_feed=activity_feed)


# ─── CEO: AI CENTER (placeholder) ────────────────────────
@app.route('/ceo/ai-center')
@ceo_required
def ceo_ai_center():
    return render_template('ceo_ai_center.html', active_page='ai')


# ─── CEO: CONTRACTOR ACTIONS ────────────────────────────
@app.route('/approve-contractor/<int:id>')
@ceo_required
def approve_contractor(id):
    cin = 'MRK' + str(random.randint(10000, 99999))
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE contractors SET status='approved', cin=%s, suspended=FALSE WHERE id=%s", (cin, id))
    conn.commit()
    conn.close()
    return redirect(url_for('ceo_contractors'))


@app.route('/reject-contractor/<int:id>')
@ceo_required
def reject_contractor(id):
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE contractors SET status='rejected' WHERE id=%s", (id,))
    conn.commit()
    conn.close()
    return redirect(url_for('ceo_contractors'))


@app.route('/suspend-contractor/<int:id>')
@ceo_required
def suspend_contractor(id):
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE contractors SET suspended=TRUE, cin=NULL WHERE id=%s", (id,))
    conn.commit()
    conn.close()
    return redirect(url_for('ceo_contractors'))


@app.route('/reinstate-contractor/<int:id>')
@ceo_required
def reinstate_contractor(id):
    cin = 'MRK' + str(random.randint(10000, 99999))
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE contractors SET suspended=FALSE, status='approved', cin=%s WHERE id=%s", (cin, id))
    conn.commit()
    conn.close()
    return redirect(url_for('ceo_contractors'))


@app.route('/delete-contractor/<int:id>')
@ceo_required
def delete_contractor(id):
    conn = get_db()
    c = conn.cursor()
    c.execute("DELETE FROM contractors WHERE id=%s", (id,))
    conn.commit()
    conn.close()
    return redirect(url_for('ceo_contractors'))


@app.route('/ban-cin/<int:id>')
@ceo_required
def ban_cin(id):
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE contractors SET cin=NULL, status='banned', suspended=TRUE WHERE id=%s", (id,))
    conn.commit()
    conn.close()
    return redirect(url_for('ceo_contractors'))


@app.route('/award-badge/<int:id>', methods=['POST'])
@ceo_required
def award_badge(id):
    badge = request.form.get('badge', '').strip()
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE contractors SET badge=%s WHERE id=%s", (badge, id))
    conn.commit()
    conn.close()
    return redirect(url_for('ceo_contractors'))


# ─── CEO: PROJECT ACTIONS ─────────────────────────
@app.route('/approve-project/<int:id>', methods=['GET', 'POST'])
@ceo_required
def approve_project(id):
    conn = get_db()
    c = conn.cursor()
    c.execute('''SELECT is_paid FROM project_payments
                 WHERE project_id=%s AND phase_number=1''', (id,))
    row = c.fetchone()
    if row and not row[0]:
        conn.close()
        flash('Cannot approve — the upfront payment for this project has not been marked as paid yet.')
        return redirect(url_for('ceo_projects'))

    contractor_pay = request.form.get('contractor_pay', '0').strip()
    if not contractor_pay:
        contractor_pay = '0'
    try:
        c.execute("UPDATE projects SET status='approved', contractor_pay=%s, updated_at=NOW() WHERE id=%s", (contractor_pay, id))
        c.execute('SELECT customer_id, title FROM projects WHERE id=%s', (id,))
        row2 = c.fetchone()
        if row2:
            log_client_activity(c, row2[0], f'Proposal approved: {row2[1]}')
        conn.commit()
    except Exception:
        conn.rollback()
    conn.close()
    return redirect(url_for('ceo_projects'))


@app.route('/reject-project/<int:id>', methods=['GET', 'POST'])
@ceo_required
def reject_project(id):
    reason = request.form.get('rejection_reason', 'No reason provided.').strip()
    if not reason:
        reason = 'No reason provided.'
    conn = get_db()
    c = conn.cursor()
    try:
        c.execute("UPDATE projects SET status='rejected', rejection_reason=%s, updated_at=NOW() WHERE id=%s", (reason, id))
        conn.commit()
    except Exception:
        conn.rollback()
    conn.close()
    return redirect(url_for('ceo_projects'))


# ─── CEO: CUSTOMER ACTIONS ──────────────────────────────
@app.route('/suspend-customer/<int:id>')
@ceo_required
def suspend_customer(id):
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE customers SET suspended=TRUE WHERE id=%s", (id,))
    conn.commit()
    conn.close()
    return redirect(url_for('ceo_clients'))


@app.route('/reinstate-customer/<int:id>')
@ceo_required
def reinstate_customer(id):
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE customers SET suspended=FALSE WHERE id=%s", (id,))
    conn.commit()
    conn.close()
    return redirect(url_for('ceo_clients'))


@app.route('/delete-customer/<int:id>')
@ceo_required
def delete_customer(id):
    conn = get_db()
    c = conn.cursor()
    c.execute("DELETE FROM customers WHERE id=%s", (id,))
    conn.commit()
    conn.close()
    return redirect(url_for('ceo_clients'))


@app.route('/ceo/team/add', methods=['POST'])
@ceo_required
def team_add():
    name = request.form['name'].strip()
    role = request.form.get('role','').strip()
    specialties = request.form.get('specialties','').strip()
    bio = request.form.get('bio','').strip()
    projects_count = request.form.get('projects_count', 0)
    photo_name = None
    photo = request.files.get('photo')
    if photo and allowed_file(photo.filename):
        photo_name = secure_filename(f'team_{name}_{photo.filename}')
        photo.save(os.path.join(app.config['UPLOAD_FOLDER'], photo_name))
    conn = get_db()
    c = conn.cursor()
    c.execute("INSERT INTO team_members (name,role,specialties,bio,projects_count,photo) VALUES (%s,%s,%s,%s,%s,%s)",
              (name,role,specialties,bio,projects_count,photo_name))
    conn.commit(); conn.close()
    flash(f'{name} added to team.','success')
    return redirect(url_for('ceo_portfolio_list'))


@app.route('/ceo/team/delete/<int:tid>')
@ceo_required
def team_delete(tid):
    conn = get_db()
    c = conn.cursor()
    c.execute("DELETE FROM team_members WHERE id=%s",(tid,))
    conn.commit(); conn.close()
    flash('Team member removed.','success')
    return redirect(url_for('ceo_portfolio_list'))


@app.route('/api/team')
def api_team():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT id,name,role,specialties,bio,projects_count,photo FROM team_members ORDER BY created_at")
    rows = c.fetchall()
    conn.close()
    return jsonify([{'id':r[0],'name':r[1],'role':r[2],'specialties':r[3],'bio':r[4],'projects':r[5],'photo':r[6]} for r in rows])


# ═══════════════════════════════════════════════════════════════════════
# PORTFOLIO & TEAM — CEO management + public pages
# ═══════════════════════════════════════════════════════════════════════

@app.route('/ceo/portfolio')
@ceo_required
def ceo_portfolio_list():
    conn, c = get_dict_db()
    c.execute("SELECT * FROM portfolio_projects ORDER BY display_order")
    portfolio_projects = c.fetchall()
    c.execute("SELECT * FROM team_members ORDER BY created_at")
    team_members_dict = c.fetchall()
    conn.close()

    conn2 = get_db(); c2 = conn2.cursor()
    c2.execute("SELECT * FROM team_members ORDER BY created_at")
    team_members = c2.fetchall()
    c2.execute('''SELECT t.id, t.rating, t.review_text, t.is_published, t.created_at,
                         cu.first_name, cu.last_name
                  FROM testimonials t JOIN customers cu ON cu.id = t.customer_id
                  ORDER BY t.created_at DESC''')
    all_testimonials = c2.fetchall()
    conn2.close()

    media_images = []
    for pr in portfolio_projects:
        if pr.get('cover_image'):
            media_images.append(pr['cover_image'])
        if pr.get('gallery_images'):
            media_images.extend([u for u in pr['gallery_images'].split(',') if u])
    for tm in team_members_dict:
        if tm.get('photo') and tm['photo'].startswith('http'):
            media_images.append(tm['photo'])

    site_settings = get_site_settings()

    return render_template('ceo_portfolio.html', active_page='portfolio',
        portfolio_projects=portfolio_projects, team_members=team_members,
        all_testimonials=all_testimonials, media_images=media_images, site_settings=site_settings)


@app.route('/ceo/portfolio/new', methods=['GET', 'POST'])
@ceo_required
def ceo_portfolio_new():
    if request.method == 'POST':
        cover_url = upload_image(request.files.get('cover_image'), folder="mrk_agency/portfolio")
        gallery_urls = upload_multiple_images(request.files.getlist('gallery_images'), folder="mrk_agency/portfolio")
        gallery_str = ','.join(gallery_urls) if gallery_urls else None

        conn = get_db()
        c = conn.cursor()
        c.execute('''INSERT INTO portfolio_projects
            (title, category, package_tier, short_summary, full_description, tech_stack,
             client_name, is_confidential, live_url, cover_image, gallery_images, display_order)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)''',
            (request.form['title'], request.form['category'], request.form.get('package_tier') or None,
             request.form['short_summary'], request.form['full_description'], request.form.get('tech_stack'),
             request.form.get('client_name'), bool(request.form.get('is_confidential')),
             request.form.get('live_url'), cover_url, gallery_str,
             int(request.form.get('display_order') or 0)))
        conn.commit()
        conn.close()
        flash('Project saved as draft. Publish it from the portfolio list when ready.')
        return redirect(url_for('ceo_portfolio_list'))

    return render_template('ceo_portfolio_form.html', project=None)


@app.route('/ceo/portfolio/<int:project_id>/edit', methods=['GET', 'POST'])
@ceo_required
def ceo_portfolio_edit(project_id):
    conn, c = get_dict_db()
    c.execute("SELECT * FROM portfolio_projects WHERE id=%s", (project_id,))
    project = c.fetchone()
    conn.close()
    if not project:
        return redirect(url_for('ceo_portfolio_list'))

    if request.method == 'POST':
        cover_url = project['cover_image']
        new_cover = request.files.get('cover_image')
        if new_cover and new_cover.filename:
            cover_url = upload_image(new_cover, folder="mrk_agency/portfolio")

        gallery_str = project['gallery_images']
        new_gallery = request.files.getlist('gallery_images')
        if new_gallery and any(f.filename for f in new_gallery):
            gallery_urls = upload_multiple_images(new_gallery, folder="mrk_agency/portfolio")
            gallery_str = ','.join(gallery_urls) if gallery_urls else None

        conn = get_db()
        c = conn.cursor()
        c.execute('''UPDATE portfolio_projects SET
            title=%s, category=%s, package_tier=%s, short_summary=%s, full_description=%s,
            tech_stack=%s, client_name=%s, is_confidential=%s, live_url=%s,
            cover_image=%s, gallery_images=%s, display_order=%s
            WHERE id=%s''',
            (request.form['title'], request.form['category'], request.form.get('package_tier') or None,
             request.form['short_summary'], request.form['full_description'], request.form.get('tech_stack'),
             request.form.get('client_name'), bool(request.form.get('is_confidential')),
             request.form.get('live_url'), cover_url, gallery_str,
             int(request.form.get('display_order') or 0), project_id))
        conn.commit()
        conn.close()
        flash('Project updated.')
        return redirect(url_for('ceo_portfolio_list'))

    return render_template('ceo_portfolio_form.html', project=project)


@app.route('/ceo/portfolio/<int:project_id>/publish', methods=['POST'])
@ceo_required
def ceo_portfolio_publish(project_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE portfolio_projects SET is_published = NOT is_published WHERE id=%s", (project_id,))
    conn.commit()
    conn.close()
    return redirect(url_for('ceo_portfolio_list'))


@app.route('/ceo/portfolio/<int:project_id>/feature', methods=['POST'])
@ceo_required
def ceo_portfolio_feature(project_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE portfolio_projects SET is_featured = NOT is_featured WHERE id=%s", (project_id,))
    conn.commit()
    conn.close()
    return redirect(url_for('ceo_portfolio_list'))


@app.route('/ceo/portfolio/<int:project_id>/delete', methods=['POST'])
@ceo_required
def ceo_portfolio_delete(project_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("DELETE FROM portfolio_projects WHERE id=%s", (project_id,))
    conn.commit()
    conn.close()
    flash('Project deleted.')
    return redirect(url_for('ceo_portfolio_list'))


@app.route('/ceo/team')
@ceo_required
def ceo_team_list():
    conn, c = get_dict_db()
    c.execute("SELECT * FROM team_members ORDER BY created_at")
    members = c.fetchall()
    conn.close()
    return render_template('ceo_portfolio.html', active_page='portfolio',
        portfolio_projects=[], team_members=members, all_testimonials=[], media_images=[],
        site_settings=get_site_settings())


@app.route('/ceo/team/new', methods=['GET', 'POST'])
@ceo_required
def ceo_team_new():
    if request.method == 'POST':
        photo_url = upload_image(request.files.get('photo'), folder="mrk_agency/team")

        conn = get_db()
        c = conn.cursor()
        c.execute('''INSERT INTO team_members (name, role, specialties, bio, photo, display_order)
                     VALUES (%s,%s,%s,%s,%s,%s) RETURNING id''',
                  (request.form['name'], request.form['role'], request.form.get('skills', ''),
                   request.form.get('bio'), photo_url, int(request.form.get('display_order') or 0)))
        new_id = c.fetchone()[0]

        for pid in request.form.getlist('project_ids'):
            c.execute("INSERT INTO team_project_links (team_member_id, portfolio_project_id) VALUES (%s,%s)",
                      (new_id, pid))
        conn.commit()
        conn.close()
        flash('Team member added (unpublished). Publish from the portfolio page when ready.')
        return redirect(url_for('ceo_portfolio_list'))

    conn, c = get_dict_db()
    c.execute("SELECT * FROM portfolio_projects ORDER BY title")
    all_projects = c.fetchall()
    conn.close()
    return render_template('ceo_team_form.html', member=None, all_projects=all_projects)


@app.route('/ceo/team/<int:member_id>/edit', methods=['GET', 'POST'])
@ceo_required
def ceo_team_edit(member_id):
    conn, c = get_dict_db()
    c.execute("SELECT * FROM team_members WHERE id=%s", (member_id,))
    member = c.fetchone()
    conn.close()
    if not member:
        return redirect(url_for('ceo_portfolio_list'))

    conn, c = get_dict_db()
    c.execute("SELECT portfolio_project_id FROM team_project_links WHERE team_member_id=%s", (member_id,))
    linked = c.fetchall()
    conn.close()
    member['project_ids'] = [str(row['portfolio_project_id']) for row in linked]

    if request.method == 'POST':
        photo_url = member['photo']
        new_photo = request.files.get('photo')
        if new_photo and new_photo.filename:
            photo_url = upload_image(new_photo, folder="mrk_agency/team")

        conn = get_db()
        c = conn.cursor()
        c.execute('''UPDATE team_members SET name=%s, role=%s, specialties=%s, bio=%s, photo=%s, display_order=%s
                     WHERE id=%s''',
                  (request.form['name'], request.form['role'], request.form.get('skills', ''),
                   request.form.get('bio'), photo_url, int(request.form.get('display_order') or 0), member_id))

        c.execute("DELETE FROM team_project_links WHERE team_member_id=%s", (member_id,))
        for pid in request.form.getlist('project_ids'):
            c.execute("INSERT INTO team_project_links (team_member_id, portfolio_project_id) VALUES (%s,%s)",
                      (member_id, pid))
        conn.commit()
        conn.close()
        flash('Team member updated.')
        return redirect(url_for('ceo_portfolio_list'))

    conn, c = get_dict_db()
    c.execute("SELECT * FROM portfolio_projects ORDER BY title")
    all_projects = c.fetchall()
    conn.close()
    return render_template('ceo_team_form.html', member=member, all_projects=all_projects)


@app.route('/ceo/team/<int:member_id>/publish', methods=['POST'])
@ceo_required
def ceo_team_publish(member_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE team_members SET is_published = NOT is_published WHERE id=%s", (member_id,))
    conn.commit()
    conn.close()
    return redirect(url_for('ceo_portfolio_list'))


@app.route('/ceo/team/<int:member_id>/delete', methods=['POST'])
@ceo_required
def ceo_team_remove(member_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("DELETE FROM team_members WHERE id=%s", (member_id,))
    conn.commit()
    conn.close()
    flash('Team member removed.')
    return redirect(url_for('ceo_portfolio_list'))


@app.route('/ceo/settings/toggle-portfolio-visibility', methods=['POST'])
@ceo_required
def toggle_portfolio_visibility():
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE site_settings SET portfolio_visible = NOT portfolio_visible WHERE id=1")
    conn.commit()
    conn.close()
    flash('Portfolio visibility updated.')
    return redirect(request.referrer or url_for('ceo_portfolio_list'))


@app.route('/ceo/settings/toggle-team-visibility', methods=['POST'])
@ceo_required
def toggle_team_visibility():
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE site_settings SET team_visible = NOT team_visible WHERE id=1")
    conn.commit()
    conn.close()
    flash('Team visibility updated.')
    return redirect(request.referrer or url_for('ceo_portfolio_list'))


# ─── PUBLIC: PORTFOLIO & TEAM ────────────────────────────
@app.route('/portfolio')
def public_portfolio():
    settings = get_site_settings()
    if not settings['portfolio_section_visible']:
        abort(404)
    conn, c = get_dict_db()
    c.execute("SELECT * FROM portfolio_projects WHERE is_published=TRUE ORDER BY is_featured DESC, display_order")
    projects = c.fetchall()
    conn.close()
    return render_template('portfolio.html', projects=projects)


@app.route('/portfolio/<int:project_id>')
def public_portfolio_detail(project_id):
    settings = get_site_settings()
    if not settings['portfolio_section_visible']:
        abort(404)
    conn, c = get_dict_db()
    c.execute("SELECT * FROM portfolio_projects WHERE id=%s AND is_published=TRUE", (project_id,))
    project = c.fetchone()
    conn.close()
    if not project:
        abort(404)
    project['gallery_images'] = project['gallery_images'].split(',') if project['gallery_images'] else []
    project['display_client_name'] = 'Confidential Client' if project['is_confidential'] else (project['client_name'] or '—')
    return render_template('portfolio_detail.html', project=project)


@app.route('/team')
def public_team():
    settings = get_site_settings()
    if not settings['team_section_visible']:
        abort(404)
    conn, c = get_dict_db()
    c.execute("SELECT * FROM team_members WHERE is_published=TRUE ORDER BY display_order")
    members = c.fetchall()
    for m in members:
        m['skills'] = [s.strip() for s in m['specialties'].split(',')] if m['specialties'] else []
        c.execute('''SELECT p.id, p.title FROM portfolio_projects p
                     JOIN team_project_links l ON p.id = l.portfolio_project_id
                     WHERE l.team_member_id=%s''', (m['id'],))
        m['projects'] = c.fetchall()
    conn.close()
    return render_template('team.html', members=members)


# ═══════════════════════════════════════════════════════════════════════
# CONTRACTOR BANK DETAILS + PROFILE PHOTO
# ═════════════════════════════════════════════════════════════════

@app.route('/contractor/update-bank', methods=['POST'])
def contractor_update_bank():
    if 'contractor_id' not in session:
        return redirect(url_for('contractor_login'))
    cid = session['contractor_id']
    title = request.form.get('bank_account_title', '').strip()
    number = request.form.get('bank_account_number', '').strip()
    bank = request.form.get('bank_name', '').strip()
    swift = request.form.get('bank_swift_iban', '').strip()

    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT bank_account_number FROM contractors WHERE id=%s', (cid,))
    row = c.fetchone()
    is_first_time = not row[0]

    if is_first_time:
        c.execute('''UPDATE contractors SET bank_account_title=%s, bank_account_number=%s,
                     bank_name=%s, bank_swift_iban=%s WHERE id=%s''',
                  (title, number, bank, swift, cid))
        log_contractor_activity(c, cid, 'Bank details added')
        conn.commit()
        conn.close()
        flash('Bank details saved.')
    else:
        c.execute('''INSERT INTO bank_edit_requests
            (contractor_id, new_bank_account_title, new_bank_account_number, new_bank_name, new_bank_swift_iban)
            VALUES (%s,%s,%s,%s,%s)''', (cid, title, number, bank, swift))
        log_contractor_activity(c, cid, 'Requested bank detail change')
        conn.commit()
        conn.close()
        flash('Bank detail change submitted — pending CEO approval before it takes effect.')

    return redirect(url_for('contractor_dashboard'))


@app.route('/contractor/update-photo', methods=['POST'])
def contractor_update_photo():
    if 'contractor_id' not in session:
        return redirect(url_for('contractor_login'))
    photo_url = upload_image(request.files.get('photo'), folder="mrk_agency/contractors")
    if photo_url:
        conn = get_db()
        c = conn.cursor()
        c.execute('UPDATE contractors SET photo=%s WHERE id=%s', (photo_url, session['contractor_id']))
        log_contractor_activity(c, session['contractor_id'], 'Profile photo updated')
        conn.commit()
        conn.close()
        flash('Profile photo updated.')
    return redirect(url_for('contractor_dashboard'))


@app.route('/ceo/bank-request/<int:req_id>/approve', methods=['POST'])
@ceo_required
def approve_bank_request(req_id):
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT * FROM bank_edit_requests WHERE id=%s', (req_id,))
    r = c.fetchone()
    if r:
        c.execute('''UPDATE contractors SET bank_account_title=%s, bank_account_number=%s,
                     bank_name=%s, bank_swift_iban=%s WHERE id=%s''',
                  (r[2], r[3], r[4], r[5], r[1]))
        c.execute("UPDATE bank_edit_requests SET status='approved', decided_at=NOW() WHERE id=%s", (req_id,))
        conn.commit()
        flash('Bank detail change approved and applied.')
    conn.close()
    return redirect(url_for('ceo_contractors'))


@app.route('/ceo/bank-request/<int:req_id>/reject', methods=['POST'])
@ceo_required
def reject_bank_request(req_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE bank_edit_requests SET status='rejected', decided_at=NOW() WHERE id=%s", (req_id,))
    conn.commit()
    conn.close()
    flash('Bank detail change rejected.')
    return redirect(url_for('ceo_contractors'))


# ═══════════════════════════════════════════════════════════════════════
# MILESTONE REVIEW: contractor submits proof, client approves
# ═══════════════════════════════════════════════════════════════════════

@app.route('/contractor/submit-milestone/<int:project_id>', methods=['POST'])
def contractor_submit_milestone(project_id):
    if 'contractor_id' not in session:
        return redirect(url_for('contractor_login'))
    proof = request.form.get('proof', '').strip()
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT accepted_by FROM projects WHERE id=%s', (project_id,))
    row = c.fetchone()
    if not row or row[0] != session['contractor_id']:
        conn.close()
        return redirect(url_for('contractor_dashboard'))

    phase = get_next_review_phase(c, project_id)
    if phase:
        c.execute('''UPDATE project_payments SET contractor_proof=%s, contractor_submitted_at=NOW(),
                     client_notes=NULL WHERE project_id=%s AND phase_number=%s''',
                  (proof, project_id, phase[0]))
        conn.commit()
    conn.close()
    return redirect(url_for('contractor_dashboard'))


@app.route('/client/approve-milestone/<int:project_id>/<int:phase_number>', methods=['POST'])
def client_approve_milestone(project_id, phase_number):
    if 'customer_id' not in session:
        return redirect(url_for('login'))
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT customer_id FROM projects WHERE id=%s', (project_id,))
    row = c.fetchone()
    if not row or row[0] != session['customer_id']:
        conn.close()
        return redirect(url_for('my_projects'))

    c.execute('''UPDATE project_payments SET client_approved=TRUE, client_approved_at=NOW()
                 WHERE project_id=%s AND phase_number=%s''', (project_id, phase_number))
    log_client_activity(c, session['customer_id'], 'Milestone approved')
    touch_project(c, project_id)

    c.execute('SELECT COUNT(*) FROM project_payments WHERE project_id=%s AND client_approved=FALSE', (project_id,))
    remaining = c.fetchone()[0]
    if remaining == 0:
        invoice_ref = 'INV-MRK-' + str(random.randint(100000, 999999))
        c.execute("UPDATE projects SET status='completed', completed=TRUE, invoice_ref=%s, updated_at=NOW() WHERE id=%s",
                  (invoice_ref, project_id))
        c.execute('SELECT accepted_by, title FROM projects WHERE id=%s', (project_id,))
        proj_row = c.fetchone()
        if proj_row and proj_row[0]:
            log_contractor_activity(c, proj_row[0], f"Completed project: {proj_row[1]}")

    conn.commit()
    conn.close()
    flash('Milestone approved.')
    return redirect(url_for('my_projects'))


@app.route('/client/request-changes/<int:project_id>/<int:phase_number>', methods=['POST'])
def client_request_changes(project_id, phase_number):
    if 'customer_id' not in session:
        return redirect(url_for('login'))
    notes = request.form.get('notes', '').strip()
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT customer_id FROM projects WHERE id=%s', (project_id,))
    row = c.fetchone()
    if not row or row[0] != session['customer_id']:
        conn.close()
        return redirect(url_for('my_projects'))

    c.execute('''UPDATE project_payments SET client_notes=%s, contractor_submitted_at=NULL
                 WHERE project_id=%s AND phase_number=%s''', (notes, project_id, phase_number))
    conn.commit()
    conn.close()
    flash('Changes requested — the contractor has been sent back to revise this milestone.')
    return redirect(url_for('my_projects'))


# ═══════════════════════════════════════════════════════════════════════
# CONTRACTOR PAYOUTS: 25% advance, requests, remaining balance
# ═══════════════════════════════════════════════════════════════════════

def create_contractor_payouts(c, project_id, contractor_id, contractor_pay):
    total = float(contractor_pay or 0)
    advance = round(total * 0.25, 2)
    remaining = round(total - advance, 2)
    c.execute('''INSERT INTO contractor_payouts (project_id, contractor_id, payout_type, amount)
                 VALUES (%s,%s,'advance',%s)''', (project_id, contractor_id, advance))
    c.execute('''INSERT INTO contractor_payouts (project_id, contractor_id, payout_type, amount)
                 VALUES (%s,%s,'remaining',%s)''', (project_id, contractor_id, remaining))


@app.route('/contractor/request-advance/<int:project_id>', methods=['POST'])
def contractor_request_advance(project_id):
    if 'contractor_id' not in session:
        return redirect(url_for('contractor_login'))
    amount = request.form.get('amount', '').strip()
    reason = request.form.get('reason', '').strip()
    if not amount or not reason:
        flash('An amount and a reason are both required to request an advance.')
        return redirect(url_for('contractor_dashboard'))

    conn = get_db()
    c = conn.cursor()
    c.execute('''INSERT INTO advance_requests (project_id, contractor_id, amount_requested, reason)
                 VALUES (%s,%s,%s,%s)''', (project_id, session['contractor_id'], amount, reason))
    conn.commit()
    conn.close()
    flash('Advance request submitted for CEO review.')
    return redirect(url_for('contractor_dashboard'))


@app.route('/ceo/advance-request/<int:req_id>/approve', methods=['POST'])
@ceo_required
def approve_advance_request(req_id):
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT project_id, contractor_id, amount_requested FROM advance_requests WHERE id=%s', (req_id,))
    r = c.fetchone()
    if r:
        c.execute('''INSERT INTO contractor_payouts (project_id, contractor_id, payout_type, amount)
                     VALUES (%s,%s,'extra',%s)''', (r[0], r[1], r[2]))
        c.execute("UPDATE advance_requests SET status='approved', decided_at=NOW() WHERE id=%s", (req_id,))
        conn.commit()
        flash('Advance request approved.')
    conn.close()
    return redirect(url_for('ceo_finance'))


@app.route('/ceo/advance-request/<int:req_id>/reject', methods=['POST'])
@ceo_required
def reject_advance_request(req_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE advance_requests SET status='rejected', decided_at=NOW() WHERE id=%s", (req_id,))
    conn.commit()
    conn.close()
    flash('Advance request rejected.')
    return redirect(url_for('ceo_finance'))


@app.route('/ceo/payout/<int:payout_id>/mark-paid', methods=['POST'])
@ceo_required
def mark_payout_paid(payout_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE contractor_payouts SET status='paid', paid_at=NOW() WHERE id=%s", (payout_id,))
    conn.commit()
    conn.close()
    flash('Payout marked as sent.')
    return redirect(url_for('ceo_finance'))


@app.errorhandler(404)
def not_found(e):
    return render_template('404.html'), 404


# ═══════════════════════════════════════════════════════════════════════
# TESTIMONIALS
# ═══════════════════════════════════════════════════════════════════════

@app.route('/submit-testimonial', methods=['POST'])
def submit_testimonial():
    if 'customer_id' not in session:
        return redirect(url_for('login'))
    rating = request.form.get('rating', '').strip()
    review_text = request.form.get('review_text', '').strip()
    if not rating or not review_text:
        flash('A rating and a review are both required.')
        return redirect(url_for('my_projects'))

    conn = get_db()
    c = conn.cursor()
    c.execute('''INSERT INTO testimonials (customer_id, rating, review_text)
                 VALUES (%s,%s,%s)''', (session['customer_id'], int(rating), review_text))
    conn.commit()
    conn.close()
    flash('Thank you — your review has been posted.')
    return redirect(url_for('my_projects'))


@app.route('/ceo/testimonial/<int:tid>/toggle', methods=['POST'])
@ceo_required
def toggle_testimonial(tid):
    conn = get_db()
    c = conn.cursor()
    c.execute('UPDATE testimonials SET is_published = NOT is_published WHERE id=%s', (tid,))
    conn.commit()
    conn.close()
    return redirect(url_for('ceo_portfolio_list'))


@app.route('/ceo/testimonial/<int:tid>/delete', methods=['POST'])
@ceo_required
def delete_testimonial(tid):
    conn = get_db()
    c = conn.cursor()
    c.execute('DELETE FROM testimonials WHERE id=%s', (tid,))
    conn.commit()
    conn.close()
    flash('Testimonial deleted.')
    return redirect(url_for('ceo_portfolio_list'))


# ═══════════════════════════════════════════════════════════════════════
# DEDICATED SERVICES PAGE
# ═══════════════════════════════════════════════════════════════════════

@app.route('/services')
def services_page():
    services = [
        {'key': k, 'name': k.replace(' (Service)', ''), 'price': v['price'],
         'weeks': v['weeks'], 'desc': v.get('desc', '')}
        for k, v in PACKAGE_INFO.items() if v.get('category') == 'service'
    ]
    return render_template('services.html', services=services)


# ─── RUN ────────────────────────────────────────────────
init_db()

if __name__ == '__main__':
    app.run(debug=True)
