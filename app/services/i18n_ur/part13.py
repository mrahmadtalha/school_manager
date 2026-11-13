"""More Urdu phrases: classes, teachers and settings."""

from .part01 import UR
from .part04 import PATTERNS
from .part07 import HTML_SENTENCES


# --- Class Results page, redesigned (Oct 2026) ---
UR.update({
    'Class Results': 'کلاس کے نتائج',
    'See how every student did, write a remark and print the report cards.':
        'دیکھیں ہر طالب علم کا نتیجہ کیسا رہا، ریمارک لکھیں اور رپورٹ کارڈ پرنٹ کریں۔',
    'More downloads': 'مزید ڈاؤن لوڈ',
    'No classes yet.': 'ابھی کوئی کلاس نہیں۔',
    'Add your classes and students first, then come back here to see results.':
        'پہلے کلاسیں اور طلبہ شامل کریں، پھر نتائج دیکھنے یہاں واپس آئیں۔',
    'Go to Classes': 'کلاسز پر جائیں',
    'These two details are printed on the report cards and the class result sheet.':
        'یہ دونوں تفصیلات رپورٹ کارڈ اور کلاس کی رزلٹ شیٹ پر چھپتی ہیں۔',
    'Everyone who sat the tests has passed. You can print the report cards now.':
        'ٹیسٹ دینے والے سب طلبہ پاس ہیں۔ اب آپ رپورٹ کارڈ پرنٹ کر سکتے ہیں۔',
    'Class average': 'کلاس کی اوسط',
    'Find a student': 'طالب علم تلاش کریں',
    'Find a student by name or roll no…': 'نام یا رول نمبر سے طالب علم تلاش کریں…',
    'All students': 'تمام طلبہ',
    'Passed': 'پاس',
    'Not passed': 'فیل',
    'Sort by': 'ترتیب',
    'Position (1st first)': 'پوزیشن (پہلی پوزیشن پہلے)',
    'Name (A to Z)': 'نام (الف سے ی)',
    'Highest marks first': 'زیادہ نمبر پہلے',
    'Lowest marks first': 'کم نمبر پہلے',
    'How grades work': 'گریڈ کیسے بنتے ہیں',
    'A student passes with any grade except F.': 'F کے علاوہ کسی بھی گریڈ پر طالب علم پاس ہوتا ہے۔',
    'Write a remark…': 'ریمارک لکھیں…',
    'No student matches your search.': 'آپ کی تلاش سے کوئی طالب علم نہیں ملا۔',
    'This class has no students yet.': 'اس کلاس میں ابھی کوئی طالب علم نہیں۔',
    'Add students to this class and their results will appear here.':
        'اس کلاس میں طلبہ شامل کریں، ان کے نتائج یہاں نظر آئیں گے۔',
    'Go to Students': 'طلبہ پر جائیں',
    'No tests of this type for this class.': 'اس کلاس کے لیے اس قسم کا کوئی ٹیسٹ نہیں۔',
    'Choose another test type, or show all of them.': 'کوئی اور ٹیسٹ کی قسم چنیں، یا سب دکھائیں۔',
    'Show all test types': 'تمام ٹیسٹ کی اقسام دکھائیں',
    'No tests for this class yet.': 'اس کلاس کا ابھی کوئی ٹیسٹ نہیں۔',
    'Make a test and enter the marks. The results will appear here by themselves.':
        'ٹیسٹ بنائیں اور نمبر لگائیں۔ نتائج خود بخود یہاں آ جائیں گے۔',
    'Go to Class Tests': 'کلاس ٹیسٹ پر جائیں',
    'Unknown Subject': 'نامعلوم مضمون',
})


PATTERNS += [
    (r'^(\d+) tests?$', r'\1 ٹیسٹ'),
    (r'^(\d+) passed, (\d+) not passed$', r'\1 پاس، \2 فیل'),
    (r'^absent in (\d+)$', r'\1 میں غیر حاضر'),
    (r'^out of ([\d.]+)$', r'کل \1 میں سے'),
    (r'^([\d.]+)% and above$', r'\1% اور اس سے اوپر'),
    (r'^Below ([\d.]+)%$', r'\1% سے کم'),
]


HTML_SENTENCES.extend([
    ('<b>{1}</b> student(s) did not pass. Press <b>Not passed</b> to see them, then write a remark for each.',
     '<b>{1}</b> طلبہ پاس نہیں ہوئے۔ انہیں دیکھنے کے لیے <b>فیل</b> دبائیں، پھر ہر ایک کے لیے ریمارک لکھیں۔'),
    ('Showing <strong id="crCount">{1}</strong> of <strong>{2}</strong> students',
     'کل <strong>{2}</strong> میں سے <strong id="crCount">{1}</strong> طلبہ دکھائے جا رہے ہیں'),
    ('<strong id="crDirty">{1}</strong> remark(s) not saved yet',
     '<strong id="crDirty">{1}</strong> ریمارکس ابھی محفوظ نہیں ہوئے'),
])


