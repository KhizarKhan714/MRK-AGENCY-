from flask import Flask, render_template, request, redirect, url_for, session
import sqlite3
import bcrypt

app = Flask(__name__)
app.secret_key = 'mrksecretkey'
DB = 'mrk.db'

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/register', methods=['GET','POST'])
def register():
    if request.method == 'POST':
        fn = request.form['first_name']
        ln = request.form['last_name']
        email = request.form['email']
        pw = bcrypt.hashpw(request.form['password'].encode(), bcrypt.gensalt())
        conn = sqlite3.connect(DB)
        c = conn.cursor()
        c.execute('INSERT INTO customers (first_name,last_name,email,password) VALUES (?,?,?,?)',(fn,ln,email,pw))
        conn.commit()
        conn.close()
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/login', methods=['GET','POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        pw = request.form['password'].encode()
        conn = sqlite3.connect(DB)
        c = conn.cursor()
        c.execute('SELECT * FROM customers WHERE email=?',(email,))
        user = c.fetchone()
        conn.close()
        if user and bcrypt.checkpw(pw, user[4]):
            session['customer_id'] = user[0]
            session['customer_name'] = user[1]
            return redirect(url_for('dashboard'))
        return render_template('login.html', error='Invalid email or password')
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
        conn = sqlite3.connect(DB)
        c = conn.cursor()
        c.execute('INSERT INTO projects (customer_id,title,description,website_type,budget,deadline,package) VALUES (?,?,?,?,?,?,?)',(session['customer_id'],request.form['title'],request.form['description'],request.form['website_type'],request.form['budget'],request.form['deadline'],request.form['package']))
        conn.commit()
        conn.close()
        return redirect(url_for('dashboard'))
    return render_template('submit_project.html')

@app.route('/contractor-apply', methods=['GET','POST'])
def contractor_apply():
    if request.method == 'POST':
        pw = bcrypt.hashpw(request.form['password'].encode(), bcrypt.gensalt())
        conn = sqlite3.connect(DB)
        c = conn.cursor()
        c.execute('INSERT INTO contractors (name,password,expertise,experience,note,status) VALUES (?,?,?,?,?,?)',(request.form['name'],pw,request.form['expertise'],request.form['experience'],request.form['note'],'pending'))
        conn.commit()
        conn.close()
        return render_template('contractor_apply.html', success='Application submitted!')
    return render_template('contractor_apply.html')

@app.route('/contractor-login', methods=['GET','POST'])
def contractor_login():
    if request.method == 'POST':
        cin = request.form['cin']
        pw = request.form['password'].encode()
        conn = sqlite3.connect(DB)
        c = conn.cursor()
        c.execute('SELECT * FROM contractors WHERE cin=?',(cin,))
        contractor = c.fetchone()
        conn.close()
        if contractor and bcrypt.checkpw(pw, contractor[2]):
            session['contractor_id'] = contractor[0]
            session['contractor_name'] = contractor[1]
            return redirect(url_for('contractor_dashboard'))
        return render_template('contractor_login.html', error='Invalid CIN or password')
    return render_template('contractor_login.html')

@app.route('/contractor-dashboard')
def contractor_dashboard():
    if 'contractor_id' not in session:
        return redirect(url_for('contractor_login'))
    return render_template('contractor_dashboard.html', name=session['contractor_name'])

@app.route('/mrkceokhan7')
def ceo_portal():
    return render_template('ceo_login.html')

@app.route('/ceo-login', methods=['POST'])
def ceo_login():
    name = request.form['name']
    pw = request.form['password']
    sk = request.form['secret_key']
    sa = request.form['security_answer']
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute('SELECT * FROM ceo WHERE name=? AND password=? AND secret_key=? AND security_answer=?',(name,pw,sk,sa))
    ceo = c.fetchone()
    conn.close()
    if ceo:
        session['ceo'] = True
        return redirect(url_for('ceo_dashboard'))
    return render_template('ceo_login.html', error='Invalid credentials')

@app.route('/ceo-dashboard')
def ceo_dashboard():
    if not session.get('ceo'):
        return redirect(url_for('ceo_portal'))
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute('SELECT * FROM contractors WHERE status=?',('pending',))
    contractors = c.fetchall()
    c.execute('SELECT * FROM projects WHERE status=?',('pending',))
    projects = c.fetchall()
    conn.close()
    return render_template('ceo_dashboard.html', contractors=contractors, projects=projects)

@app.route('/approve-contractor/<int:id>')
def approve_contractor(id):
    if not session.get('ceo'):
        return redirect(url_for('ceo_portal'))
    import random
    cin = 'MRK' + str(random.randint(10000,99999))
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute('UPDATE contractors SET status=?, cin=? WHERE id=?',('approved',cin,id))
    conn.commit()
    conn.close()
    return redirect(url_for('ceo_dashboard'))

@app.route('/reject-contractor/<int:id>')
def reject_contractor(id):
    if not session.get('ceo'):
        return redirect(url_for('ceo_portal'))
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute('UPDATE contractors SET status=? WHERE id=?',('rejected',id))
    conn.commit()
    conn.close()
    return redirect(url_for('ceo_dashboard'))

@app.route('/approve-project/<int:id>')
def approve_project(id):
    if not session.get('ceo'):
        return redirect(url_for('ceo_portal'))
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute('UPDATE projects SET status=? WHERE id=?',('approved',id))
    conn.commit()
    conn.close()
    return redirect(url_for('ceo_dashboard'))

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('home'))

if __name__ == '__main__':
    app.run(debug=False, port=5000)
