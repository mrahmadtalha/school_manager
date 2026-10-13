"""Offline admin assistant (no AI model, no internet, no API).

How it works
------------
1. The question is normalised and split into words.
2. Every word is looked up (exactly, or fuzzily for misspellings) in the
   keyword table of ``assistant_intents.INTENTS``; each intent collects a score.
3. The best-scoring intent wins.  Class, student, date and status are pulled
   out of the question separately ("entities").
4. A handler for that intent reads the numbers through the application's own
   services, so the answer always matches the rest of the software.

The assistant only READS data.  It never creates, edits or deletes anything.
"""
import difflib
import re
import unicodedata
from datetime import date, timedelta

from flask import url_for
from werkzeug.routing import BuildError

from app.database import db
from app.models import (AttendanceModel, ClassModel, StudentModel,
                        TeacherModel)
from app.services import assistant_intents as catalogue
from app.services.payroll_service import (month_bounds, month_label,
                                          shift_month, current_month_key)

MAX_QUESTION_LENGTH = 300
MAX_LIST_ROWS = 15

MONTHS = {
    'january': 1, 'february': 2, 'march': 3, 'april': 4, 'may': 5, 'june': 6,
    'july': 7, 'august': 8, 'september': 9, 'october': 10, 'november': 11,
    'december': 12,
    'jan': 1, 'feb': 2, 'apr': 4, 'jun': 6, 'jul': 7, 'aug': 8, 'sep': 9,
    'sept': 9, 'oct': 10, 'nov': 11, 'dec': 12,
}
PREVIOUS_WORDS = {'pichle', 'pichla', 'pichlay', 'pichli', 'previous', 'last',
                  'guzishta', 'guzra', 'guzri'}
MONTH_WORDS = {'mahine', 'mahina', 'month', 'mah', 'maheena', 'maheene'}
THIS_WORDS = {'is', 'this', 'isi', 'current', 'maujooda', 'iss'}
TODAY_WORDS = {'aaj', 'today', 'ajj', 'آج'}
YESTERDAY_WORDS = {'kal', 'yesterday', 'کل'}
TEACHER_WORDS = {'teacher', 'teachers', 'ustad', 'ustaad', 'asatza',
                 'asatiza', 'staff', 'استاد', 'اساتذہ'}
MALE_WORDS = {'boys', 'boy', 'larkay', 'larke', 'ladkay', 'ladke', 'larka',
              'male'}
FEMALE_WORDS = {'girls', 'girl', 'larkiyan', 'ladkiyan', 'larki', 'ladki',
                'female'}


# --------------------------------------------------------------------------- #
# Text helpers
# --------------------------------------------------------------------------- #

def normalize(text):
    text = unicodedata.normalize('NFKC', text or '').lower()
    text = text.replace("'", '').replace('\u2019', '')
    text = re.sub(r'[^\w\s]', ' ', text, flags=re.UNICODE)
    return re.sub(r'\s+', ' ', text).strip()


def rs(value):
    return 'Rs {:,.0f}'.format(value or 0)


def _link(label, endpoint, **values):
    try:
        return {'label': label, 'url': url_for(endpoint, **values)}
    except BuildError:
        return None


def _links(*items):
    return [item for item in items if item]


# --------------------------------------------------------------------------- #
# Keyword scoring
# --------------------------------------------------------------------------- #

_VOCAB = None
_FUZZY_KEYS = None
_HOW_FUZZY = None


def _vocab():
    """{keyword: {intent_id: weight}} built once from the catalogue."""
    global _VOCAB, _FUZZY_KEYS, _HOW_FUZZY
    if _VOCAB is None:
        vocab = {}
        for intent in catalogue.INTENTS:
            for word, weight in intent['keywords'].items():
                vocab.setdefault(word, {})[intent['id']] = weight
        _VOCAB = vocab
        _FUZZY_KEYS = [key for key in vocab if len(key) >= 5 and key.isascii()]
        _HOW_FUZZY = [key for key in catalogue.HOW_MARKERS
                      if len(key) >= 5 and key.isascii()]
    return _VOCAB


def _match_key(token):
    """Exact keyword, else the closest keyword for a misspelt word, else None."""
    vocab = _vocab()
    if token in vocab:
        return token
    if len(token) >= 5 and token.isascii():
        close = difflib.get_close_matches(token, _FUZZY_KEYS, n=1, cutoff=0.84)
        if close:
            return close[0]
    return None


