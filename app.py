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
                        payoneer_account_name, payment_instructions
                 FROM site_settings WHERE id=1''')
    row = c.fetchone()
    conn.close()
    keys = ['hero_tagline', 'hero_subtext', 'agency_bio', 'contact_email',
            'contact_phone', 'contact_whatsapp', 'payoneer_email',
            'payoneer_account_name', 'payment_instructions']
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
    'Bronze':   {'price': 1499, 'weeks': 2,  'phases': [(1.00, 'Full payment')]},
    'Consular': {'price': 2999, 'weeks': 3,  'phases': [(0.50, 'Upfront'), (0.50, 'On delivery')]},
    'Gold':     {'price': 4999, 'weeks': 5,  'phases': [(0.30, 'Upfront'), (0.20, 'Midpoint review'), (0.50, 'On delivery')]},
    'Diamond':  {'price': 8499, 'weeks': 10, 'phases': [(0.30, 'Upfront'), (0.20, 'Midpoint review'), (0.50, 'On delivery')]},
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
    conn.close()
    return render_template('index.html', featured_projects=featured_projects, featured_team=featured_team)


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
            return redirect(url_for('my_projects'))
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
    conn.close()
    return render_template('my_projects.html', projects=projects)


# ─── INVOICE ────────────────────────────────────────────
@app.route('/invoice/<int:project_id>')
def invoice(project_id):
    if 'customer_id' not in session:
        return redirect(url_for('login'))
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT * FROM projects WHERE id=%s AND customer_id=%s', (project_id, session['customer_id']))
    project = c.fetchone()
    conn.close()
    if not project:
        return redirect(url_for('my_projects'))
    return render_template('invoice.html', project=project)


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
             country, national_id)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'pending',%s,%s)
            RETURNING id''',
            (name, email, phone, whatsapp, national_id, cnic_image_name, cv_name,
             expertise, experience, specialties, note, hashed,
             country, national_id))
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
        conn.close()
        if contractor and bcrypt.checkpw(pw, contractor[2].encode()):
            if contractor[15]:  # suspended
                return render_template('contractor_login.html', error='Your account has been suspended. Contact MRK Agency.')
            session['contractor_id'] = contractor[0]
            session['contractor_name'] = contractor[1]
            return redirect(url_for('contractor_dashboard'))
        return render_template('contractor_login.html', error='Invalid CIN or password.')
    return render_template('contractor_login.html')


@app.route('/contractor-logout')
def contractor_logout():
    session.pop('contractor_id', None)
    session.pop('contractor_name', None)
    return redirect(url_for('contractor_login'))


# ─── CONTRACTOR DASHBOARD ───────────────────────────────
@app.route('/contractor-dashboard')
def contractor_dashboard():
    if 'contractor_id' not in session:
        return redirect(url_for('contractor_login'))
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT * FROM contractors WHERE id=%s', (session['contractor_id'],))
    contractor = c.fetchone()
    c.execute("""SELECT * FROM projects
                 WHERE status='approved' AND contractor_pay IS NOT NULL
                 AND (accepted_by IS NULL OR accepted_by=%s)
                 AND (completed IS NULL OR completed=FALSE)""",
              (session['contractor_id'],))
    projects = c.fetchall()
    conn.close()
    return render_template('contractor_dashboard.html',
        contractor=contractor, projects=projects)


@app.route('/contractor-change-password', methods=['POST'])
def contractor_change_password():
    if 'contractor_id' not in session:
        return redirect(url_for('contractor_login'))
    current_pw = request.form['current_password'].encode()
    new_pw = request.form['new_password']
    confirm_pw = request.form['confirm_password']
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT * FROM contractors WHERE id=%s', (session['contractor_id'],))
    contractor = c.fetchone()
    c.execute("""SELECT * FROM projects WHERE status='approved' AND contractor_pay IS NOT NULL
                 AND (accepted_by IS NULL OR accepted_by=%s)
                 AND (completed IS NULL OR completed=FALSE)""",
              (session['contractor_id'],))
    projects = c.fetchall()
    if not bcrypt.checkpw(current_pw, contractor[2].encode()):
        conn.close()
        return render_template('contractor_dashboard.html', contractor=contractor, projects=projects,
                               error='Current password is incorrect.')
    if new_pw != confirm_pw:
        conn.close()
        return render_template('contractor_dashboard.html', contractor=contractor, projects=projects,
                               error='New passwords do not match.')
    if len(new_pw) < 6:
        conn.close()
        return render_template('contractor_dashboard.html', contractor=contractor, projects=projects,
                               error='Password must be at least 6 characters.')
    hashed = bcrypt.hashpw(new_pw.encode(), bcrypt.gensalt()).decode()
    c.execute('UPDATE contractors SET password=%s WHERE id=%s', (hashed, session['contractor_id']))
    conn.commit()
    conn.close()
    return render_template('contractor_dashboard.html', contractor=contractor, projects=projects,
                           success='Password changed successfully.')


