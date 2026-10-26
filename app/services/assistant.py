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
import json
import logging
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
MAX_CONTEXT_LENGTH = 600        # the follow-up memory the browser sends back
AT_RISK_PERCENT = 75.0          # same line the attendance summary page uses
PAYROLL_REMINDER_DAY = 25       # "payroll not generated" is only nagged late in the month

log = logging.getLogger(__name__)

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
STUDENT_WORDS = {'student', 'students', 'bachay', 'bache', 'bachon', 'talib',
                 'talaba', 'children', 'kids', 'pupils'}

# --- follow-up memory -------------------------------------------------------
# "aur kal?", "class 6 ka?", "uska phone number?" only make sense with the
# previous answer in mind.  The browser sends back the small ``context`` dict
# every answer carries, so the server itself stays stateless.
PRONOUN_WORDS = {'us', 'uska', 'uski', 'uske', 'usko', 'iska', 'iski', 'iske',
                 'unka', 'unki', 'unke', 'his', 'her', 'their', 'him', 'them'}
FOLLOW_WORDS = {'aur', 'and', 'also', 'phir', 'about', 'or'}
FOLLOWABLE = {'attendance', 'fees_collected', 'fees_due', 'expenses', 'profit',
              'salary', 'students_count', 'low_attendance', 'new_admissions',
              'class_fees', 'compare', 'fees_payments'}
STUDENT_INTENTS = {'student_info', 'fees_due', 'attendance'}


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
        self.month_named = False
        self.month, self.month_explicit = self._month(token_set)
        self.class_obj = None
        self.students = []
        self.exact_student = False
        self.teachers = []
        self.exact_teacher = False

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
            self.month_named = True
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


def _name_candidates(ctx):
    """Words of the question that could be part of a person's name."""
    vocab = _vocab()
    return [t for t in ctx.tokens
            if len(t) >= 3 and t.isalpha()
            and t not in catalogue.STOPWORDS and t not in vocab
            and t not in catalogue.HOW_MARKERS
            and t not in MONTHS and t not in TODAY_WORDS
            and t not in YESTERDAY_WORDS and t not in PREVIOUS_WORDS
            and t not in MONTH_WORDS and t not in THIS_WORDS]


def _match_names(ctx, candidates, rows):
    """``rows`` is [(id, full name)].  -> (ids, exact_full_name_match?)."""
    by_token = {}
    names = {}
    for person_id, name in rows:
        tokens = normalize(name).split()
        names[person_id] = ' '.join(tokens)
        for token in tokens:
            by_token.setdefault(token, set()).add(person_id)

    padded = ' %s ' % ctx.norm
    exact = [pid for pid, name in names.items()
             if len(name.split()) >= 2 and ' %s ' % name in padded]
    if exact:
        return exact, True

    hits = [t for t in candidates if t in by_token]
    if not hits:
        return [], False
    matching = set.intersection(*(by_token[t] for t in hits))
    if matching:
        return sorted(matching), False
    # Words belong to different people: keep the best-covered ones.
    counts = {}
    for token in hits:
        for pid in by_token[token]:
            counts[pid] = counts.get(pid, 0) + 1
    top = max(counts.values())
    return sorted(pid for pid, c in counts.items() if c == top), False


def _find_students(ctx):
    """Active students whose name appears in the question."""
    candidates = _name_candidates(ctx)
    if not candidates:
        return [], False
    rows = (StudentModel.query.filter_by(is_active=True)
            .with_entities(StudentModel.id, StudentModel.student_name).all())
    return _match_names(ctx, candidates, rows)


def _find_teachers(ctx):
    """Active teachers whose name appears in the question."""
    candidates = _name_candidates(ctx)
    if not candidates:
        return [], False
    rows = (TeacherModel.query.filter_by(is_active=True)
            .with_entities(TeacherModel.id, TeacherModel.teacher_name).all())
    return _match_names(ctx, candidates, rows)