def _has_how_marker(tokens, norm):
    _vocab()
    for token in tokens:
        if token in catalogue.HOW_MARKERS:
            return True
        if len(token) >= 5 and token.isascii() and difflib.get_close_matches(
                token, _HOW_FUZZY, n=1, cutoff=0.86):
            return True
    return 'how to' in norm


def score_intents(tokens, norm, has_how):
    """Return ``{intent_id: score}`` for every intent with a non-zero score."""
    vocab = _vocab()
    scores = {}
    seen = set()
    for token in tokens:
        key = _match_key(token)
        if key is None or key in seen:
            continue
        seen.add(key)
        for intent_id, weight in vocab[key].items():
            scores[intent_id] = scores.get(intent_id, 0) + weight

    padded = ' %s ' % norm
    for intent in catalogue.INTENTS:
        for phrase, weight in intent.get('phrases', {}).items():
            if ' %s ' % phrase in padded:
                scores[intent['id']] = scores.get(intent['id'], 0) + weight

    # "How do I ...?" guides need a how-marker; data answers step back when one
    # is present and a guide matches.
    guide_ok = False
    for intent in catalogue.INTENTS:
        if not intent.get('howto'):
            continue
        if not has_how:
            scores.pop(intent['id'], None)
        elif scores.get(intent['id'], 0) >= intent['min_score']:
            guide_ok = True
    if guide_ok:
        for intent in catalogue.INTENTS:
            if not intent.get('howto') and intent['id'] in scores:
                scores[intent['id']] *= 0.4
    return scores


# --------------------------------------------------------------------------- #
# Entity extraction
# --------------------------------------------------------------------------- #

class Ctx:
    """Everything the handlers need to know about one question."""

    def __init__(self, text):
        self.raw = (text or '').strip()[:MAX_QUESTION_LENGTH]
        self.norm = normalize(self.raw)
        self.tokens = self.norm.split()
        token_set = set(self.tokens)
        self.lang = 'ur' if (token_set & catalogue.URDU_MARKERS or
                             re.search(r'[\u0600-\u06FF]', self.raw)) else 'en'
        self.is_teacher = bool(token_set & TEACHER_WORDS)
        self.gender = ('Male' if token_set & MALE_WORDS else
                       'Female' if token_set & FEMALE_WORDS else None)
        self.status = self._status(token_set)
        self.day = self._day(token_set)
        self.month, self.month_explicit = self._month(token_set)
        self.class_obj = None
        self.students = []
        self.exact_student = False

    def t(self, en, ur):
        return ur if self.lang == 'ur' else en

    @staticmethod
    def _status(tokens):
        if tokens & {'absent', 'absentees', 'ghayab', 'ghair', 'gair', 'غیر'}:
            return 'Absent'
        if tokens & {'late', 'laate'}:
            return 'Late'
        if tokens & {'leave', 'chutti'}:
            return 'Leave'
        if tokens & {'present', 'hazir', 'حاضر'}:
            return 'Present'
        return None

    @staticmethod
    def _day(tokens):
        if tokens & YESTERDAY_WORDS:
            return date.today() - timedelta(days=1)
        if tokens & TODAY_WORDS:
            return date.today()
        return None

    def _month(self, tokens):
        """-> ('YYYY-MM', explicit?) ; defaults to the current month."""
        current = current_month_key()
        year_match = re.search(r'\b(20\d{2})\b', self.norm)
        year = int(year_match.group(1)) if year_match else None
        for index, token in enumerate(self.tokens):
            number = MONTHS.get(token)
            if not number:
                continue
            following = self.tokens[index + 1] if index + 1 < len(self.tokens) else ''
            if token == 'may' and following in {'i', 'you', 'we', 'be', 'not'}:
                continue    # the English word "may", not the month
            today = date.today()
            use_year = year or today.year
            if not year and number > today.month:
                use_year -= 1
            return '%04d-%02d' % (use_year, number), True
        if tokens & PREVIOUS_WORDS and tokens & MONTH_WORDS:
            return shift_month(current, -1), True
        if tokens & MONTH_WORDS:
            return current, True
        return current, False


