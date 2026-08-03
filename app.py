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


# ─── ADDED: dict-cursor connection — only used by the new portfolio/team
#     routes below, so those templates can use p.title, p.category, etc.
#     Nothing about get_db() above was touched. ──────────────────────────
def get_dict_db():
    conn = psycopg2.connect(DATABASE_URL)
    return conn, conn.cursor(cursor_factory=RealDictCursor)


# ─── ADDED: Cloudinary — for portfolio/team images only. Local disk
#     storage gets wiped on every Railway redeploy, same issue you already
#     hit with SQLite, so these images go to Cloudinary instead. ─────────
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


# ─── ADDED: these were referenced (contractor_apply, team_add,
#     team_delete) but never defined in the file you sent me — that
#     would have crashed those routes on first use. UPLOAD_FOLDER still
#     saves locally, which has the same Railway-wipe risk as above —
#     worth migrating to Cloudinary too when you have time. ─────────────
app.config['UPLOAD_FOLDER'] = 'uploads'
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'pdf', 'doc', 'docx'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


# ─── ADDED: placeholders so contractor_apply doesn't crash. No audit-log
#     or notifications table exists yet — these are safe no-ops until you
#     want to build those out for real. ─────────────────────────────────
def log_audit(actor_type, actor_id, actor_name, action, target_type=None, target_id=None):
    pass

def send_notification(recipient_type, recipient_id, title, message, link=None):
    pass


# ─── ADDED: also referenced (team_add, team_delete) but never defined.
#     Matches the exact session pattern already used in ceo_dashboard(). ─
def ceo_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get('ceo'):
            return redirect(url_for('ceo_portal'))
        return f(*args, **kwargs)
    return wrapper


# ─── ADDED: reads the CEO-controlled visibility toggles, and makes them
#     available in every template as `site_settings` automatically. ─────
def get_site_settings():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT portfolio_visible, team_visible FROM site_settings WHERE id=1")
    row = c.fetchone()
    conn.close()
    return {'portfolio_section_visible': row[0], 'team_section_visible': row[1]}


# ─── ADDED: reads the editable "Site Manager" copy + Payoneer payment
#     details the CEO sets from the dashboard. Powers the /ceo/site-settings
#     form and is what makes payment details editable without touching code. ─
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


# ─── ADDED: single source of truth for package price, delivery time, and
#     payment-phase split. Nothing else in the app should hardcode a price —
#     everything reads from here, including the payment phases the client
#     confirmed: Bronze=100% upfront, Consular=50/50, Gold/Diamond=30/20/50.
#     Diamond is 10 weeks here because that's what's live in submit_project.html —
#     flagged separately since earlier notes said 8 weeks; change the 'weeks'
#     value below if 8 was correct. ────────────────────────────────────────
PACKAGE_INFO = {
    'Bronze':   {'price': 1499, 'weeks': 2,  'phases': [(1.00, 'Full payment')], 'category': 'package'},
    'Consular': {'price': 2999, 'weeks': 3,  'phases': [(0.50, 'Upfront'), (0.50, 'On delivery')], 'category': 'package'},
    'Gold':     {'price': 4999, 'weeks': 5,  'phases': [(0.30, 'Upfront'), (0.20, 'Midpoint review'), (0.50, 'On delivery')], 'category': 'package'},
    'Diamond':  {'price': 8499, 'weeks': 10, 'phases': [(0.30, 'Upfront'), (0.20, 'Midpoint review'), (0.50, 'On delivery')], 'category': 'package'},

    # ─── ADDED: à la carte Business Services — for clients who only need one
    #     piece, not a full package. 1-phase/100%-upfront like Bronze, since
    #     these are smaller, faster-turnaround jobs. "Starting at" pricing —
    #     scope varies, so this is the floor, not a rigid fixed fee.
    'Web Design (Service)':        {'price': 799,  'weeks': 1, 'phases': [(1.00, 'Full payment')], 'category': 'service', 'desc': 'Design only — no build. Ideal if you already have a developer or platform and just need the look done right.'},
    'UI/UX Design (Service)':      {'price': 999,  'weeks': 1, 'phases': [(1.00, 'Full payment')], 'category': 'service', 'desc': 'Audit and redesign of an existing product or site\u2019s user experience — flows, usability, and interface polish.'},
    'Graphic Design (Service)':    {'price': 499,  'weeks': 1, 'phases': [(1.00, 'Full payment')], 'category': 'service', 'desc': 'Logo and brand asset design — for a new identity or refreshing what you already have.'},
    'SEO (Service)':                {'price': 599,  'weeks': 1, 'phases': [(1.00, 'Full payment')], 'category': 'service', 'desc': 'One-time technical SEO setup — the foundation done right. Ongoing ranking work is a separate, recurring engagement.'},
    'Web Development (Service)':   {'price': 1299, 'weeks': 2, 'phases': [(1.00, 'Full payment')], 'category': 'service', 'desc': 'Add functionality to a site you already have — no need to rebuild everything from scratch.'},
}
CUSTOM_EXECUTIVE_PHASES = [(0.30, 'Upfront'), (0.20, 'Midpoint review'), (0.50, 'On delivery')]


