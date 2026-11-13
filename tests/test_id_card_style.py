"""ID card style feature tests.

Covers:
- Migration: id_card_style column is created on first run, idempotent on repeat
- SchoolSettings default is 'classic'
- Settings page GET shows the selector with the current value
- Settings POST saves 'classic' and 'professional'; unknown values are rejected
- Documents page GET shows the "Card design" selector on both the student and
  staff forms, pre-filled with the saved default
- Student and staff ID card PDF routes use the saved style when no override
  is in the URL
- Unlike the Result Card style, an ID card ``?card_style=...`` URL override
  also becomes the new saved default (this is the point of the feature: the
  dropdown's choice is remembered for next time)
- An unknown ``?card_style=`` value is ignored (falls back to the saved
  style, and does not overwrite it)
- Both styles produce a valid PDF for a student and for a teacher
- build_id_cards_pdf()'s style dispatcher falls back to the classic drawer
  for an unknown style key
"""

from datetime import date

import pytest

from app.database import db
from app.models import SchoolSettings, TeacherModel


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _set_style(app, style):
    with app.app_context():
        s = SchoolSettings.query.first()
        if s is None:
            s = SchoolSettings()
            db.session.add(s)
        s.id_card_style = style
        db.session.commit()


def _add_teacher(app):
    with app.app_context():
        teacher = TeacherModel(
            teacher_id_str='T001',
            teacher_name='Sara Ahmed',
            qualification='M.Ed',
            salary=40000,
            monthly_salary=40000,
            assigned_class='Class 1',
            joining_date=date(2024, 4, 1),
        )
        db.session.add(teacher)
        db.session.commit()
        return teacher.id


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
            assert 'id_card_style' in columns

    def test_migration_is_idempotent(self, app):
        """Running the migration a second time must not raise."""
        from app.migrations.id_card_style import run as migrate
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
            assert (s.id_card_style or 'classic') == 'classic'

    def test_style_can_be_set_to_professional(self, app):
        with app.app_context():
            s = _settings_row()
            s.id_card_style = 'professional'
            db.session.commit()
            db.session.expire(s)
            assert s.id_card_style == 'professional'


# ---------------------------------------------------------------------------
# Settings page  (GET + POST)
# ---------------------------------------------------------------------------

