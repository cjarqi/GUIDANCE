# GUIDANCE/mainsub/auth.py

from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user, login_required, current_user
from .models import StaffUser, AuditLog, db
from . import mail
from flask_mail import Message

auth_bp = Blueprint('auth', __name__)

def log_audit(action, target_type=None, target_id=None, details=None):
    try:
        log_entry = AuditLog(user_id=current_user.id, action=action, target_type=target_type, target_id=target_id, details=details)
        db.session.add(log_entry)
    except Exception as e:
        print(f"!!! CRITICAL: Failed to create audit log: {e}")

@auth_bp.route('/login', methods=['GET'])
def login_page():
    if current_user.is_authenticated:
        return redirect(url_for('views.dashboard'))
    return render_template('auth/login.html')

@auth_bp.route('/login', methods=['POST'])
def login_post():
    username = request.form.get('username')
    password = request.form.get('password')
    remember = True if request.form.get('remember-me') else False
    user = StaffUser.query.filter_by(username=username).first()
    if not user or not user.check_password(password) or not user.is_active_staff:
        flash('Invalid username or password, or account is inactive.', 'error')
        return redirect(url_for('auth.login_page'))
    login_user(user, remember=remember)
    log_audit("Logged In")
    db.session.commit()
    flash('Login successful!', 'success')
    return redirect(url_for('views.dashboard'))

@auth_bp.route('/logout')
@login_required
def logout():
    log_audit("Logged Out")
    db.session.commit()
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('auth.login_page'))

def send_reset_email(user):
    token = user.get_reset_token()
    msg = Message('Password Reset Request for Guidance System', recipients=[user.email])
    msg.body = f'''To reset your password, visit the following link:
{url_for('auth.reset_token', token=token, _external=True)}

This link will expire in 30 minutes.

If you did not make this request, please ignore this email and no changes will be made.
'''
    try:
        mail.send(msg)
        return True
    except Exception as e:
        print(f"!!! EMAIL SEND FAILED: {e}")
        return False

@auth_bp.route("/reset_password", methods=['GET', 'POST'])
def reset_request():
    if current_user.is_authenticated:
        return redirect(url_for('views.dashboard'))
    if request.method == 'POST':
        email = request.form.get('email')
        user = StaffUser.query.filter_by(email=email).first()
        if user:
            if send_reset_email(user):
                flash('A password reset link has been sent to your email.', 'info')
            else:
                flash('Could not send email. Please check server configuration and try again later.', 'error')
        else:
            # We still show a generic message for security
            flash('If an account with that email exists, a reset link has been sent.', 'info')
        return redirect(url_for('auth.login_page'))
    return render_template('auth/reset_request.html', title='Reset Password')

@auth_bp.route("/reset_password/<token>", methods=['GET', 'POST'])
def reset_token(token):
    if current_user.is_authenticated:
        return redirect(url_for('views.dashboard'))
    user = StaffUser.verify_reset_token(token)
    if user is None:
        flash('That is an invalid or expired token.', 'warning')
        return redirect(url_for('auth.reset_request'))
    if request.method == 'POST':
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        if password != confirm_password:
            flash('Passwords do not match.', 'error')
            return redirect(url_for('auth.reset_token', token=token))
        
        user.set_password(password)
        db.session.commit()
        log_audit("Reset Password", target_type="StaffUser", target_id=user.id)
        db.session.commit()
        flash('Your password has been updated! You are now able to log in.', 'success')
        return redirect(url_for('auth.login_page'))
    return render_template('auth/reset_token.html', title='Reset Password', token=token)