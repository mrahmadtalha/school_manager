"""More Urdu phrases: attendance and student records."""

from .part01 import UR
from .part04 import PATTERNS, _PC, _RS, _isolate, _n
from .part07 import HTML_SENTENCES
from .part10 import _MONTH_YEAR, _better, _my


PATTERNS += [
    # headline and tiles
    (r'^(\d+) thing\(s\) need your attention in %s\.$' % _MONTH_YEAR,
     lambda m: '%s باتوں پر %s میں آپ کی توجہ درکار ہے۔' % (_n(m.group(1)), _my(m.group(2), m.group(3)))),
    (r'^Everything looks fine for %s\.$' % _MONTH_YEAR,
     lambda m: '%s میں سب کچھ ٹھیک نظر آ رہا ہے۔' % _my(m.group(1), m.group(2))),
    (r'^Nothing needs your attention for %s\.$' % _MONTH_YEAR,
     lambda m: '%s میں کسی چیز پر توجہ کی ضرورت نہیں۔' % _my(m.group(1), m.group(2))),
    (r'^%s and last month$' % _MONTH_YEAR,
     lambda m: '%s اور پچھلا مہینہ' % _my(m.group(1), m.group(2))),
    (r'^%s paid out of %s due this month$' % (_RS, _RS),
     _isolate('اس مہینے واجب {2} میں سے {1} ادا ہو چکے')),
    (r'^(Better than|Lower than) last month \(%s%%\)$' % _PC,
     lambda m: 'پچھلے مہینے سے %s (%s%%)' % (_better(m.group(1)), _n(m.group(2)))),
    (r'^Same as last month \(%s%%\)$' % _PC,
     _isolate('پچھلے مہینے کے برابر ({1}%)')),
    (r'^%s from earlier months is still unpaid\.$' % _RS,
     _isolate('پچھلے مہینوں کے {1} ابھی ادا نہیں ہوئے۔')),
    (r'^Out of every Rs 100 received, about Rs (\d+) went to salaries\.$',
     _isolate('ہر 100 روپے کی آمد میں سے تقریباً {1} روپے تنخواہوں پر گئے۔')),
    (r'^Salaries paid %s \u00b7 received %s$' % (_RS, _RS),
     _isolate('ادا شدہ تنخواہیں {1} \u00b7 موصول {2}')),
    (r'^%s (better|lower) than last month \(%s\)$' % (_RS, _RS),
     lambda m: '%s پچھلے مہینے سے %s (%s)' % (_n(m.group(1)), _better(m.group(2)), _n(m.group(3)))),
    (r'^Same as last month \(%s\)$' % _RS,
     _isolate('پچھلے مہینے کے برابر ({1})')),
    (r'^%s of it went out inside admission packages \(already paid in the admission fee\)\.$' % _RS,
     _isolate('اس میں سے {1} داخلہ پیکیج کے ساتھ دیے گئے (داخلہ فیس میں پہلے ہی ادا)۔')),

    # what to do
    (r'^Collect old dues: %s from earlier months is still unpaid\.$' % _RS,
     _isolate('پرانا بقایا وصول کریں: پچھلے مہینوں کے {1} ابھی ادا نہیں ہوئے۔')),
    (r"^Only %s%% of this month's fees are paid\. Call the parents who have not paid yet\.$" % _PC,
     _isolate('اس مہینے کی صرف {1}% فیس ادا ہوئی ہے۔ جن والدین نے ابھی ادا نہیں کی ان سے رابطہ کریں۔')),
    (r'^In total, %s of fees is still unpaid\. Start with the biggest dues\.$' % _RS,
     _isolate('کل {1} فیس ابھی ادا نہیں ہوئی۔ سب سے بڑے بقایا والوں سے شروع کریں۔')),
    (r'^(.+) spending went up %s%% since last month\. Check for waste or one-time purchases\.$' % _PC,
     lambda m: '%s کے اخراجات پچھلے مہینے سے %s%% بڑھے۔ فضول خرچی یا ایک بار کی خریداری دیکھیں۔' % (
         m.group(1), _n(m.group(2)))),
    (r'^Order more stock soon: (.+) (is|are) running low\.$',
     lambda m: 'جلد مزید اسٹاک منگوائیں: %s ختم ہونے کے قریب %s۔' % (
         m.group(1), 'ہے' if m.group(2) == 'is' else 'ہیں')),
    (r'^More money went out than came in this month \(Net Position is below zero\)\.$',
     'اس مہینے آمد سے زیادہ رقم خرچ ہوئی (خالص پوزیشن صفر سے نیچے ہے)۔'),
    (r'^More money went out than came in this month \(Net Position is below zero\)\. '
     r'%s of it was spent on stock, which you still have\. It is not lost\.$' % _RS,
     _isolate('اس مہینے آمد سے زیادہ رقم خرچ ہوئی (خالص پوزیشن صفر سے نیچے ہے)۔ '
              'اس میں سے {1} اسٹاک پر لگے، جو آپ کے پاس موجود ہے۔ یہ ضائع نہیں ہوا۔')),

    # what changed
    (r'^Fee collection is (better|weaker) than last month: %s%% paid now, %s%% last month\.$' % (_PC, _PC),
     lambda m: 'فیس کی وصولی پچھلے مہینے سے %s ہے: اب %s%% ادا، پچھلے مہینے %s%%۔' % (
         'بہتر' if m.group(1) == 'better' else 'کمزور', _n(m.group(2)), _n(m.group(3)))),
    (r'^Fee collection is the same as last month: %s%% paid\.$' % _PC,
     _isolate('فیس کی وصولی پچھلے مہینے جیسی ہے: {1}% ادا۔')),
    (r'^%s of old unpaid fees was paid this month\.$' % _RS,
     _isolate('اس مہینے {1} کی پرانی غیر ادا شدہ فیس ادا ہوئی۔')),
    (r'^You received %s%% (more|less) money than last month \(%s now, %s last month\)\.$' % (_PC, _RS, _RS),
     lambda m: 'آپ کو پچھلے مہینے سے %s%% %s رقم ملی (اب %s، پچھلے مہینے %s)۔' % (
         _n(m.group(1)), 'زیادہ' if m.group(2) == 'more' else 'کم', _n(m.group(3)), _n(m.group(4)))),
    (r'^Net Position is %s (better|lower) than last month\.$' % _RS,
     lambda m: 'خالص پوزیشن پچھلے مہینے سے %s %s ہے۔' % (_n(m.group(1)), _better(m.group(2)))),
    (r'^(.+) spending went up %s%% since last month \(%s more\)\.$' % (_PC, _RS),
     lambda m: '%s کے اخراجات پچھلے مہینے سے %s%% بڑھے (%s زیادہ)۔' % (
         m.group(1), _n(m.group(2)), _n(m.group(3)))),
    (r'^Shop sales were %s and the items sold cost %s \(profit on them: %s\)\.$' % (_RS, _RS, _RS),
     _isolate('دکان کی فروخت {1} رہی اور بکنے والی اشیاء کی لاگت {2} (ان پر منافع: {3})۔')),
    (r'^Books and uniform worth %s were given with admissions\. Their price is already inside the admission fee\.$' % _RS,
     _isolate('{1} کی کتابیں اور یونیفارم داخلے کے ساتھ دیے گئے۔ ان کی قیمت داخلہ فیس میں پہلے ہی شامل ہے۔')),
    (r'^%s was spent on buying stock\. It is money paid out, but not an expense\. The cost is counted when the items are sold\.$' % _RS,
     _isolate('{1} اسٹاک خریدنے پر لگے۔ یہ ادا کی گئی رقم ہے مگر خرچ نہیں۔ اس کی لاگت چیزیں بکنے پر گنی جاتی ہے۔')),
    (r'^Estimated Net Operating Position was %s \(what the school earned, minus salaries, running costs and the cost of items sold\)\. It is an estimate, not money moved\.$' % _RS,
     _isolate('اندازاً خالص آپریٹنگ پوزیشن {1} رہی (اسکول نے جو کمایا، منفی تنخواہیں، روزمرہ اخراجات اور بکنے والی اشیاء کی لاگت)۔ یہ اندازہ ہے، رقم کی نقل و حرکت نہیں۔')),
    (r'^Students who left mean about %s less in monthly fees \(estimate\)\.$' % _RS,
     _isolate('چھوڑنے والے طلبہ کی وجہ سے ماہانہ فیس میں اندازاً {1} کم آئیں گے۔')),
]


