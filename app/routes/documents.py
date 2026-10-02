from datetime import datetime, date

from flask import (
    current_app,
    flash,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)

from app.database import db
from app.models import ClassModel, SchoolSettings, StudentModel, TeacherModel
from app.routes import main
from app.services.id_documents import (
    build_certificates_pdf,
    default_academic_session,
    build_id_cards_pdf,
    school_branding,
    student_card_payload,
    teacher_card_payload,
)

CERTIFICATE_TYPES = {
    'bonafide': 'Bonafide / Studentship',
    'character': 'Character',
    'leaving': 'School Leaving',
    'merit': 'Merit / Achievement',
}


def _school():
    return school_branding(current_app.root_path)


def _parse_issue_date(value):
    if not value:
        return date.today()
    try:
        return datetime.strptime(value, '%Y-%m-%d').date()
    except ValueError:
        return date.today()


def _active_students(class_id=None, student_id=None):
    query = StudentModel.query.filter_by(is_active=True)
    if student_id:
        query = query.filter_by(id=student_id)
    elif class_id:
        query = query.filter_by(class_id=class_id)
    return query.order_by(StudentModel.student_name).all()


@main.route('/documents')
def documents_hub():
    classes = ClassModel.query.order_by(ClassModel.name).all()
    students = StudentModel.query.filter_by(is_active=True).order_by(StudentModel.student_name).all()
    teachers = TeacherModel.query.filter_by(is_active=True).order_by(TeacherModel.teacher_name).all()
    school = SchoolSettings.query.first()
    return render_template(
        'documents.html',
        classes=classes,
        students=students,
        teachers=teachers,
        certificate_types=CERTIFICATE_TYPES,
        default_session=default_academic_session(),
        today=date.today().strftime('%Y-%m-%d'),
        school=school,
        preselect_student_id=request.args.get('student_id', type=int),
        preselect_teacher_id=request.args.get('teacher_id', type=int),
        preselect_class_id=request.args.get('class_id', type=int),
        preselect_cert=request.args.get('cert_type', 'bonafide'),
    )


@main.route('/documents/id-cards/students.pdf')
def export_student_id_cards():
    student_id = request.args.get('student_id', type=int)
    class_id = request.args.get('class_id', type=int)
    session = request.args.get('session', '').strip() or default_academic_session()
    students = _active_students(class_id=class_id, student_id=student_id)
    if not students:
        flash('No active students match those filters.', 'warning')
        return redirect(url_for('main.documents_hub'))

    people = [student_card_payload(student) for student in students]
    output = build_id_cards_pdf(people, _school(), session)
    if student_id and len(students) == 1:
        name = f'id_card_{students[0].roll_number}.pdf'
    elif class_id:
        class_name = students[0].class_info.name if students[0].class_info else 'class'
        name = f'id_cards_{class_name}.pdf'
    else:
        name = 'student_id_cards.pdf'
    return send_file(output, mimetype='application/pdf', as_attachment=True, download_name=name)


@main.route('/documents/id-cards/teachers.pdf')
def export_teacher_id_cards():
    teacher_id = request.args.get('teacher_id', type=int)
    session = request.args.get('session', '').strip() or default_academic_session()
    query = TeacherModel.query.filter_by(is_active=True)
    if teacher_id:
        query = query.filter_by(id=teacher_id)
    teachers = query.order_by(TeacherModel.teacher_name).all()
    if not teachers:
        flash('No active teachers match those filters.', 'warning')
        return redirect(url_for('main.documents_hub'))

    people = [teacher_card_payload(teacher) for teacher in teachers]
    output = build_id_cards_pdf(people, _school(), session)
    if teacher_id and len(teachers) == 1:
        name = f'id_card_{teachers[0].teacher_id_str}.pdf'
    else:
        name = 'staff_id_cards.pdf'
    return send_file(output, mimetype='application/pdf', as_attachment=True, download_name=name)


@main.route('/documents/certificates.pdf')
def export_certificates():
    cert_type = request.args.get('cert_type', 'bonafide')
    if cert_type not in CERTIFICATE_TYPES:
        cert_type = 'bonafide'
    student_id = request.args.get('student_id', type=int)
    class_id = request.args.get('class_id', type=int)
    session = request.args.get('session', '').strip() or default_academic_session()
    remarks = request.args.get('remarks', '').strip()
    issue_date = _parse_issue_date(request.args.get('issue_date'))

    if not student_id and not class_id:
        flash('Select a student or a class to export certificates.', 'warning')
        return redirect(url_for('main.documents_hub'))

    if student_id:
        # Ex-students keep their full record; certificates (SLC / character / etc.)
        # must remain printable after the student leaves.
        student = db.session.get(StudentModel, student_id)
        students = [student] if student else []
    else:
        students = _active_students(class_id=class_id)
    if not students:
        flash('Select a student or a class with active students to export certificates.', 'warning')
        return redirect(url_for('main.documents_hub'))

    output = build_certificates_pdf(students, _school(), cert_type, session, issue_date, remarks)
    if student_id and len(students) == 1:
        name = f'{cert_type}_{students[0].roll_number}.pdf'
    else:
        name = f'{cert_type}_certificates.pdf'
    return send_file(output, mimetype='application/pdf', as_attachment=True, download_name=name)
