import os
from flask import Flask, request, render_template, session, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from datetime import datetime, timedelta
import random

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'your-secret-key-here')

# SQLAlchemy configuration
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)
migrate = Migrate(app, db)

# Models
class Confession(db.Model):
    __tablename__ = 'confessions'
    id = db.Column(db.Integer, primary_key=True)
    confession = db.Column(db.Text, nullable=False)
    name = db.Column(db.Text, nullable=False)
    date = db.Column(db.String(20), nullable=False)
    likes = db.Column(db.Integer, default=0)
    dislikes = db.Column(db.Integer, default=0)
    rating_total = db.Column(db.Float, default=0)
    rating_count = db.Column(db.Integer, default=0)
    category = db.Column(db.Text)
    tags = db.Column(db.Text)
    upvotes = db.Column(db.Integer, default=0)
    downvotes = db.Column(db.Integer, default=0)
    expiry_date = db.Column(db.String(20))

class Comment(db.Model):
    __tablename__ = 'comments'
    id = db.Column(db.Integer, primary_key=True)
    confession_id = db.Column(db.Integer, db.ForeignKey('confessions.id', ondelete='CASCADE'), nullable=False)
    comment = db.Column(db.Text, nullable=False)
    date = db.Column(db.String(20), nullable=False)

class Traffic(db.Model):
    __tablename__ = 'traffic'
    id = db.Column(db.Integer, primary_key=True)
    page = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.String(20), nullable=False)

class PinnedContent(db.Model):
    __tablename__ = 'pinned_content'
    id = db.Column(db.Integer, primary_key=True)
    content_type = db.Column(db.Text, nullable=False)
    content_id = db.Column(db.Integer)
    custom_text = db.Column(db.Text)
    date = db.Column(db.String(20), nullable=False)
    expiry_date = db.Column(db.String(20))

class Interaction(db.Model):
    __tablename__ = 'interactions'
    id = db.Column(db.Integer, primary_key=True)
    ip_address = db.Column(db.Text, nullable=False)
    confession_id = db.Column(db.Integer, db.ForeignKey('confessions.id', ondelete='CASCADE'), nullable=False)
    action = db.Column(db.Text, nullable=False)
    value = db.Column(db.Integer, default=0)
    timestamp = db.Column(db.String(20), nullable=False)
    __table_args__ = (db.UniqueConstraint('ip_address', 'confession_id', 'action', name='unique_interaction'),)

