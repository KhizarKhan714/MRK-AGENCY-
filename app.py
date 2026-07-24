from flask import Flask, render_template, request, redirect, url_for, session
import psycopg2
import bcrypt
import os
import base64
import random

app = Flask(__name__)
app.secret_key = 'mrk_ultra_secure_2026_khizar'
DATABASE_URL = os.environ.get('DATABASE_URL', '').replace('postgres://', 'postgresql://')

def get_db():
    conn = psycopg2.connect(DATABASE_URL)
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()

    # CUSTOMERS
    c.execute('''CREATE TABLE IF NOT EXISTS customers (
        id SERIAL PRIMARY KEY,
        first_name TEXT, last_name TEXT,
        email TEXT UNIQUE, password TEXT,
        photo TEXT,
        suspended BOOLEAN DEFAULT FALSE)''')
    try:
        c.execute('ALTER TABLE customers ADD COLUMN IF NOT EXISTS photo TEXT')
    except: conn.rollback()
    try:
        c.execute('ALTER TABLE customers ADD COLUMN IF NOT EXISTS suspended BOOLEAN DEFAULT FALSE')
    except: conn.rollback()

    # CONTRACTORS
    c.execute('''CREATE TABLE IF NOT EXISTS contractors (
        id SERIAL PRIMARY KEY,
        name TEXT, password TEXT, expertise TEXT,
        experience TEXT, note TEXT, cin TEXT,
        status TEXT DEFAULT 'pending',
        email TEXT, phone TEXT, whatsapp TEXT,
        cnic TEXT, cnic_image TEXT, cv TEXT,
        specialties TEXT, suspended BOOLEAN DEFAULT FALSE)''')
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

    # PROJECTS
    c.execute('''CREATE TABLE IF NOT EXISTS projects (
        id SERIAL PRIMARY KEY,
        customer_id INTEGER, title TEXT, description TEXT,
        website_type TEXT, budget TEXT, deadline TEXT,
        package TEXT, status TEXT DEFAULT 'pending',
        assigned_contractor_id INTEGER,
        contractor_pay TEXT,
        accepted_by INTEGER)''')
    try:
        c.execute('ALTER TABLE projects ADD COLUMN IF NOT EXISTS contractor_pay TEXT')
    except: conn.rollback()
    try:
        c.execute('ALTER TABLE projects ADD COLUMN IF NOT EXISTS accepted_by INTEGER')
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

    conn.commit()
    conn.close()


# ─── HOME ───────────────────────────────────────────────
@app.route('/')
def home():
    return render_template('index.html')


# ─── CUSTOMER AUTH ──────────────────────────────────────
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        try:
            fn = request.form['first_name'].strip()
            ln = request.form['last_name'].strip()
            email = request.form['email'].strip()
            pw = bcrypt.hashpw(request.form['password'].encode(), bcrypt.gensalt())
            conn = get_db()
            c = conn.cursor()
            c.execute('INSERT INTO customers (first_name,last_name,email,password) VALUES (%s,%s,%s,%s)',
                      (fn, ln, email, pw.decode()))
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
    c.execute('SELECT id, first_name, last_name, email, photo FROM customers WHERE id=%s', (session['customer_id'],))
    row = c.fetchone()
    conn.close()
    customer = {'id': row[0], 'first_name': row[1], 'last_name': row[2], 'email': row[3], 'photo': row[4]}
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
            conn = get_db()
            c = conn.cursor()
            c.execute('''INSERT INTO projects
                (customer_id,title,description,website_type,budget,deadline,package)
                VALUES (%s,%s,%s,%s,%s,%s,%s)''',
                (session['customer_id'],
                 request.form['title'],
                 request.form['description'],
                 request.form['website_type'],
                 request.form.get('budget', '0'),
                 request.form['deadline'],
                 request.form['package']))
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


