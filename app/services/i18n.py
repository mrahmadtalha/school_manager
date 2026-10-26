# -*- coding: utf-8 -*-
"""English / Urdu interface switch.

How it works
------------
The templates stay in English.  When the person picks Urdu, every finished HTML
page is passed through :func:`translate_html` on its way out:

* visible text and the ``placeholder`` / ``title`` / ``aria-label`` attributes are
  swapped for the Urdu in :mod:`app.services.i18n_ur` when the whole text matches;
* the page is switched to right-to-left (``dir="rtl"``), the Bootstrap RTL style
  sheet and the Urdu font are loaded;
* what the person typed (names, addresses, amounts, class names) is never touched,
  because it never matches a dictionary entry.

Text that is not in the dictionary simply stays English, so a missing word never
breaks a page.  The choice is remembered in the browser session.
"""
import html as html_lib
import re

from flask import g, request, session

from app.services.i18n_ur import HTML_SENTENCES, PATTERNS, UR, UR_FOLDED

_COMPILED_PATTERNS = [(re.compile(p), r) for p, r in PATTERNS]

_NUMBER_VALUE = re.compile(r'^[\d:.,%+\-\u2013 ]+$')


def _compile_sentence(english, urdu):
    """Turn one (English, Urdu) pair from ``HTML_SENTENCES`` into (regex, replacement).

    Whitespace in the page may differ (line breaks, indentation), so any run of
    whitespace matches.  ``{1}``, ``{2}`` ... take whatever the page put there; numbers
    and times are wrapped in an LTR isolate so they keep their order in Urdu text.
    """
    pattern = ''
    for part in re.split(r'(\{\d+\})', english):
        if re.fullmatch(r'\{\d+\}', part):
            pattern += '([^<>]*?)'
        else:
            pattern += ''.join(r'\s+' if token.isspace() else re.escape(token)
                               for token in re.split(r'(\s+)', part) if token)

    def fill(match):
        text = urdu
        for index, value in enumerate(match.groups(), start=1):
            if value.strip() and _NUMBER_VALUE.match(value):
                value = '\u2066' + value + '\u2069'
            text = text.replace('{%d}' % index, value)
        return text
    return re.compile(pattern), fill


_COMPILED_SENTENCES = [_compile_sentence(en, ur) for en, ur in HTML_SENTENCES]

LANGUAGES = ('en', 'ur')
SESSION_KEY = 'ui_lang'

_RAW_BLOCK = re.compile(r'(<(script|style|textarea|pre|code)\b[^>]*>.*?</\2>)',
                        re.IGNORECASE | re.DOTALL)
_TEXT_NODE = re.compile(r'>([^<>]+)<')
_ATTRIBUTE = re.compile(r'\b(placeholder|title|aria-label|data-bs-title|alt)="([^"]*)"')
_HAS_LETTER = re.compile(r'[A-Za-z]')

RTL_STYLE_TAG = '<link rel="stylesheet" href="/static/rtl.css">'
DATATABLES_URDU = (
    '<script>if(window.jQuery&&jQuery.fn.dataTable){jQuery.extend(true,'
    'jQuery.fn.dataTable.defaults,{language:{search:"تلاش:",lengthMenu:"_MENU_ اندراجات دکھائیں",'
    'info:"_START_ سے _END_ (کل _TOTAL_)",infoEmpty:"کوئی اندراج نہیں",'
    'infoFiltered:"(کل _MAX_ میں سے)",zeroRecords:"کوئی ریکارڈ نہیں ملا",emptyTable:"کوئی ڈیٹا نہیں",'
    'paginate:{first:"پہلا",last:"آخری",next:"اگلا",previous:"پچھلا"}}});}</script>')

