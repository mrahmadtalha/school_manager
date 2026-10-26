# -*- coding: utf-8 -*-
"""Urdu wording for the results matrix, attendance, teachers and classes screens."""
from app.services import i18n


def _page(body):
    return '<html><head></head><body>%s</body></html>' % body


def test_result_matrix_texts_are_translated():
    html = i18n.translate_html(_page(
        '<p class="eyebrow">Results matrix</p><h1>Class Result Matrix</h1>'
        '<label>Test Type</label><option>— All Types —</option>'
        '<div>Top Scorer</div><div>Pass Rate</div><div>Class Avg</div><div>Tests</div>'
        '<span>Click column headers to sort</span><button>Save Remarks</button>'
        '<span>19 Oct 2026</span><div>17 Dec</div>'))
    for english in ('Results matrix', 'Class Result Matrix', 'Test Type', 'Top Scorer',
                    'Pass Rate', 'Class Avg', 'Save Remarks', 'Oct', 'Dec', 'All Types'):
        assert english not in html, english
    assert '19 اکتوبر 2026' in html      # 19 October 2026


def test_sentences_with_bold_parts_and_numbers_are_translated_whole():
    html = i18n.translate_html(_page(
        '<div>School hours: 08:30–15:00. Late is automatic after start + 0 minute(s) '
        'grace. Enter each student’s actual check-in time, or use '
        '<strong>All Students at Time</strong> to mark everyone on time and only change '
        'the late ones.</div>'
        '<span>Saving will <strong>lock</strong>\n this attendance and move to the next class.</span>'
        '<div>Showing <strong id="visibleCount">3</strong> teacher(s)</div>'
        '<p>Section <strong>A</strong> has <strong>3</strong> student(s)\n  (2 active).</p>'))
    assert 'School hours' not in html and 'Saving will' not in html
    assert 'Showing' not in html and 'student(s)' not in html
    assert '<strong>مقفل</strong>' in html           # <strong>lock</strong>
    assert '<strong id="visibleCount">' in html                           # the live counter survives


def test_counts_and_prices_in_badges():
    html = i18n.translate_html(_page(
        '<span>Rs. 2,500 / month</span><span>+2 archived</span><span>(5 total)</span>'
        '<span>1 class</span><span>2 classes</span><span>4 days recorded</span>'
        '<span>Total: 8</span>'))
    for english in ('/ month', 'archived', 'total', ' class', 'days recorded', 'Total:'):
        assert english not in html, english
    assert 'Rs. 2,500' in html                                            # the amount stays as is


def test_whatsapp_status_texts_inside_the_page_script_are_translated():
    html = i18n.translate_html(_page(
        '<script>badge.textContent = \'Offline\'; text.textContent = '
        '\'WhatsApp service unavailable.\'; detail.textContent = '
        '\'Connect the WhatsApp service before sending alerts.\';</script>'))
    assert 'Offline' not in html and 'unavailable' not in html and 'Connect the' not in html


def test_whatsapp_center_texts_are_translated():
    html = i18n.translate_html(_page(
        '<div class="small text-uppercase">Messages &amp; delivery</div><h1>WhatsApp Center</h1>'
        '<span>Automation on</span><span>QR Scan selected</span><span>Automatic sending</span>'
        '<strong>WhatsApp notifications</strong>'
        '<div>The WhatsApp bridge is installed but not running. Start it (or restart the app '
        'with the WhatsApp component enabled) to send queued messages.</div>'
        '<div class="small">Node runtime: v24.15.0 &middot; Bridge folder: <code>C:\\bridge</code></div>'
        '<div>Status detail</div><div>QR status</div><div>Last successful send</div>'
        '<div>17 Oct 2026, 16:08</div><div>Latest queue item: <strong>attendance_late</strong> '
        '\u2014 <span>approved</span></div>'
        '<label>Delivery mode</label><option>Fully automatic</option>'
        '<option>One-by-one delayed sending</option><label>Integration Method</label>'
        '<h3>Attendance alerts</h3><span>Late arrival</span><span>Payment slips</span>'
        '<summary>Edit message wording</summary><button>Save Settings</button>'
        '<span>Connect by QR code</span><p>Open WhatsApp on your phone and scan this code to '
        'connect.</p><span>6 total</span><th>Trigger</th><button>Approve</button>'
        '<button>Reject</button><span>Waiting approval</span>'
        '<div>Showing the newest 50 of 120 messages. Use the filters above to narrow it down.</div>'
        '<input placeholder="Search phone, message, or category">'))
    for english in ('Messages', 'WhatsApp Center', 'Automation on', 'QR Scan', 'Automatic sending',
                    'bridge is installed', 'Node runtime', 'Bridge folder', 'Status detail',
                    'Last successful', 'Oct', 'Latest queue item', 'attendance_late', 'approved',
                    'Delivery mode', 'Fully automatic', 'delayed sending', 'Integration Method',
                    'Attendance alerts', 'Late arrival', 'Payment slips', 'Edit message wording',
                    'Save Settings', 'Connect by QR', 'Open WhatsApp', ' total', 'Trigger',
                    'Approve', 'Reject', 'Waiting approval', 'Showing the newest', 'Search phone'):
        assert english not in html, english
    assert '<code>C:\\bridge</code>' in html          # the folder path itself is never touched
    assert '17 اکتوبر 2026' in html


