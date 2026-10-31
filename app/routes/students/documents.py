"""Per-student documents: detailed report, admission form, report PDF and transcript."""

import io
import re
from flask import render_template, send_file, abort
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from flask_login import current_user
from app.models import (
    StudentModel,
    AttendanceModel,
    TestModel,
    StudentMarkModel,
    FeeRecordModel,
    StudentEnrollment,
)
from app.routes import main
from app.services import admission_fee
from app.services import admission_form
from app.services.marks import ABSENT_LABEL
from app.models.settings import calculate_grade

from app.routes.students.helpers import _dues_balances


@main.route('/students/<int:id>/report')
def student_detailed_report(id):
    from app.models import TermExam
    from app.routes.term_exams import build_tabulation
    from app.services.fee_ledger import _month_sort_key
    from app.services.whatsapp_automation import normalize_whatsapp_number

    student = StudentModel.query.get_or_404(id)
    attendance_records = AttendanceModel.query.filter_by(target_type='student', target_id=student.id).order_by(AttendanceModel.date.desc()).all()
    marks = StudentMarkModel.query.filter_by(student_id=student.id).join(TestModel).order_by(TestModel.test_date.desc()).all()

    total_records = len(attendance_records)
    present_count = sum(1 for r in attendance_records if r.status == 'Present')
    absent_count = sum(1 for r in attendance_records if r.status == 'Absent')
    late_count = sum(1 for r in attendance_records if r.status == 'Late')
    leave_count = sum(1 for r in attendance_records if r.status == 'Leave')
    from app.services.attendance_service import late_counts_as_present
    attended_count = present_count + (late_count if late_counts_as_present() else 0)
    attendance_pct = round(attended_count * 100.0 / total_records, 1) if total_records else 0.0

    overall_percentage = 0.0
    if marks:
        percentages = [m.percentage for m in marks if m.percentage is not None]
        overall_percentage = round(sum(percentages) / len(percentages), 1) if percentages else 0.0
    overall_grade = calculate_grade(overall_percentage)
    if marks and all(m.is_absent for m in marks):
        overall_grade = ABSENT_LABEL   # absent from everything: not a fail
    scored_marks = [m for m in marks if not m.is_absent]

    summary = {
        'attendance_total': total_records,
        'present_count': present_count,
        'absent_count': absent_count,
        'late_count': late_count,
        'leave_count': leave_count,
        'attendance_pct': attendance_pct,
        'overall_percentage': overall_percentage,
        'overall_grade': overall_grade,
        'best_test': max(scored_marks, key=lambda m: (m.percentage or 0)).test_info.test_title if scored_marks else 'N/A',
    }

    enrollments = (StudentEnrollment.query.filter_by(student_id=student.id)
                   .order_by(StudentEnrollment.id).all())

    # Live dues + recent fee ledger (newest first)
    dues = _dues_balances([student.id]).get(student.id, 0.0)
    fee_rows = FeeRecordModel.query.filter_by(student_id=student.id).all()
    fee_rows.sort(key=lambda record: _month_sort_key(record.month_year), reverse=True)
    fee_recent = fee_rows[:12]

    # Recent term-exam results with positions (latest 4 exams of the class)
    term_results = []
    exams = (TermExam.query.filter_by(class_id=student.class_id)
             .order_by(TermExam.id.desc()).limit(4).all())
    for exam in exams:
        tests, rows, exam_summary = build_tabulation(exam)
        row = next((r for r in rows if r['student'].id == student.id), None)
        if row:
            term_results.append({'exam': exam, 'row': row,
                                 'total_max': exam_summary['total_max'],
                                 'complete': exam_summary['complete']})

    wa_digits = normalize_whatsapp_number(student.guardian_phone or '')
    wa_link = ('https://wa.me/%s' % wa_digits) if wa_digits else None

    # The list no longer carries an Admission fee button, so the report offers
    # it (same rule the list used: administrator, and the fee is in use).
    admission_link = bool(
        admission_fee.is_admin(current_user)
        and (admission_fee.is_enabled()
             or admission_fee.student_map([student.id]).get(student.id)))

    return render_template('student_report.html',
                           student=student,
                           attendance_records=attendance_records,
                           marks=marks,
                           enrollments=enrollments,
                           summary=summary,
                           dues=dues,
                           fee_recent=fee_recent,
                           term_results=term_results,
                           wa_link=wa_link,
                           admission_link=admission_link)


@main.route('/students/<int:id>/admission-form/<fmt>')
def student_admission_form(id, fmt):
    """Download this student's admission form as PDF or Excel."""
    if fmt not in ('pdf', 'xlsx'):
        abort(404)
    student = StudentModel.query.get_or_404(id)
    safe_name = re.sub(r'[^A-Za-z0-9_-]+', '_', student.student_name).strip('_') or 'student'
    if fmt == 'pdf':
        data = admission_form.build_pdf(student)
        mimetype = 'application/pdf'
    else:
        data = admission_form.build_xlsx(student)
        mimetype = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    return send_file(io.BytesIO(data), mimetype=mimetype, as_attachment=True,
                     download_name='admission_form_%s_%s.%s' % (student.roll_number, safe_name, fmt))