# A few texts that live inside the page's JavaScript.
_GUARDIAN_NAME = "(%s === 'Guardian' ? 'سرپرست کا نام' : 'والد کا نام')"
_GUARDIAN_CNIC = "(%s === 'Guardian' ? 'سرپرست کا شناختی کارڈ نمبر' : 'والد کا شناختی کارڈ نمبر')"
_SCRIPT_TEXT = {
    '"Quick Filter:"': '"فوری تلاش:"',
    # the Add Student form builds these labels in JavaScript
    "label + ' Name'": _GUARDIAN_NAME % 'label',
    "label + ' CNIC Number'": _GUARDIAN_CNIC % 'label',
    "selected + ' Name'": _GUARDIAN_NAME % 'selected',
    "selected + ' CNIC Number'": _GUARDIAN_CNIC % 'selected',
    'No section selected (optional)</option>': 'سیکشن منتخب نہیں (اختیاری)</option>',
    # WhatsApp status badges and the dashboard chart legend
    "badge.textContent = 'Connected'": "badge.textContent = 'منسلک'",
    "badge.textContent = 'Disconnected'": "badge.textContent = 'منسلک نہیں'",
    "connected: 'Connected',": "connected: 'منسلک',",
    "label: 'Revenue'": "label: 'آمدنی'",
    "label: 'Costs'": "label: 'اخراجات'",
    # attendance page: WhatsApp status panel, toasts, "All Students at Time" note
    "badge.textContent = 'Offline'": "badge.textContent = 'آف لائن'",
    "'WhatsApp service unavailable.'": "'واٹس ایپ سروس دستیاب نہیں۔'",
    "'WhatsApp is ready.'": "'واٹس ایپ تیار ہے۔'",
    "'Messages can be sent from this page.'": "'اس صفحے سے پیغامات بھیجے جا سکتے ہیں۔'",
    "'Connect the WhatsApp service before sending alerts.'":
        "'الرٹ بھیجنے سے پہلے واٹس ایپ سروس منسلک کریں۔'",
    "'Test message sent successfully.'": "'ٹیسٹ پیغام کامیابی سے بھیج دیا گیا۔'",
    "'Unable to send test message.'": "'ٹیسٹ پیغام نہیں بھیجا جا سکا۔'",
    "'WhatsApp service is unavailable or timed out.'":
        "'واٹس ایپ سروس دستیاب نہیں یا وقت ختم ہو گیا۔'",
    "'No absent students to message today.'": "'آج پیغام بھیجنے کے لیے کوئی غیر حاضر طالب علم نہیں۔'",
    "'No valid phone numbers found for absent students.'":
        "'غیر حاضر طلبہ کے کوئی درست فون نمبر نہیں ملے۔'",
    "'Opened WhatsApp messages for ' + sent + ' absent student(s).'":
        "sent + ' غیر حاضر طلبہ کے لیے واٹس ایپ پیغامات کھولے گئے۔'",
    "'Please choose a time first.'": "'پہلے وقت منتخب کریں۔'",
    "changed + ' student(s) set to ' + value + '. Edit the time of anyone who came late.'":
        "changed + ' طلبہ کا وقت ' + value + ' مقرر ہوا۔ جو دیر سے آیا ہو اس کا وقت بدل دیں۔'",
    # attendance summary: the at-risk toggle button
    "</i> Show All Students'": "</i> تمام طلبہ دکھائیں'",
    "</i> Show At-Risk Only (&lt; 75%)'": "</i> صرف خطرے والے (75% سے کم)'",
}