@app.route('/accept-project/<int:id>')
def accept_project(id):
    if 'contractor_id' not in session:
        return redirect(url_for('contractor_login'))
    conn = get_db()
    c = conn.cursor()
    c.execute('UPDATE projects SET accepted_by=%s, assigned_contractor_id=%s WHERE id=%s',
              (session['contractor_id'], session['contractor_id'], id))
    conn.commit()
    conn.close()
    return redirect(url_for('contractor_dashboard'))


@app.route('/mark-complete/<int:id>')
def mark_complete(id):
    if 'contractor_id' not in session:
        return redirect(url_for('contractor_login'))
    conn = get_db()
    c = conn.cursor()
    # Generate invoice reference
    invoice_ref = 'INV-MRK-' + str(random.randint(100000, 999999))
    c.execute("""UPDATE projects SET completed=TRUE, status='completed', invoice_ref=%s
                 WHERE id=%s AND accepted_by=%s""",
              (invoice_ref, id, session['contractor_id']))
    conn.commit()
    conn.close()
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
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT * FROM ceo WHERE name=%s', (name,))
    ceo = c.fetchone()
    conn.close()
    if ceo and ceo[2] == pw and ceo[3] == sk and ceo[4] == sa:
        session['ceo'] = True
        return redirect(url_for('ceo_dashboard'))
    return render_template('ceo_login.html', error='Invalid credentials. Access denied.')


@app.route('/ceo-logout')
def ceo_logout():
    session.pop('ceo', None)
    return redirect(url_for('ceo_portal'))


# ─── CEO DASHBOARD ──────────────────────────────────────
@app.route('/ceo-dashboard')
def ceo_dashboard():
    if not session.get('ceo'):
        return redirect(url_for('ceo_portal'))
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM contractors WHERE status='pending'")
    pending_contractors = c.fetchall()
    c.execute("SELECT * FROM contractors WHERE status='approved' AND (suspended IS NULL OR suspended=FALSE)")
    approved_contractors = c.fetchall()
    c.execute("SELECT * FROM contractors WHERE status='rejected' OR suspended=TRUE")
    rejected_contractors = c.fetchall()
    c.execute("SELECT * FROM projects WHERE status='pending'")
    pending_projects = c.fetchall()
    c.execute("SELECT * FROM projects WHERE status='approved'")
    approved_projects = c.fetchall()
    c.execute("SELECT * FROM projects WHERE status='completed'")
    completed_projects = c.fetchall()
    c.execute("SELECT * FROM customers WHERE suspended=FALSE OR suspended IS NULL")
    customers = c.fetchall()
    c.execute("SELECT * FROM customers WHERE suspended=TRUE")
    suspended_customers = c.fetchall()
    c.execute("SELECT * FROM team_members ORDER BY created_at")
    team_members = c.fetchall()
    # All contractors including banned
    c.execute("SELECT * FROM contractors WHERE status='banned'")
    banned_contractors = c.fetchall()

    # Project counts per customer
    c.execute("SELECT customer_id, COUNT(*) FROM projects GROUP BY customer_id")
    project_counts = {row[0]: row[1] for row in c.fetchall()}

    # ─── ADDED: revenue now reflects actual payments received, not just
    #     the total price of completed projects. ────────────────────────
    c.execute("SELECT COALESCE(SUM(amount),0) FROM project_payments WHERE is_paid=TRUE")
    total_revenue = float(c.fetchone()[0])

    # ─── ADDED: payment phases per project, keyed by project id, so the
    #     Pending/Active/Completed project cards can show what's owed/paid. ─
    c.execute('''SELECT project_id, phase_number, phase_label, amount, is_paid
                 FROM project_payments ORDER BY project_id, phase_number''')
    payment_phases = {}
    for row in c.fetchall():
        payment_phases.setdefault(row[0], []).append(
            {'phase_number': row[1], 'phase_label': row[2], 'amount': row[3], 'is_paid': row[4]}
        )

    # ─── ADDED: editable site copy + Payoneer payment details for the
    #     Site Manager form (was previously posting to a route that didn't
    #     exist, so `settings` was always undefined). ─────────────────────
    settings = get_site_copy()

    conn.close()
    return render_template('ceo_dashboard.html',
        pending_contractors=pending_contractors,
        approved_contractors=approved_contractors,
        rejected_contractors=rejected_contractors,
        banned_contractors=banned_contractors,
        pending_projects=pending_projects,
        approved_projects=approved_projects,
        completed_projects=completed_projects,
        customers=customers,
        suspended_customers=suspended_customers,
        project_counts=project_counts,
        total_revenue=total_revenue,
        payment_phases=payment_phases,
        settings=settings)


