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


def log_audit(actor_type, actor_id, actor_name, action, target_type=None, target_id=None,
              previous_state=None, new_state=None, category=None):
    try:
        conn = get_db()
        c = conn.cursor()
        c.execute('''INSERT INTO audit_log (actor, action, target, kind, relevant_id,
                                             previous_state, new_state, category)
                     VALUES (%s,%s,%s,%s,%s,%s,%s,%s)''',
                  (f"{actor_type}:{actor_name}" if actor_name else actor_type,
                   action, target_type, actor_type, target_id or actor_id,
                   previous_state, new_state, category))
        conn.commit()
        conn.close()
    except Exception:
        pass  # a logging failure must never break the action being logged

def send_notification(recipient_type, recipient_id, title, message, link=None):
    try:
        conn = get_db()
        c = conn.cursor()
        c.execute('''INSERT INTO notifications (recipient_type, recipient_id, title, message, link)
                     VALUES (%s,%s,%s,%s,%s)''',
                  (recipient_type, recipient_id, title, message, link))
        conn.commit()
        conn.close()
    except Exception:
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

    # ─── ADDED (backend build pass): customers business info + ban flag
    for col, ddl in [
        ('business_name', 'TEXT'),
        ('business_website', 'TEXT'),
        ('banned', 'BOOLEAN DEFAULT FALSE'),
    ]:
        try: c.execute(f'ALTER TABLE customers ADD COLUMN IF NOT EXISTS {col} {ddl}')
        except: conn.rollback()

    # ─── ADDED (backend build pass): submit_project expanded intake fields
    #     + contractor-role/task/CEO-instructions display (indices 20,21,22
    #     on the projects tuple — added after the existing 20 columns).
    for col, ddl in [
        ('contractor_role', 'TEXT'),
        ('current_task', 'TEXT'),
        ('ceo_instructions', 'TEXT'),
        ('main_objective', 'TEXT'),
        ('main_objective_other', 'TEXT'),
        ('has_existing_website', 'TEXT'),
        ('existing_website_url', 'TEXT'),
        ('specific_requirements', 'TEXT'),
        ('reference_sites', 'TEXT'),
        ('contact_preference', 'TEXT'),
        ('confirm_accurate', 'BOOLEAN DEFAULT FALSE'),
    ]:
        try: c.execute(f'ALTER TABLE projects ADD COLUMN IF NOT EXISTS {col} {ddl}')
        except: conn.rollback()

    # ─── ADDED (backend build pass): CEO review gate on contractor
    #     milestone submissions, before the client ever sees them.
    for col, ddl in [
        ('ceo_review_status', 'TEXT'),
        ('ceo_feedback', 'TEXT'),
        ('ceo_reviewed_at', 'TIMESTAMP'),
    ]:
        try: c.execute(f'ALTER TABLE project_payments ADD COLUMN IF NOT EXISTS {col} {ddl}')
        except: conn.rollback()

    # ─── ADDED (backend build pass): client/contractor file uploads
    c.execute('''CREATE TABLE IF NOT EXISTS files (
        id SERIAL PRIMARY KEY,
        project_id INTEGER REFERENCES projects(id) ON DELETE CASCADE,
        uploaded_by TEXT,
        filename TEXT,
        url TEXT,
        milestone_label TEXT,
        uploaded_at TIMESTAMP DEFAULT NOW())''')

    # ─── ADDED (backend build pass): discount codes
    c.execute('''CREATE TABLE IF NOT EXISTS discounts (
        id SERIAL PRIMARY KEY,
        name TEXT,
        code TEXT,
        discount_type TEXT,
        value NUMERIC(10,2),
        applies_to TEXT,
        usage_limit INTEGER,
        used_count INTEGER DEFAULT 0,
        start_date DATE,
        end_date DATE,
        status TEXT DEFAULT 'active',
        created_at TIMESTAMP DEFAULT NOW())''')

    # ─── ADDED (backend build pass): public site-wide update banners
    c.execute('''CREATE TABLE IF NOT EXISTS public_updates (
        id SERIAL PRIMARY KEY,
        text TEXT,
        active BOOLEAN DEFAULT FALSE,
        published_at TIMESTAMP DEFAULT NOW())''')

    # ─── ADDED (backend build pass): per-service on/off availability toggle
    c.execute('''CREATE TABLE IF NOT EXISTS service_availability (
        service_name TEXT PRIMARY KEY,
        available BOOLEAN DEFAULT TRUE)''')
    for svc in PACKAGE_INFO.keys():
        c.execute('''INSERT INTO service_availability (service_name, available)
                     VALUES (%s, TRUE) ON CONFLICT (service_name) DO NOTHING''', (svc,))

    # ─── ADDED (backend build pass): site-wide maintenance/status mode
    c.execute('''CREATE TABLE IF NOT EXISTS site_status (
        id SERIAL PRIMARY KEY,
        mode TEXT DEFAULT 'online',
        headline TEXT,
        message TEXT,
        eta TEXT,
        updated_at TIMESTAMP DEFAULT NOW())''')
    c.execute("SELECT COUNT(*) FROM site_status")
    if c.fetchone()[0] == 0:
        c.execute("INSERT INTO site_status (mode) VALUES ('online')")

    # ─── ADDED (backend build pass): administrative-action audit trail
    c.execute('''CREATE TABLE IF NOT EXISTS audit_log (
        id SERIAL PRIMARY KEY,
        actor TEXT,
        action TEXT,
        target TEXT,
        kind TEXT,
        relevant_id INTEGER,
        previous_state TEXT,
        new_state TEXT,
        category TEXT,
        timestamp TIMESTAMP DEFAULT NOW())''')

    # ─── ADDED (backend build pass): in-app notifications (client/contractor/CEO)
    c.execute('''CREATE TABLE IF NOT EXISTS notifications (
        id SERIAL PRIMARY KEY,
        recipient_type TEXT,
        recipient_id INTEGER,
        title TEXT,
        message TEXT,
        link TEXT,
        is_read BOOLEAN DEFAULT FALSE,
        created_at TIMESTAMP DEFAULT NOW())''')

    conn.commit()
    conn.close()

# ═══════════════════════════════════════════════════════════════════════
# ADDED (consolidated pass) — shared helpers for activity logging,
# notifications, business health, and the contractor→CEO→client stage flow.
# ════════════════════════════════════════════════════════════════  