# WhatsApp Center and Analytics pages: status words, messages and chart legends built in
# JavaScript.  Whole quoted strings are matched so nothing else in a script is touched.
_SCRIPT_TEXT.update({
    "connecting: 'Connecting',": "connecting: 'منسلک ہو رہا ہے',",
    "qr_ready: 'QR needed',": "qr_ready: 'QR درکار',",
    "disconnected: 'QR needed',": "disconnected: 'QR درکار',",
    "logged_out: 'QR needed',": "logged_out: 'QR درکار',",
    "reconnecting: 'Reconnecting',": "reconnecting: 'دوبارہ منسلک ہو رہا ہے',",
    "offline: 'Offline',": "offline: 'آف لائن',",
    "error: 'Error',": "error: 'خرابی',",
    "starting: 'Starting',": "starting: 'شروع ہو رہا ہے',",
    "sending: 'Sending message',": "sending: 'پیغام بھیجا جا رہا ہے',",
    "retrying: 'Retrying',": "retrying: 'دوبارہ کوشش ہو رہی ہے',",
    "session_reset: 'Starting fresh session',": "session_reset: 'نیا سیشن شروع ہو رہا ہے',",
    "|| 'Checking';": "|| 'جانچ ہو رہی ہے';",
    "'Cloud API selected'": "'Cloud API منتخب'",
    "'QR Scan selected'": "'QR اسکین منتخب'",
    "'Official WhatsApp Cloud API is active and ready to send.'":
        "'سرکاری واٹس ایپ Cloud API فعال ہے اور بھیجنے کے لیے تیار ہے۔'",
    "'Phone paired and ready to send messages.'": "'فون جڑ چکا ہے اور پیغامات بھیجنے کے لیے تیار ہے۔'",
    "'Service reachable. Scan the QR code to pair the phone.'":
        "'سروس دستیاب ہے۔ فون جوڑنے کے لیے QR کوڈ اسکین کریں۔'",
    "'Service is reachable, but phone pairing is not complete.'":
        "'سروس دستیاب ہے، لیکن فون کا جوڑنا مکمل نہیں ہوا۔'",
    "'Service is not reachable right now.'": "'سروس اس وقت دستیاب نہیں۔'",
    "'Latest event: Cloud API delivery is ready.'": "'تازہ ترین واقعہ: Cloud API سے ارسال تیار ہے۔'",
    "'Latest event: A WhatsApp message was sent successfully.'":
        "'تازہ ترین واقعہ: واٹس ایپ پیغام کامیابی سے بھیجا گیا۔'",
    "'Latest event: Phone is paired and ready to send messages.'":
        "'تازہ ترین واقعہ: فون جڑ چکا ہے اور پیغامات بھیجنے کے لیے تیار ہے۔'",
    "'Latest event: QR code is ready. Please scan it from your phone.'":
        "'تازہ ترین واقعہ: QR کوڈ تیار ہے۔ براہ کرم اپنے فون سے اسکین کریں۔'",
    "'Latest event: WhatsApp service is not connected yet.'":
        "'تازہ ترین واقعہ: واٹس ایپ سروس ابھی منسلک نہیں۔'",
    "QR scanning is not used with Cloud API.": "Cloud API کے ساتھ QR اسکین استعمال نہیں ہوتا۔",
    "No QR available yet.": "ابھی کوئی QR دستیاب نہیں۔",
    "'Not required in Cloud API mode'": "'Cloud API موڈ میں ضروری نہیں'",
    "'QR code is ready to scan'": "'QR کوڈ اسکین کے لیے تیار ہے'",
    "'Connected and ready'": "'منسلک اور تیار'",
    "'QR not ready yet'": "'QR ابھی تیار نہیں'",
    "'WhatsApp service is unavailable.'": "'واٹس ایپ سروس دستیاب نہیں۔'",
    "'Please start the service or check the connection.'":
        "'براہ کرم سروس شروع کریں یا کنکشن چیک کریں۔'",
    "'Service unavailable'": "'سروس دستیاب نہیں'",
    "'Test message sent.'": "'ٹیسٹ پیغام بھیج دیا گیا۔'",
    "'The message could not be sent. Check the connection and try again.'":
        "'پیغام نہیں بھیجا جا سکا۔ کنکشن چیک کر کے دوبارہ کوشش کریں۔'",
    "'Enter a recipient number to test Cloud API delivery.'":
        "'Cloud API سے ارسال جانچنے کے لیے وصول کنندہ کا نمبر لکھیں۔'",
    "'Leave blank to send to the connected account\\'s Message Yourself chat.'":
        "'خالی چھوڑیں تو پیغام منسلک اکاؤنٹ کی اپنی چیٹ (Message Yourself) میں بھیجا جائے گا۔'",
    "'Queue this message for every selected recipient?'":
        "'کیا یہ پیغام ہر منتخب وصول کنندہ کے لیے قطار میں لگائیں؟'",
    # Analytics & Exports chart legends
    "label: 'Present %'": "label: 'حاضر %'",
    "label: 'Average %'": "label: 'اوسط %'",
    "label: 'Collected'": "label: 'وصول شدہ'",
    "label: 'Outstanding'": "label: 'باقی'",
})
# Messages the server sends back as data (the bridge status and the test-message reply).
# Added last on purpose: the English keys inside these tables must not be rewritten again.
_SCRIPT_TEXT.update({
    "textElem.textContent = message;":
        "textElem.textContent = ({'WhatsApp service unavailable': 'واٹس ایپ سروس دستیاب نہیں', "
        "'WhatsApp service is running.': 'واٹس ایپ سروس چل رہی ہے۔', "
        "'Waiting for WhatsApp to connect.': 'واٹس ایپ کے منسلک ہونے کا انتظار ہے۔'})"
        "[message] || message;",
    "feedback.textContent = data.message || (":
        "feedback.textContent = ({'QR not ready yet.': 'QR ابھی تیار نہیں۔', "
        "'WhatsApp service unavailable.': 'واٹس ایپ سروس دستیاب نہیں۔', "
        "'Cloud API credentials are incomplete.': 'Cloud API کی معلومات نامکمل ہیں۔', "
        "'Student not found.': 'طالب علم نہیں ملا۔', "
        "'Enter a valid WhatsApp phone number.': 'درست واٹس ایپ فون نمبر لکھیں۔'})"
        "[data.message] || data.message || (",
})


def switch_allowed():
    """False when the school's license does not include the language switch."""
    status = g.get('license_status') if g else None
    return status is None or status.feature_enabled('language_switch')


def get_lang():
    lang = session.get(SESSION_KEY, 'en') if session else 'en'
    if lang not in LANGUAGES or not switch_allowed():
        return 'en'
    return lang


def set_lang(code):
    session[SESSION_KEY] = code if code in LANGUAGES else 'en'
    session.permanent = True


