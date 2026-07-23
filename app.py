import base64

@app.route('/profile')
def profile():
    if 'customer_id' not in session:
        return redirect(url_for('login'))
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT id, first_name, last_name, email, photo FROM customers WHERE id=%s', (session['customer_id'],))
    row = c.fetchone()
    conn.close()
    customer = {
        'id': row[0],
        'first_name': row[1],
        'last_name': row[2],
        'email': row[3],
        'photo': row[4]
    }
    return render_template('profile.html', customer=customer)

@app.route('/update-profile', methods=['POST'])
def update_profile():
    if 'customer_id' not in session:
        return redirect(url_for('login'))
    action = request.form.get('action')
    conn = get_db()
    c = conn.cursor()

    if action == 'update_info':
        fn = request.form['first_name'].strip()
        ln = request.form['last_name'].strip()
        email = request.form['email'].strip()
        try:
            c.execute('UPDATE customers SET first_name=%s, last_name=%s, email=%s WHERE id=%s',
                      (fn, ln, email, session['customer_id']))
            conn.commit()
            session['customer_name'] = fn
            c.execute('SELECT id, first_name, last_name, email, photo FROM customers WHERE id=%s', (session['customer_id'],))
            row = c.fetchone()
            customer = {'id': row[0], 'first_name': row[1], 'last_name': row[2], 'email': row[3], 'photo': row[4]}
            conn.close()
            return render_template('profile.html', customer=customer, success='Profile updated successfully.')
        except Exception as e:
            conn.close()
            c2 = get_db().cursor()
            c2.execute('SELECT id, first_name, last_name, email, photo FROM customers WHERE id=%s', (session['customer_id'],))
            row = c2.fetchone()
            customer = {'id': row[0], 'first_name': row[1], 'last_name': row[2], 'email': row[3], 'photo': row[4]}
            return render_template('profile.html', customer=customer, error='Email already in use.')

    elif action == 'change_password':
        current_pw = request.form['current_password'].encode()
        new_pw = request.form['new_password']
        confirm_pw = request.form['confirm_password']
        c.execute('SELECT password, first_name, last_name, email, photo FROM customers WHERE id=%s', (session['customer_id'],))
        row = c.fetchone()
        customer = {'id': session['customer_id'], 'first_name': row[1], 'last_name': row[2], 'email': row[3], 'photo': row[4]}
        if not bcrypt.checkpw(current_pw, row[0].encode()):
            conn.close()
            return render_template('profile.html', customer=customer, error='Current password is incorrect.')
        if new_pw != confirm_pw:
            conn.close()
            return render_template('profile.html', customer=customer, error='New passwords do not match.')
        if len(new_pw) < 6:
            conn.close()
            return render_template('profile.html', customer=customer, error='New password must be at least 6 characters.')
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
        c.execute('SELECT id, first_name, last_name, email, photo FROM customers WHERE id=%s', (session['customer_id'],))
        row = c.fetchone()
        customer = {'id': row[0], 'first_name': row[1], 'last_name': row[2], 'email': row[3], 'photo': row[4]}
        conn.close()
        return render_template('profile.html', customer=customer, success='Profile photo updated.')

    conn.close()
    return redirect(url_for('profile'))

from flask import Flask, render_template, request, redirect, url_for, session
import psycopg2
import bcrypt
import os

app = Flask(__name__)
app.secret_key = 'mrk_ultra_secure_2026_khizar'
DATABASE_URL = os.environ.get('DATABASE_URL', '').replace('postgres://', 'postgresql://')

