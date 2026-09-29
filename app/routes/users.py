"""Administrator user & role management."""

from flask import flash, redirect, render_template, request, url_for
from flask_login import current_user

from app.database import db
from app.models import (ROLES, ROLE_ADMIN, ROLE_LABELS, AdminUser,
                        GuardianStudentLink, StudentModel)
from app.routes import main
from app.security import role_required
from app.services.audit import log_action


def _student_choices():
    return (StudentModel.query
            .filter_by(is_active=True)
            .order_by(StudentModel.student_name)
            .all())


@main.route('/users')
@role_required(ROLE_ADMIN)
def users_list():
    users = AdminUser.query.order_by(AdminUser.id).all()
    return render_template('users.html', users=users, roles=ROLES,
                           role_labels=ROLE_LABELS, students=_student_choices())


@main.route('/users/create', methods=['POST'])
@role_required(ROLE_ADMIN)
def create_user():
    username = (request.form.get('username') or '').strip()
    password = request.form.get('password') or ''
    role = (request.form.get('role') or ROLE_ADMIN).strip()
    full_name = (request.form.get('full_name') or '').strip() or None

    # Parents may be linked to one or more children (legacy single field still accepted).
    requested_ids = [value for value in request.form.getlist('student_ids') if value.strip().isdigit()]
    requested_ids = [int(value) for value in requested_ids]
    if not requested_ids:
        legacy_id = request.form.get('student_id', type=int)
        if legacy_id:
            requested_ids = [legacy_id]
    requested_ids = list(dict.fromkeys(requested_ids))  # keep form order, drop duplicates

    if not username or not password:
        flash('Username and password are required.', 'danger')
        return redirect(url_for('main.users_list'))
    if role not in ROLES:
        flash('Unknown role.', 'danger')
        return redirect(url_for('main.users_list'))
    if len(password) < 8:
        flash('Password must be at least 8 characters.', 'danger')
        return redirect(url_for('main.users_list'))
    if role != 'parent':
        requested_ids = []
    if role == 'parent' and not requested_ids:
        flash('A parent account must be linked to at least one student.', 'danger')
        return redirect(url_for('main.users_list'))

    if requested_ids:
        found = StudentModel.query.filter(StudentModel.id.in_(requested_ids)).all()
        if len(found) != len(requested_ids):
            flash('One of the selected students no longer exists.', 'danger')
            return redirect(url_for('main.users_list'))

    if AdminUser.query.filter_by(username=username).first():
        flash(f'Username "{username}" already exists.', 'danger')
        return redirect(url_for('main.users_list'))

    user = AdminUser(username=username, role=role, full_name=full_name,
                     student_id=requested_ids[0] if requested_ids else None)
    user.set_password(password)
    db.session.add(user)
    db.session.flush()

    for student_id in requested_ids:
        db.session.add(GuardianStudentLink(user_id=user.id, student_id=student_id))

    log_action('user_admin', entity_type='AdminUser', entity_id=user.id,
               summary=f'Created user "{username}" with role {role}',
               after={'username': username, 'role': role,
                      'student_id': user.student_id, 'student_ids': requested_ids})
    db.session.commit()
    flash(f'User "{username}" created.', 'success')
    return redirect(url_for('main.users_list'))


@main.route('/users/<int:user_id>/students', methods=['POST'])
@role_required(ROLE_ADMIN)
def update_user_students(user_id):
    """Replace the linked children of a parent account."""
    user = db.session.get(AdminUser, user_id)
    if user is None:
        flash('User not found.', 'danger')
        return redirect(url_for('main.users_list'))
    if not user.is_parent:
        flash('Only parent accounts have linked students.', 'warning')
        return redirect(url_for('main.users_list'))

    requested_ids = [value for value in request.form.getlist('student_ids') if value.strip().isdigit()]
    requested_ids = list(dict.fromkeys(int(value) for value in requested_ids))
    if not requested_ids:
        flash('A parent account must be linked to at least one student.', 'danger')
        return redirect(url_for('main.users_list'))

    found = StudentModel.query.filter(StudentModel.id.in_(requested_ids)).all()
    if len(found) != len(requested_ids):
        flash('One of the selected students no longer exists.', 'danger')
        return redirect(url_for('main.users_list'))

    existing = {link.student_id: link for link in
                GuardianStudentLink.query.filter_by(user_id=user.id).all()}
    before_ids = sorted(existing)
    for student_id, link in existing.items():
        if student_id not in requested_ids:
            db.session.delete(link)
    for student_id in requested_ids:
        if student_id not in existing:
            db.session.add(GuardianStudentLink(user_id=user.id, student_id=student_id))

    user.student_id = requested_ids[0]
    log_action('user_admin', entity_type='AdminUser', entity_id=user.id,
               summary=f'Updated linked students for "{user.username}"',
               before={'student_ids': before_ids}, after={'student_ids': requested_ids})
    db.session.commit()
    flash(f'Linked students updated for "{user.username}".', 'success')
    return redirect(url_for('main.users_list'))


@main.route('/users/<int:user_id>/password', methods=['POST'])
@role_required(ROLE_ADMIN)
def reset_user_password(user_id):
    user = db.session.get(AdminUser, user_id)
    if user is None:
        flash('User not found.', 'danger')
        return redirect(url_for('main.users_list'))

    password = request.form.get('password') or ''
    if len(password) < 8:
        flash('Password must be at least 8 characters.', 'danger')
        return redirect(url_for('main.users_list'))

    user.set_password(password)
    log_action('user_admin', entity_type='AdminUser', entity_id=user.id,
               summary=f'Password reset for "{user.username}"',
               after={'password': 'reset'})
    db.session.commit()
    flash(f'Password reset for "{user.username}".', 'success')
    return redirect(url_for('main.users_list'))


@main.route('/users/<int:user_id>/toggle', methods=['POST'])
@role_required(ROLE_ADMIN)
def toggle_user_active(user_id):
    user = db.session.get(AdminUser, user_id)
    if user is None:
        flash('User not found.', 'danger')
        return redirect(url_for('main.users_list'))

    if user.id == current_user.id:
        flash('You cannot deactivate your own account.', 'warning')
        return redirect(url_for('main.users_list'))

    if user.role == ROLE_ADMIN:
        active_admins = AdminUser.query.filter_by(role=ROLE_ADMIN, is_active=True).count()
        if user.is_active and active_admins <= 1:
            flash('At least one active administrator must remain.', 'danger')
            return redirect(url_for('main.users_list'))

    before = {'is_active': user.is_active}
    user.is_active = not user.is_active
    log_action('user_admin', entity_type='AdminUser', entity_id=user.id,
               summary=f'User "{user.username}" {"activated" if user.is_active else "deactivated"}',
               before=before, after={'is_active': user.is_active})
    db.session.commit()
    flash(f'User "{user.username}" {"activated" if user.is_active else "deactivated"}.', 'success')
    return redirect(url_for('main.users_list'))
