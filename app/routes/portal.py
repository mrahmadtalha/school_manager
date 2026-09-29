"""Parent / guardian self-service portal (read-only)."""

from flask import abort, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app.models import AttendanceModel, ROLE_PARENT, StudentMarkModel, TestModel
from app.routes import main
from app.services.fee_ledger import student_summary


def _children_for(user):
    """All students linked to a guardian account, sorted by name.

    Falls back to the legacy single ``student`` relationship for accounts that
    have not been mirrored into the link table yet.
    """
    children = list(getattr(user, 'linked_students', []) or [])
    if not children:
        legacy = getattr(user, 'student', None)
        if legacy is not None:
            children = [legacy]
    return sorted(children, key=lambda child: (child.student_name or '').lower())


@main.route('/portal')
@login_required
def portal():
    if getattr(current_user, 'role', None) != ROLE_PARENT:
        return redirect(url_for('main.dashboard'))

    children = _children_for(current_user)

    student = None
    if children:
        requested_id = request.args.get('student_id', type=int)
        if requested_id is None:
            student = children[0]
        else:
            student = next((child for child in children if child.id == requested_id), None)
            if student is None:
                abort(404)

    if student is None:
        return render_template('portal.html', student=None, children=[],
                               attendance=[], marks=[],
                               fees=[], totals={'charged': 0.0, 'paid': 0.0, 'balance': 0.0})

    attendance = (AttendanceModel.query
                  .filter_by(target_type='student', target_id=student.id)
                  .order_by(AttendanceModel.date.desc())
                  .limit(60).all())

    counts = {'Present': 0, 'Absent': 0, 'Late': 0, 'Leave': 0}
    for record in attendance:
        if record.status in counts:
            counts[record.status] += 1

    marks = (StudentMarkModel.query
             .filter_by(student_id=student.id)
             .join(TestModel, StudentMarkModel.test_id == TestModel.id)
             .order_by(TestModel.test_date.desc())
             .limit(50).all())

    fees = student_summary(student.id)
    totals = {
        'charged': round(sum(row['charged'] for row in fees), 2),
        'paid': round(sum(row['paid'] for row in fees), 2),
        'balance': round(sum(row['balance'] for row in fees), 2),
    }

    return render_template('portal.html', student=student, children=children,
                           attendance=attendance, counts=counts, marks=marks,
                           fees=fees, totals=totals)