# --- Teacher attendance page, redesigned (Oct 2026) ---
UR.update({
    'Monthly Summary': 'ماہانہ خلاصہ',
    'Teachers in school': 'اسکول کے اساتذہ',
    'Saved for this day': 'اس دن کی حاضری محفوظ ہے',
    'You can still change a teacher and save again.': 'آپ اب بھی کسی استاد کو بدل کر دوبارہ محفوظ کر سکتے ہیں۔',
    'Not Yet Saved': 'ابھی محفوظ نہیں',
    'Find a teacher by name or ID…': 'نام یا شناخت سے استاد تلاش کریں…',
    'Find a teacher': 'استاد تلاش کریں',
    'Show only these teachers': 'صرف یہ اساتذہ دکھائیں',
    'Show all teachers': 'تمام اساتذہ دکھائیں',
    'All Teachers at Time': 'سب اساتذہ اس وقت پر',
    'No teacher matches your search.': 'آپ کی تلاش سے کوئی استاد نہیں ملا۔',
    'Go to Teachers': 'اساتذہ پر جائیں',
    'Mark every teacher as Absent?': 'کیا تمام اساتذہ کو غیر حاضر لگانا ہے؟',
    'Save Teacher Attendance': 'اساتذہ کی حاضری محفوظ کریں',
    'You can open this day again later and change it.': 'آپ اس دن کو بعد میں دوبارہ کھول کر بدل سکتے ہیں۔',
})


