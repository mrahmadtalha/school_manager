"""End-of-session student promotion wizard."""
from datetime import date, datetime

from flask import flash, redirect, render_template, request, url_for

from app.database import db
from app.models import ClassModel, StudentModel
from app.routes import main
from app.services.audit import log_action
from app.services.enrollments import session_label_default, start_enrollment


def _back_params(source_id, target_id, session_value, promo_date):
    params = {}
    if source_id:
        params['source_class_id'] = source_id
    if target_id:
        params['target_class_id'] = target_id
    if session_value:
        params['session'] = session_value
    if promo_date:
        params['promotion_date'] = promo_date
    return params


@main.route('/promotions')
def promotions_page():
    classes = ClassModel.query.order_by(ClassModel.name).all()
    source_id = request.args.get('source_class_id', type=int)
    target_id = request.args.get('target_class_id', type=int)
    session_value = (request.args.get('session') or '').strip() or session_label_default()
    promo_date = (request.args.get('promotion_date') or '').strip() or date.today().isoformat()

    preview = []
    if source_id:
        students = (StudentModel.query.filter_by(is_active=True, class_id=source_id)
                    .order_by(StudentModel.roll_number).all())
        for i, s in enumerate(students, 1):
            preview.append({'student': s, 'new_roll': i})

    return render_template('promotions.html',
                           classes=classes,
                           source_id=source_id,
                           target_id=target_id,
                           session_value=session_value,
                           promo_date=promo_date,
                           preview=preview)


@main.route('/promotions/apply', methods=['POST'])
def promotions_apply():
    source_id = request.form.get('source_class_id', type=int)
    target_id = request.form.get('target_class_id', type=int)
    session_value = (request.form.get('session') or '').strip()
    promo_date_str = (request.form.get('promotion_date') or '').strip()
    promo_date = None
    if promo_date_str:
        try:
            promo_date = datetime.strptime(promo_date_str, '%Y-%m-%d').date()
        except ValueError:
            promo_date = None
    promo_date = promo_date or date.today()

    params = _back_params(source_id, target_id, session_value, promo_date.isoformat())

    if not source_id or not target_id or source_id == target_id:
        flash('Choose two different classes (source and target).', 'danger')
        return redirect(url_for('main.promotions_page', **params))

    students = (StudentModel.query.filter_by(is_active=True, class_id=source_id)
                .order_by(StudentModel.roll_number).all())

    promote = []
    errors = []
    for s in students:
        if request.form.get('include_%d' % s.id) != 'on':
            continue
        raw = (request.form.get('new_roll_%d' % s.id) or '').strip()
        try:
            roll = int(raw)
        except ValueError:
            errors.append('Please enter a valid roll number for %s.' % s.student_name)
            continue
        promote.append((s, roll))

    if not promote:
        flash('No students were selected — tick at least one student to promote.', 'warning')
        return redirect(url_for('main.promotions_page', **params))

    rolls = [roll for _, roll in promote]
    if len(set(rolls)) != len(rolls):
        errors.append('The new roll numbers contain duplicates.')

    promoted_ids = [s.id for s, _ in promote]
    staying = (StudentModel.query
               .filter(StudentModel.class_id == target_id,
                       StudentModel.is_active == True,  # noqa: E712
                       StudentModel.id.notin_(promoted_ids))
               .all())
    staying_rolls = {s.roll_number for s in staying}
    for _, roll in promote:
        if roll in staying_rolls:
            errors.append('Roll %d is already used by a student staying in the target class.' % roll)

    if errors:
        for e in errors:
            flash(e, 'danger')
        return redirect(url_for('main.promotions_page', **params))

    source_class = db.session.get(ClassModel, source_id)
    target_class = db.session.get(ClassModel, target_id)
    target_sections = {sec.name: sec.id for sec in target_class.sections}

    for s, roll in promote:
        old_section = s.section_info.name if s.section_info else None
        s.class_id = target_id
        s.roll_number = roll
        s.section_id = target_sections.get(old_section) if old_section else None
        start_enrollment(s, reason='promoted', start_date=promo_date,
                         session_label=session_value)

    log_action('promotion', entity_type='ClassModel', entity_id=source_id,
               summary=('Promoted %d student(s) from "%s" to "%s" (session %s)'
                        % (len(promote), source_class.name, target_class.name,
                           session_value or 'n/a')),
               after={'count': len(promote), 'target_class_id': target_id,
                      'session': session_value, 'date': promo_date.isoformat()})
    db.session.commit()

    flash('%d student(s) promoted to %s.' % (len(promote), target_class.name), 'success')
    return redirect(url_for('main.students_list', class_id=target_id))
