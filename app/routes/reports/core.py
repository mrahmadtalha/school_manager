"""Shared class-result evaluation used by the reports hub, exports and report cards."""

from datetime import datetime
from app.models import StudentModel, TestModel, StudentMarkModel, StudentRemark
from app.services.marks import ABSENT_LABEL, mark_is_absent


def _format_result_date(value):
    value = (value or '').strip()
    if not value:
        return ''
    for fmt in ('%Y-%m-%d', '%d-%m-%Y', '%d %b %Y', '%d %B %Y'):
        try:
            return datetime.strptime(value, fmt).strftime('%d %b %Y')
        except ValueError:
            continue
    return value


def _class_results_evaluation(class_id, test_type=''):
    """Shared evaluation for the class-results page and the PDF exports.

    Returns (test_types, class_tests, matrix_data, marks_map). Each matrix row
    carries scores/grades per test, totals, percentage, overall grade,
    pass/fail status and a competition rank.

    A paper marked Absent is left out of the student's total, maximum,
    percentage, grade and rank (``row['absent']`` flags those papers); they are
    judged only on the papers they sat.  A student absent from every paper has
    status ``Absent`` and no rank.
    """
    from app.models.settings import calculate_grade

    all_tests = (TestModel.query.filter_by(class_id=class_id)
                 .order_by(TestModel.test_date).all())
    test_types = sorted(set(t.test_type for t in all_tests if t.test_type))
    class_tests = [t for t in all_tests if not test_type or t.test_type == test_type]

    students = StudentModel.query.filter_by(is_active=True, class_id=class_id).all()
    test_ids = [t.id for t in class_tests]
    all_marks = (StudentMarkModel.query.filter(StudentMarkModel.test_id.in_(test_ids)).all()
                 if test_ids else [])
    marks_map = {(m.student_id, m.test_id): m for m in all_marks}

    matrix_data = []
    for s in students:
        student_row = {'student': s, 'scores': {}, 'grades': {}, 'absent': {}}
        total_obtained = 0.0
        total_max = 0.0
        absent_count = 0

        for t in class_tests:
            m = marks_map.get((s.id, t.id))
            if mark_is_absent(m):
                # Absent: not scored, and its maximum is not held against them.
                student_row['scores'][t.id] = None
                student_row['grades'][t.id] = None
                student_row['absent'][t.id] = True
                absent_count += 1
                continue
            if m:
                student_row['scores'][t.id] = m.marks_obtained
                student_row['grades'][t.id] = m.grade
                total_obtained += m.marks_obtained
            else:
                student_row['scores'][t.id] = None
                student_row['grades'][t.id] = None
            total_max += t.total_marks

        all_absent = bool(absent_count and absent_count == len(class_tests))
        overall_pct = (total_obtained / total_max * 100) if total_max > 0 else 0.0
        if all_absent:
            ov_grade = ABSENT_LABEL
        else:
            ov_grade = calculate_grade(overall_pct) if total_max > 0 else 'N/A'
        is_pass = bool(total_max > 0 and ov_grade != 'F')

        student_row['total_obtained'] = total_obtained
        student_row['total_max'] = total_max
        student_row['absent_count'] = absent_count
        student_row['all_absent'] = all_absent
        student_row['percentage'] = round(overall_pct, 1)
        student_row['overall_grade'] = ov_grade
        student_row['is_pass'] = is_pass
        if all_absent:
            student_row['status'] = 'Absent'
        else:
            student_row['status'] = 'Pass' if is_pass else ('Fail' if total_max > 0 else 'N/A')
        matrix_data.append(student_row)

    # Rank by percentage on the papers actually sat, so a student who missed a
    # paper is not pushed down for marks they could not earn.  (With no absences
    # every student has the same maximum, so this orders exactly as ranking by
    # total marks did.)  Equal results share the position; all-absent students
    # come last and have no rank.
    ranked = [r for r in matrix_data if not r['all_absent']]
    unranked = [r for r in matrix_data if r['all_absent']]

    def _standing(r):
        return (r['total_obtained'] / r['total_max']) if r['total_max'] > 0 else 0.0

    ranked.sort(key=_standing, reverse=True)
    rank = 0
    prev_standing = None
    for i, row in enumerate(ranked, 1):
        standing = _standing(row)
        if prev_standing is None or standing != prev_standing:
            rank = i
            prev_standing = standing
        row['rank'] = rank
        row['rank_label'] = str(rank)
    for row in unranked:
        row['rank'] = None
        row['rank_label'] = '—'

    return test_types, class_tests, ranked + unranked, marks_map


def _class_results_summary(matrix_data, class_tests):
    scored = [r for r in matrix_data if r['total_max'] > 0]
    percentages = [r['percentage'] for r in scored]
    pass_count = sum(1 for r in scored if r['is_pass'])
    return {
        'total_students': len(matrix_data),
        'total_tests': len(class_tests),
        'class_avg': round(sum(percentages) / len(percentages), 1) if percentages else 0,
        'pass_rate': round((pass_count / len(scored)) * 100, 1) if scored else 0,
        'pass_count': pass_count,
        'top_scorer': matrix_data[0]['student'].student_name if matrix_data else '—',
        'top_pct': matrix_data[0]['percentage'] if matrix_data else 0,
    }


def _load_result_remarks(class_id, test_type, session_value):
    rows = StudentRemark.query.filter_by(class_id=class_id,
                                         test_type=(test_type or ''),
                                         session=(session_value or '')).all()
    return {r.student_id: r.remarks for r in rows}


def _fit_report_on_one_page(doc, story):
    """Wrap one student's report so it can never run past a single page.

    A report that already fits is left exactly as it was; a longer one (many
    marks) is scaled down just enough to fit. Because the result is a single
    flowable no taller than the page, a bulk PDF always has one page per student
    and no stray or blank pages.
    """
    from reportlab.platypus import KeepInFrame
    return KeepInFrame(doc.width - 12, doc.height - 12, story,
                       mode='shrink', hAlign='CENTER', vAlign='TOP')
