"""Executive (Principal / Owner) read-only dashboard and printable summary.

Only GET endpoints live here: the owner role is strictly read-only, enforced
by the deny-by-default route guard (see app/security.py) plus explicit
role_required decorators.
"""
import io
from datetime import date, datetime

from flask import current_app, render_template, send_file
from sqlalchemy import case, func

from app.database import db
from app.models import (ROLE_ADMIN, ROLE_OWNER, AttendanceModel, ClassModel,
                        FeeRecordModel, SchoolSettings, StudentModel, TeacherModel)
from app.routes import main
from app.security import role_required
from app.services.audit import log_action
from app.services.financial_summary import month_snapshot
from app.services.payroll_service import month_bounds


def _reporting_month():
    """Current month when it already has fee data, otherwise the latest month."""
    current = date.today().strftime('%B %Y')
    if FeeRecordModel.query.filter_by(month_year=current).first():
        return current
    rows = [row[0] for row in
            db.session.query(FeeRecordModel.month_year).distinct().all() if row[0]]
    dated = []
    for label in rows:
        try:
            dated.append((datetime.strptime(label, '%B %Y'), label))
        except ValueError:
            continue
    if dated:
        dated.sort(reverse=True)
        return dated[0][1]
    return current


def _month_key(label):
    try:
        parsed = datetime.strptime(label, '%B %Y')
        return '%04d-%02d' % (parsed.year, parsed.month)
    except (TypeError, ValueError):
        return None


def _attendance_stats(target_type, start, end):
    query = AttendanceModel.query.filter(
        AttendanceModel.target_type == target_type,
        AttendanceModel.date >= start,
        AttendanceModel.date <= end)
    total = query.count()
    present = query.filter(AttendanceModel.status == 'Present').count()
    return {
        'total': total,
        'present': present,
        'pct': round(present / total * 100, 1) if total else None,
    }


def _fee_totals(month_label_value):
    row = (db.session.query(
               func.coalesce(func.sum(func.min(FeeRecordModel.amount_paid,
                                               FeeRecordModel.amount_due)), 0.0),
               func.coalesce(func.sum(func.max(FeeRecordModel.amount_due -
                                               FeeRecordModel.amount_paid, 0.0)), 0.0))
           .join(StudentModel, StudentModel.id == FeeRecordModel.student_id)
           .filter(StudentModel.is_active.is_(True),
                   FeeRecordModel.month_year == month_label_value)
           .one())
    return float(row[0] or 0.0), float(row[1] or 0.0)


def _fee_chart(month_label_value):
    rows = (db.session.query(
                ClassModel.name,
                func.coalesce(func.sum(func.min(FeeRecordModel.amount_paid,
                                                FeeRecordModel.amount_due)), 0.0),
                func.coalesce(func.sum(func.max(FeeRecordModel.amount_due -
                                                FeeRecordModel.amount_paid, 0.0)), 0.0))
            .join(StudentModel, StudentModel.class_id == ClassModel.id)
            .join(FeeRecordModel, FeeRecordModel.student_id == StudentModel.id)
            .filter(StudentModel.is_active.is_(True),
                    FeeRecordModel.month_year == month_label_value)
            .group_by(ClassModel.id).order_by(ClassModel.id).all())
    return {
        'labels': [row[0] for row in rows],
        'collected': [float(row[1] or 0) for row in rows],
        'outstanding': [float(row[2] or 0) for row in rows],
    }


def _class_performance():
    from app.routes.reports import _class_results_evaluation

    rows = []
    for class_obj in ClassModel.query.order_by(ClassModel.id).all():
        _, _tests, matrix_data, _ = _class_results_evaluation(class_obj.id)
        scored = [row['percentage'] for row in matrix_data if row['total_max'] > 0]
        rows.append({
            'name': class_obj.name,
            'students': len(matrix_data),
            'avg': round(sum(scored) / len(scored), 1) if scored else None,
        })
    return rows


def _attendance_trend(start, end):
    expr = func.strftime('%d', AttendanceModel.date)
    rows = (db.session.query(expr.label('bucket'),
                             func.count(AttendanceModel.id),
                             func.sum(case((AttendanceModel.status == 'Present', 1),
                                           else_=0)))
            .filter(AttendanceModel.target_type == 'student',
                    AttendanceModel.date >= start,
                    AttendanceModel.date <= end)
            .group_by('bucket').order_by('bucket').all())
    labels, values = [], []
    for bucket, total, present in rows:
        labels.append(str(int(bucket)))
        values.append(round((present or 0) / total * 100, 1) if total else 0)
    return {'labels': labels, 'values': values}


