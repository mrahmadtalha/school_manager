"""Handlers: one student's or teacher's profile, birthdays and new admissions."""

from app.models import StudentModel, TeacherModel
from app.services.payroll_service import month_bounds

from .constants import MAX_LIST_ROWS
from .formatting import _json_list, _link, _links, _period_label, _reply, rs
from .lookup import _ask_which_student, _ask_which_teacher, _students_by_ids


def h_student_info(ctx):
    from app.services import fee_ledger
    if not ctx.students and ctx.is_teacher:
        return _reply('student_info', ctx.t(
            'Which teacher? Please type the teacher\'s name, for example '
            '"Sir Ahmed phone number".',
            'Kaunsa teacher? Teacher ka naam likhein, maslan '
            '"Sir Ahmed ka phone number".'))
    if not ctx.students:
        return _reply('student_info', ctx.t(
            'Which student? Please type the student\'s name, for example '
            '"Ali Khan phone number".',
            'Kaunsa student? Student ka naam likhein, maslan '
            '"Ali Khan ka phone number".'))
    students = _students_by_ids(ctx.students)
    if len(students) > 1 and not ctx.exact_student:
        return _ask_which_student(ctx, students, 'student_info')
    student = students[0]
    section = student.section_info.name if student.section_info else '-'
    klass = student.class_info.name if student.class_info else '-'
    due = fee_ledger.student_outstanding_paisa(student.id) / 100.0
    text = ctx.t(
        '%s - class %s, section %s, roll no. %s.\nFather: %s. Guardian '
        'phone: %s.\nFee outstanding: %s.',
        '%s - class %s, section %s, roll no. %s.\nWalid: %s. Guardian '
        'phone: %s.\nBaqaya fees: %s.'
    ) % (student.student_name, klass, section, student.roll_number,
         student.father_name, student.guardian_phone, rs(due))
    return _reply('student_info', text,
                  links=_links(_link('Student report',
                                     'main.student_detailed_report',
                                     id=student.id),
                               _link('Fee ledger', 'main.fee_student_ledger',
                                     student_id=student.id)))


def h_birthdays(ctx):
    from app.services import dashboard_service
    data = dashboard_service.birthdays()
    today_list, soon = data['today'], data['soon']
    rows = []
    for entry in today_list + soon:
        rows.append([entry['name'],
                     ('%s %s' % (entry['kind'], entry['meta'])).strip(),
                     entry['date'].strftime('%d %b'),
                     entry['age'] if entry['age'] else '-'])
    if not data['total_with_dob']:
        return _reply('birthdays', ctx.t(
            'No birthdays are recorded yet. Add a date of birth on a student '
            'or teacher to see them here.',
            'Abhi kisi ki date of birth darj nahi. Student ya teacher mein '
            'date of birth likhein to yahan nazar aayegi.'),
            links=_links(_link('Students', 'main.students_list')))
    if today_list:
        names = ', '.join(entry['name'] for entry in today_list[:5])
        text = ctx.t('Birthday today: %s.', 'Aaj ki birthday: %s.') % names
        if soon:
            text += ' ' + ctx.t('More in the next 7 days are listed below.',
                                'Agle 7 din ki birthdays neeche hain.')
    elif soon:
        text = ctx.t('No birthdays today. %d coming up in the next 7 days.',
                     'Aaj kisi ki birthday nahi. Agle 7 din mein %d hain.'
                     ) % len(soon)
    else:
        text = ctx.t('No birthdays today or in the next 7 days.',
                     'Aaj ya agle 7 din mein kisi ki birthday nahi.')
    table = None
    if rows:
        table = {'columns': [ctx.t('Name', 'Naam'), ctx.t('Who', 'Kaun'),
                             ctx.t('Date', 'Tareekh'), ctx.t('Turns', 'Umar')],
                 'rows': rows[:MAX_LIST_ROWS]}
    return _reply('birthdays', text, table=table,
                  links=_links(_link('Dashboard', 'main.dashboard')))


