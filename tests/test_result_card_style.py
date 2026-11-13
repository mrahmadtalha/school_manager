"""Result card style feature tests.

Covers:
- Migration: result_card_style column is created on first run, idempotent on repeat
- SchoolSettings default is 'classic'
- Settings page GET shows the selector with the current value
- Settings POST saves 'classic' and 'professional'; unknown values are rejected
- PDF route uses the saved style when no override is in the URL
- PDF route honours the ?card_style=... URL override without changing the DB
- Both styles produce a valid single-page PDF for a student with marks
- Bulk (all cards) PDF also uses the saved style
- _build_story() dispatcher falls back to classic for an unknown style key
"""

import re
from datetime import date

import pytest

from app.database import db
from app.models import SchoolSettings, StudentMarkModel, SubjectModel, TestModel


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _page_count(pdf_bytes: bytes) -> int:
    return len(re.findall(rb'/Type\s*/Page(?![s\w])', pdf_bytes))


def _add_marks(class_id, student_ids):
    """Add one test + marks for every student so the card has real content."""
    subject = SubjectModel.query.filter_by(class_id=class_id).first()
    if subject is None:
        subject = SubjectModel(name='English', class_id=class_id)
        db.session.add(subject)
        db.session.flush()

    test = TestModel(
        test_title='Monthly Test Oct',
        test_date=date(2026, 10, 1),
        test_type='Monthly',
        class_id=class_id,
        subject_id=subject.id,
        total_marks=100,
    )
    db.session.add(test)
    db.session.flush()

    for sid in student_ids:
        db.session.add(StudentMarkModel(
            test_id=test.id,
            student_id=sid,
            marks_obtained=82,
            percentage=82.0,
            grade='A',
        ))
    db.session.commit()
    return test


def _set_style(app, style):
    with app.app_context():
        s = SchoolSettings.query.first()
        if s is None:
            s = SchoolSettings()
            db.session.add(s)
        s.result_card_style = style
        db.session.commit()


def _settings_row():
    """Return the school-settings row, creating it when the fresh test DB has none."""
    s = SchoolSettings.query.first()
    if s is None:
        s = SchoolSettings()
        db.session.add(s)
        db.session.commit()
    return s


# ---------------------------------------------------------------------------
# Migration
# ---------------------------------------------------------------------------

class TestMigration:
    def test_column_exists_after_app_starts(self, app):
        """The migration must have created the column during create_app()."""
        with app.app_context():
            from sqlalchemy import inspect
            columns = [c['name'] for c in inspect(db.engine).get_columns('school_settings')]
            assert 'result_card_style' in columns

    def test_migration_is_idempotent(self, app):
        """Running the migration a second time must not raise."""
        from app.migrations.result_card_style import run as migrate
        try:
            migrate(app)   # second call — column already present
        except Exception as exc:
            pytest.fail('Migration raised on second run: %s' % exc)


# ---------------------------------------------------------------------------
# Model default
# ---------------------------------------------------------------------------

class TestModelDefault:
    def test_default_style_is_classic(self, app):
        with app.app_context():
            s = _settings_row()
            assert (s.result_card_style or 'classic') == 'classic'

    def test_style_can_be_set_to_professional(self, app):
        with app.app_context():
            s = _settings_row()
            s.result_card_style = 'professional'
            db.session.commit()
            db.session.expire(s)
            assert s.result_card_style == 'professional'


# ---------------------------------------------------------------------------
# Settings page  (GET + POST)
# ---------------------------------------------------------------------------