class TestSettingsPage:
    def test_get_shows_style_selector(self, admin_client):
        r = admin_client.get('/settings?tab=academic')
        assert r.status_code == 200
        assert b'id_card_style' in r.data

    def test_post_saves_professional(self, admin_client, app, seed):
        r = admin_client.post('/settings', data={
            'action': 'save_academic_settings',
            'id_card_style': 'professional',
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
            assert s.id_card_style == 'professional'

    def test_post_saves_classic(self, admin_client, app, seed):
        _set_style(app, 'professional')
        r = admin_client.post('/settings', data={
            'action': 'save_academic_settings',
            'id_card_style': 'classic',
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
            assert s.id_card_style == 'classic'

    def test_post_ignores_unknown_style(self, admin_client, app, seed):
        """An unknown value must not overwrite the saved style."""
        _set_style(app, 'professional')
        admin_client.post('/settings', data={
            'action': 'save_academic_settings',
            'id_card_style': 'invalid_design',
            'result_card_style': 'classic',
            'academic_session': '2026-27',
            'result_announcement_date': '',
            'school_start_time': '08:30',
            'school_end_time': '15:00',
            'attendance_grace_minutes': '0',
        }, follow_redirects=False)
        with app.app_context():
            s = SchoolSettings.query.first()
            # unchanged — invalid value was silently dropped
            assert s.id_card_style == 'professional'


# ---------------------------------------------------------------------------
# Documents page
# ---------------------------------------------------------------------------

class TestDocumentsPage:
    def test_get_shows_card_style_dropdown(self, admin_client, seed):
        r = admin_client.get('/documents')
        assert r.status_code == 200
        assert r.data.count(b'name="card_style"') == 2  # student form + staff form

    def test_dropdown_preselects_saved_default(self, admin_client, app, seed):
        _set_style(app, 'professional')
        r = admin_client.get('/documents')
        assert r.status_code == 200
        assert b'value="professional" selected' in r.data


# ---------------------------------------------------------------------------
# Student ID card PDF
# ---------------------------------------------------------------------------

class TestStudentIdCardPdf:
    def _url(self, student_id, **extra):
        base = '/documents/id-cards/students.pdf?student_id=%d' % student_id
        for k, v in extra.items():
            base += '&%s=%s' % (k, v)
        return base

    def test_classic_style_returns_pdf(self, admin_client, app, seed):
        _set_style(app, 'classic')
        r = admin_client.get(self._url(seed['student_id']))
        assert r.status_code == 200
        assert r.mimetype == 'application/pdf'
        assert r.data.startswith(b'%PDF')

    def test_professional_style_returns_pdf(self, admin_client, app, seed):
        _set_style(app, 'professional')
        r = admin_client.get(self._url(seed['student_id']))
        assert r.status_code == 200
        assert r.mimetype == 'application/pdf'
        assert r.data.startswith(b'%PDF')

    def test_url_override_is_saved_as_new_default(self, admin_client, app, seed):
        """Unlike the Result Card style, choosing a card design here is meant
        to be remembered for next time — the dropdown's value both renders
        this PDF and becomes the new saved default."""
        _set_style(app, 'classic')
        r = admin_client.get(self._url(seed['student_id'], card_style='professional'))
        assert r.status_code == 200
        assert r.mimetype == 'application/pdf'
        with app.app_context():
            s = SchoolSettings.query.first()
            assert s.id_card_style == 'professional'

    def test_unknown_url_style_falls_back_and_is_not_saved(self, admin_client, app, seed):
        _set_style(app, 'classic')
        r = admin_client.get(self._url(seed['student_id'], card_style='totally_unknown'))
        assert r.status_code == 200
        assert r.mimetype == 'application/pdf'
        with app.app_context():
            s = SchoolSettings.query.first()
            # ignored — the saved default is untouched
            assert s.id_card_style == 'classic'

    def test_all_students_classic(self, admin_client, app, seed):
        _set_style(app, 'classic')
        r = admin_client.get('/documents/id-cards/students.pdf')
        assert r.status_code == 200
        assert r.mimetype == 'application/pdf'

    def test_all_students_professional(self, admin_client, app, seed):
        _set_style(app, 'professional')
        r = admin_client.get('/documents/id-cards/students.pdf')
        assert r.status_code == 200
        assert r.mimetype == 'application/pdf'


# ---------------------------------------------------------------------------
# Staff ID card PDF
# ---------------------------------------------------------------------------

class TestStaffIdCardPdf:
    def _url(self, teacher_id, **extra):
        base = '/documents/id-cards/teachers.pdf?teacher_id=%d' % teacher_id
        for k, v in extra.items():
            base += '&%s=%s' % (k, v)
        return base

    def test_classic_style_returns_pdf(self, admin_client, app, seed):
        teacher_id = _add_teacher(app)
        _set_style(app, 'classic')
        r = admin_client.get(self._url(teacher_id))
        assert r.status_code == 200
        assert r.mimetype == 'application/pdf'
        assert r.data.startswith(b'%PDF')

    def test_professional_style_returns_pdf(self, admin_client, app, seed):
        teacher_id = _add_teacher(app)
        _set_style(app, 'professional')
        r = admin_client.get(self._url(teacher_id))
        assert r.status_code == 200
        assert r.mimetype == 'application/pdf'
        assert r.data.startswith(b'%PDF')

    def test_url_override_is_saved_as_new_default(self, admin_client, app, seed):
        teacher_id = _add_teacher(app)
        _set_style(app, 'classic')
        r = admin_client.get(self._url(teacher_id, card_style='professional'))
        assert r.status_code == 200
        with app.app_context():
            s = SchoolSettings.query.first()
            assert s.id_card_style == 'professional'


# ---------------------------------------------------------------------------
# Style dispatcher (build_id_cards_pdf)
# ---------------------------------------------------------------------------

class TestCardStyleDispatcher:
    def test_unknown_style_falls_back_to_classic_drawer(self):
        """build_id_cards_pdf() with a garbage style must not raise, and must
        fall back to the classic drawer."""
        from app.services.id_documents import build_id_cards_pdf, _CARD_DRAWERS, _draw_id_card

        assert _CARD_DRAWERS.get('totally_unknown_style', _draw_id_card) is _draw_id_card

        school = {'name': 'Test School', 'tagline': '', 'address': '', 'phone': '',
                  'email': '', 'logo_path': ''}
        person = {
            'name': 'Ali Khan', 'role_label': 'STUDENT IDENTITY CARD', 'badge': 'ID 1001',
            'photo_path': None, 'qr': 'STUDENT|1001|Ali Khan', 'role_pill': 'Class 1',
            'rows': [('Roll No', '1001'), ('Class', 'Class 1'),
                     ('Father', 'Imran Khan'), ('Phone', '03001234567')],
        }
        try:
            output = build_id_cards_pdf([person], school, '2026-27',
                                        style='totally_unknown_style')
        except Exception as exc:
            pytest.fail('build_id_cards_pdf raised for unknown style: %s' % exc)
        assert output.read().startswith(b'%PDF')

    def test_classic_and_professional_both_registered(self):
        from app.services.id_documents import CARD_STYLES, _CARD_DRAWERS

        assert set(CARD_STYLES) == {'classic', 'professional'}
        assert set(_CARD_DRAWERS.keys()) == {'classic', 'professional'}