def _settle_people(ctx):
    """A name can match both a student and a teacher: keep only one kind."""
    if not (ctx.students and ctx.teachers):
        return
    if ctx.exact_teacher and not ctx.exact_student:
        prefer_teacher = True
    elif ctx.exact_student and not ctx.exact_teacher:
        prefer_teacher = False
    else:
        prefer_teacher = ctx.is_teacher
    if prefer_teacher:
        ctx.students, ctx.exact_student = [], False
    else:
        ctx.teachers, ctx.exact_teacher = [], False


# --------------------------------------------------------------------------- #
# Follow-up memory
# --------------------------------------------------------------------------- #

def _clean_context(raw):
    """Trust nothing the browser sends back: keep only well-formed values."""
    if not isinstance(raw, dict):
        return {}
    out = {}
    for key in ('intent', 'awaiting'):
        value = raw.get(key)
        if isinstance(value, str) and value in catalogue.INTENTS_BY_ID:
            out[key] = value
    for key in ('class_id', 'student_id', 'teacher_id'):
        value = raw.get(key)
        if isinstance(value, int) and not isinstance(value, bool) and value > 0:
            out[key] = value
    month = raw.get('month')
    if isinstance(month, str) and re.fullmatch(r'\d{4}-\d{2}', month):
        if month_label(month):
            out['month'] = month
    day = raw.get('day')
    if isinstance(day, str):
        try:
            out['day'] = date.fromisoformat(day).isoformat()
        except ValueError:
            pass
    if raw.get('status') in ('Present', 'Absent', 'Late', 'Leave'):
        out['status'] = raw['status']
    if raw.get('gender') in ('Male', 'Female'):
        out['gender'] = raw['gender']
    for key in ('month_explicit', 'is_teacher'):
        if raw.get(key) is True:
            out[key] = True
    return out


def _context_out(ctx, intent_id, awaiting=None):
    """The small memory sent back to the browser with every answer."""
    out = {'intent': intent_id}
    if awaiting:
        out['awaiting'] = awaiting
    if ctx.class_obj:
        out['class_id'] = ctx.class_obj.id
    if ctx.month_explicit:
        out['month'] = ctx.month
        out['month_explicit'] = True
    if ctx.day:
        out['day'] = ctx.day.isoformat()
    if ctx.status:
        out['status'] = ctx.status
    if ctx.gender:
        out['gender'] = ctx.gender
    if ctx.is_teacher:
        out['is_teacher'] = True
    if ctx.students and (len(ctx.students) == 1 or ctx.exact_student) \
            and intent_id in STUDENT_INTENTS:
        out['student_id'] = ctx.students[0]
    if ctx.teachers and (len(ctx.teachers) == 1 or ctx.exact_teacher) \
            and intent_id == 'teacher_info':
        out['teacher_id'] = ctx.teachers[0]
    return out


def _resolve_pronoun(ctx, prev):
    """\"uska phone number?\" -> the person the last answer was about."""
    if ctx.students or ctx.teachers or not (set(ctx.tokens) & PRONOUN_WORDS):
        return
    student_id = prev.get('student_id')
    if student_id and db.session.get(StudentModel, student_id):
        ctx.students, ctx.exact_student = [student_id], True
        return
    teacher_id = prev.get('teacher_id')
    if teacher_id and db.session.get(TeacherModel, teacher_id):
        ctx.teachers, ctx.exact_teacher = [teacher_id], True


def _follow_up(ctx, prev, has_how):
    """Fill the gaps of a short question from the previous answer.

    Returns True when the question is a follow-up (it then repeats the
    previous intent with the new class / day / month / status on top).
    """
    intent_id = prev.get('intent')
    if intent_id not in FOLLOWABLE or has_how or len(ctx.tokens) > 8:
        return False
    tokens = set(ctx.tokens)
    has_entity = bool(ctx.class_obj or ctx.day or ctx.month_explicit
                      or ctx.status or ctx.gender or ctx.is_teacher
                      or ctx.students)
    if not (has_entity or tokens & FOLLOW_WORDS):
        return False

    if ctx.class_obj is None and prev.get('class_id') and not ctx.is_teacher:
        ctx.class_obj = db.session.get(ClassModel, prev['class_id'])
    if ctx.day is None and prev.get('day') and not ctx.month_explicit:
        ctx.day = date.fromisoformat(prev['day'])
    if (not ctx.month_explicit and ctx.day is None and prev.get('month')
            and prev.get('month_explicit')):
        ctx.month, ctx.month_explicit = prev['month'], True
    if ctx.status is None:
        ctx.status = prev.get('status')
    if ctx.gender is None:
        ctx.gender = prev.get('gender')
    if (not ctx.is_teacher and prev.get('is_teacher')
            and not tokens & STUDENT_WORDS):
        ctx.is_teacher = True
    if (intent_id in STUDENT_INTENTS and not ctx.students
            and prev.get('student_id') and not ctx.class_obj
            and not ctx.is_teacher):
        if db.session.get(StudentModel, prev['student_id']):
            ctx.students, ctx.exact_student = [prev['student_id']], True
    return True


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