# ─── CEO: CONTRACTOR ACTIONS ────────────────────────────
@app.route('/approve-contractor/<int:id>')
def approve_contractor(id):
    if not session.get('ceo'):
        return redirect(url_for('ceo_portal'))
    cin = 'MRK' + str(random.randint(10000, 99999))
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE contractors SET status='approved', cin=%s, suspended=FALSE WHERE id=%s", (cin, id))
    conn.commit()
    conn.close()
    return redirect(url_for('ceo_dashboard'))


@app.route('/reject-contractor/<int:id>')
def reject_contractor(id):
    if not session.get('ceo'):
        return redirect(url_for('ceo_portal'))
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE contractors SET status='rejected' WHERE id=%s", (id,))
    conn.commit()
    conn.close()
    return redirect(url_for('ceo_dashboard'))


@app.route('/suspend-contractor/<int:id>')
def suspend_contractor(id):
    if not session.get('ceo'):
        return redirect(url_for('ceo_portal'))
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE contractors SET suspended=TRUE, cin=NULL WHERE id=%s", (id,))
    conn.commit()
    conn.close()
    return redirect(url_for('ceo_dashboard'))


@app.route('/reinstate-contractor/<int:id>')
def reinstate_contractor(id):
    if not session.get('ceo'):
        return redirect(url_for('ceo_portal'))
    cin = 'MRK' + str(random.randint(10000, 99999))
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE contractors SET suspended=FALSE, status='approved', cin=%s WHERE id=%s", (cin, id))
    conn.commit()
    conn.close()
    return redirect(url_for('ceo_dashboard'))


@app.route('/delete-contractor/<int:id>')
def delete_contractor(id):
    if not session.get('ceo'):
        return redirect(url_for('ceo_portal'))
    conn = get_db()
    c = conn.cursor()
    c.execute("DELETE FROM contractors WHERE id=%s", (id,))
    conn.commit()
    conn.close()
    return redirect(url_for('ceo_dashboard'))


@app.route('/ban-cin/<int:id>')
def ban_cin(id):
    if not session.get('ceo'):
        return redirect(url_for('ceo_portal'))
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE contractors SET cin=NULL, status='banned', suspended=TRUE WHERE id=%s", (id,))
    conn.commit()
    conn.close()
    return redirect(url_for('ceo_dashboard'))


@app.route('/award-badge/<int:id>', methods=['POST'])
def award_badge(id):
    if not session.get('ceo'):
        return redirect(url_for('ceo_portal'))
    badge = request.form.get('badge', '').strip()
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE contractors SET badge=%s WHERE id=%s", (badge, id))
    conn.commit()
    conn.close()
    return redirect(url_for('ceo_dashboard'))


# ─── CEO: PROJECT ACTIONS ───────────────────────────────
@app.route('/approve-project/<int:id>', methods=['GET', 'POST'])
def approve_project(id):
    if not session.get('ceo'):
        return redirect(url_for('ceo_portal'))
    contractor_pay = request.form.get('contractor_pay', '0').strip()
    if not contractor_pay:
        contractor_pay = '0'
    conn = get_db()
    c = conn.cursor()
    try:
        c.execute("UPDATE projects SET status='approved', contractor_pay=%s WHERE id=%s", (contractor_pay, id))
        conn.commit()
    except Exception as e:
        conn.rollback()
    conn.close()
    return redirect(url_for('ceo_dashboard'))


@app.route('/reject-project/<int:id>', methods=['GET', 'POST'])
def reject_project(id):
    if not session.get('ceo'):
        return redirect(url_for('ceo_portal'))
    reason = request.form.get('rejection_reason', 'No reason provided.').strip()
    if not reason:
        reason = 'No reason provided.'
    conn = get_db()
    c = conn.cursor()
    try:
        c.execute("UPDATE projects SET status='rejected', rejection_reason=%s WHERE id=%s", (reason, id))
        conn.commit()
    except Exception as e:
        conn.rollback()
    conn.close()
    return redirect(url_for('ceo_dashboard'))


# ─── CEO: CUSTOMER ACTIONS ──────────────────────────────
@app.route('/suspend-customer/<int:id>')
def suspend_customer(id):
    if not session.get('ceo'):
        return redirect(url_for('ceo_portal'))
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE customers SET suspended=TRUE WHERE id=%s", (id,))
    conn.commit()
    conn.close()
    return redirect(url_for('ceo_dashboard'))


@app.route('/reinstate-customer/<int:id>')
def reinstate_customer(id):
    if not session.get('ceo'):
        return redirect(url_for('ceo_portal'))
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE customers SET suspended=FALSE WHERE id=%s", (id,))
    conn.commit()
    conn.close()
    return redirect(url_for('ceo_dashboard'))