def is_rtl():
    return get_lang() == 'ur'


def lookup(text):
    """Urdu for an English text, or ``None``."""
    key = ' '.join(html_lib.unescape(text).split())
    if not key or not _HAS_LETTER.search(key):
        return None
    found = UR.get(key) or UR_FOLDED.get(key.lower())
    if found is not None:
        return found
    for pattern, replacement in _COMPILED_PATTERNS:
        if pattern.match(key):
            return pattern.sub(replacement, key)   # replacement: text or a function
    return None


# Phone numbers and dates (digits with + - space . ( ) only) must stay left-to-right,
# otherwise "+92 300 1234567" is shown as "1234567 300 92+" inside a right-to-left page.
_NUMBER_LIKE = re.compile(r'^\+?\d[\d\s\-().]{5,}$')


def _swap_text(match):
    raw = match.group(1)
    urdu = lookup(raw)
    if urdu is None:
        core = raw.strip()
        if _NUMBER_LIKE.match(core):
            lead = raw[:len(raw) - len(raw.lstrip())]
            trail = raw[len(raw.rstrip()):]
            return '>%s<span dir="ltr" style="unicode-bidi:isolate">%s</span>%s<' % (lead, core, trail)
        return match.group(0)
    lead = raw[:len(raw) - len(raw.lstrip())]
    trail = raw[len(raw.rstrip()):]
    return '>' + lead + html_lib.escape(urdu, quote=False) + trail + '<'


def _swap_attribute(match):
    urdu = lookup(match.group(2))
    if urdu is None:
        return match.group(0)
    return '%s="%s"' % (match.group(1), html_lib.escape(urdu, quote=True))


def translate_html(page):
    """Translate one rendered page to Urdu and make it right-to-left."""
    blocks = []

    def stash(match):
        block = match.group(1)
        if match.group(2).lower() == 'script':
            for english, urdu in _SCRIPT_TEXT.items():
                block = block.replace(english, urdu)
        blocks.append(block)
        return '\x00%d\x00' % (len(blocks) - 1)

    work = _RAW_BLOCK.sub(stash, page)
    for sentence, replacement in _COMPILED_SENTENCES:
        work = sentence.sub(replacement, work)
    work = _TEXT_NODE.sub(_swap_text, work)
    work = _ATTRIBUTE.sub(_swap_attribute, work)
    work = re.sub(r'\x00(\d+)\x00', lambda m: blocks[int(m.group(1))], work)

    work = _AUTO_DIR.sub(_add_auto_dir, work)
    work = re.sub(r'<html\b([^>]*)>', _html_tag, work, count=1, flags=re.IGNORECASE)
    work = work.replace('vendor/bootstrap/bootstrap.min.css',
                        'vendor/bootstrap/bootstrap.rtl.min.css')
    work = work.replace('</head>', RTL_STYLE_TAG + '</head>', 1)
    work = re.sub(r'(<script[^>]*dataTables\.bootstrap5\.min\.js[^>]*></script>)',
                  lambda m: m.group(1) + DATATABLES_URDU, work, count=1)
    return work


# Paragraphs, list items and small print take the direction of their first letter, so a
# sentence still in English keeps its full stop at the end instead of the wrong side.
_AUTO_DIR = re.compile(r'<(p|li|small)\b([^>]*)>|<(div|span)\b([^>]*\bclass="[^"]*\bform-text\b[^"]*"[^>]*)>',
                       re.IGNORECASE)


def _add_auto_dir(match):
    tag = match.group(1) or match.group(3)
    attrs = match.group(2) if match.group(1) else match.group(4)
    if re.search(r'\sdir\s*=', attrs or ''):
        return match.group(0)
    return '<%s%s dir="auto">' % (tag, attrs or '')


def _html_tag(match):
    attrs = re.sub(r'\s(lang|dir)="[^"]*"', '', match.group(1))
    return '<html%s lang="ur" dir="rtl">' % attrs


def register(app):
    """Hook the switch into the app: translate Urdu pages, expose ``ui_lang``."""

    @app.context_processor
    def _inject_language():
        return {'ui_lang': get_lang()}

    @app.after_request
    def _translate_response(response):
        try:
            if (get_lang() != 'ur' or response.status_code != 200
                    or response.mimetype != 'text/html' or response.direct_passthrough
                    or request.endpoint in (None, 'static')):
                return response
            body = response.get_data(as_text=True)
            if '<html' not in body[:2000].lower():
                return response          # an HTML fragment, not a whole page
            response.set_data(translate_html(body))
        except Exception:                # never let a translation problem break a page
            app.logger.exception('Urdu translation skipped for %s', request.path)
        return response
