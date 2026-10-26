# -*- coding: utf-8 -*-
"""English / Urdu interface switch (Phase 1)."""
import os

import pytest

from app.services import i18n
from tests.test_admission_fee import (  # noqa: F401  (fixtures are used by name)
    accountant_client, admin_client, teacher_client, _add_student, _student)

STATIC = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'app', 'static')


def _urdu(client):
    assert client.get('/language/ur').status_code == 302


def test_english_stays_english_by_default(admin_client, seed):
    html = admin_client.get('/students').get_data(as_text=True)
    assert 'dir="rtl"' not in html and 'Add Student' in html and 'bootstrap.rtl' not in html


def test_switching_to_urdu_translates_and_flips_the_page(admin_client, seed):
    _urdu(admin_client)
    html = admin_client.get('/students').get_data(as_text=True)
    assert '<html' in html and 'lang="ur" dir="rtl"' in html
    assert 'bootstrap.rtl.min.css' in html and 'rtl.css' in html
    assert 'طالب علم شامل کریں' in html            # Add Student
    assert 'رول نمبر' in html                       # Roll No
    assert 'داخلہ نمبر' in html                     # Admission No
    assert '>Add Student<' not in html and 'Add Student</button>' not in html


def test_the_switch_is_remembered_and_can_be_undone(admin_client, seed):
    _urdu(admin_client)
    assert 'dir="rtl"' in admin_client.get('/fees').get_data(as_text=True)
    assert 'dir="rtl"' in admin_client.get('/students').get_data(as_text=True)
    admin_client.get('/language/en')
    html = admin_client.get('/fees').get_data(as_text=True)
    assert 'dir="rtl"' not in html and 'Fee Management Ledger' in html


def test_an_unknown_language_falls_back_to_english(admin_client, seed):
    admin_client.get('/language/xx')
    assert 'dir="rtl"' not in admin_client.get('/students').get_data(as_text=True)


def test_everyday_words_use_the_agreed_urdu_terms(admin_client, seed):
    _urdu(admin_client)
    fees = admin_client.get('/fees').get_data(as_text=True)
    assert 'داخلہ فیس' in fees and 'پوری کلاس کی ماہانہ فیس مقرر کریں' in fees
    assert 'ایڈمشن' not in fees


@pytest.mark.parametrize('path', ['/', '/students', '/fees', '/fees/reminders',
                                  '/admission-fees', '/classes', '/settings', '/automation'])
def test_key_pages_render_in_urdu(admin_client, seed, path):
    _urdu(admin_client)
    resp = admin_client.get(path)
    assert resp.status_code == 200
    assert 'dir="rtl"' in resp.get_data(as_text=True)


def test_what_people_typed_is_never_translated(admin_client, seed):
    _add_student(admin_client, seed, 5001, 'Present Class')       # a name made of dictionary words
    _urdu(admin_client)
    html = admin_client.get('/students').get_data(as_text=True)
    assert 'Present Class' in html


def test_teacher_and_accountant_can_switch_too(teacher_client, accountant_client, seed):
    for client in (teacher_client, accountant_client):
        assert client.get('/language/ur').status_code == 302
        assert client.get('/language/en').status_code == 302


def test_translate_html_unit():
    page = ('<html lang="en"><head><link href="/static/vendor/bootstrap/bootstrap.min.css"></head>'
            '<body><h1>  Add Student </h1><input placeholder="Search" title="Save">'
            '<p>Ali Khan</p><script>var a = "Add Student"; x = "Quick Filter:";</script>'
            '<textarea>Add Student</textarea></body></html>')
    out = i18n.translate_html(page)
    assert 'lang="ur" dir="rtl"' in out and 'bootstrap.rtl.min.css' in out
    assert '>  طالب علم شامل کریں </h1>' in out
    assert 'placeholder="تلاش"' in out and 'title="محفوظ کریں"' in out
    assert '>Ali Khan</p>' in out                    # typed text untouched
    assert 'var a = "Add Student"' in out            # script code left alone
    assert 'فوری تلاش:' in out                       # known script text translated
    assert '<textarea>Add Student</textarea>' in out


