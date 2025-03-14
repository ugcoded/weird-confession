from flask import Flask, request, render_template, session, redirect, url_for, flash
import sqlite3
from datetime import datetime, timedelta
import random

app = Flask(__name__)
app.secret_key = 'your-secret-key-here'  # Change this to a random string for security

ADMIN_USERNAME = 'admin'
ADMIN_PASSWORD = 'password123'

def init_db():
    conn = sqlite3.connect('confessions.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS confessions 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                  confession TEXT, 
                  name TEXT, 
                  date TEXT, 
                  likes INTEGER DEFAULT 0, 
                  rating_total REAL DEFAULT 0, 
                  rating_count INTEGER DEFAULT 0, 
                  category TEXT, 
                  tags TEXT, 
                  upvotes INTEGER DEFAULT 0, 
                  downvotes INTEGER DEFAULT 0, 
                  expiry_date TEXT NULL)''')
    c.execute('''CREATE TABLE IF NOT EXISTS comments 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                  confession_id INTEGER, 
                  comment TEXT, 
                  date TEXT, 
                  FOREIGN KEY (confession_id) REFERENCES confessions(id))''')
    c.execute('''CREATE TABLE IF NOT EXISTS traffic 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                  page TEXT, 
                  timestamp TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS pinned_content 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                  content_type TEXT, 
                  content_id INTEGER, 
                  custom_text TEXT, 
                  date TEXT, 
                  expiry_date TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS interactions 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                  ip_address TEXT, 
                  confession_id INTEGER, 
                  action TEXT,  -- 'like', 'upvote', 'downvote', 'rating'
                  value INTEGER DEFAULT 0,  -- For rating value, 0 for others
                  timestamp TEXT,
                  UNIQUE(ip_address, confession_id, action))''')
    for col, col_type in [
        ("category", "TEXT"),
        ("tags", "TEXT"),
        ("upvotes", "INTEGER DEFAULT 0"),
        ("downvotes", "INTEGER DEFAULT 0"),
        ("expiry_date", "TEXT NULL")
    ]:
        try:
            c.execute(f"ALTER TABLE confessions ADD COLUMN {col} {col_type}")
        except sqlite3.OperationalError:
            pass
    conn.commit()
    conn.close()

def admin_required(f):
    def wrap(*args, **kwargs):
        if 'admin_logged_in' not in session:
            flash('Please log in as admin first.', 'danger')
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    wrap.__name__ = f.__name__
    return wrap

def log_traffic(page):
    conn = sqlite3.connect('confessions.db')
    c = conn.cursor()
    c.execute("INSERT INTO traffic (page, timestamp) VALUES (?, ?)",
              (page, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit()
    conn.close()

def get_client_ip():
    if request.headers.getlist("X-Forwarded-For"):
        return request.headers.getlist("X-Forwarded-For")[0]
    return request.remote_addr

@app.route('/')
def index():
    return redirect(url_for('confessions'))

@app.route('/submit', methods=['GET', 'POST'])
def submit():
    log_traffic('submit')
    conn = sqlite3.connect('confessions.db')
    c = conn.cursor()
    if request.method == 'POST':
        confession = request.form['confession'].strip()
        name = request.form['name'].strip()
        category = request.form['category']
        tags = request.form['tags'].strip()
        if confession and name:
            c.execute("INSERT INTO confessions (confession, name, date, category, tags) VALUES (?, ?, ?, ?, ?)",
                      (confession, name, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), category, tags))
            conn.commit()
            flash('Confession submitted successfully!', 'success')
            return redirect(url_for('confessions'))
    conn.close()
    return render_template('submit.html')

@app.route('/confessions', methods=['GET', 'POST'])
def confessions():
    log_traffic('confessions')
    conn = sqlite3.connect('confessions.db')
    c = conn.cursor()
    client_ip = get_client_ip()

    if request.method == 'POST':
        confession_id = request.form['confession_id']
        action_performed = False

        if 'like' in request.form:
            c.execute("SELECT id FROM interactions WHERE ip_address = ? AND confession_id = ? AND action = ?",
                      (client_ip, confession_id, 'like'))
            if not c.fetchone():
                c.execute("UPDATE confessions SET likes = likes + 1 WHERE id = ?", (confession_id,))
                c.execute("INSERT INTO interactions (ip_address, confession_id, action, timestamp) VALUES (?, ?, ?, ?)",
                          (client_ip, confession_id, 'like', datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
                action_performed = True
            else:
                flash('You have already liked this confession.', 'warning')

        elif 'upvote' in request.form:
            c.execute("SELECT id FROM interactions WHERE ip_address = ? AND confession_id = ? AND action = ?",
                      (client_ip, confession_id, 'upvote'))
            if not c.fetchone():
                c.execute("SELECT id FROM interactions WHERE ip_address = ? AND confession_id = ? AND action = ?",
                          (client_ip, confession_id, 'downvote'))
                if not c.fetchone():
                    c.execute("UPDATE confessions SET upvotes = upvotes + 1 WHERE id = ?", (confession_id,))
                    c.execute("INSERT INTO interactions (ip_address, confession_id, action, timestamp) VALUES (?, ?, ?, ?)",
                              (client_ip, confession_id, 'upvote', datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
                    action_performed = True
                else:
                    flash('You have already downvoted this confession and cannot upvote it.', 'warning')
            else:
                flash('You have already upvoted this confession.', 'warning')

        elif 'downvote' in request.form:
            c.execute("SELECT id FROM interactions WHERE ip_address = ? AND confession_id = ? AND action = ?",
                      (client_ip, confession_id, 'downvote'))
            if not c.fetchone():
                c.execute("SELECT id FROM interactions WHERE ip_address = ? AND confession_id = ? AND action = ?",
                          (client_ip, confession_id, 'upvote'))
                if not c.fetchone():
                    c.execute("UPDATE confessions SET downvotes = downvotes + 1 WHERE id = ?", (confession_id,))
                    c.execute("INSERT INTO interactions (ip_address, confession_id, action, timestamp) VALUES (?, ?, ?, ?)",
                              (client_ip, confession_id, 'downvote', datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
                    action_performed = True
                else:
                    flash('You have already upvoted this confession and cannot downvote it.', 'warning')
            else:
                flash('You have already downvoted this confession.', 'warning')

        elif 'rating' in request.form:
            c.execute("SELECT id FROM interactions WHERE ip_address = ? AND confession_id = ? AND action = ?",
                      (client_ip, confession_id, 'rating'))
            if not c.fetchone():
                rating = int(request.form['rating'])
                c.execute("UPDATE confessions SET rating_total = rating_total + ?, rating_count = rating_count + 1 WHERE id = ?",
                          (rating, confession_id))
                c.execute("INSERT INTO interactions (ip_address, confession_id, action, value, timestamp) VALUES (?, ?, ?, ?, ?)",
                          (client_ip, confession_id, 'rating', rating, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
                action_performed = True
            else:
                flash('You have already rated this confession.', 'warning')

        elif 'comment' in request.form:
            comment = request.form['comment'].strip()
            if comment:
                c.execute("INSERT INTO comments (confession_id, comment, date) VALUES (?, ?, ?)",
                          (confession_id, comment, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
                action_performed = True

        if action_performed:
            conn.commit()

    pinned_content = None
    pinned_name = None
    c.execute("SELECT content_type, content_id, custom_text, expiry_date FROM pinned_content ORDER BY date DESC LIMIT 1")
    pinned = c.fetchone()
    if pinned and pinned[3]:
        expiry_date = datetime.strptime(pinned[3], "%Y-%m-%d %H:%M:%S")
        if expiry_date > datetime.now():
            if pinned[0] == 'confession' and pinned[1]:
                c.execute("SELECT confession, name FROM confessions WHERE id = ?", (pinned[1],))
                result = c.fetchone()
                if result:
                    pinned_content, pinned_name = result
            elif pinned[0] == 'post':
                pinned_content = pinned[2]
                pinned_name = "Admin"

    c.execute("SELECT id, confession, name, date, likes, rating_total, rating_count, category, tags, upvotes, downvotes, expiry_date FROM confessions WHERE expiry_date IS NULL OR expiry_date > ? ORDER BY date DESC",
              (datetime.now().strftime("%Y-%m-%d %H:%M:%S"),))
    confessions_list = c.fetchall()
    confessions_with_data = []
    for conf in confessions_list:
        c.execute("SELECT comment, date FROM comments WHERE confession_id = ? ORDER BY date ASC", (conf[0],))
        comments = c.fetchall()
        comment_count = len(comments)
        avg_rating = (conf[5] / conf[6]) if conf[6] > 0 else 0
        score = conf[9] - conf[10]
        c.execute("SELECT action FROM interactions WHERE ip_address = ? AND confession_id = ?", (client_ip, conf[0]))
        interactions = {row[0] for row in c.fetchall()}
        confessions_with_data.append((conf, comments, avg_rating, comment_count, score, interactions))

    conn.close()
    dark_mode = request.cookies.get('dark_mode', 'off') == 'on'
    return render_template('confessions.html', confessions=confessions_with_data, pinned_content=pinned_content,
                          pinned_name=pinned_name, dark_mode=dark_mode)

@app.route('/random')
def random_confession():
    conn = sqlite3.connect('confessions.db')
    c = conn.cursor()
    c.execute("SELECT id FROM confessions WHERE expiry_date IS NULL OR expiry_date > ?",
              (datetime.now().strftime("%Y-%m-%d %H:%M:%S"),))
    ids = c.fetchall()
    if ids:
        random_id = random.choice(ids)[0]
        return redirect(url_for('confessions') + f'?highlight={random_id}')
    return redirect(url_for('confessions'))

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    log_traffic('admin_login')
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            session['admin_logged_in'] = True
            flash('Logged in successfully!', 'success')
            return redirect(url_for('admin_dashboard'))
        else:
            flash('Invalid credentials.', 'danger')
    return render_template('admin_login.html')

@app.route('/admin/logout')
def admin_logout():
    session.pop('admin_logged_in', None)
    flash('Logged out successfully.', 'success')
    return redirect(url_for('confessions'))

@app.route('/admin/dashboard', methods=['GET', 'POST'])
@admin_required
def admin_dashboard():
    conn = sqlite3.connect('confessions.db')
    c = conn.cursor()

    if request.method == 'POST':
        if 'delete_confession' in request.form:
            confession_id = request.form['confession_id']
            c.execute("DELETE FROM confessions WHERE id = ?", (confession_id,))
            c.execute("DELETE FROM comments WHERE confession_id = ?", (confession_id,))
            c.execute("DELETE FROM interactions WHERE confession_id = ?", (confession_id,))
            conn.commit()
            flash('Confession deleted.', 'success')
        elif 'delete_comment' in request.form:
            comment_id = request.form['comment_id']
            c.execute("DELETE FROM comments WHERE id = ?", (comment_id,))
            conn.commit()
            flash('Comment deleted.', 'success')
        elif 'pin_confession' in request.form:
            confession_id = request.form['confession_id']
            days = int(request.form['pin_days'])
            expiry_date = datetime.now() + timedelta(days=days)
            c.execute("DELETE FROM pinned_content")
            c.execute("INSERT INTO pinned_content (content_type, content_id, date, expiry_date) VALUES (?, ?, ?, ?)",
                      ('confession', confession_id, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), expiry_date.strftime("%Y-%m-%d %H:%M:%S")))
            conn.commit()
            flash(f'Confession pinned for {days} days.', 'success')
        elif 'pin_post' in request.form:
            custom_text = request.form['custom_text'].strip()
            days = int(request.form['pin_days'])
            if custom_text:
                expiry_date = datetime.now() + timedelta(days=days)
                c.execute("DELETE FROM pinned_content")
                c.execute("INSERT INTO pinned_content (content_type, custom_text, date, expiry_date) VALUES (?, ?, ?, ?)",
                          ('post', custom_text, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), expiry_date.strftime("%Y-%m-%d %H:%M:%S")))
                conn.commit()
                flash(f'Custom post pinned for {days} days.', 'success')
        elif 'delete_pin' in request.form:
            c.execute("DELETE FROM pinned_content")
            conn.commit()
            flash('Pinned content removed.', 'success')
        elif 'set_expiry' in request.form:
            confession_id = request.form['confession_id']
            days = int(request.form['expiry_days'])
            if days > 0:
                expiry_date = datetime.now() + timedelta(days=days)
                c.execute("UPDATE confessions SET expiry_date = ? WHERE id = ?",
                          (expiry_date.strftime("%Y-%m-%d %H:%M:%S"), confession_id))
                flash(f'Confession set to expire in {days} days.', 'success')
            else:
                c.execute("UPDATE confessions SET expiry_date = NULL WHERE id = ?", (confession_id,))
                flash('Expiry removed from confession.', 'success')
            conn.commit()

    c.execute("SELECT id, confession, name, date, likes, rating_total, rating_count, expiry_date FROM confessions ORDER BY date DESC")
    confessions_list = c.fetchall()
    confessions_with_comments = []
    for conf in confessions_list:
        c.execute("SELECT id, comment, date FROM comments WHERE confession_id = ? ORDER BY date ASC", (conf[0],))
        comments = c.fetchall()
        avg_rating = (conf[5] / conf[6]) if conf[6] > 0 else 0
        confessions_with_comments.append((conf, comments, avg_rating))

    c.execute("SELECT id, confession, name, likes FROM confessions ORDER BY likes DESC LIMIT 1")
    most_liked = c.fetchone()
    c.execute("SELECT c.id, c.confession, c.name, COUNT(com.id) as comment_count FROM confessions c LEFT JOIN comments com ON c.id = com.confession_id GROUP BY c.id, c.confession, c.name ORDER BY comment_count DESC LIMIT 1")
    most_commented = c.fetchone()
    c.execute("SELECT COUNT(*) FROM traffic")
    total_visits = c.fetchone()[0]

    conn.close()
    return render_template('admin_dashboard.html', confessions=confessions_with_comments, most_liked=most_liked,
                          most_commented=most_commented, total_visits=total_visits)

if __name__ == '__main__':
    init_db()
    app.run(debug=True)