def _with_context(reply, context):
    reply['context'] = context
    return reply


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
    reply = _reply(intent, text, table=table, suggestions=suggestions)
    reply['awaiting'] = intent      # the next bare name answers THIS question
    return reply


def _ask_which_teacher(ctx, teachers):
    shown = teachers[:8]
    text = ctx.t('I found %d teachers with that name. Which one do you mean?',
                 'Is naam ke %d teachers mile hain. Kaunsa chahiye?'
                 ) % len(teachers)
    table = {'columns': [ctx.t('Teacher', 'Teacher'), ctx.t('ID', 'ID')],
             'rows': [[t.teacher_name, t.teacher_id_str] for t in shown]}
    reply = _reply('teacher_info', text, table=table,
                   suggestions=[t.teacher_name for t in shown])
    reply['awaiting'] = 'teacher_info'
    return reply


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


def _pct_change(current, previous):
    if not previous:
        return '-'
    change = (current - previous) * 100.0 / previous
    return '%+.0f%%' % change


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


def h_attention(ctx):
    """One short to-do list built from the numbers the software already has."""
    from app.services import dashboard_service
    from app.services.financial_summary import payroll_snapshot, summary_alerts

    today = date.today()
    lines, links = [], []

    attendance = dashboard_service.today_attendance()
    if _is_working_day(today):
        students = attendance['student']
        if students['expected'] and not students['marked']:
            lines.append(ctx.t('Student attendance has not been marked today.',
                               'Aaj ki student attendance abhi mark nahi hui.'))
            links.append(_link('Daily attendance', 'main.student_attendance'))
        elif students['not_marked']:
            lines.append(ctx.t(
                'Attendance is still missing for %d students today.',
                'Aaj %d students ki attendance baqi hai.')
                % students['not_marked'])
            links.append(_link('Daily attendance', 'main.student_attendance'))
        teachers = attendance['teacher']
        if teachers['expected'] and not teachers['marked']:
            lines.append(ctx.t('Teacher attendance has not been marked today.',
                               'Aaj ki teacher attendance abhi mark nahi hui.'))
            links.append(_link('Teacher attendance', 'main.teacher_attendance'))
    absent = attendance['student']['counts']['Absent']
    if absent:
        lines.append(ctx.t('%d students are absent today (ask "aaj kaun absent '
                           'hai?" for names and phone numbers).',
                           'Aaj %d students ghair hazir hain ("aaj kaun absent '
                           'hai?" se naam aur phone dekhein).') % absent)

    if today.day >= PAYROLL_REMINDER_DAY \
            and TeacherModel.query.filter_by(is_active=True).count():
        snap = payroll_snapshot(current_month_key())
        if not snap['count']:
            lines.append(ctx.t('Payroll for %s has not been generated yet.',
                               '%s ki payroll abhi generate nahi hui.')
                         % month_label(current_month_key()))
            links.append(_link('Payroll', 'main.payroll_page'))

    try:
        alerts = summary_alerts(current_month_key())
    except Exception:  # pragma: no cover - degrade, do not fail the answer
        db.session.rollback()
        log.exception('assistant: summary alerts failed')
        alerts = []
    seen_urls = set()
    for alert in alerts[:5]:
        lines.append(alert['text'])
        url = alert.get('url')
        if url and url not in seen_urls:
            seen_urls.add(url)
            links.append({'label': alert.get('link_text') or 'Open',
                          'url': url})

    try:
        birthdays_today = dashboard_service.birthdays()['today']
    except Exception:  # pragma: no cover
        db.session.rollback()
        birthdays_today = []
    if birthdays_today:
        names = ', '.join(entry['name'] for entry in birthdays_today[:5])
        lines.append(ctx.t('Birthday today: %s.', 'Aaj ki birthday: %s.')
                     % names)

    links = _links(*links)[:5]
    if not lines:
        return _reply('attention', ctx.t(
            'Nothing needs attention right now. Attendance is done and there '
            'are no alerts.',
            'Abhi kisi cheez par tawajjuh ki zaroorat nahi. Attendance mukammal '
            'hai aur koi alert nahi.'),
            suggestions=['defaulters kaun hain?'])
    text = ctx.t('Things that need attention:', 'In cheezon par tawajjuh dein:')
    text += '\n' + '\n'.join('%d. %s' % (i, line)
                             for i, line in enumerate(lines, 1))
    return _reply('attention', text, links=links,
                  suggestions=['defaulters kaun hain?',
                               'aaj kis kis ne fees di?'])


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


