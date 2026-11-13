"""Handlers: a student's attendance, the class attendance list, and who is below the at-risk threshold."""

from datetime import date

from app.database import db
from app.models import AttendanceModel, ClassModel, StudentModel, TeacherModel
from app.services.payroll_service import month_bounds, month_label

from .constants import AT_RISK_PERCENT, MAX_LIST_ROWS
from .formatting import _link, _links, _period_label, _reply
from .lookup import _ask_which_student, _students_by_ids


def _student_attendance(ctx):
    students = _students_by_ids(ctx.students)
    if len(students) > 1 and not ctx.exact_student:
        return _ask_which_student(ctx, students, 'attendance')
    student = students[0]
    start, end = month_bounds(ctx.month)
    rows = (db.session.query(AttendanceModel.status,
                             db.func.count(AttendanceModel.id))
            .filter(AttendanceModel.target_type == 'student',
                    AttendanceModel.target_id == student.id,
                    AttendanceModel.date >= start, AttendanceModel.date <= end)
            .group_by(AttendanceModel.status).all())
    counts = {'Present': 0, 'Absent': 0, 'Late': 0, 'Leave': 0}
    counts.update({status: number for status, number in rows
                   if status in counts})
    if not sum(counts.values()):
        text = ctx.t('No attendance has been marked for %s in %s.',
                     '%s ki %s mein koi attendance mark nahi hui.') % (
                         student.student_name, month_label(ctx.month))
    else:
        text = ctx.t(
            '%s in %s: %d present, %d absent, %d late, %d on leave.',
            '%s ki %s mein: %d hazir, %d ghair hazir, %d late, %d chutti.'
        ) % (student.student_name, month_label(ctx.month), counts['Present'],
             counts['Absent'], counts['Late'], counts['Leave'])
    return _reply('attendance', text,
                  links=_links(_link('Daily attendance',
                                     'main.student_attendance')))


def h_attendance(ctx):
    if ctx.students and not ctx.is_teacher:
        return _student_attendance(ctx)
    day = ctx.day or date.today()
    is_today = day == date.today()
    day_word = ctx.t('today' if is_today else 'on %s' % day.strftime('%d %b'),
                     'aaj' if is_today else '%s ko' % day.strftime('%d %b'))

    if ctx.is_teacher:
        base = AttendanceModel.query.filter(
            AttendanceModel.date == day, AttendanceModel.target_type == 'teacher')
        expected = TeacherModel.query.filter_by(is_active=True).count()
        who = ctx.t('teachers', 'teachers')
    else:
        base = AttendanceModel.query.filter(
            AttendanceModel.date == day, AttendanceModel.target_type == 'student')
        expected_query = StudentModel.query.filter_by(is_active=True)
        if ctx.class_obj:
            base = base.join(StudentModel,
                             StudentModel.id == AttendanceModel.target_id
                             ).filter(StudentModel.class_id == ctx.class_obj.id)
            expected_query = expected_query.filter(
                StudentModel.class_id == ctx.class_obj.id)
        expected = expected_query.count()
        who = ctx.t('students', 'students')

    counts = {'Present': 0, 'Absent': 0, 'Late': 0, 'Leave': 0}
    grouped = base.with_entities(AttendanceModel.status,
                                 db.func.count(AttendanceModel.id)
                                 ).group_by(AttendanceModel.status).all()
    for status, number in grouped:
        if status in counts:
            counts[status] = number
    marked = sum(counts.values())
    scope = ctx.class_obj.name + ' ' if ctx.class_obj and not ctx.is_teacher else ''
    links = _links(_link(
        'Teacher attendance' if ctx.is_teacher else 'Daily attendance',
        'main.teacher_attendance' if ctx.is_teacher else 'main.student_attendance'))

    if not marked:
        text = ctx.t('Attendance for %s%s has not been marked %s.',
                     '%s%s ki attendance %s mark nahi hui.') % (
                         scope, who, day_word)
        return _reply('attendance', text, links=links)

    label = {'Present': ctx.t('present', 'hazir'),
             'Absent': ctx.t('absent', 'ghair hazir'),
             'Late': ctx.t('late', 'late'),
             'Leave': ctx.t('on leave', 'chutti par')}
    table = None
    if ctx.status and ctx.status != 'Present':
        if ctx.lang == 'ur':
            text = 'Kul %d %s%s mein se %d %s %s.' % (
                marked, scope, who, counts[ctx.status], label[ctx.status],
                day_word)
        else:
            text = '%d of %d %s%s are %s %s.' % (
                counts[ctx.status], marked, scope, who, label[ctx.status],
                day_word)
        if counts[ctx.status]:
            names = _attendance_names(ctx, day, ctx.status)
            table = {'columns': [ctx.t('Name', 'Naam'),
                                 ctx.t('Class / ID', 'Class / ID'),
                                 ctx.t('Phone', 'Phone')],
                     'rows': names[:MAX_LIST_ROWS]}
            if len(names) > MAX_LIST_ROWS:
                text += ctx.t(' (showing first %d)', ' (pehle %d dikhaye gaye)'
                              ) % MAX_LIST_ROWS
    else:
        text = ctx.t(
            'Attendance %s for %s%s: %d present, %d absent, %d late, %d on '
            'leave (%d marked of %d).',
            'Attendance %s ke liye %s%s: %d hazir, %d ghair hazir, %d late, '
            '%d chutti par (%d mark, kul %d).'
        ) % (day_word, scope, who, counts['Present'], counts['Absent'],
             counts['Late'], counts['Leave'], marked, expected)
    return _reply('attendance', text, table=table, links=links,
                  suggestions=[ctx.t('absent students today',
                                     'aaj kon kon absent hai?')])