# ─── CONTRACTOR APPLY ───────────────────────────────────
@app.route('/contractor-apply', methods=['GET', 'POST'])
def contractor_apply():
    if request.method == 'POST':
        try:
            pw = bcrypt.hashpw(request.form['password'].encode(), bcrypt.gensalt())

            # Handle file uploads
            cv_data = None
            cv_file = request.files.get('cv')
            if cv_file and cv_file.filename:
                cv_bytes = cv_file.read()
                cv_b64 = base64.b64encode(cv_bytes).decode()
                cv_data = f'data:{cv_file.content_type};base64,{cv_b64}'

            cnic_img_data = None
            cnic_img = request.files.get('cnic_image')
            if cnic_img and cnic_img.filename:
                cnic_bytes = cnic_img.read()
                cnic_b64 = base64.b64encode(cnic_bytes).decode()
                cnic_img_data = f'data:{cnic_img.content_type};base64,{cnic_b64}'

            conn = get_db()
            c = conn.cursor()
            c.execute('''INSERT INTO contractors
                (name, password, expertise, experience, note, status,
                 email, phone, whatsapp, cnic, cnic_image, cv, specialties)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)''',
                (request.form['name'].strip(),
                 pw.decode(),
                 request.form['expertise'],
                 request.form['experience'],
                 request.form['note'].strip(),
                 'pending',
                 request.form['email'].strip(),
                 request.form['phone'].strip(),
                 request.form['whatsapp'].strip(),
                 request.form['cnic'].strip(),
                 cnic_img_data,
                 cv_data,
                 request.form['specialties'].strip()))
            conn.commit()
            conn.close()
            return render_template('contractor_apply.html',
                success='Application submitted successfully. The CEO will review your application.')
        except Exception as e:
            return render_template('contractor_apply.html', error=str(e))
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


# ─── CONTRACTOR DASHBOARD ───────────────────────────────
@app.route('/contractor-dashboard')
def contractor_dashboard():
    if 'contractor_id' not in session:
        return redirect(url_for('contractor_login'))
    conn = get_db()
    c = conn.cursor()
    # Get contractor profile
    c.execute('SELECT * FROM contractors WHERE id=%s', (session['contractor_id'],))
    contractor = c.fetchone()
    # Get all CEO-approved projects with contractor pay set
    c.execute("""SELECT * FROM projects
                 WHERE status='approved' AND contractor_pay IS NOT NULL
                 AND (accepted_by IS NULL OR accepted_by=%s)""",
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
    c.execute("SELECT * FROM projects WHERE status='approved' AND contractor_pay IS NOT NULL AND (accepted_by IS NULL OR accepted_by=%s)",
              (session['contractor_id'],))
    projects = c.fetchall()
    if not bcrypt.checkpw(current_pw, contractor[2].encode()):
        conn.close()
        return render_template('contractor_dashboard.html', contractor=contractor, projects=projects, error='Current password is incorrect.')
    if new_pw != confirm_pw:
        conn.close()
        return render_template('contractor_dashboard.html', contractor=contractor, projects=projects, error='New passwords do not match.')
    if len(new_pw) < 6:
        conn.close()
        return render_template('contractor_dashboard.html', contractor=contractor, projects=projects, error='Password must be at least 6 characters.')
    hashed = bcrypt.hashpw(new_pw.encode(), bcrypt.gensalt()).decode()
    c.execute('UPDATE contractors SET password=%s WHERE id=%s', (hashed, session['contractor_id']))
    conn.commit()
    conn.close()
    return render_template('contractor_dashboard.html', contractor=contractor, projects=projects, success='Password changed successfully.')


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


# ─── CEO DASHBOARD ──────────────────────────────────────
@app.route('/ceo-dashboard')
def ceo_dashboard():
    if not session.get('ceo'):
        return redirect(url_for('ceo_portal'))
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM contractors WHERE status='pending'")
    pending_contractors = c.fetchall()
    c.execute("SELECT * FROM contractors WHERE status='approved'")
    approved_contractors = c.fetchall()
    c.execute("SELECT * FROM contractors WHERE status='rejected' OR suspended=TRUE")
    rejected_contractors = c.fetchall()
    c.execute("SELECT * FROM projects WHERE status='pending'")
    pending_projects = c.fetchall()
    c.execute("SELECT * FROM projects WHERE status='approved'")
    approved_projects = c.fetchall()
    c.execute("SELECT * FROM customers")
    customers = c.fetchall()
    conn.close()
    return render_template('ceo_dashboard.html',
        pending_contractors=pending_contractors,
        approved_contractors=approved_contractors,
        rejected_contractors=rejected_contractors,
        pending_projects=pending_projects,
        approved_projects=approved_projects,
        customers=customers)


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
    c.execute("UPDATE contractors SET suspended=TRUE, cin=NULL WHERE id=%s", (id,)