@main.route('/students/<int:id>/report/pdf')
def student_report_pdf(id):
    student = StudentModel.query.get_or_404(id)
    marks = StudentMarkModel.query.filter_by(student_id=student.id).join(TestModel).order_by(TestModel.test_date.asc()).all()
    attendance_records = AttendanceModel.query.filter_by(target_type='student', target_id=student.id).order_by(AttendanceModel.date.asc()).all()

    total_records = len(attendance_records)
    present_count = sum(1 for r in attendance_records if r.status == 'Present')
    absent_count = sum(1 for r in attendance_records if r.status == 'Absent')
    late_count = sum(1 for r in attendance_records if r.status == 'Late')
    leave_count = sum(1 for r in attendance_records if r.status == 'Leave')

    percentages = [m.percentage for m in marks if m.percentage is not None]
    overall_percentage = round(sum(percentages) / len(percentages), 1) if percentages else 0.0

    if overall_percentage >= 85:
        overall_grade = 'A+'
    elif overall_percentage >= 70:
        overall_grade = 'A'
    elif overall_percentage >= 60:
        overall_grade = 'B'
    elif overall_percentage >= 50:
        overall_grade = 'C'
    elif overall_percentage >= 40:
        overall_grade = 'D'
    else:
        overall_grade = 'F'
    if marks and all(m.is_absent for m in marks):
        overall_grade = ABSENT_LABEL   # absent from everything: not a fail

    output = io.BytesIO()
    doc = SimpleDocTemplate(output, pagesize=letter, rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=30)
    story = []
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('TitleStyle', parent=styles['Heading1'], fontSize=18, textColor=colors.HexColor('#0f172a'), spaceAfter=8, alignment=1, fontName='Helvetica-Bold')
    subtitle_style = ParagraphStyle('SubTitleStyle', parent=styles['Normal'], fontSize=10, textColor=colors.HexColor('#475569'), spaceAfter=12, alignment=1)
    label_style = ParagraphStyle('LabelStyle', parent=styles['Normal'], fontSize=9, textColor=colors.HexColor('#475569'), leading=12)

    from app.models import SchoolSettings
    school = SchoolSettings.query.first()
    school_name = school.school_name if school else 'School Management System'

    story.append(Paragraph(f"{school_name}", title_style))
    story.append(Paragraph('Student Performance Report Card', subtitle_style))
    story.append(Paragraph(f"<b>Student:</b> {student.student_name} &nbsp;&nbsp;|&nbsp;&nbsp; <b>Roll No:</b> {student.roll_number} &nbsp;&nbsp;|&nbsp;&nbsp; <b>Class:</b> {student.class_info.name if student.class_info else 'N/A'} &nbsp;&nbsp;|&nbsp;&nbsp; <b>Father:</b> {student.father_name}", label_style))

    metric_data = [
        ['Overall %', f'{overall_percentage}%'],
        ['Grade', overall_grade],
        ['Present', str(present_count)],
        ['Absent', str(absent_count)],
        ['Late', str(late_count)],
        ['Leave', str(leave_count)],
    ]
    metric_table = Table(metric_data, colWidths=[75, 65], rowHeights=28)
    metric_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f8fafc')),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('TEXTCOLOR', (0, 0), (-1, -1), colors.HexColor('#0f172a')),
        ('BACKGROUND', (0, 0), (0, 5), colors.HexColor('#dbeafe')),
        ('BACKGROUND', (1, 0), (1, 0), colors.HexColor('#dcfce7')),
        ('BACKGROUND', (1, 1), (1, 1), colors.HexColor('#fef3c7')),
    ]))
    story.append(Spacer(1, 8))
    story.append(metric_table)
    story.append(Spacer(1, 12))

    table_data = [['Test', 'Type', 'Subject', 'Date', 'Obtained', '%', 'Grade']]
    for mark in marks:
        test = mark.test_info
        table_data.append([
            test.test_title if test else 'N/A',
            test.test_type if test else 'N/A',
            test.subject_info.name if test and test.subject_info else 'N/A',
            str(test.test_date) if test else 'N/A',
            ABSENT_LABEL if mark.is_absent else str(mark.marks_obtained),
            f"{mark.percentage}%" if mark.percentage is not None else '—',
            ABSENT_LABEL if mark.is_absent else (mark.grade or '—')
        ])

    table = Table(table_data, colWidths=[110, 55, 80, 70, 55, 45, 45])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0f172a')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
        ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#f8fafc')),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
    ]))
    story.append(table)
    doc.build(story)
    output.seek(0)
    return send_file(output, mimetype='application/pdf', as_attachment=True, download_name=f'{student.roll_number}_{student.student_name}_result_card.pdf')


@main.route('/students/<int:id>/transcript.pdf')
def student_transcript_pdf(id):
    student = StudentModel.query.get_or_404(id)
    enrollments = (StudentEnrollment.query.filter_by(student_id=student.id)
                   .order_by(StudentEnrollment.id).all())
    marks = (StudentMarkModel.query.filter_by(student_id=student.id)
             .join(TestModel).order_by(TestModel.test_date.asc()).all())

    from flask import current_app
    from app.services.transcripts import build_transcript_pdf

    output = build_transcript_pdf(student, enrollments, marks, current_app.root_path)
    return send_file(output, mimetype='application/pdf', as_attachment=True,
                     download_name=f'transcript_{student.roll_number}_{student.student_name}.pdf')
