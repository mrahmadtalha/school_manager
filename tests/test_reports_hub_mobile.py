# -*- coding: utf-8 -*-
"""Analytics & Exports page (/reports/hub) on phones.

Same HTML for every screen size. On a phone the frame is smaller, the four tabs sit
in a 2 x 2 grid, the number boxes use a smaller figure, and the PDF / XLSX / CSV
buttons are finger-sized. These tests check the pieces that layout needs and that no
tab, filter, export button or chart went missing."""


def _page(admin_client, tab='analytics', query=''):
    response = admin_client.get('/reports/hub?tab=%s%s' % (tab, query))
    assert response.status_code == 200
    return response.get_data(as_text=True)


def _css(body):
    # base.html has its own <style>; the page's styles are the block that holds .hub-shell
    blocks = [part.split('</style>', 1)[0] for part in body.split('<style>')[1:]]
    return [block for block in blocks if '.hub-shell' in block][0]


def _phone(css):
    return css.split('@media (max-width: 767.98px) {', 1)[1].split('@media (max-width: 575.98px)', 1)[0]


def _small(css):
    return css.split('@media (max-width: 575.98px) {', 1)[1]


def test_phone_frame_tabs_and_filters_fit_the_screen(admin_client, app):
    phone = _phone(_css(_page(admin_client)))
    for needle in ('.hub-shell { padding: 0.8rem;',
                   '.hub-hero { padding: 1rem 1.1rem;',
                   '.hub-tabs { display: grid; grid-template-columns: 1fr 1fr;',
                   '.hub-tabs .nav-link { height: 100%; min-height: 3rem;',
                   '.hub-filter-card .btn { min-height: 2.7rem;'):
        assert needle in phone, needle


def test_phone_numbers_charts_and_export_buttons(admin_client, app):
    phone = _phone(_css(_page(admin_client)))
    for needle in ('.hub-kpi .kpi-num { font-size: 1.25rem; overflow-wrap: anywhere; }',
                   '.hub-chart-wrap { height: 230px; }',
                   '.hub-sec-head { flex-wrap: wrap;',
                   '.hub-export-card:hover { transform: none; }',
                   '.hub-export-card .card-footer .btn { flex: 1 1 auto; min-height: 2.5rem;'):
        assert needle in phone, needle


def test_small_phone_menus_do_not_zoom_the_page(admin_client, app):
    small = _small(_css(_page(admin_client)))
    assert '.hub-filter-card .form-select, .hub-export-card .form-select { font-size: 16px; }' in small


def test_section_headings_can_wrap_on_every_tab(admin_client, app):
    for tab in ('finance', 'academic', 'operations'):
        assert 'hub-sec-head' in _page(admin_client, tab), tab


def test_nothing_was_removed_from_the_analytics_tab(admin_client, app):
    body = _page(admin_client)
    for needle in ('Analytics &amp; Exports', 'Session:', 'name="month"', 'name="year"', 'name="class_id"',
                   'Apply', 'Reset', 'Analytics', 'Finance &amp; Fees', 'Academic &amp; Examinations',
                   'Students, Staff &amp; Operations', 'Attendance Rate', 'Exam Pass Rate', 'Active Teachers',
                   'id="hubFeeChart"', 'id="hubAttendanceChart"', 'id="hubAcademicChart"'):
        assert needle in body, needle


def test_nothing_was_removed_from_the_export_tabs(admin_client, app):
    finance = _page(admin_client, 'finance')
    for needle in ('Monthly Fee Ledgers', 'Defaulter Lists', 'Collection Summaries', 'Discount Summaries',
                   'Admission Fees Register', 'Staff Salary Register', 'Financial Summary', 'Expense Reports',
                   'Open insights', '>PDF<', '>XLSX<', '>CSV<'):
        assert needle in finance, needle
    academic = _page(admin_client, 'academic')
    for needle in ('Consolidated Class Result', 'Whole Class Result Matrix', 'All Report Cards',
                   'Term Examination Documents', 'Merit / Position List', 'Broad Sheets',
                   'Select a class to enable class exports'):
        assert needle in academic, needle
    operations = _page(admin_client, 'operations')
    for needle in ('Student Enrolment Roster', 'Staff Directory', 'Class Attendance (Daily)', 'Staff Attendance',
                   'Attendance Summary', 'Subject-Teacher Allocation', '/students/export/excel', '/teachers/export/pdf'):
        assert needle in operations, needle
