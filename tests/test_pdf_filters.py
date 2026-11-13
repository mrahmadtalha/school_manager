"""Tests for the PDF mark-filter feature.

Covers:
- _parse_pdf_filters: valid month/year/date/subject, bad values, empty
- _apply_pdf_filters: month, year, date_from, date_to, subject_id, combined,
  no-op when all None, absent mark passthrough
- _filter_label: empty / partial / full
- Single-student PDF route honours each filter param
- Bulk PDF route honours each filter param
- Class results page exposes 'subjects' in template context
- Filter modal markup is present in class_results.html
"""

from datetime import date
import types
import pytest

from app.database import db
from app.models import SubjectModel, TestModel, StudentMarkModel


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

MONTH_NAMES = ['', 'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
               'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']


def _make_mark(test_date, subject_id=1, marks=80, is_absent=False):
    """Return a mock StudentMarkModel-like object (no DB needed)."""
    t = types.SimpleNamespace(
        id=1,
        test_date=test_date,
        subject_id=subject_id,
        total_marks=100,
        test_title='Test',
    )
    m = types.SimpleNamespace(
        test_id=1,
        test_info=t,
        marks_obtained=marks,
        is_absent=is_absent,
        grade='A',
        percentage=float(marks),
    )
    return m


def _seed_two_months(app, seed):
    """Create tests in Oct and Nov for the seed student; return both marks."""
    with app.app_context():
        subj = SubjectModel.query.filter_by(class_id=seed['class_id']).first()
        if subj is None:
            subj = SubjectModel(name='Maths', class_id=seed['class_id'])
            db.session.add(subj)
            db.session.flush()

        t_oct = TestModel(test_title='Oct Test', test_date=date(2026, 10, 5),
                          test_type='Monthly', class_id=seed['class_id'],
                          subject_id=subj.id, total_marks=100)
        t_nov = TestModel(test_title='Nov Test', test_date=date(2026, 11, 5),
                          test_type='Monthly', class_id=seed['class_id'],
                          subject_id=subj.id, total_marks=100)
        db.session.add_all([t_oct, t_nov])
        db.session.flush()

        m_oct = StudentMarkModel(test_id=t_oct.id, student_id=seed['student_id'],
                                 marks_obtained=75, percentage=75.0, grade='B')
        m_nov = StudentMarkModel(test_id=t_nov.id, student_id=seed['student_id'],
                                 marks_obtained=85, percentage=85.0, grade='A')
        db.session.add_all([m_oct, m_nov])
        db.session.commit()
        return t_oct.id, t_nov.id, subj.id


# ---------------------------------------------------------------------------
# Unit: _parse_pdf_filters
# ---------------------------------------------------------------------------

class TestParsePdfFilters:
    def _parse(self, **kwargs):
        from app.routes.reports.cards import _parse_pdf_filters
        return _parse_pdf_filters(kwargs)

    def test_all_empty_returns_all_none(self):
        f = self._parse()
        assert f == {'month': None, 'year': None,
                     'date_from': None, 'date_to': None, 'subject_id': None}

    def test_valid_month(self):
        assert self._parse(pdf_month='10')['month'] == 10

    def test_month_zero_treated_as_none(self):
        assert self._parse(pdf_month='0')['month'] is None

    def test_invalid_month_string_returns_none(self):
        assert self._parse(pdf_month='abc')['month'] is None

    def test_valid_year(self):
        assert self._parse(pdf_year='2026')['year'] == 2026

    def test_valid_subject_id(self):
        assert self._parse(pdf_subject='3')['subject_id'] == 3

    def test_valid_date_from_iso(self):
        f = self._parse(pdf_date_from='2026-10-01')
        assert f['date_from'] == date(2026, 10, 1)

    def test_valid_date_to_iso(self):
        f = self._parse(pdf_date_to='2026-10-31')
        assert f['date_to'] == date(2026, 10, 31)

    def test_bad_date_string_returns_none(self):
        assert self._parse(pdf_date_from='not-a-date')['date_from'] is None

    def test_empty_string_date_returns_none(self):
        assert self._parse(pdf_date_from='')['date_from'] is None


# ---------------------------------------------------------------------------
# Unit: _apply_pdf_filters
# ---------------------------------------------------------------------------

