"""Month and weekday names, regex patterns, and small text helpers used throughout."""

from .part01 import UR


UR.update({
    'Select all': 'سب منتخب کریں', 'Select none': 'کوئی نہیں', 'Export CSV': 'سی ایس وی ایکسپورٹ',
    'Collection rate': 'وصولی کی شرح', 'Amount (Rs.)': 'رقم (روپے)', 'Total (Rs.)': 'کل (روپے)',
    'Back to Classes & Subjects': 'کلاسز اور مضامین پر واپس', 'What changed': 'کیا تبدیل ہوا',
    'No teachers found.': 'کوئی استاد نہیں ملا۔', 'Not enough history yet.': 'ابھی کافی ریکارڈ نہیں۔',
    'Assessment center': 'جانچ کا مرکز', 'Leaving Reason / Notes': 'چھوڑنے کی وجہ / نوٹ',
    # dashboard
    'Disconnected': 'منسلک نہیں', 'Mark / View →': 'لگائیں / دیکھیں ←',
    'No attendance marked yet today.': 'آج ابھی حاضری نہیں لگی۔',
    'No staff attendance marked yet today.': 'آج ابھی عملے کی حاضری نہیں لگی۔',
    'Account Book': 'کھاتہ بک', 'This Month Net': 'اس مہینے کا خالص',
    'Revenue (fees + other income + sales)': 'آمدنی (فیس + دیگر آمدنی + فروخت)',
    'Cost of Goods Sold': 'فروخت شدہ مال کی لاگت',
    'Estimated Net Operating Position': 'اندازاً خالص آپریٹنگ پوزیشن',
    'No students have left this session.': 'اس سیشن میں کسی طالب علم نے اسکول نہیں چھوڑا۔',
    'No tests yet.': 'ابھی کوئی ٹیسٹ نہیں۔', 'Student added successfully!': 'طالب علم کامیابی سے شامل ہو گیا!',
    'no previous month data': 'پچھلے مہینے کا ڈیٹا نہیں',
    # students page / field picker
    'Show / hide fields': 'خانے دکھائیں / چھپائیں', 'Show all fields': 'تمام خانے دکھائیں',
    'Basic': 'بنیادی', 'Photo': 'تصویر', 'Contact': 'رابطہ', 'Phone': 'فون', 'Record': 'ریکارڈ',
    'Profile Photo': 'پروفائل تصویر', 'Remove current photo': 'موجودہ تصویر ہٹائیں',
    'Father': 'والد', 'Father / Guardian Name': 'والد / سرپرست کا نام', 'Sponsor CNIC': 'سرپرست کا شناختی کارڈ',
    'Admission Fee Received': 'داخلہ فیس وصول', 'Admission Fee Pending': 'داخلہ فیس باقی',
    'Admission Fee Status': 'داخلہ فیس کی حیثیت', 'Leaving Reason': 'اسکول چھوڑنے کی وجہ',
    'Class Fee (before discount)': 'کلاس فیس (رعایت سے پہلے)', 'Street 1': 'گلی 1', 'Street 2': 'گلی 2',
    'Street': 'گلی', 'Showing': 'دکھا رہے ہیں', 'Easiest way:': 'آسان طریقہ:',
    'Optional columns:': 'اختیاری کالم:', 'Good to know:': 'جاننا مفید:', 'What to do now:': 'اب کیا کریں:',
    'Track admissions, fees, and student records from one place.':
        'داخلے، فیس اور طلبہ کا ریکارڈ ایک ہی جگہ سے سنبھالیں۔',
    'JPG, PNG or WEBP, up to 5 MB. You can leave this empty.': 'جے پی جی، پی این جی یا ویب پی، زیادہ سے زیادہ 5 ایم بی۔ خالی بھی چھوڑ سکتے ہیں۔',
    'Final amount after discount.': 'رعایت کے بعد حتمی رقم۔',
    'PDF — columns on screen': 'پی ڈی ایف — سکرین کے کالم', 'Excel — columns on screen': 'ایکسل — سکرین کے کالم',
    'CSV — columns on screen': 'سی ایس وی — سکرین کے کالم', 'PDF — every field': 'پی ڈی ایف — تمام خانے',
    'Excel — every field': 'ایکسل — تمام خانے', 'CSV — every field': 'سی ایس وی — تمام خانے',
    'skipped': 'چھوڑ دی گئی', 'and': 'اور',
    'Admission Receipt': 'داخلہ کی رسید', 'Admission Fee Summary': 'داخلہ فیس کا خلاصہ',
    'Admission Fee, Books & Uniform': 'داخلہ فیس، کتابیں اور یونیفارم',
    'Still pending': 'ابھی باقی', 'Admission fee still pending': 'داخلہ فیس ابھی باقی',
    'English': 'English', 'Concession': 'رعایت',
    # students page banner (the sentence is split around bold buttons)
    'Use the search and filters to find a student, click a name to open their full report, or':
        'تلاش اور فلٹر سے طالب علم ڈھونڈیں، نام پر کلک کر کے مکمل رپورٹ کھولیں، یا',
    'to admit someone new.': 'نیا داخلہ کرنے کے لیے۔',
    'controls which fields you see;': 'طے کرتا ہے کہ کون سے خانے نظر آئیں؛',
    'downloads what is on screen (or every field).': 'سکرین پر نظر آنے والا (یا تمام خانوں کا) ڈیٹا ڈاؤن لوڈ کرتا ہے۔',
    'There are no students yet. Start with': 'ابھی کوئی طالب علم نہیں۔ آغاز کریں',
    ', or use': '، یا استعمال کریں',
    'to add a whole class at once from a spreadsheet.': 'تاکہ اسپریڈ شیٹ سے پوری کلاس ایک ساتھ شامل ہو۔',
    'Name, roll no, father name, phone…': 'نام، رول نمبر، والد کا نام، فون…',
    'Name, roll no, father name, phone...': 'نام، رول نمبر، والد کا نام، فون...',
    # fees page
    'Shows the current month and months that still have unpaid fees.':
        'موجودہ مہینہ اور وہ مہینے جن کی فیس باقی ہے۔',
    'Track monthly dues, collections, and outstanding balances.':
        'ماہانہ واجبات، وصولیاں اور باقی رقم کی نگرانی۔',
})


