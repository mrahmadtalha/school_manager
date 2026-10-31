# -*- coding: utf-8 -*-
"""Staff Salaries page (/payroll) on phones.

Same HTML for every screen size. On a phone the header buttons sit in a grid, the month bar
and the find box are stacked, the summary is two lines of two boxes, every teacher card has
big tap targets (salary on its own line, bonus and deductions side by side, Pay on top of
the card buttons), the Save bar leaves room for the round assistant button, and the Pay /
Void windows fit the screen. These tests check the pieces that layout needs and that no
button, box, filter, form or window went missing."""

from datetime import date

from app.database import db
from app.models import StaffPayroll
from app.services import payroll_service
from tests.test_payroll_redesign import _teacher


def _page(admin_client, query=''):
    response = admin_client.get('/payroll' + query)
    assert response.status_code == 200
    return response.get_data(as_text=True)


def _css(body):
    # base.html has its own <style>; the page's styles are the block that holds .pr-band
    blocks = [part.split('</style>', 1)[0] for part in body.split('<style>')[1:]]
    return [block for block in blocks if '.pr-band' in block][0]


def _phone(css):
    return css.split('@media (max-width: 767.98px) {', 1)[1].split('@media (max-width: 575.98px)', 1)[0]


def _small(css):
    return css.split('@media (max-width: 575.98px) {', 1)[1]


def _teachers_with_a_part_paid_salary(app):
    """One teacher not saved yet, one saved and part paid (so Pay, Void and Payslip show)."""
    with app.app_context():
        saved = _teacher('PM1', 'Phone Saved Teacher', 30000.0)
        _teacher('PM2', 'Phone Unsaved Teacher', 20000.0)
        month = payroll_service.current_month_key()
        payroll_service.generate(month, {'include_%d' % saved.id: 'on'}, generated_by='tester')
        record = StaffPayroll.query.filter_by(teacher_id=saved.id, month_year=month).one()
        payroll_service.record_salary_payment(record, 10000.0, date.today())
        db.session.commit()


def test_phone_header_month_bar_and_find_box_fit_the_screen(admin_client, app):
    with app.app_context():
        _teacher()
    phone = _phone(_css(_page(admin_client)))
    for needle in ('.pr-tools { width: 100%; display: grid; grid-template-columns: 1fr 1fr;',
                   '.pr-tools > .btn { width: 100%; min-height: 2.6rem;',
                   '.pr-bar-top { flex-direction: column; align-items: stretch; }',
                   '.pr-nav form { order: -1; flex: 1 1 100%; }',                         # month menu on its own line
                   '.pr-nav > .btn { flex: 1; min-height: 2.6rem;',                       # Previous and Next side by side
                   '.pr-nav .pr-seg { flex: 1 1 100%; display: flex; }',
                   '.pr-find { flex-direction: column; align-items: stretch;',
                   '.pr-search { flex: 1 1 auto; min-width: 0; max-width: none; width: 100%; }',
                   '.pr-chip { min-height: 2.3rem;',
                   '.pr-count { flex-direction: column; align-items: stretch;'):
        assert needle in phone, needle


def test_header_buttons_use_the_phone_grid(admin_client, app):
    with app.app_context():
        _teacher()
    body = _page(admin_client)
    assert 'btn-toolbar mb-2 mb-md-0 gap-2 pr-tools' in body
    assert 'Deduction rules' in body and 'Teachers' in body


def test_phone_summary_is_two_lines_and_boxes_do_not_zoom(admin_client, app):
    with app.app_context():
        _teacher()
    css = _css(_page(admin_client))
    small = _small(css)
    assert '.pr-band { grid-template-columns: 1fr; }' not in css                          # no longer one tall stack
    assert '.pr-stat + .pr-stat { border-left: 0; border-top: 1px solid #eef2f7; }' not in css
    assert '.pr-band { grid-template-columns: 1fr 1fr; }' in css                          # two boxes per line
    for needle in ('.pr-num { font-size: 1.2rem; }', 'font-size: 16px', '.pr-list { grid-template-columns: 1fr; }'):
        assert needle in small, needle
    for box in ('.pr-search input', '.pr-nav .form-select', '.pr-rules .form-control',
                '.pr-fld .form-control', '.pr-noteline .form-control', '.pr-form .form-control'):
        assert box in small.split('font-size: 16px', 1)[0], box


def test_teacher_card_is_easy_to_use_on_a_phone(admin_client, app):
    _teachers_with_a_part_paid_salary(app)
    css = _css(_page(admin_client))
    phone, small = _phone(css), _small(css)
    for needle in ('.pr-fld .form-control { min-height: 2.75rem; }',
                   '.pr-pick .form-check-input { width: 1.4rem; height: 1.4rem; }',   # bigger Save tick box
                   '.pr-foot .btn { flex: 1 1 calc(50% - 0.4rem); min-height: 2.6rem;',
                   '.pr-foot .btn-success { flex: 1 1 100%; order: -1; }',            # Pay on top
                   '.pr-foot .pr-hint { flex: 1 1 100%;',
                   '.pr-sugg button { min-height: 2.2rem;',
                   '.pr-noteline > a { display: inline-block; padding: 0.4rem 0; }'):
        assert needle in phone, needle
    for needle in ('.pr-flds { grid-template-columns: 1fr 1fr; }',
                   '.pr-flds > .pr-fld:first-child { grid-column: 1 / -1; }'):          # salary alone, bonus + deductions together
        assert needle in small, needle