class TestApplyPdfFilters:
    def _apply(self, marks, **kwargs):
        from app.routes.reports.cards import _apply_pdf_filters
        # Build a full filters dict (all None by default)
        base = {'month': None, 'year': None, 'date_from': None,
                'date_to': None, 'subject_id': None}
        base.update(kwargs)
        return _apply_pdf_filters(marks, base)

    def test_no_filters_returns_all(self):
        marks = [_make_mark(date(2026, 10, 1)), _make_mark(date(2026, 11, 1))]
        assert self._apply(marks) == marks

    def test_month_keeps_matching(self):
        oct_m = _make_mark(date(2026, 10, 1))
        nov_m = _make_mark(date(2026, 11, 1))
        result = self._apply([oct_m, nov_m], month=10)
        assert result == [oct_m]

    def test_month_excludes_all_when_no_match(self):
        marks = [_make_mark(date(2026, 10, 1))]
        assert self._apply(marks, month=3) == []

    def test_year_filter(self):
        m2026 = _make_mark(date(2026, 10, 1))
        m2025 = _make_mark(date(2025, 10, 1))
        assert self._apply([m2026, m2025], year=2026) == [m2026]

    def test_date_from_inclusive(self):
        early = _make_mark(date(2026, 10, 1))
        late  = _make_mark(date(2026, 10, 15))
        result = self._apply([early, late], date_from=date(2026, 10, 10))
        assert result == [late]

    def test_date_to_inclusive(self):
        early = _make_mark(date(2026, 10, 1))
        late  = _make_mark(date(2026, 10, 15))
        result = self._apply([early, late], date_to=date(2026, 10, 10))
        assert result == [early]

    def test_date_range(self):
        m1 = _make_mark(date(2026, 10, 5))
        m2 = _make_mark(date(2026, 10, 15))
        m3 = _make_mark(date(2026, 10, 25))
        result = self._apply([m1, m2, m3],
                             date_from=date(2026, 10, 10),
                             date_to=date(2026, 10, 20))
        assert result == [m2]

    def test_subject_id_filter(self):
        maths = _make_mark(date(2026, 10, 1), subject_id=1)
        eng   = _make_mark(date(2026, 10, 1), subject_id=2)
        assert self._apply([maths, eng], subject_id=1) == [maths]

    def test_combined_month_and_subject(self):
        oct_maths = _make_mark(date(2026, 10, 1), subject_id=1)
        oct_eng   = _make_mark(date(2026, 10, 1), subject_id=2)
        nov_maths = _make_mark(date(2026, 11, 1), subject_id=1)
        result = self._apply([oct_maths, oct_eng, nov_maths],
                             month=10, subject_id=1)
        assert result == [oct_maths]

    def test_absent_mark_passes_through_filter(self):
        """Absent marks are not special-cased by the filter — the PDF builder
        decides how to render them.  An absent mark in the target month must
        still be included."""
        absent = _make_mark(date(2026, 10, 1), is_absent=True)
        result = self._apply([absent], month=10)
        assert result == [absent]

    def test_empty_marks_list(self):
        assert self._apply([], month=10) == []


# ---------------------------------------------------------------------------
# Unit: _filter_label
# ---------------------------------------------------------------------------

class TestFilterLabel:
    def _label(self, **kwargs):
        from app.routes.reports.cards import _filter_label
        base = {'month': None, 'year': None, 'date_from': None,
                'date_to': None, 'subject_id': None}
        base.update(kwargs)
        return _filter_label(base)

    def test_empty_filters_returns_empty_string(self):
        assert self._label() == ''

    def test_month_only(self):
        lbl = self._label(month=10)
        assert '_m10' in lbl

    def test_year_only(self):
        assert '2026' in self._label(year=2026)

    def test_subject_id_only(self):
        assert 'subj3' in self._label(subject_id=3)

    def test_date_from_included(self):
        assert 'from' in self._label(date_from=date(2026, 10, 1)).lower()

    def test_combined_label_starts_with_underscore(self):
        lbl = self._label(month=10, year=2026)
        assert lbl.startswith('_')


# ---------------------------------------------------------------------------
# Integration: single-student PDF route
# ---------------------------------------------------------------------------

