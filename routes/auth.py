from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from werkzeug.security import check_password_hash
from ext import db
from models import User
from functools import wraps

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function

bp = Blueprint('auth', __name__)

@bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        user = User.query.filter_by(username=username).first()
        
        if user and check_password_hash(user.password_hash, password):
            session['user_id'] = user.id
            session['username'] = user.username
            session['role'] = user.role
            if user.role == 'admin':
                return redirect(url_for('dashboard.admin_dashboard'))
            return redirect(url_for('dashboard.index'))
        else:
            flash('Invalid credentials', 'error')
    
    return render_template('login.html')

@bp.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('auth.login'))

@bp.route('/users')
@login_required
def users():
    if session.get('role') != 'admin':
        flash('Access denied', 'error')
        return redirect(url_for('dashboard.index'))
    users = User.query.all()
    return render_template('users.html', users=users)

@bp.route('/users/add', methods=['GET', 'POST'])
@login_required
def add_user():
    if session.get('role') != 'admin':
        flash('Access denied', 'error')
        return redirect(url_for('dashboard.index'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        role = request.form.get('role')
        
        if User.query.filter_by(username=username).first():
            flash('Username already exists', 'error')
        else:
            from werkzeug.security import generate_password_hash
            user = User(username=username, password_hash=generate_password_hash(password), role=role)
            db.session.add(user)
            db.session.commit()
            flash('User created successfully', 'success')
        return redirect(url_for('auth.users'))
    
    return render_template('add_user.html')

@bp.route('/users/delete/<int:id>')
@login_required
def delete_user(id):
    if session.get('role') != 'admin':
        flash('Access denied', 'error')
        return redirect(url_for('dashboard.index'))
    
    user = User.query.get_or_404(id)
    if user.username == 'admin':
        flash('Cannot delete admin', 'error')
    else:
        db.session.delete(user)
        db.session.commit()
        flash('User deleted', 'success')
    return redirect(url_for('auth.users'))