def h_class_fees(ctx):
    from app.services.financial_summary import student_outstanding_rows
    month_key = ctx.month if ctx.month_explicit else None
    rows = student_outstanding_rows(month_year=month_key)
    scope = (' (%s)' % month_label(month_key)) if month_key else ''
    if not rows:
        return _reply('class_fees', ctx.t('No outstanding fees%s.',
                                          'Koi baqaya fees nahi%s.') % scope,
                      links=_links(_link('Fees Management', 'main.fees_list')))
    per_class = {}
    for item in rows:
        entry = per_class.setdefault(item['class_name'], [0, 0.0])
        entry[0] += 1
        entry[1] += item['outstanding']
    ranked = sorted(per_class.items(), key=lambda pair: -pair[1][1])
    total = sum(item['outstanding'] for item in rows)
    text = ctx.t('%d students in %d classes owe %s%s.',
                 '%d students (%d classes mein) ka baqaya %s hai%s.'
                 ) % (len(rows), len(per_class), rs(total), scope)
    table = {'columns': [ctx.t('Class', 'Class'),
                         ctx.t('Students owing', 'Baqaya wale students'),
                         ctx.t('Total due', 'Kul baqaya')],
             'rows': [[name, count, rs(amount)]
                      for name, (count, amount) in ranked]}
    return _reply('class_fees', text, table=table,
                  links=_links(_link('Student dues',
                                     'main.financials_student_outstanding'),
                               _link('Fees Management', 'main.fees_list')),
                  suggestions=[ctx.t('defaulters of %s' % ranked[0][0],
                                     '%s ke defaulters' % ranked[0][0])])


def h_compare(ctx):
    from app.services.financial_summary import month_snapshot
    # "pichle mahine se muqabla" means THIS month against last month, so the
    # word "pichle" must not shift the base month; only a named month does.
    base = ctx.month if ctx.month_named else current_month_key()
    before = shift_month(base, -1)
    now_snap, old_snap = month_snapshot(base), month_snapshot(before)
    pairs = [
        (ctx.t('Fees collected', 'Fees wasooli'),
         now_snap['fee_income'], old_snap['fee_income']),
        (ctx.t('Expenses', 'Kharcha'),
         now_snap['expenses'], old_snap['expenses']),
        (ctx.t('Net (cash in - cash out)', 'Bachat (aamdani - kharcha)'),
         now_snap['net'], old_snap['net']),
    ]
    table = {'columns': [ctx.t('Item', 'Cheez'), month_label(base),
                         month_label(before), ctx.t('Change', 'Farq')],
             'rows': [[label, rs(now), rs(old), _pct_change(now, old)]
                      for label, now, old in pairs]}
    tokens = set(ctx.tokens)
    if tokens & {'expense', 'expenses', 'kharcha', 'kharch', 'kharche'}:
        label, now, old = pairs[1]
        word = ctx.t('higher', 'zyada') if now > old else ctx.t('lower', 'kam')
    elif tokens & {'profit', 'munafa', 'nafa', 'net', 'loss', 'nuqsan'}:
        label, now, old = pairs[2]
        word = ctx.t('higher', 'zyada') if now > old else ctx.t('lower', 'kam')
    else:
        label, now, old = pairs[0]
        word = ctx.t('higher', 'zyada') if now > old else ctx.t('lower', 'kam')
    if now == old:
        text = ctx.t('%s is the same in %s and %s (%s).',
                     '%s %s aur %s mein barabar hai (%s).') % (
                         label, month_label(base), month_label(before), rs(now))
    else:
        text = ctx.t('%s: %s in %s, which is %s %s than %s (%s).',
                     '%s: %s mein %s, jo %s ke muqable mein %s %s hai.'
                     ) % ((label, rs(now), month_label(base), rs(abs(now - old)),
                           word, month_label(before), rs(old))
                          if ctx.lang == 'en' else
                          (label, month_label(base), rs(now),
                           month_label(before), rs(abs(now - old)), word))
    return _reply('compare', text, table=table,
                  links=_links(_link('Financial Overview',
                                     'main.financials_summary')))


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