def create_payment_phases(conn_cursor, project_id, total_amount, phases):
    """Inserts one project_payments row per phase for a newly submitted project."""
    for i, (pct, label) in enumerate(phases, start=1):
        conn_cursor.execute(
            '''INSERT INTO project_payments (project_id, phase_number, phase_label, amount)
               VALUES (%s,%s,%s,%s)''',
            (project_id, i, label, round(float(total_amount) * pct, 2))
        )


def init_db():
    conn = get_db()
    c = conn.cursor()

    # CUSTOMERS
    c.execute('''CREATE TABLE IF NOT EXISTS customers (
        id SERIAL PRIMARY KEY,
        first_name TEXT, last_name TEXT,
        email TEXT UNIQUE, password TEXT,
        photo TEXT,
        suspended BOOLEAN DEFAULT FALSE,
        phone TEXT,
        whatsapp TEXT)''')
    try:
        c.execute('ALTER TABLE customers ADD COLUMN IF NOT EXISTS photo TEXT')
    except: conn.rollback()
    try:
        c.execute('ALTER TABLE customers ADD COLUMN IF NOT EXISTS suspended BOOLEAN DEFAULT FALSE')
    except: conn.rollback()
    try:
        c.execute('ALTER TABLE customers ADD COLUMN IF NOT EXISTS phone TEXT')
    except: conn.rollback()
    try:
        c.execute('ALTER TABLE customers ADD COLUMN IF NOT EXISTS whatsapp TEXT')
    except: conn.rollback()

    # CONTRACTORS
    c.execute('''CREATE TABLE IF NOT EXISTS contractors (
        id SERIAL PRIMARY KEY,
        name TEXT, password TEXT, expertise TEXT,
        experience TEXT, note TEXT, cin TEXT,
        status TEXT DEFAULT 'pending',
        email TEXT, phone TEXT, whatsapp TEXT,
        cnic TEXT, cnic_image TEXT, cv TEXT,
        specialties TEXT, suspended BOOLEAN DEFAULT FALSE,
        badge TEXT)''')
    try:
        c.execute('ALTER TABLE contractors ADD COLUMN IF NOT EXISTS email TEXT')
    except: conn.rollback()
    try:
        c.execute('ALTER TABLE contractors ADD COLUMN IF NOT EXISTS phone TEXT')
    except: conn.rollback()
    try:
        c.execute('ALTER TABLE contractors ADD COLUMN IF NOT EXISTS whatsapp TEXT')
    except: conn.rollback()
    try:
        c.execute('ALTER TABLE contractors ADD COLUMN IF NOT EXISTS cnic TEXT')
    except: conn.rollback()
    try:
        c.execute('ALTER TABLE contractors ADD COLUMN IF NOT EXISTS cnic_image TEXT')
    except: conn.rollback()
    try:
        c.execute('ALTER TABLE contractors ADD COLUMN IF NOT EXISTS cv TEXT')
    except: conn.rollback()
    try:
        c.execute('ALTER TABLE contractors ADD COLUMN IF NOT EXISTS specialties TEXT')
    except: conn.rollback()
    try:
        c.execute('ALTER TABLE contractors ADD COLUMN IF NOT EXISTS suspended BOOLEAN DEFAULT FALSE')
    except: conn.rollback()
    try:
        c.execute('ALTER TABLE contractors ADD COLUMN IF NOT EXISTS badge TEXT')
    except: conn.rollback()
    try:
        c.execute("ALTER TABLE contractors ADD COLUMN IF NOT EXISTS country TEXT")
    except: conn.rollback()
    try:
        c.execute("ALTER TABLE contractors ADD COLUMN IF NOT EXISTS national_id TEXT")
    except: conn.rollback()

    # PROJECTS
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
    try:
        c.execute('ALTER TABLE projects ADD COLUMN IF NOT EXISTS contractor_pay TEXT')
    except: conn.rollback()
    try:
        c.execute('ALTER TABLE projects ADD COLUMN IF NOT EXISTS accepted_by INTEGER')
    except: conn.rollback()
    try:
        c.execute('ALTER TABLE projects ADD COLUMN IF NOT EXISTS rejection_reason TEXT')
    except: conn.rollback()
    try:
        c.execute('ALTER TABLE projects ADD COLUMN IF NOT EXISTS invoice_ref TEXT')
    except: conn.rollback()
    try:
        c.execute('ALTER TABLE projects ADD COLUMN IF NOT EXISTS completed BOOLEAN DEFAULT FALSE')
    except: conn.rollback()

    # CEO
    c.execute('''CREATE TABLE IF NOT EXISTS ceo (
        id SERIAL PRIMARY KEY,
        name TEXT, password TEXT, secret_key TEXT,
        security_answer TEXT)''')
    c.execute("SELECT COUNT(*) FROM ceo")
    if c.fetchone()[0] == 0:
        c.execute("INSERT INTO ceo (name, password, secret_key, security_answer) VALUES (%s,%s,%s,%s)",
             ('Khizar Khan', 'CEOMRKAgencyKhizarKhan', 'KhizarKhanCEOMRK7', 'Kiran'))

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

    # ─── ADDED: portfolio/team publishing feature ──────────────────────
    try:
        c.execute('ALTER TABLE team_members ADD COLUMN IF NOT EXISTS is_published BOOLEAN DEFAULT FALSE')
    except: conn.rollback()
    try:
        c.execute('ALTER TABLE team_members ADD COLUMN IF NOT EXISTS display_order INTEGER DEFAULT 0')
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

    # ─── ADDED: site copy + Payoneer payment details, editable from the CEO
    #     dashboard's existing "Site Manager" form — no code changes needed
    #     to update the account email/name the way the CEO asked for. ──────
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
        try:
            c.execute(f'ALTER TABLE site_settings ADD COLUMN IF NOT EXISTS {col} {ddl}')
        except: conn.rollback()

    # ─── ADDED: tracks each client payment phase per project (auto-created
    #     when a project is submitted, based on PACKAGE_INFO's phase split). ─
    c.execute('''CREATE TABLE IF NOT EXISTS project_payments (
        id SERIAL PRIMARY KEY,
        project_id INTEGER REFERENCES projects(id) ON DELETE CASCADE,
        phase_number INTEGER,
        phase_label TEXT,
        amount NUMERIC(10,2),
        is_paid BOOLEAN DEFAULT FALSE,
        paid_at TIMESTAMP,
        payment_method TEXT DEFAULT 'Payoneer')''')

    # ─── ADDED: contractor bank details (set at application, editable after
    #     approval — but any edit after the first fill-in requires CEO
    #     sign-off, handled via bank_edit_requests below) + profile photo
    #     (self-service, no approval — CEO uses these on the public site). ──
    for col, ddl in [
        ('bank_account_title', 'TEXT'),
        ('bank_account_number', 'TEXT'),
        ('bank_name', 'TEXT'),
        ('bank_swift_iban', 'TEXT'),
        ('photo', 'TEXT'),
    ]:
        try:
            c.execute(f'ALTER TABLE contractors ADD COLUMN IF NOT EXISTS {col} {ddl}')
        except: conn.rollback()

    # ─── ADDED: pending bank-detail changes — a contractor's live bank
    #     fields on `contractors` only change once the CEO approves the
    #     request here. First-ever fill-in (fields currently blank) skips
    #     this and writes directly — see /contractor/update-bank.
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

    # ─── ADDED: per-payment-phase work review. A contractor submits proof
    #     for a phase; the client approves it or sends it back with notes.
    #     Approving the LAST phase is what actually completes the project —
    #     replaces the old one-click "Mark Complete" with real client sign-off.
    for col, ddl in [
        ('contractor_proof', 'TEXT'),
        ('contractor_submitted_at', 'TIMESTAMP'),
        ('client_approved', 'BOOLEAN DEFAULT FALSE'),
        ('client_approved_at', 'TIMESTAMP'),
        ('client_notes', 'TEXT'),
    ]:
        try:
            c.execute(f'ALTER TABLE project_payments ADD COLUMN IF NOT EXISTS {col} {ddl}')
        except: conn.rollback()

    # ─── ADDED: contractor payouts — separate from client payment phases.
    #     An advance (25% of contractor_pay) and the remaining balance are
    #     auto-created when the CEO approves a project; extra approved
    #     advance requests add more rows here too. CEO marks each paid
    #     manually, same pattern as client payments.
    c.execute('''CREATE TABLE IF NOT EXISTS contractor_payouts (
        id SERIAL PRIMARY KEY,
        project_id INTEGER REFERENCES projects(id) ON DELETE CASCADE,
        contractor_id INTEGER REFERENCES contractors(id) ON DELETE CASCADE,
        payout_type TEXT,
        amount NUMERIC(10,2),
        status TEXT DEFAULT 'pending',
        paid_at TIMESTAMP,
        created_at TIMESTAMP DEFAULT NOW())''')

    # ─── ADDED: contractor requests for extra funds beyond their advance —
    #     always requires a reason; CEO approves (creates a payout row) or
    #     rejects. Nothing moves without CEO sign-off.
    c.execute('''CREATE TABLE IF NOT EXISTS advance_requests (
        id SERIAL PRIMARY KEY,
        project_id INTEGER REFERENCES projects(id) ON DELETE CASCADE,
        contractor_id INTEGER REFERENCES contractors(id) ON DELETE CASCADE,
        amount_requested NUMERIC(10,2),
        reason TEXT,
        status TEXT DEFAULT 'pending',
        requested_at TIMESTAMP DEFAULT NOW(),
        decided_at TIMESTAMP)''')

    # ─── ADDED: testimonials — public only when at least one exists, no
    #     empty-state section. is_published lets the CEO hide a bad-faith
    #     or low-quality review without deleting it outright.
    c.execute('''CREATE TABLE IF NOT EXISTS testimonials (
        id SERIAL PRIMARY KEY,
        customer_id INTEGER REFERENCES customers(id) ON DELETE CASCADE,
        rating INTEGER,
        review_text TEXT,
        is_published BOOLEAN DEFAULT TRUE,
        created_at TIMESTAMP DEFAULT NOW())''')

    # ─── ADDED: social media links — editable from the CEO dashboard,
    #     same Site Manager mechanism as everything else, no code changes
    for col, ddl in [
        ('linkedin_url', 'TEXT'),
        ('facebook_url', 'TEXT'),
        ('instagram_url', 'TEXT'),
        ('twitter_url', 'TEXT'),
    ]:
        try:
            c.execute(f'ALTER TABLE site_settings ADD COLUMN IF NOT EXISTS {col} {ddl}')
        except: conn.rollback()

    conn.commit()
    conn.close()