def test_whatsapp_center_script_texts_are_translated():
    html = i18n.translate_html(_page(
        "<script>const map = {connecting: 'Connecting', qr_ready: 'QR needed', "
        "offline: 'Offline', error: 'Error', starting: 'Starting',}; return map[v] || 'Checking';\n"
        "badge.textContent = selected === 'cloud_api' ? 'Cloud API selected' : 'QR Scan selected';\n"
        "detail.textContent = 'Service is not reachable right now.';\n"
        "last.textContent = 'Latest event: WhatsApp service is not connected yet.';\n"
        "qrStatus.textContent = status.connected ? 'Connected and ready' : 'QR not ready yet';\n"
        "text.textContent = 'WhatsApp service is unavailable.';\n"
        "textElem.textContent = message;\n"
        "feedback.textContent = data.message || (data.ok ? 'Test message sent.' : "
        "'Unable to send test message.');\n"
        "help.textContent = 'Leave blank to send to the connected account\\'s Message Yourself chat.';"
        "</script>"))
    for english in ('Connecting', 'QR needed', "'Offline'", "'Error'", "'Checking'",
                    'Cloud API selected', 'QR Scan selected', 'not reachable', 'Latest event',
                    'Connected and ready', 'QR not ready yet\'', 'is unavailable',
                    'Test message sent', 'Message Yourself chat'):
        assert english not in html, english
    # messages the server sends back as data are looked up in a small Urdu table first
    assert "'WhatsApp service unavailable': 'واٹس ایپ سروس دستیاب نہیں'" in html
    assert '[data.message] || data.message' in html


def test_documents_page_texts_are_translated():
    html = i18n.translate_html(_page(
        '<span>Print &amp; export</span><p>Create ready-to-print ID cards and certificates.</p>'
        '<h2>Student ID Cards</h2><p>Choose a student or class. Leave both blank to print cards '
        'for all active students.</p><label>Whole Class</label><label>Single student</label>'
        '<option>\u2014 All students \u2014</option><a>Download student cards</a>'
        '<h2>Staff ID Cards</h2><option>\u2014 All active teachers \u2014</option>'
        '<a>Download staff cards</a><h2>Certificates</h2><label>Certificate type</label>'
        '<option>\u2014 Optional class filter \u2014</option><option>\u2014 Select a student \u2014</option>'
        '<label>Issue date</label><label>Remarks / achievement</label>'
        '<a>Download certificates PDF</a>'
        '<input placeholder="e.g. 1st position in Class 8 annual exams, 92%">'
        '<span title="Leave blank to include every class.">i</span>'))
    for english in ('Print', 'ready-to-print', 'ID Cards', 'Whole Class', 'Single student',
                    'All students', 'Download', 'Certificates', 'Certificate type',
                    'Optional class filter', 'Issue date', 'Remarks', 'e.g.', 'Leave blank'):
        assert english not in html, english


def test_analytics_hub_texts_are_translated():
    html = i18n.translate_html(_page(
        '<p>Analytics hub</p><div>October 2026 &middot; All classes</div>'
        '<span>Session: 2026-2027</span><label>Year</label><span>Analytics</span>'
        '<span>Finance &amp; Fees</span><span>Academic &amp; Examinations</span>'
        '<span>Students, Staff &amp; Operations</span><div>Attendance Rate</div>'
        '<div>Exam Pass Rate</div><div>Total Outstanding Dues (October 2026)</div>'
        '<h6>Fee Recovery vs Outstanding</h6><h6>Attendance Trend (Present %)</h6>'
        '<h6>Academic Performance (Average %)</h6>'
        '<span>current filters: October 2026 &middot; selected class</span>'
        '<span>Available</span><h6>Monthly Fee Ledgers</h6><h6>Defaulter Lists</h6>'
        '<a>Open insights</a><span>Select a class to enable class exports</span>'
        '<h6>Subject-Teacher Allocation</h6>'
        '<button title="Select a class first">PDF</button>'
        "<script>datasets: [{ label: 'Present %' }, { label: 'Average %' }, "
        "{ label: 'Collected' }, { label: 'Outstanding' }]</script>"))
    for english in ('Analytics', 'October', 'Session:', 'Year', 'Finance', 'Examinations',
                    'Attendance Rate', 'Pass Rate', 'Outstanding', 'Recovery', 'Trend',
                    'Performance', 'current filters', 'Available', 'Ledgers', 'Defaulter',
                    'insights', 'Select a class', 'Allocation', 'Present %', 'Average %',
                    'Collected'):
        assert english not in html, english
    assert 'اکتوبر 2026' in html