def test_save_bar_stays_on_screen_and_leaves_room_for_the_assistant_button(admin_client, app):
    _teachers_with_a_part_paid_salary(app)
    css = _css(_page(admin_client))
    phone = _phone(css)
    assert '.pr-save { position: sticky;' in css                                          # still always in reach
    for needle in ('.pr-save { bottom: 0.5rem; flex-direction: column;',
                   'padding-inline-end: 4.9rem;',                                         # round assistant button is 3.4rem wide
                   '.pr-save > .d-flex { display: grid !important; grid-template-columns: 1fr 1fr;',
                   '.pr-save .btn:only-child { grid-column: 1 / -1; }'):
        assert needle in phone, needle


def test_cards_and_list_switch_only_where_it_does_something(admin_client, app):
    with app.app_context():
        _teacher()
    body = _page(admin_client)
    css = _css(body)
    assert 'pr-seg pr-viewseg' in body
    assert 'data-mode="cards"' in body and 'data-mode="list"' in body                    # still in the page
    assert '@media (max-width: 1199.98px) {\n        .pr-viewseg { display: none; }' in css.replace('\r\n', '\n')
    assert '@media (min-width: 1200px) {\n        .pr-mode-list .pr-list' in css.replace('\r\n', '\n')


def test_pay_and_void_windows_fit_the_phone(admin_client, app):
    _teachers_with_a_part_paid_salary(app)
    phone = _phone(_css(_page(admin_client)))
    for needle in ('.pr-page .modal .modal-header, .pr-page .modal .modal-body, .pr-page .modal .modal-footer { padding-left: 1rem; padding-right: 1rem; }',
                   '.pr-page .modal .modal-footer .btn { flex: 1 1 0; min-height: 2.7rem; }',
                   '.pr-form .pr-pay label { min-height: 2.8rem;',
                   '.pr-form .pr-quick button { min-height: 2.3rem;',
                   '.pr-form .form-control { min-height: 2.9rem; }'):
        assert needle in phone, needle


def test_deduction_rules_form_is_phone_friendly(admin_client, app):
    with app.app_context():
        _teacher()
    phone = _phone(_css(_page(admin_client)))
    for needle in ('.pr-rules .btn { width: 100%; min-height: 2.7rem; }',
                   '.pr-rules .form-check-input { width: 1.25rem; height: 1.25rem;'):
        assert needle in phone, needle


def test_phone_rules_are_only_inside_media_queries(admin_client, app):
    """The computer layout must not change: every new rule sits inside a max-width query."""
    with app.app_context():
        _teacher()
    css = _css(_page(admin_client)).replace('\r\n', '\n')
    outside = css.split('@media (max-width: 991.98px) {', 1)[0]
    for needle in ('.pr-tools', '.pr-viewseg', '.pr-save .btn:only-child', 'padding-inline-end: 4.9rem'):
        assert needle not in outside, needle


def test_nothing_was_removed_from_the_page(admin_client, app):
    _teachers_with_a_part_paid_salary(app)
    body = _page(admin_client)
    for needle in ('Staff Salaries', 'Deduction rules', 'id="rulesBox"', 'name="per_late"', 'name="leave_as_absent"',
                   'Apply Rules', 'Previous', 'Next', 'This Month', 'name="month"', 'Choose month',
                   'Check the amounts', 'Save the salaries', 'Pay and mark as paid',
                   'Teachers saved', 'Total salaries (after deductions)', 'Already paid', 'Still to pay',
                   'id="prSearch"', 'data-filter="all"', 'data-filter="unsaved"', 'data-filter="partial"',
                   'id="selectAllRows"', 'Tick all', 'data-mode="cards"', 'data-mode="list"', 'id="prBody"',
                   'Use suggested', 'Add note', 'Take-home', 'Payslip', 'void-salary-btn', 'Pay rest',
                   'Save Salaries', 'Mark All as Paid', 'id="ticked-total"', 'id="payrollForm"', 'id="bulkPaidForm"',
                   'id="markPaidModal"', 'id="voidSalaryModal"', 'How much are you paying now?', 'How did you pay?',
                   'On which day?', 'Pay the full amount', 'Entered by mistake', 'Yes, Mark as Paid', 'Void payment',
                   'value="Cash"', 'value="Bank"', 'value="Cheque"', 'data-quick-date="0"', 'data-quick-date="-1"'):
        assert needle in body, needle
