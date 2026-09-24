from flask import Blueprint, render_template, redirect, url_for, request, flash
from flask_login import login_user, logout_user, login_required
from werkzeug.security import check_password_hash, generate_password_hash
from app.models import AdminUser, SchoolSettings
from app.database import db
from app.bootstrap import seed_demo_data

auth = Blueprint('auth', __name__)

@auth.route('/setup-admin', methods=['GET', 'POST'])
def setup_admin():
    if AdminUser.query.first():
        return redirect(url_for('auth.login'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        confirm = request.form.get('confirm_password', '')
        school_name = request.form.get('school_name', '').strip() or 'School Manager'
        tagline = request.form.get('tagline', '').strip()
        address = request.form.get('address', '').strip()
        phone = request.form.get('phone', '').strip()
        email = request.form.get('email', '').strip()
        include_dummy_data = request.form.get('dummy_data') == 'on'

        def clean_int(value, default):
            try:
                parsed = int(value)
                return max(0, parsed)
            except (TypeError, ValueError):
                return default

        dummy_student_count = clean_int(request.form.get('dummy_student_count'), 60)
        dummy_teacher_count = clean_int(request.form.get('dummy_teacher_count'), 8)
        dummy_fee_value = request.form.get('dummy_fee', '').strip()
        try:
            dummy_fee = float(dummy_fee_value) if dummy_fee_value else 2500.0
        except ValueError:
            dummy_fee = 2500.0

        if not username or not password:
            flash('Username and password are required.', 'danger')
        elif password != confirm:
            flash('Passwords do not match.', 'danger')
        elif len(password) < 8:
            flash('Password must be at least 8 characters.', 'danger')
        else:
            admin = AdminUser(username=username, password_hash=generate_password_hash(password))
            db.session.add(admin)

            settings = SchoolSettings.query.first()
            if settings is None:
                settings = SchoolSettings()
                db.session.add(settings)

            settings.school_name = school_name
            settings.tagline = tagline
            settings.address = address
            settings.phone = phone
            settings.email = email

            if include_dummy_data:
                seed_demo_data(
                    student_count=dummy_student_count,
                    teacher_count=dummy_teacher_count,
                    default_monthly_fee=dummy_fee,
                )

            db.session.commit()
            flash('School setup completed successfully. Please log in.', 'success')
            return redirect(url_for('auth.login'))

    return render_template('setup_admin.html')

@auth.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        user = AdminUser.query.filter_by(username=username).first()
        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            next_page = request.args.get('next')
            return redirect(next_page or url_for('main.dashboard'))
        flash('Incorrect username or password.', 'danger')
    return render_template('login.html')

@auth.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('auth.login'))

@auth.route('/change-password', methods=['POST'])
@login_required
def change_password():
    from flask_login import current_user
    from werkzeug.security import generate_password_hash, check_password_hash
    current_pw = request.form.get('current_password')
    new_pw = request.form.get('new_password')
    confirm_pw = request.form.get('confirm_password')
    if not check_password_hash(current_user.password_hash, current_pw):
        flash('Current password is incorrect.', 'danger')
    elif new_pw != confirm_pw:
        flash('New passwords do not match.', 'danger')
    elif len(new_pw) < 6:
        flash('New password must be at least 6 characters.', 'danger')
    else:
        current_user.password_hash = generate_password_hash(new_pw)
        from app.database import db
        db.session.commit()
        flash('Password changed successfully!', 'success')
    return redirect(url_for('main.dashboard'))