def _find_class(ctx):
    classes = ClassModel.query.all()
    if not classes:
        return None
    padded = ' %s ' % ctx.norm
    for cls in sorted(classes, key=lambda c: -len(c.name or '')):
        name = normalize(cls.name)
        if name and ' %s ' % name in padded:
            return cls
    numbers = set(re.findall(
        r'(?:class|cls|jamaat|jamat|grade|std|standard)\s*(\d{1,2})', ctx.norm))
    numbers |= set(re.findall(r'\b(\d{1,2})(?:st|nd|rd|th)\b', ctx.norm))
    if numbers:
        for cls in classes:
            digits = re.findall(r'\d+', cls.name or '')
            if digits and digits[0] in numbers:
                return cls
    generic = {'class', 'grade', 'std', 'standard'}
    token_set = set(ctx.tokens)
    for cls in classes:
        for word in normalize(cls.name).split():
            if len(word) >= 3 and word.isalpha() and word not in generic \
                    and word in token_set:
                return cls
    return None


def _find_students(ctx):
    """Active students whose name appears in the question."""
    vocab = _vocab()
    candidates = [t for t in ctx.tokens
                  if len(t) >= 3 and t.isalpha()
                  and t not in catalogue.STOPWORDS and t not in vocab
                  and t not in catalogue.HOW_MARKERS
                  and t not in MONTHS and t not in TODAY_WORDS
                  and t not in YESTERDAY_WORDS and t not in PREVIOUS_WORDS
                  and t not in MONTH_WORDS and t not in THIS_WORDS]
    if not candidates:
        return [], False
    rows = (StudentModel.query.filter_by(is_active=True)
            .with_entities(StudentModel.id, StudentModel.student_name).all())
    by_token = {}
    names = {}
    for student_id, name in rows:
        tokens = normalize(name).split()
        names[student_id] = ' '.join(tokens)
        for token in tokens:
            by_token.setdefault(token, set()).add(student_id)

    padded = ' %s ' % ctx.norm
    exact = [sid for sid, name in names.items()
             if len(name.split()) >= 2 and ' %s ' % name in padded]
    if exact:
        return exact, True

    hits = [t for t in candidates if t in by_token]
    if not hits:
        return [], False
    matching = set.intersection(*(by_token[t] for t in hits))
    if matching:
        return sorted(matching), False
    # Words belong to different students: keep the best-covered ones.
    counts = {}
    for token in hits:
        for sid in by_token[token]:
            counts[sid] = counts.get(sid, 0) + 1
    top = max(counts.values())
    return sorted(sid for sid, c in counts.items() if c == top), False


# --------------------------------------------------------------------------- #
# Answer helpers
# --------------------------------------------------------------------------- #

def _reply(intent, text, *, table=None, links=None, suggestions=None):
    return {
        'intent': intent,
        'answer': text,
        'table': table,
        'links': links or [],
        'suggestions': suggestions or [],
    }


def _period_label(ctx):
    return month_label(ctx.month)


def _students_by_ids(ids):
    return StudentModel.query.filter(StudentModel.id.in_(ids)).all()


# --------------------------------------------------------------------------- #
# Handlers
# --------------------------------------------------------------------------- #

def h_help(ctx):
    examples = catalogue.STARTER_QUESTIONS
    text = ctx.t(
        'I am the offline school assistant. I answer from your own data, with '
        'no internet and no AI service. I can only read data, never change it.\n'
        'You can ask about: today\'s attendance, fee collection, defaulters, a '
        'student\'s dues, expenses, salary, profit, student/teacher counts, and '
        'how to do common tasks.',
        'Main offline school assistant hoon. Aap ke apne data se jawab deta '
        'hoon, internet ya kisi AI service ke baghair. Main sirf data parhta '
        'hoon, kuch badalta nahi.\n'
        'Aap poochh sakte hain: aaj ki attendance, fees ki wasooli, defaulters, '
        'kisi student ka baqaya, kharcha, salary, profit, students/teachers ki '
        'tadad, aur aam kaam kaise karte hain.')
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
                                 ctx.t('Class / ID', 'Class / ID')],
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
                                  TeacherModel.teacher_id_str)
                 .join(AttendanceModel,
                       AttendanceModel.target_id == TeacherModel.id)
                 .filter(AttendanceModel.target_type == 'teacher',
                         AttendanceModel.date == day,
                         AttendanceModel.status == status)
                 .order_by(TeacherModel.teacher_name))
        return [[name, ident] for name, ident in query.all()]
    query = (db.session.query(StudentModel.student_name, ClassModel.name,
                              StudentModel.roll_number)
             .join(AttendanceModel, AttendanceModel.target_id == StudentModel.id)
             .join(ClassModel, ClassModel.id == StudentModel.class_id)
             .filter(AttendanceModel.target_type == 'student',
                     AttendanceModel.date == day,
                     AttendanceModel.status == status))
    if ctx.class_obj:
        query = query.filter(StudentModel.class_id == ctx.class_obj.id)
    for name, class_name, roll in query.order_by(ClassModel.name,
                                                 StudentModel.roll_number).all():
        rows.append([name, '%s (#%s)' % (class_name, roll)])
    return rows


