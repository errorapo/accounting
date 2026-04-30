from flask import Blueprint, render_template, request, redirect, url_for, session, flash, g
from werkzeug.security import check_password_hash, generate_password_hash
from ext import db
from models import User
from functools import wraps
from datetime import datetime

bp = Blueprint('auth', __name__)

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('auth.login'))
        
        session_age = datetime.utcnow() - session.get('session_created', datetime.utcnow())
        if session_age.total_seconds() > 3600:
            session.clear()
            flash('Session expired. Please login again.', 'error')
            return redirect(url_for('auth.login'))
        
        return f(*args, **kwargs)
    return decorated_function


@bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        from flask_limiter import Limiter
        username = request.form.get('username')
        password = request.form.get('password')
        
        user = User.query.filter_by(username=username).first()
        
        if user and check_password_hash(user.password_hash, password):
            session['user_id'] = user.id
            session['username'] = user.username
            session['role'] = user.role
            session['session_created'] = datetime.utcnow()
            session.permanent = True
            
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
            try:
                from validators import validate_password
                validate_password(password)
            except ValueError as e:
                flash(str(e), 'error')
                return render_template('add_user.html')
            
            user = User(username=username, password_hash=generate_password_hash(password), role=role)
            db.session.add(user)
            db.session.commit()
            
            from accounting_engine import log_audit
            log_audit(db.session, session.get('user_id'), 'create', 'user', user.id,
                     new_values={'username': username, 'role': role})
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
        from accounting_engine import log_audit
        user_id = user.id
        username = user.username
        db.session.delete(user)
        db.session.commit()
        
        log_audit(db.session, session.get('user_id'), 'delete', 'user', user_id,
                 old_values={'username': username})
        
        flash('User deleted', 'success')
    return redirect(url_for('auth.users'))