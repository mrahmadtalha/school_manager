"""Finding the class, students or teachers a question refers to, and asking which one when it is ambiguous."""

import re

from app.models import ClassModel, StudentModel, TeacherModel
from app.services import assistant_intents as catalogue

from .constants import (MONTHS, MONTH_WORDS, PREVIOUS_WORDS, THIS_WORDS, TODAY_WORDS, YESTERDAY_WORDS)
from .formatting import _reply
from .nlu import _vocab, normalize


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


def _students_by_ids(ids):
    return StudentModel.query.filter(StudentModel.id.in_(ids)).all()


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