def test_assets_are_shipped():
    for rel in ('rtl.css', 'vendor/bootstrap/bootstrap.rtl.min.css',
                'fonts/noto-naskh-arabic-arabic-400-normal.woff2',
                'fonts/noto-naskh-arabic-arabic-700-normal.woff2'):
        assert os.path.getsize(os.path.join(STATIC, rel)) > 1000, rel


def test_numbers_inside_short_texts_are_translated():
    assert i18n.lookup('Roll 6001') == 'رول 6001'
    assert i18n.lookup('Pending Rs 4,500') == 'باقی Rs 4,500'
    assert i18n.lookup('Ali Khan') is None


def test_phone_numbers_and_the_students_banner_in_urdu(admin_client, seed):
    _add_student(admin_client, seed, 5002, 'Phone Kid', guardian_phone='+92 300 1234567')
    _urdu(admin_client)
    html = admin_client.get('/students').get_data(as_text=True)
    assert '<span dir="ltr" style="unicode-bidi:isolate">+92 300 1234567</span>' in html
    assert 'تلاش اور فلٹر سے طالب علم ڈھونڈیں' in html
    assert 'to admit someone new' not in html and 'controls which fields' not in html
    fees = admin_client.get('/fees').get_data(as_text=True)
    assert 'ماہانہ واجبات، وصولیاں اور باقی رقم کی نگرانی' in fees
    assert i18n.lookup('Outstanding: 0 PKR') == 'باقی: 0 PKR'


def test_month_names_and_counts_in_urdu(admin_client, seed):
    assert i18n.lookup('October 2026') == 'اکتوبر 2026'
    assert i18n.lookup('March 2025 \u2014 pending') == 'مارچ 2025 \u2014 باقی'
    assert i18n.lookup('12 students') == '12 طلبہ' and i18n.lookup('1 student') == '1 طلبہ'
    _urdu(admin_client)
    html = admin_client.get('/fees').get_data(as_text=True)
    assert 'value="October 2026"' in html            # what the form posts stays English
    assert 'اکتوبر 2026' in html


def test_dashboard_and_finance_sentences_in_urdu():
    n = i18n.lookup
    assert n('Sunday, 18 October 2026 \u00b7 Session 2026-2027') == 'اتوار، 18 اکتوبر 2026 · سیشن 2026-2027'
    assert 'آپریٹنگ منظر' in n('Operating View \u2014 October 2026 (estimated)')
    assert n('settled 100.0%') == 'ادا \u2066100.0\u2069%'
    assert 'پرانا بقایا' in n('Rs 331,973.66 of older arrears is still recoverable.')
    assert 'فیس وصولی' in n('Fee collection is 54.8% higher than last month.')
    assert 'بہتر' in n('Net Position improved by Rs 211,246.92 (cash basis).')
    assert 'کم ہوئی' in n('Net Position fell by Rs 1,000.00 (cash basis).')
    assert 'اخراجات' in n('Refreshment/Events expenses rose 703.6% vs last month (+Rs 17,511.19).')
    assert 'اسٹاک' in n('Restock soon: hamza (4 left) is below minimum stock.')
    assert n('Recommendations') == 'سفارشات'


def test_script_labels_and_auto_direction():
    page = ('<html><head></head><body><p>Hello there.</p><p dir="rtl">Keep</p><ul><li>Item one.</li></ul>'
            '<div class="form-text">Hint.</div>'
            '<script>sponsorName.textContent = label + \' Name\'; badge.textContent = \'Disconnected\';'
            ' x = {label: \'Revenue\'}; s.innerHTML = \'<option value="">No section selected (optional)</option>\';</script>'
            '</body></html>')
    out = i18n.translate_html(page)
    assert '<p dir="auto">Hello there.</p>' in out and '<p dir="rtl">Keep</p>' in out
    assert '<li dir="auto">Item one.</li>' in out and '<div class="form-text" dir="auto">Hint.</div>' in out
    assert "label === 'Guardian' ? 'سرپرست کا نام' : 'والد کا نام'" in out
    assert "badge.textContent = 'منسلک نہیں'" in out and "label: 'آمدنی'" in out
    assert 'سیکشن منتخب نہیں (اختیاری)</option>' in out
