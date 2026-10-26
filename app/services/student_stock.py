"""Admission-linked stock (Inventory Phase 3).

When a student is admitted with books and / or uniform, the stock of the items
in the class's books / uniform **set** goes down by itself.  The price of those
items is already part of the admission fee, so the issue is booked with price 0:
the income is never counted twice, but the cost of the items still becomes Cost
of Goods Sold (see ``inventory_service.record_sale``).

* Stock stays per item - a set is only a recipe (``ProductSet``).
* Later a student can take a single item (say one English book) - either as a
  normal sale (money received now) or as stock already paid for in the
  admission fee (``issue_item``).
* A wrong issue is voided, never deleted: the stock goes back.
* Only students admitted while the feature was on are tracked
  (``StudentModel.stock_tracked``); older students are never touched.
"""
from datetime import date, datetime

from app.database import db
from app.models import Product, ProductSet, StudentIssue, StudentModel
from app.services import inventory_service as inv

KINDS = ('books', 'uniform')
KIND_LABELS = {'books': 'books', 'uniform': 'uniform', 'item': 'item'}


def wanted_sets(student):
    """``{'books': n, 'uniform': n}`` - sets the student's admission terms call for."""
    books = (student.books_qty or 1) if student.books_fee_paisa else 0
    return {'books': books, 'uniform': student.uniform_qty or 0}


def class_set(class_id, kind):
    """The active set of ``kind`` (books / uniform) built for this class, or None.

    A class's own set always wins.  For ``uniform`` only, a uniform set that was
    made for no particular class ("all classes") is used when the class has none
    of its own, so a school with one common uniform sets it up once.
    """
    if not class_id:
        return None
    own = (ProductSet.query
           .filter_by(class_id=class_id, kind=kind, is_active=True)
           .order_by(ProductSet.id).first())
    if own is not None or kind != 'uniform':
        return own
    return (ProductSet.query
            .filter(ProductSet.kind == 'uniform', ProductSet.is_active.is_(True),
                    ProductSet.class_id.is_(None))
            .order_by(ProductSet.id).first())


def issued_sets(student_id, kind):
    """Sets of ``kind`` already handed to the student (voided issues excluded)."""
    total = (db.session.query(db.func.coalesce(db.func.sum(StudentIssue.quantity), 0))
             .filter(StudentIssue.student_id == student_id,
                     StudentIssue.kind == kind,
                     StudentIssue.is_void.is_(False)).scalar())
    return int(total or 0)


def _actor(actor):
    return inv._actor_name(actor)


def _check_stock(lines):
    """``lines`` is ``[(product, qty)]``; raises when anything is short."""
    if inv.sales_beyond_stock_allowed():
        return
    short = ['%s (need %d, have %d)' % (p.name, q, p.stock_qty or 0)
             for p, q in lines if q > (p.stock_qty or 0)]
    if short:
        raise ValueError('Not enough stock for: %s' % '; '.join(short))


# --------------------------------------------------------------------------- #
# Issuing and returning
# --------------------------------------------------------------------------- #

def issue_set(student, target, kind, count, actor=None, issue_date=None, note=None):
    """Hand ``count`` sets to the student.  All-or-nothing; does not commit."""
    count = int(count)
    if count <= 0:
        raise ValueError('The number of sets must be greater than zero.')
    if not target.items:
        raise ValueError('The set "%s" has no items.' % target.name)
    lines = [(i.product, i.quantity * count) for i in target.items]
    _check_stock(lines)
    when = issue_date or date.today()
    issue = StudentIssue(student_id=student.id, kind=kind, set_id=target.id,
                         quantity=count, issue_date=when,
                         note=(note or '').strip()[:200] or None,
                         created_by_name=_actor(actor))
    db.session.add(issue)
    label = 'Admission: %s - %s x %d' % (student.student_name, target.name, count)
    for product, qty in lines:
        inv.record_sale(product, qty, note=label[:200], sale_date=when, actor=actor,
                        student_id=student.id, admission_issue=issue)
    db.session.flush()
    return issue


def issue_item(student, product, quantity, actor=None, issue_date=None, note=None):
    """Hand ONE item (e.g. one English book) to the student, already paid for
    through the admission fee.  Does not commit."""
    try:
        quantity = int(quantity)
    except (TypeError, ValueError):
        raise ValueError('Quantity must be a whole number.')
    if quantity <= 0:
        raise ValueError('Quantity must be greater than zero.')
    if not product.is_active:
        raise ValueError('"%s" is retired.' % product.name)
    _check_stock([(product, quantity)])
    when = issue_date or date.today()
    issue = StudentIssue(student_id=student.id, kind='item', product_id=product.id,
                         quantity=quantity, issue_date=when,
                         note=(note or '').strip()[:200] or None,
                         created_by_name=_actor(actor))
    db.session.add(issue)
    label = 'Admission: %s - %s' % (student.student_name, product.name)
    if (note or '').strip():
        label += ' - ' + note.strip()
    inv.record_sale(product, quantity, note=label[:200], sale_date=when, actor=actor,
                    student_id=student.id, admission_issue=issue)
    db.session.flush()
    return issue


