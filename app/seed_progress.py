"""Background runner for demo-data generation started from the setup wizard.

The first-run form finishes immediately (the admin account and school settings
are committed first), then a daemon thread generates the demo dataset while
the browser watches a live progress page.  Job state lives in this process's
memory: seeding only ever runs once, right after setup, so no persistence is
needed.  A job is addressed by a random token stored in the starter's session,
so the status endpoints are only usable by the browser that started the run.
"""
import threading
import traceback
import uuid

from app.services.seed_generator import SeedConfig, run_seed

_lock = threading.Lock()
_jobs = {}


def start_seed_job(app, config):
    """Start generating demo data in a daemon thread; return the job token."""
    token = uuid.uuid4().hex
    with _lock:
        _jobs[token] = {
            'state': 'running',
            'stage': 'Starting…',
            'percent': 0,
            'summary': None,
            'error': None,
        }

    def _worker():
        def on_progress(stage, percent):
            with _lock:
                job = _jobs.get(token)
                if job is not None:
                    job['stage'] = stage.replace('_', ' ').title()
                    job['percent'] = percent

        with app.app_context():
            try:
                summary = run_seed(config, on_progress)
                with _lock:
                    job = _jobs.get(token)
                    if job is not None:
                        job['state'] = 'done'
                        job['stage'] = 'Complete'
                        job['percent'] = 100
                        job['summary'] = summary
            except Exception as exc:  # noqa: BLE001 - surfaced on the progress page
                traceback.print_exc()
                from app.database import db
                try:
                    db.session.rollback()
                except Exception:
                    pass
                with _lock:
                    job = _jobs.get(token)
                    if job is not None:
                        job['state'] = 'error'
                        job['stage'] = 'Failed'
                        job['error'] = str(exc)

    thread = threading.Thread(target=_worker, name='seed-demo-data', daemon=True)
    thread.start()
    return token


def get_seed_job(token):
    """Snapshot of a job's state, or ``None`` for an unknown/expired token."""
    if not token:
        return None
    with _lock:
        job = _jobs.get(token)
        if job is None:
            return None
        return dict(job)


def seed_config_from_form(form):
    """Build a :class:`SeedConfig` from the setup wizard's posted fields."""
    def flag(name):
        return form.get(name) == 'on'

    def clean_int(value, default):
        try:
            return max(0, int(value))
        except (TypeError, ValueError):
            return default

    try:
        fee = float(form.get('dummy_fee') or 2500.0)
    except (TypeError, ValueError):
        fee = 2500.0

    months = clean_int(form.get('dummy_period_months'), 12)
    return SeedConfig(
        student_count=clean_int(form.get('dummy_student_count'), 60),
        teacher_count=clean_int(form.get('dummy_teacher_count'), 8),
        monthly_fee=max(0.0, fee),
        months=min(240, max(1, months)),
        include_attendance=flag('dummy_attendance'),
        include_fees=flag('dummy_fees'),
        include_expenses=flag('dummy_expenses'),
        include_class_tests=flag('dummy_tests'),
        include_term_exams=flag('dummy_term_exams'),
        include_payroll=flag('dummy_payroll'),
        generate_photos=flag('dummy_photos'),
    )
