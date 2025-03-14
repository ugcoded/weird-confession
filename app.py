import os
from flask import Flask, request, render_template, session, redirect, url_for, flash
import psycopg2
from psycopg2 import pool
from datetime import datetime, timedelta
import random

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'b500bf05b424886fb798ce1cb543c923')

# PostgreSQL connection pool
db_pool = None

def get_db_connection():
    global db_pool
    if db_pool is None:
        db_url = os.environ.get('DATABASE_URL')
        if not db_url:
            raise ValueError("DATABASE_URL environment variable not set")
        db_pool = psycopg2.pool.SimpleConnectionPool(1, 20, dsn=db_url, sslmode='require')
    return db_pool.getconn()

def release_db_connection(conn):
    db_pool.putconn(conn)

def init_db():
    try:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS confessions (
                     id SERIAL PRIMARY KEY, confession TEXT NOT NULL, name TEXT NOT NULL, date TEXT NOT NULL,
                     likes INTEGER DEFAULT 0, dislikes INTEGER DEFAULT 0, rating_total REAL DEFAULT 0, rating_count INTEGER DEFAULT 0,
                     category TEXT, tags TEXT, upvotes INTEGER DEFAULT 0, downvotes INTEGER DEFAULT 0, expiry_date TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS comments (
                     id SERIAL PRIMARY KEY, confession_id INTEGER, comment TEXT NOT NULL, date TEXT NOT NULL,
                     FOREIGN KEY (confession_id) REFERENCES confessions(id) ON DELETE CASCADE)''')
        c.execute('''CREATE TABLE IF NOT EXISTS traffic (
                     id SERIAL PRIMARY KEY, page TEXT NOT NULL, timestamp TEXT NOT NULL)''')
        c.execute('''CREATE TABLE IF NOT EXISTS pinned_content (
                     id SERIAL PRIMARY KEY, content_type TEXT NOT NULL, content_id INTEGER, custom_text TEXT,
                     date TEXT NOT NULL, expiry_date TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS interactions (
                     id SERIAL PRIMARY KEY, ip_address TEXT NOT NULL, confession_id INTEGER NOT NULL, action TEXT NOT NULL,
                     value INTEGER DEFAULT 0, timestamp TEXT NOT NULL, UNIQUE(ip_address, confession_id, action),
                     FOREIGN KEY (confession_id) REFERENCES confessions(id) ON DELETE CASCADE)''')
        conn.commit()
        print("Database schema initialized successfully.")
    except Exception as e:
        print(f"Error initializing database: {e}")
    finally:
        release_db_connection(conn)

init_db()

ADMIN_USERNAME = os.environ.get('ADMIN_USERNAME', 'admin')
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'password123')

def admin_required(f):
    def wrap(*args, **kwargs):
        if 'admin_logged_in' not in session:
            flash('Please log in as admin first.', 'danger')
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    wrap.__name__ = f.__name__
    return wrap

def log_traffic(page):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("INSERT INTO traffic (page, timestamp) VALUES (%s, %s)",
              (page, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit()
    release_db_connection(conn)

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
    conn = get_db_connection()
    c = conn.cursor()
    if request.method == 'POST':
        confession = request.form['confession'].strip()
        name = request.form['name'].strip()
        category = request.form['category']
        tags = request.form['tags'].strip()
        if confession and name:
            c.execute("INSERT INTO confessions (confession, name, date, category, tags) VALUES (%s, %s, %s, %s, %s)",
                      (confession, name, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), category, tags))
            conn.commit()
            flash('Confession submitted successfully!', 'success')
            release_db_connection(conn)
            return redirect(url_for('confessions'))
    release_db_connection(conn)
    return render_template('submit.html')

@app.route('/confessions', methods=['GET', 'POST'])
def confessions():
    log_traffic('confessions')
    conn = get_db_connection()
    c = conn.cursor()
    client_ip = get_client_ip()

    if request.method == 'POST':
        confession_id = request.form['confession_id']
        action_performed = False

        def has_interaction(action):
            c.execute("SELECT id FROM interactions WHERE ip_address = %s AND confession_id = %s AND action = %s",
                      (client_ip, confession_id, action))
            return c.fetchone() is not None

        if 'upvote' in request.form and not has_interaction('upvote'):
            if not has_interaction('downvote'):
                c.execute("UPDATE confessions SET upvotes = upvotes + 1 WHERE id = %s", (confession_id,))
                c.execute("INSERT INTO interactions (ip_address, confession_id, action, timestamp) VALUES (%s, %s, %s, %s)",
                          (client_ip, confession_id, 'upvote', datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
                action_performed = True
                flash('Upvoted successfully!', 'success')
            else:
                flash('You already downvoted this confession.', 'warning')
        elif 'downvote' in request.form and not has_interaction('downvote'):
            if not has_interaction('upvote'):
                c.execute("UPDATE confessions SET downvotes = downvotes + 1 WHERE id = %s", (confession_id,))
                c.execute("INSERT INTO interactions (ip_address, confession_id, action, timestamp) VALUES (%s, %s, %s, %s)",
                          (client_ip, confession_id, 'downvote', datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
                action_performed = True
                flash('Downvoted successfully!', 'success')
            else:
                flash('You already upvoted this confession.', 'warning')
        elif 'like' in request.form and not has_interaction('like'):
            if not has_interaction('dislike'):
                c.execute("UPDATE confessions SET likes = likes + 1 WHERE id = %s", (confession_id,))
                c.execute("INSERT INTO interactions (ip_address, confession_id, action, timestamp) VALUES (%s, %s, %s, %s)",
                          (client_ip, confession_id, 'like', datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
                action_performed = True
                flash('Liked successfully!', 'success')
            else:
                flash('You already disliked this confession.', 'warning')
        elif 'dislike' in request.form and not has_interaction('dislike'):
            if not has_interaction('like'):
                c.execute("UPDATE confessions SET dislikes = dislikes + 1 WHERE id = %s", (confession_id,))
                c.execute("INSERT INTO interactions (ip_address, confession_id, action, timestamp) VALUES (%s, %s, %s, %s)",
                          (client_ip, confession_id, 'dislike', datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
                action_performed = True
                flash('Disliked successfully!', 'success')
            else:
                flash('You already liked this confession.', 'warning')
        elif 'rating' in request.form and not has_interaction('rating'):
            rating = int(request.form['rating'])
            c.execute("UPDATE confessions SET rating_total = rating_total + %s, rating_count = rating_count + 1 WHERE id = %s",
                      (rating, confession_id))
            c.execute("INSERT INTO interactions (ip_address, confession_id, action, value, timestamp) VALUES (%s, %s, %s, %s, %s)",
                      (client_ip, confession_id, 'rating', rating, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
            action_performed = True
            flash('Rated successfully!', 'success')
        elif 'comment' in request.form:
            comment = request.form['comment'].strip()
            if comment:
                c.execute("INSERT INTO comments (confession_id, comment, date) VALUES (%s, %s, %s)",
                          (confession_id, comment, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
                if not has_interaction('comment'):
                    c.execute("INSERT INTO interactions (ip_address, confession_id, action, timestamp) VALUES (%s, %s, %s, %s)",
                              (client_ip, confession_id, 'comment', datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
                action_performed = True
                flash('Comment added successfully!', 'success')

        if action_performed:
            conn.commit()
        release_db_connection(conn)
        return redirect(url_for('confessions'))

    pinned_content = None
    pinned_name = None
    c.execute("SELECT content_type, content_id, custom_text, expiry_date FROM pinned_content ORDER BY date DESC LIMIT 1")
    pinned = c.fetchone()
    if pinned and pinned[3]:
        expiry_date = datetime.strptime(pinned[3], "%Y-%m-%d %H:%M:%S")
        if expiry_date > datetime.now():
            if pinned[0] == 'confession' and pinned[1]:
                c.execute("SELECT confession, name FROM confessions WHERE id = %s", (pinned[1],))
                result = c.fetchone()
                if result:
                    pinned_content, pinned_name = result
            elif pinned[0] == 'post':
                pinned_content = pinned[2]
                pinned_name = "Admin"

    c.execute("SELECT id, confession, name, date, likes, dislikes, rating_total, rating_count, category, tags, upvotes, downvotes, expiry_date FROM confessions WHERE expiry_date IS NULL OR expiry_date > %s ORDER BY date DESC",
              (datetime.now().strftime("%Y-%m-%d %H:%M:%S"),))
    confessions_list = c.fetchall()
    confessions_with_data = []
    for conf in confessions_list:
        c.execute("SELECT comment, date FROM comments WHERE confession_id = %s ORDER BY date ASC", (conf[0],))
        comments = c.fetchall()
        comment_count = len(comments)
        avg_rating = (conf[6] / conf[7]) if conf[7] > 0 else 0  # Updated indices for rating_total and rating_count
        score = conf[10] - conf[11]  # Updated indices for upvotes and downvotes
        c.execute("SELECT action FROM interactions WHERE ip_address = %s AND confession_id = %s", (client_ip, conf[0]))
        interactions = {row[0] for row in c.fetchall()}
        confessions_with_data.append((conf, comments, avg_rating, comment_count, score, interactions))

    release_db_connection(conn)
    dark_mode = request.cookies.get('dark_mode', 'off') == 'on'
    return render_template('confessions.html', confessions=confessions_with_data, pinned_content=pinned_content, 
                          pinned_name=pinned_name, dark_mode=dark_mode)

@app.route('/random')
def random_confession():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT id FROM confessions WHERE expiry_date IS NULL OR expiry_date > %s",
              (datetime.now().strftime("%Y-%m-%d %H:%M:%S"),))
    ids = c.fetchall()
    release_db_connection(conn)
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
    flash('Logged out successfully!', 'success')
    return redirect(url_for('confessions'))

@app.route('/admin/dashboard', methods=['GET', 'POST'])
@admin_required
def admin_dashboard():
    conn = get_db_connection()
    c = conn.cursor()

    if request.method == 'POST':
        if 'delete_confession' in request.form:
            confession_id = request.form['confession_id']
            c.execute("DELETE FROM confessions WHERE id = %s", (confession_id,))
            conn.commit()
            flash('Confession deleted.', 'success')
        elif 'delete_comment' in request.form:
            comment_id = request.form['comment_id']
            c.execute("DELETE FROM comments WHERE id = %s", (comment_id,))
            conn.commit()
            flash('Comment deleted.', 'success')
        elif 'pin_confession' in request.form:
            confession_id = request.form['confession_id']
            days = int(request.form['pin_days'])
            expiry_date = datetime.now() + timedelta(days=days)
            c.execute("DELETE FROM pinned_content")
            c.execute("INSERT INTO pinned_content (content_type, content_id, date, expiry_date) VALUES (%s, %s, %s, %s)",
                      ('confession', confession_id, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), expiry_date.strftime("%Y-%m-%d %H:%M:%S")))
            conn.commit()
            flash(f'Confession pinned for {days} days.', 'success')
        elif 'pin_post' in request.form:
            custom_text = request.form['custom_text'].strip()
            days = int(request.form['pin_days'])
            if custom_text:
                expiry_date = datetime.now() + timedelta(days=days)
                c.execute("DELETE FROM pinned_content")
                c.execute("INSERT INTO pinned_content (content_type, custom_text, date, expiry_date) VALUES (%s, %s, %s, %s)",
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
                c.execute("UPDATE confessions SET expiry_date = %s WHERE id = %s",
                          (expiry_date.strftime("%Y-%m-%d %H:%M:%S"), confession_id))
                flash(f'Confession set to expire in {days} days.', 'success')
            else:
                c.execute("UPDATE confessions SET expiry_date = NULL WHERE id = %s", (confession_id,))
                flash('Expiry removed from confession.', 'success')
            conn.commit()

    c.execute("SELECT id, confession, name, date, likes, dislikes, rating_total, rating_count, expiry_date FROM confessions ORDER BY date DESC")
    confessions_list = c.fetchall()
    confessions_with_comments = []
    for conf in confessions_list:
        c.execute("SELECT id, comment, date FROM comments WHERE confession_id = %s ORDER BY date ASC", (conf[0],))
        comments = c.fetchall()
        avg_rating = (conf[6] / conf[7]) if conf[7] > 0 else 0
        confessions_with_comments.append((conf, comments, avg_rating))

    c.execute("SELECT id, confession, name, likes FROM confessions ORDER BY likes DESC LIMIT 1")
    most_liked = c.fetchone()
    c.execute("SELECT c.id, c.confession, c.name, COUNT(com.id) as comment_count FROM confessions c LEFT JOIN comments com ON c.id = com.confession_id GROUP BY c.id, c.confession, c.name ORDER BY comment_count DESC LIMIT 1")
    most_commented = c.fetchone()
    c.execute("SELECT COUNT(*) FROM traffic")
    total_visits = c.fetchone()[0]

    release_db_connection(conn)
    return render_template('admin_dashboard.html', confessions=confessions_with_comments, most_liked=most_liked,
                          most_commented=most_commented, total_visits=total_visits)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