def _executive_context():
    report_month = _reporting_month()
    key = _month_key(report_month)
    start, end = month_bounds(key) if key else (None, None)

    collected, outstanding = _fee_totals(report_month)
    snapshot = month_snapshot(key) if key else None
    if start:
        students_att = _attendance_stats('student', start, end)
        staff_att = _attendance_stats('teacher', start, end)
    else:
        students_att = {'total': 0, 'present': 0, 'pct': None}
        staff_att = {'total': 0, 'present': 0, 'pct': None}

    performance = _class_performance()
    scored = [row['avg'] for row in performance if row['avg'] is not None]
    class_avg = round(sum(scored) / len(scored), 1) if scored else None

    school = SchoolSettings.query.first()
    session_label = ((school.academic_session or '').strip()
                     if school and school.academic_session else 'N/A')

    return {
        'report_month': report_month,
        'today': date.today(),
        'session_label': session_label,
        'kpis': {
            'collected': collected,
            'outstanding': outstanding,
            'class_avg': class_avg,
            'students_att': students_att['pct'],
            'staff_att': staff_att['pct'],
            'active_students': StudentModel.query.filter_by(is_active=True).count(),
            'active_staff': TeacherModel.query.filter_by(is_active=True).count(),
        },
        'finance': {
            'collected': collected,
            'outstanding': outstanding,
            'expenses': (snapshot or {}).get('expenses', 0.0),
            'payroll': (snapshot or {}).get('payroll', 0.0),
            'net': (snapshot or {}).get('net', 0.0),
        },
        'performance': performance,
        'attendance_stats': {'students': students_att, 'staff': staff_att},
        'charts': {
            'fee': _fee_chart(report_month),
            'academic': {
                'labels': [row['name'] for row in performance],
                'values': [row['avg'] if row['avg'] is not None else 0
                           for row in performance],
            },
            'attendance': _attendance_trend(start, end) if start else {'labels': [], 'values': []},
        },
    }


@main.route('/executive')
@role_required(ROLE_ADMIN, ROLE_OWNER)
def executive_dashboard():
    """Read-only executive overview for the Principal / Owner."""
    return render_template('executive.html', **_executive_context())


@main.route('/executive/summary.pdf')
@role_required(ROLE_ADMIN, ROLE_OWNER)
def executive_summary_pdf():
    """One-click printable executive summary PDF (read-only GET)."""
    context = _executive_context()
    output = _build_executive_pdf(context, current_app.root_path)
    log_action('export', entity_type='ExecutiveSummary',
               summary='Executive summary PDF downloaded (%s)'
                       % context['report_month'])
    db.session.commit()
    return send_file(output, mimetype='application/pdf', as_attachment=True,
                     download_name='executive_summary_%s.pdf'
                                   % date.today().strftime('%Y-%m-%d'))


def _money(value):
    return '{:,.2f}'.format(float(value or 0))


