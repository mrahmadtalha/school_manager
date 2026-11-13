"""The case-folded lookup table, and period / dues-title / filter-summary helpers."""

import re

from .part01 import UR
from .part04 import MONTH_UR, PATTERNS, _MONTHS, _isolate, _n
from .part05 import _fold
from .part06 import _M3, _M3_UR
from .part07 import HTML_SENTENCES


def _period_ur(text):
    """\"October 2026\" -> Urdu month name; anything else (\"All months\") is left as is."""
    found = re.match(r'^(%s) (\d{4})$' % '|'.join(_MONTHS), text.strip())
    return '%s %s' % (MONTH_UR[found.group(1)], found.group(2)) if found else text


def _dues_title(match):
    title = 'کل باقی واجبات'
    return title + ' (%s)' % _period_ur(match.group(1)) if match.group(1) else title


def _current_filters(match):
    text = 'موجودہ فلٹر: ' + _period_ur(match.group(1))
    return text + ' \u00b7 منتخب کلاس' if match.group(2) else text


PATTERNS += [
    (r'^Node runtime: (.+?) \u00b7 Bridge folder:$', _isolate('نوڈ رن ٹائم: {1} \u00b7 برج فولڈر:')),
    (r'^(\d{1,2}) (%s) (\d{4}), (\d{1,2}:\d{2})$' % _M3,
     lambda m: '%s %s %s، %s' % (m.group(1), _M3_UR[m.group(2)], m.group(3), _n(m.group(4)))),
    (r'^(\d+) total$', r'کل \1'),
    (r'^Showing the newest (\d+) of (\d+) messages\. Use the filters above to narrow it down\.$',
     r'\2 میں سے تازہ ترین \1 پیغامات دکھائے جا رہے ہیں۔ تعداد کم کرنے کے لیے اوپر کے فلٹر استعمال کریں۔'),
    (r'^Session: (.+)$', r'سیشن: \1'),
    (r'^Total Outstanding Dues(?: \((.+)\))?$', _dues_title),
    (r'^current filters: (.+?)( \u00b7 selected class)?$', _current_filters),
    (r'^(%s) (\d{4}) \u00b7 All classes$' % '|'.join(_MONTHS),
     lambda m: '%s %s \u00b7 تمام کلاسز' % (MONTH_UR[m.group(1)], m.group(2))),
]


# students page redesign
UR.update({
    'On this list': 'اس فہرست میں', 'Boys': 'لڑکے', 'Girls': 'لڑکیاں',
    'With dues': 'واجبات والے', 'Total due': 'کل واجب',
    'Open full report': 'مکمل رپورٹ کھولیں',
    'Show everyone': 'سب کو دکھائیں',
    'Show only students with dues': 'صرف واجبات والے طلبہ دکھائیں',
})


# teachers page redesign
UR.update({
    'Leadership': 'قیادت', 'Senior staff': 'سینئر عملہ', 'Admin staff': 'انتظامی عملہ',
    'Other / not set': 'دیگر / مقرر نہیں',
    'Principal': 'پرنسپل', 'Vice Principal': 'وائس پرنسپل', 'Head Teacher': 'ہیڈ ٹیچر',
    'Senior Teacher': 'سینئر ٹیچر', 'Admin Staff': 'انتظامی عملہ',
    'In school today': 'آج اسکول میں', 'Not marked': 'درج نہیں',
    'Staff attendance is not marked yet today': 'آج عملے کی حاضری ابھی درج نہیں ہوئی',
    'Classes with a teacher': 'استاد والی کلاسیں',
    'No teacher yet:': 'ابھی کوئی استاد نہیں:',
    'No classes created yet': 'ابھی کوئی کلاس نہیں بنی',
    'Open staff attendance': 'عملے کی حاضری کھولیں',
    'Staff by role': 'عہدے کے لحاظ سے عملہ', 'Staff attendance today': 'آج عملے کی حاضری',
    'Cards': 'کارڈز', 'Table': 'جدول',
    'Present today': 'آج حاضر', 'Late today': 'آج دیر سے', 'On leave today': 'آج چھٹی پر',
    'Absent today': 'آج غیر حاضر', 'Attendance not marked today': 'آج حاضری درج نہیں',
    'No classes assigned yet': 'ابھی کوئی کلاس تفویض نہیں',
})


PATTERNS.extend([
    (r'^Since (\d{4})$', r'\1 سے'),
    (r'^Call (.+)$', r'کال کریں \1'),
])


# --- Student attendance page, redesigned (Oct 2026) ---
UR.update({
    'Attendance Sheet': 'حاضری شیٹ',
    'Students in this class': 'اس کلاس کے طلبہ',
    'Saved. Nobody can change it by mistake.': 'محفوظ ہو گئی۔ غلطی سے کوئی تبدیل نہیں کر سکتا۔',
    'Press Save when you are done.': 'کام مکمل ہونے پر محفوظ کریں دبائیں۔',
    'Find a student by name or roll no…': 'نام یا رول نمبر سے طالب علم تلاش کریں…',
    'Find a student': 'طالب علم تلاش کریں',
    'Previous day': 'پچھلا دن',
    'Next day': 'اگلا دن',
    'Arrival time': 'آمد کا وقت',
    'Save Attendance': 'حاضری محفوظ کریں',
    'Not marked': 'نشان زد نہیں',
    'Not marked yet': 'ابھی نشان زد نہیں',
    'No student matches your search.': 'آپ کی تلاش سے کوئی طالب علم نہیں ملا۔',
    'Go to Students': 'طلبہ پر جائیں',
    'Go to Classes': 'کلاسز پر جائیں',
    'There are no classes yet. Add a class first, then its students will appear here.':
        'ابھی کوئی کلاس نہیں ہے۔ پہلے کلاس بنائیں، پھر اس کے طلبہ یہاں نظر آئیں گے۔',
    'Mark every student of this class as Absent?': 'کیا اس کلاس کے تمام طلبہ کو غیر حاضر لگانا ہے؟',
    'Mark all Absent': 'سب کو غیر حاضر لگائیں',
})


