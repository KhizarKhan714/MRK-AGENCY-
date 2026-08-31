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
    