def h_fees_payments(ctx):
    """Who paid on a given day (default today) - the cash-book view."""
    from app.models import FeeTransaction
    from app.services.financial_summary import _cash_date_column
    day = ctx.day or date.today()
    is_today = day == date.today()
    day_word = ctx.t('today' if is_today else 'on %s' % day.strftime('%d %b'),
                     'aaj' if is_today else '%s ko' % day.strftime('%d %b'))
    cash_date = _cash_date_column()
    query = (db.session.query(StudentModel.student_name, ClassModel.name,
                              FeeTransaction.amount_paisa,
                              FeeTransaction.method)
             .select_from(FeeTransaction)
             .join(StudentModel, StudentModel.id == FeeTransaction.student_id)
             .outerjoin(ClassModel, ClassModel.id == StudentModel.class_id)
             .filter(FeeTransaction.txn_type == 'payment',
                     FeeTransaction.is_void.is_(False),
                     # same comparison shape as financial_summary.fee_collections
                     cash_date >= day.isoformat(),
                     cash_date <= day.isoformat()))
    if ctx.class_obj:
        query = query.filter(StudentModel.class_id == ctx.class_obj.id)
    rows = query.order_by(FeeTransaction.id).all()
    links = _links(_link('Fees Management', 'main.fees_list'))
    if not rows:
        return _reply('fees_payments', ctx.t('No fee payments %s.',
                                             'Fees ki koi wasooli %s nahi hui.'
                                             ) % day_word, links=links)
    total = sum(paisa or 0 for _n, _c, paisa, _m in rows) / 100.0
    text = ctx.t('%d payments %s, %s in total.',
                 '%s: %d payments, kul %s.') % (
                     (len(rows), day_word, rs(total)) if ctx.lang == 'en'
                     else (day_word, len(rows), rs(total)))
    if len(rows) > MAX_LIST_ROWS:
        text += ctx.t(' (showing first %d)', ' (pehle %d dikhaye gaye)'
                      ) % MAX_LIST_ROWS
    table = {'columns': [ctx.t('Student', 'Student'), ctx.t('Class', 'Class'),
                         ctx.t('Amount', 'Raqam'), ctx.t('Method', 'Tareeqa')],
             'rows': [[name, class_name or '-', rs((paisa or 0) / 100.0),
                       (method or '-').title()]
                      for name, class_name, paisa, method in rows[:MAX_LIST_ROWS]]}
    return _reply('fees_payments', text, table=table, links=links,
                  suggestions=[ctx.t('defaulters', 'defaulters kaun hain?')])


def _json_list(value):
    try:
        data = json.loads(value or '[]')
    except (TypeError, ValueError):
        return []
    return [str(item) for item in data] if isinstance(data, list) else []


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
    'attention': h_attention,
    'birthdays': h_birthdays,
    'low_attendance': h_low_attendance,
    'class_fees': h_class_fees,
    'compare': h_compare,
    'new_admissions': h_new_admissions,
    'fees_payments': h_fees_payments,
    'teacher_info': h_teacher_info,
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