# Admin credentials
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
    traffic = Traffic(page=page, timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    db.session.add(traffic)
    db.session.commit()

def get_client_ip():
    return request.headers.getlist("X-Forwarded-For")[0] if request.headers.getlist("X-Forwarded-For") else request.remote_addr

@app.route('/')
def index():
    return redirect(url_for('confessions'))

@app.route('/submit', methods=['GET', 'POST'])
def submit():
    log_traffic('submit')
    if request.method == 'POST':
        confession = request.form['confession'].strip()
        name = request.form['name'].strip()
        category = request.form['category']
        tags = request.form['tags'].strip()
        if confession and name:
            new_confession = Confession(
                confession=confession,
                name=name,
                date=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                category=category,
                tags=tags
            )
            db.session.add(new_confession)
            db.session.commit()
            flash('Confession submitted successfully!', 'success')
            return redirect(url_for('confessions'))
    return render_template('submit.html')

@app.route('/confessions', methods=['GET', 'POST'])
def confessions():
    log_traffic('confessions')
    client_ip = get_client_ip()

    if request.method == 'POST':
        confession_id = int(request.form['confession_id'])
        action_performed = False
        confession = Confession.query.get_or_404(confession_id)

        def has_interaction(action):
            return Interaction.query.filter_by(ip_address=client_ip, confession_id=confession_id, action=action).first() is not None

        if 'upvote' in request.form and not has_interaction('upvote'):
            if not has_interaction('downvote'):
                confession.upvotes += 1
                db.session.add(Interaction(ip_address=client_ip, confession_id=confession_id, action='upvote', timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
                action_performed = True
                flash('Upvoted successfully!', 'success')
            else:
                flash('You already downvoted this confession.', 'warning')
        elif 'downvote' in request.form and not has_interaction('downvote'):
            if not has_interaction('upvote'):
                confession.downvotes += 1
                db.session.add(Interaction(ip_address=client_ip, confession_id=confession_id, action='downvote', timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
                action_performed = True
                flash('Downvoted successfully!', 'success')
            else:
                flash('You already upvoted this confession.', 'warning')
        elif 'like' in request.form and not has_interaction('like'):
            if not has_interaction('dislike'):
                confession.likes += 1
                db.session.add(Interaction(ip_address=client_ip, confession_id=confession_id, action='like', timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
                action_performed = True
                flash('Liked successfully!', 'success')
            else:
                flash('You already disliked this confession.', 'warning')
        elif 'dislike' in request.form and not has_interaction('dislike'):
            if not has_interaction('like'):
                confession.dislikes += 1
                db.session.add(Interaction(ip_address=client_ip, confession_id=confession_id, action='dislike', timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
                action_performed = True
                flash('Disliked successfully!', 'success')
            else:
                flash('You already liked this confession.', 'warning')
        elif 'rating' in request.form and not has_interaction('rating'):
            rating = int(request.form['rating'])
            confession.rating_total += rating
            confession.rating_count += 1
            db.session.add(Interaction(ip_address=client_ip, confession_id=confession_id, action='rating', value=rating, timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
            action_performed = True
            flash('Rated successfully!', 'success')
        elif 'comment' in request.form:
            comment_text = request.form['comment'].strip()
            if comment_text:
                new_comment = Comment(confession_id=confession_id, comment=comment_text, date=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
                db.session.add(new_comment)
                if not has_interaction('comment'):
                    db.session.add(Interaction(ip_address=client_ip, confession_id=confession_id, action='comment', timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
                action_performed = True
                flash('Comment added successfully!', 'success')

        if action_performed:
            db.session.commit()
        return redirect(url_for('confessions'))

    pinned = PinnedContent.query.order_by(PinnedContent.date.desc()).first()
    pinned_content = None
    pinned_name = None
    if pinned and pinned.expiry_date:
        expiry_date = datetime.strptime(pinned.expiry_date, "%Y-%m-%d %H:%M:%S")
        if expiry_date > datetime.now():
            if pinned.content_type == 'confession' and pinned.content_id:
                conf = Confession.query.get(pinned.content_id)
                if conf:
                    pinned_content, pinned_name = conf.confession, conf.name
            elif pinned.content_type == 'post':
                pinned_content, pinned_name = pinned.custom_text, "Admin"

    confessions = Confession.query.filter(
        (Confession.expiry_date.is_(None)) | (Confession.expiry_date > datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    ).order_by(Confession.date.desc()).all()
    confessions_with_data = []
    for conf in confessions:
        comments = Comment.query.filter_by(confession_id=conf.id).order_by(Comment.date.asc()).all()
        comment_count = len(comments)
        avg_rating = (conf.rating_total / conf.rating_count) if conf.rating_count > 0 else 0
        score = conf.upvotes - conf.downvotes
        interactions = {i.action for i in Interaction.query.filter_by(ip_address=client_ip, confession_id=conf.id).all()}
        confessions_with_data.append((conf, [(c.comment, c.date) for c in comments], avg_rating, comment_count, score, interactions))

    dark_mode = request.cookies.get('dark_mode', 'off') == 'on'
    return render_template('confessions.html', confessions=confessions_with_data, pinned_content=pinned_content, 
                          pinned_name=pinned_name, dark_mode=dark_mode)

@app.route('/random')
def random_confession():
    valid_ids = [c.id for c in Confession.query.filter(
        (Confession.expiry_date.is_(None)) | (Confession.expiry_date > datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    ).all()]
    if valid_ids:
        random_id = random.choice(valid_ids)
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
    if request.method == 'POST':
        if 'delete_confession' in request.form:
            confession_id = int(request.form['confession_id'])
            Confession.query.filter_by(id=confession_id).delete()
            db.session.commit()
            flash('Confession deleted.', 'success')
        elif 'delete_comment' in request.form:
            comment_id = int(request.form['comment_id'])
            Comment.query.filter_by(id=comment_id).delete()
            db.session.commit()
            flash('Comment deleted.', 'success')
        elif 'pin_confession' in request.form:
            confession_id = int(request.form['confession_id'])
            days = int(request.form['pin_days'])
            expiry_date = datetime.now() + timedelta(days=days)
            PinnedContent.query.delete()
            db.session.add(PinnedContent(content_type='confession', content_id=confession_id, date=datetime.now().strftime("%Y-%m-%d %H:%M:%S"), expiry_date=expiry_date.strftime("%Y-%m-%d %H:%M:%S")))
            db.session.commit()
            flash(f'Confession pinned for {days} days.', 'success')
        elif 'pin_post' in request.form:
            custom_text = request.form['custom_text'].strip()
            days = int(request.form['pin_days'])
            if custom_text:
                expiry_date = datetime.now() + timedelta(days=days)
                PinnedContent.query.delete()
                db.session.add(PinnedContent(content_type='post', custom_text=custom_text, date=datetime.now().strftime("%Y-%m-%d %H:%M:%S"), expiry_date=expiry_date.strftime("%Y-%m-%d %H:%M:%S")))
                db.session.commit()
                flash(f'Custom post pinned for {days} days.', 'success')
        elif 'delete_pin' in request.form:
            PinnedContent.query.delete()
            db.session.commit()
            flash('Pinned content removed.', 'success')
        elif 'set_expiry' in request.form:
            confession_id = int(request.form['confession_id'])
            days = int(request.form['expiry_days'])
            conf = Confession.query.get_or_404(confession_id)
            if days > 0:
                conf.expiry_date = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
                flash(f'Confession set to expire in {days} days.', 'success')
            else:
                conf.expiry_date = None
                flash('Expiry removed from confession.', 'success')
            db.session.commit()

    confessions = Confession.query.order_by(Confession.date.desc()).all()
    confessions_with_comments = []
    for conf in confessions:
        comments = Comment.query.filter_by(confession_id=conf.id).order_by(Comment.date.asc()).all()
        avg_rating = (conf.rating_total / conf.rating_count) if conf.rating_count > 0 else 0
        confessions_with_comments.append((conf, [(c.id, c.comment, c.date) for c in comments], avg_rating))

    most_liked = Confession.query.order_by(Confession.likes.desc()).first()
    most_commented = db.session.query(Confession, db.func.count(Comment.id).label('comment_count')).outerjoin(Comment).group_by(Confession).order_by(db.text('comment_count DESC')).first()
    total_visits = Traffic.query.count()

    return render_template('admin_dashboard.html', confessions=confessions_with_comments, most_liked=most_liked,
                          most_commented=most_commented[0] if most_commented else None, total_visits=total_visits)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