def h_new_admissions(ctx):
    start, end = month_bounds(ctx.month)
    query = StudentModel.query.filter(StudentModel.admission_date >= start,
                                      StudentModel.admission_date <= end)
    if ctx.class_obj:
        query = query.filter(StudentModel.class_id == ctx.class_obj.id)
    students = query.order_by(StudentModel.admission_date,
                              StudentModel.student_name).all()
    scope = (' (%s)' % ctx.class_obj.name) if ctx.class_obj else ''
    links = _links(_link('Students', 'main.students_list'))
    if not students:
        text = ctx.t('No admissions recorded in %s%s.',
                     '%s%s mein koi admission darj nahi.') % (
                         _period_label(ctx), scope)
        missing = StudentModel.query.filter(
            StudentModel.is_active.is_(True),
            StudentModel.admission_date.is_(None)).count()
        if missing:
            text += ' ' + ctx.t('(%d students have no admission date, so they '
                                'cannot be counted.)',
                                '(%d students ki admission date darj nahi, is '
                                'liye shumar nahi hue.)') % missing
        return _reply('new_admissions', text, links=links)
    text = ctx.t('%d new admissions in %s%s.', '%s%s mein %d naye admissions.'
                 ) % ((len(students), _period_label(ctx), scope)
                      if ctx.lang == 'en'
                      else (_period_label(ctx), scope, len(students)))
    if len(students) > MAX_LIST_ROWS:
        text += ctx.t(' (showing first %d)', ' (pehle %d dikhaye gaye)'
                      ) % MAX_LIST_ROWS
    table = {'columns': [ctx.t('Student', 'Student'), ctx.t('Class', 'Class'),
                         ctx.t('Admitted', 'Dakhla')],
             'rows': [[s.student_name,
                       s.class_info.name if s.class_info else '-',
                       s.admission_date.strftime('%d %b')]
                      for s in students[:MAX_LIST_ROWS]]}
    return _reply('new_admissions', text, table=table, links=links)


def h_teacher_info(ctx):
    if not ctx.teachers:
        return _reply('teacher_info', ctx.t(
            'Which teacher? Please type the teacher\'s name, for example '
            '"Sir Ahmed phone number".',
            'Kaunsa teacher? Teacher ka naam likhein, maslan '
            '"Sir Ahmed ka phone number".'))
    teachers = TeacherModel.query.filter(
        TeacherModel.id.in_(ctx.teachers)).all()
    if len(teachers) > 1 and not ctx.exact_teacher:
        return _ask_which_teacher(ctx, teachers)
    teacher = teachers[0]
    classes = ', '.join(_json_list(teacher.assigned_classes)) \
        or teacher.assigned_class or '-'
    subjects = ', '.join(_json_list(teacher.assigned_subjects)) or '-'
    lines = [ctx.t('%s (%s)%s', '%s (%s)%s') % (
        teacher.teacher_name, teacher.teacher_id_str,
        ' - %s' % teacher.designation if teacher.designation else ''),
        ctx.t('Phone: %s.', 'Phone: %s.') % (teacher.contact_number or '-'),
        ctx.t('Classes: %s. Subjects: %s.', 'Classes: %s. Subjects: %s.'
              ) % (classes, subjects),
        ctx.t('Joined: %s.', 'Shamil hue: %s.') % (
            teacher.joining_date.strftime('%d %b %Y')
            if teacher.joining_date else '-')]
    if set(ctx.tokens) & {'salary', 'salaries', 'tankhwah', 'tankhwa',
                          'tankha', 'wages'}:
        if teacher.salary_type == 'hourly':
            lines.append(ctx.t('Salary: %s per hour.', 'Tankhwah: %s per ghanta.'
                               ) % rs(teacher.hourly_rate))
        else:
            lines.append(ctx.t('Salary: %s per month.', 'Tankhwah: %s mahana.'
                               ) % rs(teacher.monthly_salary or teacher.salary))
    return _reply('teacher_info', '\n'.join(lines),
                  links=_links(_link('Teachers', 'main.teachers_list')))