def answer(question, context=None):
    """Answer one question. Always returns a dict (never raises on bad input).

    ``context`` is the small memory dict the previous answer carried (see
    ``_context_out``); it lets short follow-ups such as "aur kal?" work.
    """
    prev = _clean_context(context)
    ctx = Ctx(question)
    if not ctx.norm:
        return _with_context(
            _reply('empty', 'Please type a question.',
                   suggestions=catalogue.STARTER_QUESTIONS[:4]), prev)

    has_how = _has_how_marker(ctx.tokens, ctx.norm)
    scores = score_intents(ctx.tokens, ctx.norm, has_how)
    # How strongly the WORDS alone pointed at an intent (before name boosts):
    # a bare name such as "Ali Khan" answers a pending "which student?".
    keyword_peak = max(scores.values(), default=0)

    ctx.class_obj = _find_class(ctx)
    ctx.students, ctx.exact_student = _find_students(ctx)
    ctx.teachers, ctx.exact_teacher = _find_teachers(ctx)
    _settle_people(ctx)
    _resolve_pronoun(ctx, prev)
    if ctx.students and not has_how:
        # A student's name is a strong hint: a bare name shows their details.
        scores['student_info'] = scores.get('student_info', 0) + 2.5
    if ctx.teachers and not has_how:
        # A teacher's name works the same way; "uski salary" must reach the
        # teacher, not the whole-school payroll.
        boost = 2.5 + (1.5 if scores.get('salary', 0) >= 2.5 else 0)
        scores['teacher_info'] = scores.get('teacher_info', 0) + boost
    if ctx.students and not has_how and scores.get('fees_due', 0) >= 1:
        scores['fees_due'] = scores.get('fees_due', 0) + 1.5
    if ctx.class_obj and scores.get('students_count', 0) >= 1:
        # "nursery ke students" - a class plus the word "students" is a count.
        scores['students_count'] += 1.5
    if (ctx.month_explicit and scores.get('fees_collected', 0) >= 1.5
            and scores.get('fees_due', 0) < 2.5):
        # "october ki fees" - a month plus "fees" means the collection.
        scores['fees_collected'] += 1.5
    if ctx.students or ctx.teachers:
        # A name rules out whole-school counts such as "kitne students".
        for intent_id in ('students_count', 'teachers_count', 'class_strength'):
            scores.pop(intent_id, None)
    if ctx.teachers:
        # "Ahmed ka phone number" is about the teacher; the words "phone" and
        # "number" must not pull it towards the student details.
        scores.pop('student_info', None)

    best_id, best_score = None, 0.0
    for intent in catalogue.INTENTS:   # catalogue order breaks ties
        score = scores.get(intent['id'], 0)
        if score >= intent['min_score'] and score > best_score:
            best_id, best_score = intent['id'], score
    if (prev.get('awaiting') and (ctx.students or ctx.teachers)
            and keyword_peak < 2 and not has_how):
        # "Which student?" was asked and the person just typed a name.
        best_id = prev['awaiting']
    if best_id is None and not has_how:
        # A bare topic such as "backup" or "student add" still gets its guide.
        guide_scores = score_intents(ctx.tokens, ctx.norm, True)
        for intent in catalogue.INTENTS:
            score = guide_scores.get(intent['id'], 0)
            if intent.get('howto') and score >= intent['min_score'] \
                    and score > best_score:
                best_id, best_score = intent['id'], score
    if best_id is None and _follow_up(ctx, prev, has_how):
        best_id = prev['intent']
    if best_id is None:
        return _with_context(_unknown(ctx, scores), prev)

    intent = catalogue.INTENTS_BY_ID[best_id]
    try:
        if intent.get('howto'):
            return _with_context(h_howto(ctx, intent), prev)
        reply = HANDLERS[best_id](ctx)
        awaiting = reply.pop('awaiting', None)
        if best_id == 'help':
            return _with_context(reply, prev)
        return _with_context(reply, _context_out(ctx, best_id, awaiting))
    except Exception:  # pragma: no cover - never show a stack trace in chat
        db.session.rollback()
        log.exception('assistant: handler failed')
        return _with_context(_reply(best_id, ctx.t(
            'Sorry, something went wrong while reading that data.',
            'Maaf kijiye, yeh data parhte hue masla aa gaya.')), prev)