# Texts with a number or name inside: (pattern, Urdu).  Only whole-text matches.
_MONTHS = ('January', 'February', 'March', 'April', 'May', 'June', 'July', 'August',
           'September', 'October', 'November', 'December')


_MONTHS_UR = ('جنوری', 'فروری', 'مارچ', 'اپریل', 'مئی', 'جون', 'جولائی', 'اگست',
              'ستمبر', 'اکتوبر', 'نومبر', 'دسمبر')


MONTH_UR = dict(zip(_MONTHS, _MONTHS_UR))


PATTERNS = [
    # "October 2026" and "October 2026 — pending" (only the shown text; the form value stays English)
    (r'^(%s) (\d{4})$' % '|'.join(_MONTHS), lambda m: '%s %s' % (MONTH_UR[m.group(1)], m.group(2))),
    (r'^(%s) (\d{4}) \u2014 pending$' % '|'.join(_MONTHS),
     lambda m: '%s %s \u2014 باقی' % (MONTH_UR[m.group(1)], m.group(2))),
    (r'^(\d+) students?$', r'\1 طلبہ'), (r'^(\d+) teachers?$', r'\1 اساتذہ'),
    (r'^(\d+) staff$', r'\1 عملہ'), (r'^(\d+) classes$', r'\1 کلاسز'),
    (r'^(\d+) sections$', r'\1 سیکشنز'), (r'^(\d+) subjects$', r'\1 مضامین'),
    (r'^(\d+) entries$', r'\1 اندراجات'),
    (r'^Roll (\S+)$', r'رول \1'),
    (r'^Outstanding: (.+)$', r'باقی: \1'),
    (r'^(\d+)% settled$', r'\1% ادا'),
    (r'^Pending Rs ([\d,.]+)$', r'باقی Rs \1'),
    (r'^(\d+) fields$', r'\1 خانے'),
    (r'^All available fields \((\d+)\)$', r'تمام دستیاب خانے (\1)'),
]


# --- sentences with numbers inside (finance insights, dashboard cards) -------------------
# Numbers/amounts are wrapped in Unicode LTR isolates (\u2066 ... \u2069) so "Rs 1,200.50"
# and "+12.5%" keep their reading order inside a right-to-left sentence.
_W = ('Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday')


_W_UR = ('پیر', 'منگل', 'بدھ', 'جمعرات', 'جمعہ', 'ہفتہ', 'اتوار')


WEEKDAY_UR = dict(zip(_W, _W_UR))


_M = r'(?:%s)' % '|'.join(_MONTHS)


_RS = r'([+-]?Rs\.? ?[+-]?[\d,]+(?:\.\d+)?)'


_PC = r'([+-]?[\d,]+(?:\.\d+)?)'


def _n(group):
    return '\u2066' + group + '\u2069'


def _isolate(template):
    """Replacement function: fills ``{1}``, ``{2}`` ... with isolated numbers."""
    def fill(match):
        text = template
        for index, value in enumerate(match.groups(), start=1):
            text = text.replace('{%d}' % index, _n(value))
        return text
    return fill