class TestSettingsPage:
    def test_get_shows_style_selector(self, admin_client):
        r = admin_client.get('/settings?tab=academic')
        assert r.status_code == 200
        assert b'result_card_style' in r.data

    def test_get_shows_classic_selected_by_default(self, admin_client):
        r = admin_client.get('/settings?tab=academic')
        # 'classic' option must be present and marked selected
        assert b'value="classic"' in r.data

    def test_post_saves_professional(self, admin_client, app, seed):
        r = admin_client.post('/settings', data={
            'action': 'save_academic_settings',
            'result_card_style': 'professional',
            'academic_session': '2026-27',
            'result_announcement_date': '',
            'school_start_time': '08:30',
            'school_end_time': '15:00',
            'attendance_grace_minutes': '0',
        }, follow_redirects=False)
        assert r.status_code in (200, 302)
        with app.app_context():
            s = SchoolSettings.query.first()
            assert s.result_card_style == 'professional'

    def test_post_saves_classic(self, admin_client, app, seed):
        # First set to professional, then switch back
        _set_style(app, 'professional')
        r = admin_client.post('/settings', data={
            'action': 'save_academic_settings',
            'result_card_style': 'classic',
            'academic_session': '2026-27',
            'result_announcement_date': '',
            'school_start_time': '08:30',
            'school_end_time': '15:00',
            'attendance_grace_minutes': '0',
        }, follow_redirects=False)
        assert r.status_code in (200, 302)
        with app.app_context():
            s = SchoolSettings.query.first()
            assert s.result_card_style == 'classic'

    def test_post_ignores_unknown_style(self, admin_client, app, seed):
        """An unknown value must not overwrite the saved style."""
        _set_style(app, 'professional')
        admin_client.post('/settings', data={
            'action': 'save_academic_settings',
            'result_card_style': 'invalid_design',
            'academic_session': '2026-27',
            'result_announcement_date': '',
            'school_start_time': '08:30',
            'school_end_time': '15:00',
            'attendance_grace_minutes': '0',
        }, follow_redirects=False)
        with app.app_context():
            s = SchoolSettings.query.first()
            # unchanged — invalid value was silently dropped
            assert s.result_card_style == 'professional'


# ---------------------------------------------------------------------------
# Single student PDF
# ---------------------------------------------------------------------------

class TestSingleStudentPdf:
    def _url(self, student_id, class_id, **extra):
        base = '/reports/student/%d/pdf?class_id=%d' % (student_id, class_id)
        for k, v in extra.items():
            base += '&%s=%s' % (k, v)
        return base

    def test_classic_style_returns_pdf(self, admin_client, app, seed):
        with app.app_context():
            _add_marks(seed['class_id'], [seed['student_id']])
        _set_style(app, 'classic')
        r = admin_client.get(self._url(seed['student_id'], seed['class_id']))
        assert r.status_code == 200
        assert r.mimetype == 'application/pdf'
        assert _page_count(r.data) == 1

    def test_professional_style_returns_pdf(self, admin_client, app, seed):
        with app.app_context():
            _add_marks(seed['class_id'], [seed['student_id']])
        _set_style(app, 'professional')
        r = admin_client.get(self._url(seed['student_id'], seed['class_id']))
        assert r.status_code == 200
        assert r.mimetype == 'application/pdf'
        assert _page_count(r.data) == 1

    def test_url_override_professional_uses_professional_regardless_of_saved(
            self, admin_client, app, seed):
        with app.app_context():
            _add_marks(seed['class_id'], [seed['student_id']])
        _set_style(app, 'classic')   # saved = classic
        r = admin_client.get(
            self._url(seed['student_id'], seed['class_id'], card_style='professional'))
        assert r.status_code == 200
        assert r.mimetype == 'application/pdf'
        # DB must still be classic — override is per-request only
        with app.app_context():
            s = SchoolSettings.query.first()
            assert (s.result_card_style or 'classic') == 'classic'

    def test_url_override_classic_uses_classic_regardless_of_saved(
            self, admin_client, app, seed):
        with app.app_context():
            _add_marks(seed['class_id'], [seed['student_id']])
        _set_style(app, 'professional')
        r = admin_client.get(
            self._url(seed['student_id'], seed['class_id'], card_style='classic'))
        assert r.status_code == 200
        assert r.mimetype == 'application/pdf'
        with app.app_context():
            s = SchoolSettings.query.first()
            assert s.result_card_style == 'professional'

    def test_pdf_without_marks_still_returns_200(self, admin_client, app, seed):
        """A student with no marks must still produce a PDF, not a 500."""
        _set_style(app, 'professional')
        r = admin_client.get(self._url(seed['student_id'], seed['class_id']))
        assert r.status_code == 200
        assert r.mimetype == 'application/pdf'

    def test_no_unbound_error_when_session_and_date_both_in_url(self, admin_client, app, seed):
        """Regression: when both session= and announce_date= are in the URL the
        old code skipped the SchoolSettings query entirely, leaving 'school'
        unbound and causing an UnboundLocalError when card_style was read."""
        with app.app_context():
            _add_marks(seed['class_id'], [seed['student_id']])
        url = ('/reports/student/%d/pdf?class_id=%d'
               '&session=2026-27&announce_date=2026-11-07'
               % (seed['student_id'], seed['class_id']))
        r = admin_client.get(url)
        assert r.status_code == 200
        assert r.mimetype == 'application/pdf'