def h_fees_collected(ctx):
    from app.services.financial_summary import collection_split, fee_collections
    if ctx.day and not ctx.month_explicit:
        start = end = ctx.day
        label = ctx.t('today' if ctx.day == date.today() else
                      'on %s' % ctx.day.strftime('%d %b'),
                      'aaj' if ctx.day == date.today() else
                      '%s ko' % ctx.day.strftime('%d %b'))
        total = fee_collections(start, end)
        text = ctx.t('Fees collected %s: %s.', 'Fees wasooli %s: %s.') % (
            label, rs(total))
    else:
        start, end = month_bounds(ctx.month)
        total = fee_collections(start, end)
        split = collection_split(ctx.month)
        text = ctx.t(
            'Fees collected in %s: %s (current-month fees %s, arrears %s).',
            '%s mein fees wasooli: %s (isi mahine ki %s, purana baqaya %s).'
        ) % (_period_label(ctx), rs(total), rs(split['current']),
             rs(split['arrears']))
    return _reply('fees_collected', text,
                  links=_links(_link('Fees Management', 'main.fees_list'),
                               _link('Financial Overview',
                                     'main.financials_summary')),
                  suggestions=[ctx.t('defaulters', 'defaulters kaun hain?')])


def h_fees_due(ctx):
    from app.services import fee_ledger
    from app.services.financial_summary import student_outstanding_rows

    if ctx.students:
        students = _students_by_ids(ctx.students)
        if len(students) > 1 and not ctx.exact_student:
            return _ask_which_student(ctx, students, 'fees_due')
        student = students[0]
        total = fee_ledger.student_outstanding_paisa(student.id) / 100.0
        months = fee_ledger.student_dues_months(student.id)
        klass = student.class_info.name if student.class_info else '-'
        if total <= 0:
            text = ctx.t('%s (%s) has no outstanding fees.',
                         '%s (%s) ka koi baqaya nahi.') % (
                             student.student_name, klass)
            table = None
        else:
            text = ctx.t('%s (%s) owes %s in total.',
                         '%s (%s) ka kul baqaya %s hai.') % (
                             student.student_name, klass, rs(total))
            table = {'columns': [ctx.t('Month', 'Mahina'),
                                 ctx.t('Due', 'Baqaya')],
                     'rows': [[m, rs(v)] for m, v in months]}
        return _reply('fees_due', text, table=table,
                      links=_links(_link('Fee ledger', 'main.fee_student_ledger',
                                         student_id=student.id)))

    class_id = ctx.class_obj.id if ctx.class_obj else None
    month_key = ctx.month if ctx.month_explicit else None
    rows = student_outstanding_rows(class_id=class_id, month_year=month_key)
    scope = ''
    if ctx.class_obj:
        scope += ' %s' % ctx.class_obj.name
    if month_key:
        scope += ' (%s)' % month_label(month_key)
    if not rows:
        return _reply('fees_due', ctx.t('No outstanding fees%s.',
                                        'Koi baqaya fees nahi%s.') % scope,
                      links=_links(_link('Fees Management', 'main.fees_list')))
    total = sum(item['outstanding'] for item in rows)
    text = ctx.t('%d students owe %s%s.', '%d students ka baqaya %s hai%s.') % (
        len(rows), rs(total), scope)
    if len(rows) > MAX_LIST_ROWS:
        text += ctx.t(' Top %d shown.', ' Sab se zyada wale %d dikhaye gaye.'
                      ) % MAX_LIST_ROWS
    table = {'columns': [ctx.t('Student', 'Student'), ctx.t('Class', 'Class'),
                         ctx.t('Due', 'Baqaya')],
             'rows': [[item['student'].student_name, item['class_name'],
                       rs(item['outstanding'])]
                      for item in rows[:MAX_LIST_ROWS]]}
    return _reply('fees_due', text, table=table,
                  links=_links(_link('Student dues',
                                     'main.financials_student_outstanding'),
                               _link('Fees Management', 'main.fees_list')))