HTML_SENTENCES.extend([
    ('Mark which teachers came to school. Everyone starts as <b>Present</b>, so you only need to '
     'touch the teachers who are absent, late or on leave.',
     'دیکھیں کون سے اساتذہ اسکول آئے۔ سب پہلے سے <b>حاضر</b> ہوتے ہیں، اس لیے صرف غیر حاضر، '
     'دیر سے آنے والے یا رخصت والے اساتذہ کو بدلیں۔'),
    ('Tap <b>Absent</b>, <b>Late</b> or <b>Leave</b> for the teachers who need it, then press '
     '<b>Save Teacher Attendance</b> at the bottom.',
     'جن اساتذہ کو ضرورت ہو ان کے لیے <b>غیر حاضر</b>، <b>تاخیر</b> یا <b>رخصت</b> دبائیں، '
     'پھر نیچے <b>اساتذہ کی حاضری محفوظ کریں</b> دبائیں۔'),
    ('School hours: {1}–{2}. Late is automatic after start + {3} minute(s) grace. '
     'Enter each teacher’s actual check-in time, or use <strong>All Teachers at Time</strong> '
     'to mark everyone on time and only change the late ones.',
     'اسکول کے اوقات: {1}–{2}۔ آغاز + {3} منٹ کی رعایت کے بعد تاخیر خود بخود لگ جاتی ہے۔ '
     'ہر استاد کے آنے کا اصل وقت درج کریں، یا سب کو وقت پر حاضر کرنے اور صرف دیر سے آنے '
     'والوں کا وقت بدلنے کے لیے <strong>سب اساتذہ اس وقت پر</strong> استعمال کریں۔'),
    ('Showing <strong id="taVisible">{1}</strong> of <strong>{2}</strong> teachers',
     'کل <strong>{2}</strong> میں سے <strong id="taVisible">{1}</strong> اساتذہ دکھائے جا رہے ہیں'),
    ('<strong>{1} of {2}</strong> teachers: attendance not marked yet',
     '<strong>{1} of {2}</strong> اساتذہ کی حاضری ابھی نہیں لگی'),
    ('Teachers you do not touch are saved as <strong>Present</strong> when you press Save.',
     'جن اساتذہ کو آپ نہیں چھیڑیں گے وہ محفوظ کرتے وقت <strong>حاضر</strong> لگ جائیں گے۔'),
])