# --- Login page, redesigned (Oct 2026) ---
UR.update({
    'Welcome! Sign in to open your school records.':
        'خوش آمدید! اپنے اسکول کا ریکارڈ کھولنے کے لیے لاگ ان کریں۔',
    'Type your username and password, then press the green button.':
        'اپنا صارف نام اور پاس ورڈ لکھیں، پھر سبز بٹن دبائیں۔',
    'Type your username': 'اپنا صارف نام لکھیں',
    'Type your password': 'اپنا پاس ورڈ لکھیں',
    'School logo': 'اسکول کا لوگو',
    'Signing in…': 'لاگ ان ہو رہا ہے…',
    'Caps Lock is on. Your password may be typed in capital letters.':
        'کیپس لاک آن ہے۔ آپ کا پاس ورڈ بڑے حروف میں لکھا جا سکتا ہے۔',
    'First time here? Use this starting login:': 'پہلی بار آئے ہیں؟ یہ شروع کا لاگ ان استعمال کریں:',
    'Username:': 'صارف نام:',
    'Password:': 'پاس ورڈ:',
    'Please change this password after you sign in.': 'لاگ ان کے بعد یہ پاس ورڈ ضرور تبدیل کر لیں۔',
    'Need help? Ask your school administrator.': 'مدد چاہیے؟ اپنے اسکول کے ایڈمن سے پوچھیں۔',
    'Incorrect username or password.': 'صارف نام یا پاس ورڈ درست نہیں ہے۔',
})


# --- Audit Log page, redesigned (Oct 2026) ---
UR.update({
    'See who did what and when: every add, change, delete and sign-in is recorded here.':
        'دیکھیں کس نے کیا اور کب کیا: ہر اضافہ، تبدیلی، حذف اور لاگ ان یہاں درج ہوتا ہے۔',
    'Use the search and filters to find an entry, then press See what changed on a row to read the old and new values. If something looks wrong, check Failed sign-ins and Deleted first.':
        'اندراج ڈھونڈنے کے لیے تلاش اور فلٹر استعمال کریں، پھر کسی قطار پر "کیا بدلا دیکھیں" دبا کر پرانی اور نئی قدریں پڑھیں۔ اگر کچھ غلط لگے تو پہلے ناکام لاگ ان اور حذف شدہ دیکھیں۔',
    'Nothing is recorded for these filters. Choose Any time, or clear the filters.':
        'ان فلٹرز کے لیے کچھ درج نہیں۔ "کسی بھی وقت" چنیں، یا فلٹر ہٹا دیں۔',
    'Entries on this list': 'اس فہرست میں اندراجات',
    'To check:': 'جانچنے کے لیے:',
    'Failed sign-ins': 'ناکام لاگ ان',
    'Failed sign-in': 'ناکام لاگ ان',
    'Show failed sign-ins': 'ناکام لاگ ان دکھائیں',
    'Show deleted records': 'حذف شدہ ریکارڈ دکھائیں',
    'Deleted': 'حذف شدہ',
    'Added': 'شامل کیا',
    'Changed': 'تبدیل کیا',
    'Signed in': 'لاگ ان ہوا',
    'Signed out': 'لاگ آؤٹ ہوا',
    'Fee charged': 'فیس لگائی گئی',
    'Payment received': 'ادائیگی وصول ہوئی',
    'Cancelled (void)': 'منسوخ',
    'Settings changed': 'سیٹنگز بدلی گئیں',
    'Data exported': 'ڈیٹا ایکسپورٹ ہوا',
    'User account': 'صارف اکاؤنٹ',
    'Reminder sent': 'یاددہانی بھیجی گئی',
    'Search a name or a sentence…': 'نام یا جملہ تلاش کریں…',
    '— All records —': '— تمام ریکارڈ —',
    '— Everything that happened —': '— جو کچھ ہوا —',
    '— All users —': '— تمام صارفین —',
    'What was it about': 'کس بارے میں تھا',
    'What happened': 'کیا ہوا',
    'Who did it': 'کس نے کیا',
    'Any time': 'کسی بھی وقت',
    'Last 7 days': 'پچھلے 7 دن',
    'Last 30 days': 'پچھلے 30 دن',
    'entries, newest first': 'اندراجات، نئے پہلے',
    'When': 'کب',
    'Details': 'تفصیل',
    'Who': 'کون',
    'About': 'متعلق',
    'See what changed': 'کیا بدلا دیکھیں',
    'Field': 'خانہ',
    'Before': 'پہلے',
    'After': 'بعد میں',
    'Show everything': 'سب دکھائیں',
    'No audit entries match these filters.': 'ان فلٹرز سے کوئی آڈٹ اندراج نہیں ملا۔',
    'Showing up to 500 most recent matching entries (CSV export is uncapped).':
        'زیادہ سے زیادہ 500 تازہ ترین اندراجات دکھائے جا رہے ہیں (CSV ایکسپورٹ میں سب شامل ہوتے ہیں)۔',
})