HTML_SENTENCES.extend([
    ('Mark who came to school. Everyone starts as <b>Present</b>, so you only need to touch '
     'the students who are absent, late or on leave.',
     'دیکھیں کون اسکول آیا۔ سب پہلے سے <b>حاضر</b> ہوتے ہیں، اس لیے صرف غیر حاضر، '
     'دیر سے آنے والے یا رخصت والے طلبہ کو بدلیں۔'),
    ('Tap <b>Absent</b>, <b>Late</b> or <b>Leave</b> for the students who need it, then press '
     '<b>Save Attendance</b> at the bottom.',
     'جن طلبہ کو ضرورت ہو ان کے لیے <b>غیر حاضر</b>، <b>تاخیر</b> یا <b>رخصت</b> دبائیں، '
     'پھر نیچے <b>حاضری محفوظ کریں</b> دبائیں۔'),
    ('This day is saved. To correct a mistake press <b>Unlock</b>, change the student and save again.',
     'یہ دن محفوظ ہے۔ غلطی ٹھیک کرنے کے لیے <b>کھولیں</b> دبائیں، طالب علم بدلیں اور دوبارہ محفوظ کریں۔'),
    ('Showing <strong id="saVisible">{1}</strong> of <strong>{2}</strong> students',
     'کل <strong>{2}</strong> میں سے <strong id="saVisible">{1}</strong> طلبہ دکھائے جا رہے ہیں'),
    ('Ready to save: <b id="sumPresent">{1}</b> present · <b id="sumAbsent">{2}</b> absent · '
     '<b id="sumLate">{3}</b> late · <b id="sumLeave">{4}</b> on leave',
     'محفوظ کرنے کے لیے تیار: <b id="sumPresent">{1}</b> حاضر · <b id="sumAbsent">{2}</b> غیر حاضر · '
     '<b id="sumLate">{3}</b> تاخیر · <b id="sumLeave">{4}</b> رخصت پر'),
])


UR_FOLDED = {_fold(k): v for k, v in UR.items()}


UR.update({
    # QR gate scans tab
    'QR Scans': 'کیو آر اسکین',
    'Print QR ID cards': 'کیو آر شناختی کارڈ پرنٹ کریں',
    'Guard phone is ready': 'گارڈ کا فون تیار ہے',
    'Connect the guard\u2019s phone': 'گارڈ کا فون جوڑیں',
    'Just 3 easy steps. Nothing to type on the phone.': 'صرف 3 آسان مراحل۔ فون میں کچھ لکھنے کی ضرورت نہیں۔',
    'Allow guard phones to reach this computer': 'گارڈ کے فون کو اس کمپیوٹر سے جڑنے کی اجازت دیں',
    'Guard phones are allowed': 'گارڈ کے فون کی اجازت ہے',
    'Guard account': 'گارڈ اکاؤنٹ',
    'Create guard account': 'گارڈ اکاؤنٹ بنائیں',
    'Connect the phone with a code': 'کوڈ سے فون جوڑیں',
    'Show the connection code': 'کنکشن کوڈ دکھائیں',
    'New code': 'نیا کوڈ',
    'Update by itself': 'خود بخود اپڈیٹ',
    'Update now': 'ابھی اپڈیٹ کریں',
    'Arrived': 'پہنچ گئے', 'Not arrived': 'نہیں پہنچے', 'Not arrived yet': 'ابھی نہیں پہنچے',
    'Not scanned': 'اسکین نہیں ہوئے', 'Marked absent': 'غیر حاضر لگا دیا',
    'On leave': 'رخصت پر', 'Arrived on time': 'وقت پر پہنچے', 'Everyone': 'سب',
    'Scanned at': 'اسکین کا وقت', 'Roll': 'رول',
    'Students in this class': 'اس کلاس کے طلبہ', 'Students in the school': 'اسکول کے طلبہ',
    'Find a student': 'طالب علم تلاش کریں',
    'Mark absent by itself': 'خود بخود غیر حاضر لگائیں',
    'At what time?': 'کس وقت؟',
    'Should it ask you first?': 'کیا پہلے آپ سے پوچھے؟',
    'Safety check (%)': 'حفاظتی جانچ (%)',
    'Save these settings': 'یہ ترتیبات محفوظ کریں',
    'No, do not mark anyone': 'نہیں، کسی کو غیر حاضر نہ لگائیں',
    'Auto-absent is waiting for approval': 'خودکار غیر حاضری آپ کی منظوری کی منتظر ہے',
})