def _ask_which_student(ctx, students, intent):
    shown = students[:8]
    text = ctx.t('I found %d students with that name. Which one do you mean?',
                 'Is naam ke %d students mile hain. Kaunsa chahiye?'
                 ) % len(students)
    table = {'columns': [ctx.t('Student', 'Student'), ctx.t('Class', 'Class'),
                         ctx.t('Father', 'Walid')],
             'rows': [[s.student_name,
                       s.class_info.name if s.class_info else '-',
                       s.father_name] for s in shown]}
    suggestions = [s.student_name for s in shown]
    return _reply(intent, text, table=table, suggestions=suggestions)


def h_expenses(ctx):
    from app.services.financial_summary import (expense_breakdown,
                                                expenses_total, month_snapshot)
    if ctx.day and not ctx.month_explicit:
        total = expenses_total(ctx.day, ctx.day)
        label = ctx.t('today' if ctx.day == date.today() else
                      'on %s' % ctx.day.strftime('%d %b'),
                      'aaj' if ctx.day == date.today() else
                      '%s ko' % ctx.day.strftime('%d %b'))
        text = ctx.t('Expenses %s: %s.', 'Kharcha %s: %s.') % (label, rs(total))
        return _reply('expenses', text,
                      links=_links(_link('Expenses', 'main.expenses_list')))
    snapshot = month_snapshot(ctx.month)
    start, end = month_bounds(ctx.month)
    breakdown = expense_breakdown(start, end)
    text = ctx.t(
        'Expenses in %s: %s in total (salaries %s, other expenses %s).',
        '%s ka kul kharcha: %s (salaries %s, baqi kharcha %s).'
    ) % (_period_label(ctx), rs(snapshot['expenses']),
         rs(snapshot['salaries_paid']), rs(snapshot['other_expenses']))
    table = None
    if breakdown:
        table = {'columns': [ctx.t('Category', 'Category'),
                             ctx.t('Amount', 'Raqam')],
                 'rows': [[row['name'], rs(row['total'])]
                          for row in breakdown[:6]]}
    return _reply('expenses', text, table=table,
                  links=_links(_link('Expenses', 'main.expenses_list')))


def h_profit(ctx):
    from app.services.financial_summary import month_snapshot
    snap = month_snapshot(ctx.month)
    net = snap['net']
    verdict_en = 'surplus' if net >= 0 else 'deficit'
    verdict_ur = 'munafa' if net >= 0 else 'nuqsan'
    text = ctx.t(
        '%s: cash in %s, cash out %s, so a %s of %s.',
        '%s: aamdani %s, kharcha %s, yani %s %s.'
    ) % (_period_label(ctx), rs(snap['cash_in']), rs(snap['cash_out']),
         ctx.t(verdict_en, verdict_ur), rs(abs(net)))
    text += '\n' + ctx.t('Fees still to be collected: %s.',
                         'Abhi wasool honay wali fees: %s.') % rs(
                             snap['fees_remaining'])
    return _reply('profit', text,
                  links=_links(_link('Financial Overview',
                                     'main.financials_summary')))


def h_salary(ctx):
    from app.services.financial_summary import payroll_snapshot
    snap = payroll_snapshot(ctx.month)
    if not snap['count']:
        text = ctx.t('Payroll for %s has not been generated yet.',
                     '%s ki payroll abhi generate nahi hui.') % _period_label(ctx)
    else:
        text = ctx.t(
            'Payroll %s: total %s, paid %s, pending %s (%d paid, %d partly '
            'paid, %d unpaid).',
            'Payroll %s: kul %s, ada %s, baqaya %s (%d ada, %d adhoori ada, '
            '%d baqi).'
        ) % (_period_label(ctx), rs(snap['total']), rs(snap['paid']),
             rs(snap['pending']), snap['paid_count'], snap['partial_count'],
             snap['unpaid_count'])
    return _reply('salary', text,
                  links=_links(_link('Payroll', 'main.payroll_page')))


def h_student_info(ctx):
    from app.services import fee_ledger
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