def get_db():
    conn = psycopg2.connect(DATABASE_URL)
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS customers (
        id SERIAL PRIMARY KEY,
        first_name TEXT, last_name TEXT,
        email TEXT UNIQUE, password TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS contractors (
        id SERIAL PRIMARY KEY,
        name TEXT, password TEXT, expertise TEXT,
        experience TEXT, note TEXT, cin TEXT,
        status TEXT DEFAULT 'pending')''')
    c.execute('''CREATE TABLE IF NOT EXISTS projects (
        id SERIAL PRIMARY KEY,
        customer_id INTEGER, title TEXT, description TEXT,
        website_type TEXT, budget TEXT, deadline TEXT,
        package TEXT, status TEXT DEFAULT 'pending',
        assigned_contractor_id INTEGER)''')
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

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/register', methods=['GET','POST'])
def register():
    if request.method == 'POST':
        try:
            fn = request.form['first_name']
            ln = request.form['last_name']
            email = request.form['email']
            pw = bcrypt.hashpw(request.form['password'].encode(), bcrypt.gensalt())
            conn = get_db()
            c = conn.cursor()
            c.execute('INSERT INTO customers (first_name,last_name,email,password) VALUES (%s,%s,%s,%s)',
                      (fn, ln, email, pw.decode()))
            conn.commit()
            conn.close()
            return redirect(url_for('login'))
        except Exception as e:
            return render_template('register.html', error='Email already exists or invalid data.')
    return render_template('register.html')

@app.route('/login', methods=['GET','POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        pw = request.form['password'].encode()
        conn = get_db()
        c = conn.cursor()
        c.execute('SELECT * FROM customers WHERE email=%s', (email,))
        user = c.fetchone()
        conn.close()
        if user and bcrypt.checkpw(pw, user[4].encode()):
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

@app.route('/submit-project', methods=['GET','POST'])
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

@app.route('/contractor-apply', methods=['GET','POST'])
def contractor_apply():
    if request.method == 'POST':
        try:
            pw = bcrypt.hashpw(request.form['password'].encode(), bcrypt.gensalt())
            conn = get_db()
            c = conn.cursor()
            c.execute('''INSERT INTO contractors
                (name,password,expertise,experience,note,status)
                VALUES (%s,%s,%s,%s,%s,%s)''',
                (request.form['name'], pw.decode(),
                 request.form['expertise'],
                 request.form['experience'],
                 request.form['note'], 'pending'))
            conn.commit()
            conn.close()
            return render_template('contractor_apply.html',
                success='Application submitted! Wait for CEO approval.')
        except Exception as e:
            return render_template('contractor_apply.html', error=str(e))
    return render_template('contractor_apply.html')

@app.route('/contractor-login', methods=['GET','POST'])
def contractor_login():
    if request.method == 'POST':
        cin = request.form['cin']
        pw = request.form['password'].encode()
        conn = get_db()
        c = conn.cursor()
        c.execute('SELECT * FROM contractors WHERE cin=%s', (cin,))
        contractor = c.fetchone()
        conn.close()
        if contractor and bcrypt.checkpw(pw, contractor[2].encode()):
            session['contractor_id'] = contractor[0]
            session['contractor_name'] = contractor[1]
            return redirect(url_for('contractor_dashboard'))
        return render_template('contractor_login.html', error='Invalid CIN or password.')
    return render_template('contractor_login.html')

@app.route('/contractor-dashboard')
def contractor_dashboard():
    if 'contractor_id' not in session:
        return redirect(url_for('contractor_login'))
    return render_template('contractor_dashboard.html',
        name=session['contractor_name'])

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

@app.route('/ceo-dashboard')
def ceo_dashboard():
    if not session.get('ceo'):
        return redirect(url_for('ceo_portal'))
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM contractors WHERE status='pending'")
    contractors = c.fetchall()
    c.execute("SELECT * FROM projects WHERE status='pending'")
    projects = c.fetchall()
    conn.close()
    return render_template('ceo_dashboard.html',
        contractors=contractors, projects=projects)

@app.route('/approve-contractor/<int:id>')
def approve_contractor(id):
    if not session.get('ceo'):
        return redirect(url_for('ceo_portal'))
    import random
    cin = 'MRK' + str(random.randint(10000, 99999))
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE contractors SET status='approved', cin=%s WHERE id=%s",
              (cin, id))
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

@app.route('/approve-project/<int:id>')
def approve_project(id):
    if not session.get('ceo'):
        return redirect(url_for('ceo_portal'))
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE projects SET status='approved' WHERE id=%s", (id,))
    conn.commit()
    conn.close()
    return redirect(url_for('ceo_dashboard'))

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('home'))

init_db()

if __name__ == '__main__':
    app.run(debug=False, port=5000)
