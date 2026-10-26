from datetime import datetime, date

from flask import (
    abort,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)
from flask_login import current_user

from app.database import db
from app.models import (ClassModel, IssuedDocument, ROLE_ADMIN, SchoolSettings,
                        StudentModel, TeacherModel)
from app.models.issued_document import DOC_CERTIFICATE, DOC_ID_CARD
from app.routes import main
from app.security import role_required
from app.services import document_fees
from app.services.payroll_service import amount_in_words
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


def _is_admin():
    return (getattr(current_user, 'role', None) or ROLE_ADMIN) == ROLE_ADMIN


def _issue_redirect(kind, student_id, cert_type=None):
    """Send a single-student download to the Issue page (a fee applies)."""
    if not _is_admin():
        flash('A fee is set for this document, so it is issued by the school '
              'office (administrator).', 'warning')
        return redirect(url_for('main.documents_hub'))
    params = {'kind': kind, 'student_id': student_id}
    if kind == DOC_CERTIFICATE:
        params['cert_type'] = cert_type
    for key in ('session', 'issue_date', 'remarks'):
        value = (request.args.get(key) or '').strip()
        if value:
            params[key] = value
    return redirect(url_for('main.document_issue', **params))


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
        is_admin=_is_admin(),
        fee_cfg=document_fees.fee_settings(),
        fee_money=document_fees.money,
        id_card_fee=document_fees.first_fee_paisa(DOC_ID_CARD),
        id_card_dup_fee=document_fees.duplicate_fee_paisa(DOC_ID_CARD),
        cert_fees={key: (document_fees.first_fee_paisa(DOC_CERTIFICATE, key),
                         document_fees.duplicate_fee_paisa(DOC_CERTIFICATE, key))
                   for key in CERTIFICATE_TYPES},
        recent_issues=document_fees.recent_issues() if _is_admin() else [],
        title_for=document_fees.title_for,
    )


@main.route('/documents/id-cards/students.pdf')
def export_student_id_cards():
    student_id = request.args.get('student_id', type=int)
    class_id = request.args.get('class_id', type=int)
    session = request.args.get('session', '').strip() or default_academic_session()
    if student_id and document_fees.is_gated(DOC_ID_CARD):
        return _issue_redirect(DOC_ID_CARD, student_id)
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

    if student_id and document_fees.is_gated(DOC_CERTIFICATE, cert_type):
        return _issue_redirect(DOC_CERTIFICATE, student_id, cert_type)

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


# --------------------------------------------------------------------------- #
# Fees, issuing and receipts (Phase 5).  Administrator only: these endpoints are
# not in any other role's list, so the deny-by-default guard applies.
# --------------------------------------------------------------------------- #

@main.route('/documents/fees', methods=['POST'])
@role_required(ROLE_ADMIN)
def document_fees_save():
    try:
        document_fees.save_fee_settings(request.form)
        from app.services.audit import log_action
        log_action('settings_change', entity_type='DocumentFees',
                   summary='ID card / certificate fees updated')
        db.session.commit()
        flash('Document fees saved. A fee of 0 or blank means free.', 'success')
    except ValueError as error:
        db.session.rollback()
        flash(str(error), 'danger')
    return redirect(url_for('main.documents_hub') + '#doc-fees')


def _issue_target():
    """Read kind / student / certificate type from the request, or abort."""
    source = request.form if request.method == 'POST' else request.args
    kind = (source.get('kind') or '').strip()
    if kind not in (DOC_ID_CARD, DOC_CERTIFICATE):
        abort(404)
    student = db.session.get(StudentModel, source.get('student_id', type=int) or 0)
    if student is None:
        abort(404)
    cert_type = None
    if kind == DOC_CERTIFICATE:
        cert_type = (source.get('cert_type') or 'bonafide').strip()
        if cert_type not in CERTIFICATE_TYPES:
            cert_type = 'bonafide'
    return source, kind, student, cert_type


@main.route('/documents/issue', methods=['GET', 'POST'])
@role_required(ROLE_ADMIN)
def document_issue():
    source, kind, student, cert_type = _issue_target()
    session = (source.get('session') or '').strip() or default_academic_session()
    issue_date = _parse_issue_date(source.get('issue_date'))
    remarks = (source.get('remarks') or '').strip()[:200]
    info = document_fees.plan(student, kind, cert_type)

    if request.method == 'POST':
        if kind == DOC_ID_CARD and not student.is_active:
            flash('ID cards are only issued to active students.', 'danger')
        else:
            free = (request.form.get('duplicate_choice') == 'free'
                    and info['is_duplicate'])
            try:
                row = document_fees.issue(
                    student, kind, cert_type, session=session,
                    issue_date=issue_date, remarks=remarks,
                    method=request.form.get('payment_method'),
                    duplicate_free=free, actor=current_user)
                db.session.commit()
                if row.income is not None:
                    flash('Receipt %s created. Please give it to the parent.'
                          % row.income.receipt_no, 'success')
                else:
                    flash('Issued with no fee.', 'success')
                return redirect(url_for('main.document_receipt', doc_id=row.id))
            except ValueError as error:
                db.session.rollback()
                flash(str(error), 'danger')

    return render_template(
        'document_issue.html', student=student, kind=kind, cert_type=cert_type,
        title=document_fees.title_for(kind, cert_type), info=info,
        session=session, issue_date=issue_date, remarks=remarks,
        methods=document_fees.PAYMENT_METHODS, money=document_fees.money,
        today=date.today().strftime('%Y-%m-%d'))


@main.route('/documents/issued/<int:doc_id>')
@role_required(ROLE_ADMIN)
def document_receipt(doc_id):
    doc = IssuedDocument.query.get_or_404(doc_id)
    row = doc.income
    return render_template(
        'document_receipt.html', doc=doc, row=row, student=doc.student,
        title=document_fees.title_for(doc.doc_kind, doc.cert_type),
        school=SchoolSettings.query.first(), money=document_fees.money,
        words=amount_in_words(row.amount) if row is not None else '')


@main.route('/documents/issued/<int:doc_id>.pdf')
@role_required(ROLE_ADMIN)
def document_issued_pdf(doc_id):
    doc = IssuedDocument.query.get_or_404(doc_id)
    if doc.is_void:
        flash('This issue was voided, so it cannot be downloaded.', 'warning')
        return redirect(url_for('main.document_receipt', doc_id=doc.id))
    output = document_fees.build_pdf(doc, current_app.root_path)
    return send_file(output, mimetype='application/pdf', as_attachment=True,
                     download_name=document_fees.pdf_name(doc))


@main.route('/documents/issued/<int:doc_id>/void', methods=['POST'])
@role_required(ROLE_ADMIN)
def document_void(doc_id):
    doc = IssuedDocument.query.get_or_404(doc_id)
    try:
        document_fees.void_issue(doc, request.form.get('reason'),
                                 actor=current_user)
        db.session.commit()
        flash('Voided. The fee receipt (if any) no longer counts in any total.',
              'warning')
    except ValueError as error:
        db.session.rollback()
        flash(str(error), 'danger')
    return redirect(url_for('main.document_receipt', doc_id=doc.id))
