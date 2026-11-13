"""Size limits carried by the license: how many students and staff logins a school may have.

A vendor sells School Manager by size as well as by module, so a license key may carry

* ``max_students`` - the number of *active* students (archived students do not count), and
* ``max_staff``    - the number of *active* staff logins: teacher, accountant, owner (principal)
  and gate-guard accounts.  Administrators are always free (a school can never be locked out) and
  parent logins are controlled by the *Parent portal* feature switch instead, so a school with
  hundreds of parents is not punished.

A missing limit means "unlimited" (every key issued before this release).  ``0`` means "none can
be added".  Limits only stop *new* additions: a school that is already above a limit (for example
after a cheaper plan) keeps everything it has; it just cannot add more until it upgrades or
archives some students / switches some logins off.

Enforcement lives where records are created (add / restore / import student, create / re-activate /
re-role a user, create a guard account); this module only counts and words the message.
"""

from flask import g, has_request_context

from app.services.licensing import LIMIT_MAX_STAFF, LIMIT_MAX_STUDENTS

#: Login roles counted against the staff limit.
STAFF_ROLES = ('teacher', 'accountant', 'owner', 'guard')

UPGRADE_HINT = 'Please contact your software vendor to upgrade your plan.'


def _status():
    if has_request_context():
        status = g.get('license_status')
        if status is not None:
            return status
    from app.license_guard import get_manager
    return get_manager().status()


def _limit(name):
    """The numeric limit, or None when unlimited (also when enforcement is off)."""
    status = _status()
    if not status.enforced:
        return None
    return status.limit(name)


def count_students():
    from app.models import StudentModel
    return StudentModel.query.filter_by(is_active=True).count()


def count_staff():
    from app.models import AdminUser
    return (AdminUser.query
            .filter(AdminUser.is_active.is_(True), AdminUser.role.in_(STAFF_ROLES))
            .count())


def _usage(limit, used):
    room = None if limit is None else max(0, limit - used)
    return {'used': used, 'limit': limit, 'room': room,
            'full': room == 0, 'over': limit is not None and used > limit}


def student_usage():
    """``{'used', 'limit', 'room', 'full', 'over'}``; ``limit`` and ``room`` are None when unlimited."""
    return _usage(_limit(LIMIT_MAX_STUDENTS), count_students())


def staff_usage():
    return _usage(_limit(LIMIT_MAX_STAFF), count_staff())


def summary():
    """Both usages together, for the License page."""
    return {'students': student_usage(), 'staff': staff_usage()}


def student_room():
    """How many more students may be added (None = any number)."""
    return student_usage()['room']


def _message(what, info, adding):
    if info['room'] is None or info['room'] >= adding:
        return ''
    used = info['used']
    if info['room'] == 0:
        return (f"Your license allows up to {info['limit']} active {what} and {used} "
                f"{'is' if used == 1 else 'are'} already in use, so no more can be added. {UPGRADE_HINT}")
    return (f"Your license allows up to {info['limit']} active {what}: only {info['room']} more "
            f"can be added, but {adding} were requested. {UPGRADE_HINT}")


def student_block_message(adding=1):
    """Why ``adding`` more students cannot be added ('' when they can)."""
    return _message('students', student_usage(), adding)


def staff_block_message(role, adding=1):
    """Why one more login of ``role`` cannot be added ('' when it can, or the role is not counted)."""
    if role not in STAFF_ROLES:
        return ''
    return _message('staff logins (teachers, accountants, owners and guards)', staff_usage(), adding)