def void_issue(issue, reason, actor=None):
    """Take an issue back: the stock returns (average cost kept fair).  No commit."""
    reason = (reason or '').strip()
    if not reason:
        raise ValueError('A reason is required to void an issue.')
    if issue.is_void:
        raise ValueError('This issue is already voided.')
    for sale in issue.sales:
        if sale.is_void:
            continue
        product = sale.product
        old_stock = product.stock_qty or 0
        new_stock = old_stock + sale.quantity
        product.cost_paisa = int(round(
            (old_stock * (product.cost_paisa or 0)
             + sale.quantity * (sale.unit_cost_paisa or 0)) / new_stock))
        product.stock_qty = new_stock
        sale.is_void = True
    issue.is_void = True
    issue.void_reason = reason[:255]
    issue.voided_at = datetime.utcnow()
    issue.voided_by_name = _actor(actor)
    return issue


# --------------------------------------------------------------------------- #
# Keeping the stock in step with the admission terms
# --------------------------------------------------------------------------- #

def sync_student_stock(student, actor=None, new_admission=False, issue_date=None):
    """Make the issued sets match what the student's terms call for.

    ``new_admission`` marks the student as tracked (called once, when the
    student is added).  After that only tracked students are touched.  Never
    raises for a stock problem: the student is still admitted and the result
    says what could not be done.  Does not commit.

    Returns ``[(flash_category, message)]`` (empty when nothing happened).
    """
    if not inv.inventory_enabled():
        return []
    if student.id is None:
        db.session.flush()
    if new_admission:
        student.stock_tracked = True
    if not student.stock_tracked:
        return []

    out = []
    want = wanted_sets(student)
    for kind in KINDS:
        wanted = want[kind]
        have = issued_sets(student.id, kind)
        # Fewer sets than before (terms lowered): take the latest issues back.
        while have > wanted:
            latest = (StudentIssue.query
                      .filter_by(student_id=student.id, kind=kind, is_void=False)
                      .order_by(StudentIssue.id.desc()).first())
            if latest is None:
                break
            void_issue(latest, 'Admission terms changed', actor)
            out.append(('info', 'Stock returned: %s of %s.' % (
                latest.label, student.student_name)))
            have = issued_sets(student.id, kind)
        if wanted > have:
            target = class_set(student.class_id, kind)
            if target is None:
                out.append(('info',
                            'No active %s set is set up for this class in Inventory, '
                            'so the %s stock was not reduced.' % (kind, kind)))
                continue
            try:
                issue = issue_set(student, target, kind, wanted - have, actor,
                                  issue_date=issue_date)
                out.append(('success', 'Stock reduced: %s given to %s.' % (
                    issue.label, student.student_name)))
            except ValueError as error:
                out.append(('warning',
                            '%s stock was NOT reduced for %s: %s. Add stock, then '
                            'press "Issue now" in Inventory.' % (
                                kind.capitalize(), student.student_name, error)))
    return out


def pending_rows(limit=200):
    """Tracked students whose books / uniform has not been issued (fully) yet."""
    if not inv.inventory_enabled():
        return []
    students = (StudentModel.query
                .filter(StudentModel.stock_tracked.is_(True),
                        StudentModel.is_active.is_(True))
                .order_by(StudentModel.id.desc()).all())
    issued = {}
    rows = (db.session.query(StudentIssue.student_id, StudentIssue.kind,
                             db.func.sum(StudentIssue.quantity))
            .filter(StudentIssue.is_void.is_(False),
                    StudentIssue.kind.in_(KINDS))
            .group_by(StudentIssue.student_id, StudentIssue.kind).all())
    for student_id, kind, total in rows:
        issued[(student_id, kind)] = int(total or 0)
    sets = {}
    result = []
    for student in students:
        want = wanted_sets(student)
        for kind in KINDS:
            missing = want[kind] - issued.get((student.id, kind), 0)
            if missing <= 0:
                continue
            key = (student.class_id, kind)
            if key not in sets:
                sets[key] = class_set(student.class_id, kind)
            result.append({'student': student, 'kind': kind, 'missing': missing,
                           'set': sets[key]})
            if len(result) >= limit:
                return result
    return result


def recent_issues(limit=20):
    return (StudentIssue.query
            .order_by(StudentIssue.created_at.desc(), StudentIssue.id.desc())
            .limit(limit).all())


def student_issues(student_id):
    """Every issue of one student, newest first (voided ones included)."""
    return (StudentIssue.query.filter_by(student_id=student_id)
            .order_by(StudentIssue.id.desc()).all())


def find_student(reference):
    """Student from a form value like ``Ali Khan (Class 1, Roll 5) #123``."""
    import re
    match = re.search(r'#(\d+)\s*$', (reference or '').strip())
    if not match:
        return None
    return db.session.get(StudentModel, int(match.group(1)))


def student_choices(limit=3000):
    """``[(label, student)]`` for the "Student" suggestion box."""
    rows = (StudentModel.query.filter(StudentModel.is_active.is_(True))
            .order_by(StudentModel.student_name).limit(limit).all())
    result = []
    for student in rows:
        class_name = student.class_info.name if getattr(student, 'class_info', None) else ''
        result.append(('%s (%s, Roll %s) #%d' % (
            student.student_name, class_name, student.roll_number, student.id), student))
    return result