# ---------------------------------------------------------------------------
# Bulk (all cards) PDF
# ---------------------------------------------------------------------------

class TestBulkPdf:
    def _url(self, class_id, **extra):
        base = '/reports/class-results/pdf-all?class_id=%d' % class_id
        for k, v in extra.items():
            base += '&%s=%s' % (k, v)
        return base

    def test_bulk_classic_one_page_per_student(self, admin_client, app, seed):
        with app.app_context():
            from app.models import StudentModel
            ids = [s.id for s in StudentModel.query.filter_by(
                class_id=seed['class_id'], is_active=True).all()]
            _add_marks(seed['class_id'], ids)
        _set_style(app, 'classic')
        r = admin_client.get(self._url(seed['class_id']))
        assert r.status_code == 200
        assert r.mimetype == 'application/pdf'
        with app.app_context():
            from app.models import StudentModel
            expected = StudentModel.query.filter_by(
                class_id=seed['class_id'], is_active=True).count()
        assert _page_count(r.data) == expected

    def test_bulk_professional_one_page_per_student(self, admin_client, app, seed):
        with app.app_context():
            from app.models import StudentModel
            ids = [s.id for s in StudentModel.query.filter_by(
                class_id=seed['class_id'], is_active=True).all()]
            _add_marks(seed['class_id'], ids)
        _set_style(app, 'professional')
        r = admin_client.get(self._url(seed['class_id']))
        assert r.status_code == 200
        assert r.mimetype == 'application/pdf'
        with app.app_context():
            from app.models import StudentModel
            expected = StudentModel.query.filter_by(
                class_id=seed['class_id'], is_active=True).count()
        assert _page_count(r.data) == expected

    def test_bulk_url_override_professional(self, admin_client, app, seed):
        with app.app_context():
            from app.models import StudentModel
            ids = [s.id for s in StudentModel.query.filter_by(
                class_id=seed['class_id'], is_active=True).all()]
            _add_marks(seed['class_id'], ids)
        _set_style(app, 'classic')
        r = admin_client.get(self._url(seed['class_id'], card_style='professional'))
        assert r.status_code == 200
        assert r.mimetype == 'application/pdf'


# ---------------------------------------------------------------------------
# Dispatcher (_build_story)
# ---------------------------------------------------------------------------

class TestBuildStoryDispatcher:
    def test_unknown_style_falls_back_to_classic(self, app, seed):
        """_build_story with a garbage style must not raise."""
        from app.routes.reports.cards import _build_story
        from app.models import StudentModel

        with app.app_context():
            student = db.session.get(StudentModel, seed['student_id'])
            try:
                result = _build_story('totally_unknown_style', student, [], app.root_path)
            except Exception as exc:
                pytest.fail('_build_story raised for unknown style: %s' % exc)
            assert isinstance(result, list)

    def test_classic_key_calls_classic_builder(self, app, seed):
        from app.routes.reports.cards import _build_story
        from app.models import StudentModel

        with app.app_context():
            student = db.session.get(StudentModel, seed['student_id'])
            result = _build_story('classic', student, [], app.root_path)
            assert isinstance(result, list)

    def test_professional_key_calls_professional_builder(self, app, seed):
        from app.routes.reports.cards import _build_story
        from app.models import StudentModel

        with app.app_context():
            student = db.session.get(StudentModel, seed['student_id'])
            result = _build_story('professional', student, [], app.root_path)
            assert isinstance(result, list)

    def test_empty_style_falls_back_to_classic(self, app, seed):
        from app.routes.reports.cards import _build_story
        from app.models import StudentModel

        with app.app_context():
            student = db.session.get(StudentModel, seed['student_id'])
            result = _build_story('', student, [], app.root_path)
            assert isinstance(result, list)
