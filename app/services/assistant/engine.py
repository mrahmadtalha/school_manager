"""The entry point: ``answer()`` scores the question, resolves context, runs the handler and remembers the context."""

from app.database import db
from app.services import assistant_intents as catalogue

from .constants import log
from .context import (Ctx, _clean_context, _context_out, _follow_up, _resolve_pronoun, _settle_people)
from .formatting import _reply, _with_context
from .handlers_misc import HANDLERS, h_howto
from .lookup import _find_class, _find_students, _find_teachers
from .nlu import _has_how_marker, score_intents


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