def _attendance_names(ctx, day, status):
    rows = []
    if ctx.is_teacher:
        query = (db.session.query(TeacherModel.teacher_name,
                                  TeacherModel.teacher_id_str,
                                  TeacherModel.contact_number)
                 .join(AttendanceModel,
                       AttendanceModel.target_id == TeacherModel.id)
                 .filter(AttendanceModel.target_type == 'teacher',
                         AttendanceModel.date == day,
                         AttendanceModel.status == status)
                 .order_by(TeacherModel.teacher_name))
        return [[name, ident, phone or '-'] for name, ident, phone in query.all()]
    query = (db.session.query(StudentModel.student_name, ClassModel.name,
                              StudentModel.roll_number,
                              StudentModel.guardian_phone)
             .join(AttendanceModel, AttendanceModel.target_id == StudentModel.id)
             .join(ClassModel, ClassModel.id == StudentModel.class_id)
             .filter(AttendanceModel.target_type == 'student',
                     AttendanceModel.date == day,
                     AttendanceModel.status == status))
    if ctx.class_obj:
        query = query.filter(StudentModel.class_id == ctx.class_obj.id)
    for name, class_name, roll, phone in query.order_by(
            ClassModel.name, StudentModel.roll_number).all():
        rows.append([name, '%s (#%s)' % (class_name, roll), phone or '-'])
    return rows


def _is_working_day(day):
    """False on weekends / holidays the school has configured."""
    try:
        from app.models import SchoolSettings
        from app.services.teacher_payroll import get_school_working_days
        settings = SchoolSettings.query.first() or type(
            'DefaultSettings', (), {'weekend_off': True,
                                    'custom_off_days': ''})()
        return day in set(get_school_working_days(day, day, settings))
    except Exception:  # pragma: no cover - never block an answer on this
        return True


def h_low_attendance(ctx):
    from app.services.attendance_service import build_school_attendance_summary
    start, end = month_bounds(ctx.month)
    summary = build_school_attendance_summary(start, end)
    if not summary['taken_dates']:
        return _reply('low_attendance', ctx.t(
            'No attendance has been marked in %s yet.',
            '%s mein abhi tak koi attendance mark nahi hui.')
            % _period_label(ctx),
            links=_links(_link('Daily attendance', 'main.student_attendance')))
    risky = [row for row in summary['matrix_data']
             if row['is_at_risk']
             and (not ctx.class_obj
                  or row['student'].class_id == ctx.class_obj.id)]
    risky.sort(key=lambda row: (row['percentage'], row['student'].student_name))
    scope = (' (%s)' % ctx.class_obj.name) if ctx.class_obj else ''
    if not risky:
        return _reply('low_attendance', ctx.t(
            'Nobody is below %d%% attendance in %s%s.',
            '%s%s mein koi student %d%% attendance se neeche nahi.'
        ) % ((AT_RISK_PERCENT, _period_label(ctx), scope) if ctx.lang == 'en'
             else (_period_label(ctx), scope, AT_RISK_PERCENT)),
            links=_links(_link('Attendance summary',
                               'main.attendance_summary')))
    text = ctx.t(
        '%d students are below %d%% attendance in %s%s.',
        '%s%s mein %d students ki attendance %d%% se kam hai.'
    ) % ((len(risky), AT_RISK_PERCENT, _period_label(ctx), scope)
         if ctx.lang == 'en'
         else (_period_label(ctx), scope, len(risky), AT_RISK_PERCENT))
    if len(risky) > MAX_LIST_ROWS:
        text += ctx.t(' Lowest %d shown.', ' Sab se kam wale %d dikhaye gaye.'
                      ) % MAX_LIST_ROWS
    table = {'columns': [ctx.t('Student', 'Student'), ctx.t('Class', 'Class'),
                         '%', ctx.t('Absent', 'Ghair hazir'),
                         ctx.t('Phone', 'Phone')],
             'rows': [[row['student'].student_name,
                       summary['classes'][row['student'].class_id].name
                       if row['student'].class_id in summary['classes'] else '-',
                       '%.0f%%' % row['percentage'], row['a_count'],
                       row['student'].guardian_phone or '-']
                      for row in risky[:MAX_LIST_ROWS]]}
    return _reply('low_attendance', text, table=table,
                  links=_links(_link('Attendance summary',
                                     'main.attendance_summary')))