def h_howto(ctx, intent):
    guide = intent['guide']
    steps = guide['steps_ur'] if ctx.lang == 'ur' else guide['steps_en']
    title = guide['title_ur'] if ctx.lang == 'ur' else guide['title_en']
    text = title + ':\n' + '\n'.join('%d. %s' % (i, s)
                                     for i, s in enumerate(steps, 1))
    return _reply(intent['id'], text,
                  links=_links(_link(guide['link_label'], guide['endpoint'])))


HANDLERS = {
    'help': h_help,
    'today_summary': h_today_summary,
    'students_count': h_students_count,
    'teachers_count': h_teachers_count,
    'class_strength': h_class_strength,
    'attendance': h_attendance,
    'fees_collected': h_fees_collected,
    'fees_due': h_fees_due,
    'expenses': h_expenses,
    'profit': h_profit,
    'salary': h_salary,
    'student_info': h_student_info,
}


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #

def _unknown(ctx, scores):
    ranked = sorted((s, i) for i, s in scores.items() if s > 0)
    suggestions = []
    for _score, intent_id in reversed(ranked):
        examples = catalogue.INTENTS_BY_ID[intent_id]['examples']
        if examples and examples[0] not in suggestions:
            suggestions.append(examples[0])
        if len(suggestions) == 3:
            break
    if not suggestions:
        suggestions = catalogue.STARTER_QUESTIONS[:4]
    text = ctx.t(
        'Sorry, I did not understand that. Did you mean one of these?',
        'Maaf kijiye, main samajh nahi saka. Kya aap yeh poochna chahte the?')
    return _reply('unknown', text, suggestions=suggestions)


def answer(question):
    """Answer one question. Always returns a dict (never raises on bad input)."""
    ctx = Ctx(question)
    if not ctx.norm:
        return _reply('empty', 'Please type a question.',
                      suggestions=catalogue.STARTER_QUESTIONS[:4])

    has_how = _has_how_marker(ctx.tokens, ctx.norm)
    scores = score_intents(ctx.tokens, ctx.norm, has_how)

    ctx.class_obj = _find_class(ctx)
    ctx.students, ctx.exact_student = _find_students(ctx)
    if ctx.students and not has_how:
        # A student's name is a strong hint: a bare name shows their details.
        scores['student_info'] = scores.get('student_info', 0) + 2.5
    if ctx.students and not has_how and scores.get('fees_due', 0) >= 1:
        scores['fees_due'] = scores.get('fees_due', 0) + 1.5
    if ctx.class_obj and scores.get('students_count', 0) >= 1:
        # "nursery ke students" - a class plus the word "students" is a count.
        scores['students_count'] += 1.5
    if (ctx.month_explicit and scores.get('fees_collected', 0) >= 1.5
            and scores.get('fees_due', 0) < 2.5):
        # "october ki fees" - a month plus "fees" means the collection.
        scores['fees_collected'] += 1.5
    if ctx.students:
        # A name rules out whole-school counts such as "kitne students".
        for intent_id in ('students_count', 'teachers_count', 'class_strength'):
            scores.pop(intent_id, None)

    best_id, best_score = None, 0.0
    for intent in catalogue.INTENTS:   # catalogue order breaks ties
        score = scores.get(intent['id'], 0)
        if score >= intent['min_score'] and score > best_score:
            best_id, best_score = intent['id'], score
    if best_id is None and not has_how:
        # A bare topic such as "backup" or "student add" still gets its guide.
        guide_scores = score_intents(ctx.tokens, ctx.norm, True)
        for intent in catalogue.INTENTS:
            score = guide_scores.get(intent['id'], 0)
            if intent.get('howto') and score >= intent['min_score'] \
                    and score > best_score:
                best_id, best_score = intent['id'], score
    if best_id is None:
        return _unknown(ctx, scores)

    intent = catalogue.INTENTS_BY_ID[best_id]
    try:
        if intent.get('howto'):
            return h_howto(ctx, intent)
        return HANDLERS[best_id](ctx)
    except Exception:  # pragma: no cover - never show a stack trace in chat
        db.session.rollback()
        import logging
        logging.getLogger(__name__).exception('assistant: handler failed')
        return _reply(best_id, ctx.t(
            'Sorry, something went wrong while reading that data.',
            'Maaf kijiye, yeh data parhte hue masla aa gaya.'))