def _build_executive_pdf(context, root_path=None):
    from xml.sax.saxutils import escape

    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.platypus import (Paragraph, SimpleDocTemplate, Spacer, Table,
                                    TableStyle)

    from app.services.id_documents import school_branding

    school = school_branding(root_path)
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('ETitle', parent=styles['Heading1'], fontSize=16,
                                 alignment=1, fontName='Helvetica-Bold',
                                 textColor=colors.HexColor('#0f172a'), spaceAfter=2)
    sub_style = ParagraphStyle('ESub', parent=styles['Normal'], fontSize=9,
                               alignment=1, textColor=colors.HexColor('#475569'),
                               spaceAfter=6)
    section_style = ParagraphStyle('ESection', parent=styles['Normal'], fontSize=11,
                                   fontName='Helvetica-Bold',
                                   textColor=colors.HexColor('#0f172a'),
                                   spaceBefore=12, spaceAfter=4)

    kpis = context['kpis']
    finance = context['finance']

    story = [Paragraph(escape(str(school['name'])), title_style),
             Paragraph('EXECUTIVE SUMMARY &mdash; %s'
                       % escape(context['report_month']).upper(), sub_style)]
    tail = ' | '.join([part for part in (school.get('address') or '',
                                         school.get('phone') or '') if part])
    if tail:
        story.append(Paragraph(escape(tail), sub_style))
    story.append(Paragraph(
        'Prepared for the Principal / Owner &middot; Academic session %s &middot; '
        'Generated on %s' % (escape(context['session_label']),
                             context['today'].strftime('%d %b %Y')), sub_style))

    headline_rows = [
        ['Fee Collections (%s)' % context['report_month'],
         'Rs. %s' % _money(kpis['collected'])],
        ['Outstanding Dues', 'Rs. %s' % _money(kpis['outstanding'])],
        ['Average Class Performance',
         ('%s%%' % kpis['class_avg']) if kpis['class_avg'] is not None else '—'],
        ['Student Attendance',
         ('%s%%' % kpis['students_att']) if kpis['students_att'] is not None else '—'],
        ['Staff Attendance',
         ('%s%%' % kpis['staff_att']) if kpis['staff_att'] is not None else '—'],
    ]
    headline = Table(headline_rows, colWidths=[330, 222])
    headline.setStyle(TableStyle([
        ('FONTSIZE', (0, 0), (-1, -1), 10.5),
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
        ('GRID', (0, 0), (-1, -1), 0.4, colors.HexColor('#cbd5e0')),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('LEFTPADDING', (0, 0), (-1, -1), 9),
        ('RIGHTPADDING', (0, 0), (-1, -1), 9),
        ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#f8fafc')),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTNAME', (1, 0), (1, -1), 'Helvetica-Bold'),
    ]))
    story.append(Paragraph('At a glance', section_style))
    story.append(headline)

    money_rows = [
        ['Fee Collections', 'Rs. %s' % _money(finance['collected'])],
        ['Operational Expenses', 'Rs. %s' % _money(finance['expenses'])],
        ['Staff Payroll (Net)', 'Rs. %s' % _money(finance['payroll'])],
        ['Net Position (Collections - Expenses - Payroll)',
         'Rs. %s' % _money(finance['net'])],
    ]
    money_table = Table(money_rows, colWidths=[330, 222])
    money_table.setStyle(TableStyle([
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
        ('GRID', (0, 0), (-1, -1), 0.4, colors.HexColor('#cbd5e0')),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('LEFTPADDING', (0, 0), (-1, -1), 9),
        ('RIGHTPADDING', (0, 0), (-1, -1), 9),
        ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#eef2f7')),
    ]))
    story.append(Paragraph('Financial health', section_style))
    story.append(money_table)

    story.append(Paragraph('Class performance', section_style))
    perf_rows = [['Class', 'Students', 'Average %']]
    for row in context['performance']:
        perf_rows.append([row['name'], str(row['students']),
                          ('%s%%' % row['avg']) if row['avg'] is not None else '—'])
    if len(perf_rows) == 1:
        perf_rows.append(['No classes recorded', '', ''])
    perf_table = Table(perf_rows, colWidths=[300, 102, 150])
    perf_table.setStyle(TableStyle([
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1f2937')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('ALIGN', (1, 0), (-1, -1), 'CENTER'),
        ('GRID', (0, 0), (-1, -1), 0.4, colors.HexColor('#cbd5e0')),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(perf_table)

    students_att = context['attendance_stats']['students']
    staff_att = context['attendance_stats']['staff']
    story.append(Paragraph('Attendance detail', section_style))
    att_rows = [
        ['Students present', '%d of %d marked days (%s%%)'
         % (students_att['present'], students_att['total'],
            students_att['pct'] if students_att['pct'] is not None else '—')],
        ['Staff present', '%d of %d marked days (%s%%)'
         % (staff_att['present'], staff_att['total'],
            staff_att['pct'] if staff_att['pct'] is not None else '—')],
        ['Active students / staff', '%d students · %d staff'
         % (context['kpis']['active_students'], context['kpis']['active_staff'])],
    ]
    att_table = Table(att_rows, colWidths=[200, 352])
    att_table.setStyle(TableStyle([
        ('FONTSIZE', (0, 0), (-1, -1), 9.5),
        ('GRID', (0, 0), (-1, -1), 0.4, colors.HexColor('#cbd5e0')),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('LEFTPADDING', (0, 0), (-1, -1), 9),
        ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#f8fafc')),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
    ]))
    story.append(att_table)

    story.append(Spacer(1, 14))
    story.append(Paragraph(
        'Read-only executive report &mdash; figures are drawn live from the school '
        'database; attendance covers days with marked attendance for %s.'
        % escape(context['report_month']),
        ParagraphStyle('EFoot', parent=styles['Normal'], fontSize=8,
                       textColor=colors.HexColor('#64748b'))))

    output = io.BytesIO()
    doc = SimpleDocTemplate(output, pagesize=letter, rightMargin=40, leftMargin=40,
                            topMargin=34, bottomMargin=30)
    doc.build(story)
    output.seek(0)
    return output