@app.route('/delete-customer/<int:id>')
def delete_customer(id):
    if not session.get('ceo'):
        return redirect(url_for('ceo_portal'))
    conn = get_db()
    c = conn.cursor()
    c.execute("DELETE FROM customers WHERE id=%s", (id,))
    conn.commit()
    conn.close()
    return redirect(url_for('ceo_dashboard'))


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
    return redirect(url_for('ceo_dashboard'))


@app.route('/ceo/team/delete/<int:tid>')
@ceo_required
def team_delete(tid):
    conn = get_db()
    c = conn.cursor()
    c.execute("DELETE FROM team_members WHERE id=%s",(tid,))
    conn.commit(); conn.close()
    flash('Team member removed.','success')
    return redirect(url_for('ceo_dashboard'))


@app.route('/api/team')
def api_team():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT id,name,role,specialties,bio,projects_count,photo FROM team_members ORDER BY created_at")
    rows = c.fetchall()
    conn.close()
    return jsonify([{'id':r[0],'name':r[1],'role':r[2],'specialties':r[3],'bio':r[4],'projects':r[5],'photo':r[6]} for r in rows])


# ═══════════════════════════════════════════════════════════════════════
# ADDED — SITE COPY + PAYMENT SETTINGS + PAYMENT PHASE TRACKING
# ═══════════════════════════════════════════════════════════════════════

@app.route('/ceo/site-settings', methods=['POST'])
@ceo_required
def ceo_site_settings():
    conn = get_db()
    c = conn.cursor()
    c.execute('''UPDATE site_settings SET
        hero_tagline=%s, hero_subtext=%s, agency_bio=%s,
        contact_email=%s, contact_phone=%s, contact_whatsapp=%s,
        payoneer_email=%s, payoneer_account_name=%s, payment_instructions=%s
        WHERE id=1''',
        (request.form.get('hero_tagline'), request.form.get('hero_subtext'), request.form.get('agency_bio'),
         request.form.get('contact_email'), request.form.get('contact_phone'), request.form.get('contact_whatsapp'),
         request.form.get('payoneer_email'), request.form.get('payoneer_account_name'),
         request.form.get('payment_instructions')))
    conn.commit()
    conn.close()
    flash('Settings updated.')
    return redirect(url_for('ceo_dashboard'))


@app.route('/ceo/project/<int:project_id>/mark-phase-paid/<int:phase_number>', methods=['POST'])
@ceo_required
def mark_phase_paid(project_id, phase_number):
    conn = get_db()
    c = conn.cursor()
    c.execute('''UPDATE project_payments SET is_paid=TRUE, paid_at=NOW()
                 WHERE project_id=%s AND phase_number=%s''', (project_id, phase_number))
    conn.commit()
    conn.close()
    flash('Payment marked as received.')
    return redirect(url_for('ceo_dashboard'))


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
    return redirect(url_for('ceo_dashboard'))


# ═══════════════════════════════════════════════════════════════════════
# ADDED — PORTFOLIO & TEAM: CEO management + public pages
# ═══════════════════════════════════════════════════════════════════════

# ─── CEO: PORTFOLIO ─────────────────────────────────────
@app.route('/ceo/portfolio')
@ceo_required
def ceo_portfolio_list():
    conn, c = get_dict_db()
    c.execute("SELECT * FROM portfolio_projects ORDER BY display_order")
    projects = c.fetchall()
    conn.close()
    return render_template('ceo_portfolio.html', projects=projects)


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


# ─── CEO: TEAM (dedicated pages — separate from the quick-add form
#     already on your CEO dashboard; both write to the same table) ──────
@app.route('/ceo/team')
@ceo_required
def ceo_team_list():
    conn, c = get_dict_db()
    c.execute("SELECT * FROM team_members ORDER BY display_order")
    members = c.fetchall()
    conn.close()
    return render_template('ceo_team.html', members=members)


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
        flash('Team member added (unpublished). Publish from the team list when ready.')
        return redirect(url_for('ceo_team_list'))

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
        return redirect(url_for('ceo_team_list'))

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
        return redirect(url_for('ceo_team_list'))

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
    return redirect(url_for('ceo_team_list'))


@app.route('/ceo/team/<int:member_id>/delete', methods=['POST'])
@ceo_required
def ceo_team_remove(member_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("DELETE FROM team_members WHERE id=%s", (member_id,))
    conn.commit()
    conn.close()
    flash('Team member removed.')
    return redirect(url_for('ceo_team_list'))


# ─── CEO: SITE-WIDE VISIBILITY TOGGLES ──────────────────
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
    return redirect(request.referrer or url_for('ceo_team_list'))


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


# ─── RUN ────────────────────────────────────────────────
init_db()

if __name__ == '__main__':
    app.run(debug=True)