class TestSingleStudentPdfFilters:
    def _url(self, student_id, class_id, **extra):
        base = '/reports/student/%d/pdf?class_id=%d' % (student_id, class_id)
        for k, v in extra.items():
            base += '&%s=%s' % (k, v)
        return base

    def test_month_filter_returns_pdf(self, admin_client, app, seed):
        _seed_two_months(app, seed)
        r = admin_client.get(self._url(seed['student_id'], seed['class_id'],
                                       pdf_month=10))
        assert r.status_code == 200
        assert r.mimetype == 'application/pdf'

    def test_subject_filter_returns_pdf(self, admin_client, app, seed):
        _, _, subj_id = _seed_two_months(app, seed)
        r = admin_client.get(self._url(seed['student_id'], seed['class_id'],
                                       pdf_subject=subj_id))
        assert r.status_code == 200
        assert r.mimetype == 'application/pdf'

    def test_date_range_filter_returns_pdf(self, admin_client, app, seed):
        _seed_two_months(app, seed)
        r = admin_client.get(self._url(seed['student_id'], seed['class_id'],
                                       pdf_date_from='2026-10-01',
                                       pdf_date_to='2026-10-31'))
        assert r.status_code == 200
        assert r.mimetype == 'application/pdf'

    def test_filter_that_matches_nothing_still_returns_pdf(self, admin_client, app, seed):
        """Zero marks after filtering must not cause a 500 — an empty card is valid."""
        _seed_two_months(app, seed)
        r = admin_client.get(self._url(seed['student_id'], seed['class_id'],
                                       pdf_month=1))   # January — no tests
        assert r.status_code == 200
        assert r.mimetype == 'application/pdf'

    def test_filter_label_in_filename(self, admin_client, app, seed):
        _seed_two_months(app, seed)
        r = admin_client.get(self._url(seed['student_id'], seed['class_id'],
                                       pdf_month=10, pdf_year=2026))
        cd = r.headers.get('Content-Disposition', '')
        assert 'm10' in cd
        assert '2026' in cd

    def test_bad_filter_values_ignored_gracefully(self, admin_client, app, seed):
        """Garbage filter values must not raise — they fall back to no filter."""
        _seed_two_months(app, seed)
        r = admin_client.get(self._url(seed['student_id'], seed['class_id'],
                                       pdf_month='abc', pdf_date_from='not-a-date'))
        assert r.status_code == 200
        assert r.mimetype == 'application/pdf'


# ---------------------------------------------------------------------------
# Integration: bulk PDF route
# ---------------------------------------------------------------------------

class TestBulkPdfFilters:
    def _url(self, class_id, **extra):
        base = '/reports/class-results/pdf-all?class_id=%d' % class_id
        for k, v in extra.items():
            base += '&%s=%s' % (k, v)
        return base

    def test_month_filter_bulk(self, admin_client, app, seed):
        _seed_two_months(app, seed)
        r = admin_client.get(self._url(seed['class_id'], pdf_month=10))
        assert r.status_code == 200
        assert r.mimetype == 'application/pdf'

    def test_subject_filter_bulk(self, admin_client, app, seed):
        _, _, subj_id = _seed_two_months(app, seed)
        r = admin_client.get(self._url(seed['class_id'], pdf_subject=subj_id))
        assert r.status_code == 200
        assert r.mimetype == 'application/pdf'

    def test_date_range_filter_bulk(self, admin_client, app, seed):
        _seed_two_months(app, seed)
        r = admin_client.get(self._url(seed['class_id'],
                                       pdf_date_from='2026-10-01',
                                       pdf_date_to='2026-10-31'))
        assert r.status_code == 200
        assert r.mimetype == 'application/pdf'

    def test_filter_label_in_bulk_filename(self, admin_client, app, seed):
        _seed_two_months(app, seed)
        r = admin_client.get(self._url(seed['class_id'], pdf_month=11))
        cd = r.headers.get('Content-Disposition', '')
        assert 'm11' in cd


# ---------------------------------------------------------------------------
# Integration: class_results page — subjects in context + modal in HTML
# ---------------------------------------------------------------------------

class TestClassResultsPageFilters:
    def test_subjects_present_in_response(self, admin_client, app, seed):
        _seed_two_months(app, seed)
        r = admin_client.get('/reports/class-results?class_id=%d' % seed['class_id'])
        assert r.status_code == 200
        assert b'pdfFilterModal' in r.data

    def test_pdf_filter_modal_has_month_buttons(self, admin_client, app, seed):
        _seed_two_months(app, seed)
        r = admin_client.get('/reports/class-results?class_id=%d' % seed['class_id'])
        assert b'pdf-month-btn' in r.data

    def test_pdf_filter_modal_has_subject_select(self, admin_client, app, seed):
        _seed_two_months(app, seed)
        r = admin_client.get('/reports/class-results?class_id=%d' % seed['class_id'])
        assert b'pdfSubject' in r.data

    def test_pdf_filter_modal_has_date_range(self, admin_client, app, seed):
        _seed_two_months(app, seed)
        r = admin_client.get('/reports/class-results?class_id=%d' % seed['class_id'])
        assert b'pdfDateFrom' in r.data
        assert b'pdfDateTo' in r.data

    def test_subjects_list_populated(self, admin_client, app, seed):
        """Subject name must appear inside the modal select."""
        _seed_two_months(app, seed)
        with app.app_context():
            subj = SubjectModel.query.filter_by(class_id=seed['class_id']).first()
        r = admin_client.get('/reports/class-results?class_id=%d' % seed['class_id'])
        assert subj.name.encode() in r.data
