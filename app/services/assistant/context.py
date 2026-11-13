"""Conversation context: the ``Ctx`` entities pulled from a question, pronoun and follow-up handling."""

import re
from datetime import date, timedelta

from app.database import db
from app.models import ClassModel, StudentModel, TeacherModel
from app.services import assistant_intents as catalogue
from app.services.payroll_service import month_label, shift_month, current_month_key

from .constants import (FEMALE_WORDS, FOLLOWABLE, FOLLOW_WORDS, MALE_WORDS, MAX_QUESTION_LENGTH, MONTHS,
                        MONTH_WORDS, PREVIOUS_WORDS, PRONOUN_WORDS, STUDENT_INTENTS, STUDENT_WORDS,
                        TEACHER_WORDS, TODAY_WORDS, YESTERDAY_WORDS)
from .nlu import normalize


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
