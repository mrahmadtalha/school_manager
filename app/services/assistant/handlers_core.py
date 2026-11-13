"""Handlers: help, the daily summary, and student / teacher / class counts."""

from app.database import db
from app.models import ClassModel, StudentModel, TeacherModel
from app.services import assistant_intents as catalogue
from app.services.payroll_service import current_month_key

from .formatting import _link, _links, _reply, rs


def h_help(ctx):
    examples = catalogue.STARTER_QUESTIONS
    text = ctx.t(
        'I am the offline school assistant. I answer from your own data, with '
        'no internet and no AI service. I can only read data, never change it.\n'
        'You can ask about: today\'s attendance (with parents\' phone numbers), '
        'fee collection and who paid, defaulters (also class-wise), a student\'s '
        'dues, low-attendance students, expenses, salary, profit, comparison '
        'with last month, new admissions, birthdays, a teacher\'s details, '
        '"what needs attention today", and how to do common tasks.\n'
        'I remember the last answer, so you can follow up with short questions '
        'like "aur kal?" or "uska phone number?".',
        'Main offline school assistant hoon. Aap ke apne data se jawab deta '
        'hoon, internet ya kisi AI service ke baghair. Main sirf data parhta '
        'hoon, kuch badalta nahi.\n'
        'Aap poochh sakte hain: aaj ki attendance (walid ke phone ke saath), '
        'fees ki wasooli aur kis ne fees di, defaulters (class wise bhi), kisi '
        'student ka baqaya, kam attendance wale students, kharcha, salary, '
        'profit, pichle mahine se muqabla, naye admissions, birthdays, kisi '
        'teacher ki maloomat, "aaj kya kaam baqi hai", aur aam kaam kaise '
        'karte hain.\n'
        'Main pichla jawab yaad rakhta hoon, is liye "aur kal?" ya "uska phone '
        'number?" jaisay chhotay sawal bhi poochh sakte hain.')
    return _reply('help', text, suggestions=examples)


def h_today_summary(ctx):
    from app.services import dashboard_service
    from app.services.financial_summary import month_snapshot
    counts = dashboard_service.active_counts()
    attendance = dashboard_service.today_attendance()['student']
    snapshot = month_snapshot(current_month_key())
    absent = attendance['counts']['Absent']
    if attendance['marked']:
        att_line = ctx.t(
            'Attendance today: %d present, %d absent, %d late, %d on leave.',
            'Aaj ki attendance: %d hazir, %d ghair hazir, %d late, %d chutti par.'
        ) % (attendance['counts']['Present'], absent,
             attendance['counts']['Late'], attendance['counts']['Leave'])
    else:
        att_line = ctx.t('Attendance has not been marked today.',
                         'Aaj ki attendance abhi mark nahi hui.')
    text = '\n'.join([
        ctx.t('%d students, %d teachers, %d classes.',
              '%d students, %d teachers, %d classes.') % (
                  counts['students'], counts['teachers'], counts['classes']),
        att_line,
        ctx.t('Fees collected this month: %s.',
              'Is mahine ki fees wasooli: %s.') % rs(snapshot['fee_income']),
        ctx.t('Total fees outstanding: %s.',
              'Kul baqaya fees: %s.') % rs(snapshot['fees_remaining']),
        ctx.t('Expenses this month: %s.',
              'Is mahine ka kharcha: %s.') % rs(snapshot['expenses']),
    ])
    return _reply('today_summary', text,
                  links=_links(_link('Dashboard', 'main.dashboard')),
                  suggestions=['aaj kitne students absent hain?',
                               'defaulters kaun hain?'])


def h_students_count(ctx):
    query = StudentModel.query.filter_by(is_active=True)
    cls = ctx.class_obj
    if cls:
        query = query.filter(StudentModel.class_id == cls.id)
    if ctx.gender:
        query = query.filter(StudentModel.gender == ctx.gender)
    total = query.count()

    if ctx.gender and not cls:
        word = ctx.t('boys' if ctx.gender == 'Male' else 'girls',
                     'larkay' if ctx.gender == 'Male' else 'larkiyan')
        text = ctx.t('There are %d %s in the school.',
                     'School mein %d %s hain.') % (total, word)
        unset = StudentModel.query.filter(
            StudentModel.is_active.is_(True),
            StudentModel.gender.is_(None)).count()
        if unset:
            text += ' ' + ctx.t('(%d students have no gender recorded.)',
                                '(%d students ka gender darj nahi.)') % unset
        return _reply('students_count', text,
                      links=_links(_link('Students', 'main.students_list')))
    if cls:
        text = ctx.t('%s has %d active students.',
                     '%s mein %d active students hain.') % (cls.name, total)
        if ctx.gender:
            text = ctx.t('%s has %d %s.', '%s mein %d %s hain.') % (
                cls.name, total,
                ctx.t('boys' if ctx.gender == 'Male' else 'girls',
                      'larkay' if ctx.gender == 'Male' else 'larkiyan'))
        return _reply('students_count', text,
                      links=_links(_link('Students', 'main.students_list',
                                         class_id=cls.id)))

    male = StudentModel.query.filter_by(is_active=True, gender='Male').count()
    female = StudentModel.query.filter_by(is_active=True,
                                          gender='Female').count()
    text = ctx.t('The school has %d active students (%d boys, %d girls, %d '
                 'not specified).',
                 'School mein %d active students hain (%d larkay, %d '
                 'larkiyan, %d ka zikr nahi).') % (
                     total, male, female, total - male - female)
    return _reply('students_count', text,
                  links=_links(_link('Students', 'main.students_list')),
                  suggestions=['class wise students'])


def h_teachers_count(ctx):
    total = TeacherModel.query.filter_by(is_active=True).count()
    text = ctx.t('There are %d active teachers.',
                 'School mein %d active teachers hain.') % total
    return _reply('teachers_count', text,
                  links=_links(_link('Teachers', 'main.teachers_list')))


def h_class_strength(ctx):
    rows = []
    counts = dict(db.session.query(StudentModel.class_id,
                                   db.func.count(StudentModel.id))
                  .filter(StudentModel.is_active.is_(True))
                  .group_by(StudentModel.class_id).all())
    classes = ClassModel.query.order_by(ClassModel.id).all()
    for cls in classes:
        rows.append([cls.name, len(cls.sections), counts.get(cls.id, 0)])
    if not classes:
        return _reply('class_strength', ctx.t('No classes have been created yet.',
                                              'Abhi koi class nahi bani.'))
    text = ctx.t('There are %d classes and %d active students.',
                 '%d classes hain aur %d active students.') % (
                     len(classes), sum(r[2] for r in rows))
    table = {'columns': [ctx.t('Class', 'Class'),
                         ctx.t('Sections', 'Sections'),
                         ctx.t('Students', 'Students')], 'rows': rows}
    return _reply('class_strength', text, table=table,
                  links=_links(_link('Classes & Subjects', 'main.classes_list')))