# ─── HOME ───────────────────────────────────────────────
@app.route('/')
def home():
    # ADDED: featured projects/team for the homepage preview sections
    conn, c = get_dict_db()
    c.execute("SELECT * FROM portfolio_projects WHERE is_published=TRUE AND is_featured=TRUE ORDER BY display_order LIMIT 3")
    featured_projects = c.fetchall()
    c.execute("SELECT * FROM team_members WHERE is_published=TRUE ORDER BY display_order LIMIT 3")
    featured_team = c.fetchall()

    # ADDED: testimonials — empty list if none exist, template hides the
    # whole section rather than showing an empty state
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
            if user[6]:  # suspended
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


@app.route('/dashboard')
def dashboard():
    if 'customer_id' not in session:
        return redirect(url_for('login'))
    return render_template('dashboard.html', name=session['customer_name'])


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

            # Fold the optional extra detail fields into the description so
            # nothing is lost, without needing new projects table columns.
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

    # ADDED: amount still owed per project, so the payment status is visible
    # on every card, not just after the project is marked complete
    amount_due = {}
    for p in projects:
        c.execute('''SELECT COALESCE(SUM(amount),0) FROM project_payments
                     WHERE project_id=%s AND is_paid=FALSE''', (p[0],))
        amount_due[p[0]] = float(c.fetchone()[0])

    # ADDED: the phase currently awaiting the client's review, if any —
    # only shown once the contractor has actually submitted proof
    review_status = {}
    for p in projects:
        phase = get_next_review_phase(c, p[0])
        if phase and phase[3]:  # contractor_submitted_at is set
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

    # ADDED: fetch the real payment plan instead of assuming one lump sum due at completion
    c.execute('''SELECT phase_number, phase_label, amount, is_paid, paid_at
                 FROM project_payments WHERE project_id=%s ORDER BY phase_number''', (project_id,))
    phase_rows = c.fetchall()
    conn.close()

    phases = [{'number': r[0], 'label': r[1], 'amount': float(r[2]), 'is_paid': r[3], 'paid_at': r[4]} for r in phase_rows]
    total_amount = sum(p['amount'] for p in phases)
    total_paid = sum(p['amount'] for p in phases if p['is_paid'])
    amount_due_now = sum(p['amount'] for p in phases if not p['is_paid'])
    fully_paid = amount_due_now == 0 and len(phases) > 0
    # The next unpaid phase, in order — this is what the payment instructions box should point at
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

        # ADDED: payout details, now collected on the application form
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
