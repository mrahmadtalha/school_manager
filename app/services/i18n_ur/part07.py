"""Whole-sentence Urdu translations used when a line matches exactly."""

from .part04 import PATTERNS
from .part06 import _M3, _M3_UR, _per_month


PATTERNS += [
    # "19 Oct 2026" and the "17 Dec" shown over each test column
    (r'^(\d{1,2}) (%s) (\d{4})$' % _M3,
     lambda m: '%s %s %s' % (m.group(1), _M3_UR[m.group(2)], m.group(3))),
    (r'^(\d{1,2}) (%s)$' % _M3, lambda m: '%s %s' % (m.group(1), _M3_UR[m.group(2)])),
    (r'^absent in (\d+)$', r'\1 ٹیسٹ میں غیر حاضر'),
    (r'^No tests of type "(.+)" found\.$', r'"\1" قسم کا کوئی ٹیسٹ نہیں ملا۔'),
    (r'^(\d+) days recorded$', r'\1 دن کا ریکارڈ'),
    (r'^Total: (\d+)$', r'کل: \1'),
    (r'^Late · (\d+) min$', r'تاخیر · \1 منٹ'),
    (r'^(\d+) class$', r'\1 کلاس'), (r'^(\d+) subject$', r'\1 مضمون'),
    (r'^Edit: (.+)$', r'ترمیم: \1'),
    (r'^No teachers found\.$', 'کوئی استاد نہیں ملا۔'),
    (r'^No teachers found for "(.+)"\.$', r'"\1" کے لیے کوئی استاد نہیں ملا۔'),
    (r'^Rs\.? ?([\d,]+) / month$', _per_month),
    (r'^Rs\.? ?([\d,]+) / mo$', _per_month),
    (r'^\+(\d+) archived$', r'+\1 محفوظ شدہ'),
    (r'^\((\d+) total\)$', r'(کل \1)'),
    (r'^Section (\S+)$', r'سیکشن \1'),
    (r'^\(Roll (\S+)\)$', r'(رول \1)'),
    (r'^\(Roll (\S+) · archived\)$', r'(رول \1 · محفوظ شدہ)'),
    (r'^…and (\d+) more$', r'…اور \1 مزید'),
    (r'^Add Section — (.+)$', r'سیکشن شامل کریں — \1'),
    (r'^Add Subject — (.+)$', r'مضمون شامل کریں — \1'),
    (r'^Standard Fee — (.+)$', r'معیاری فیس — \1'),
    (r'^(\d+) test\(s\) already use this subject — they keep their marks; '
     r'the subject is only hidden from new test/exam creation\.$',
     r'\1 ٹیسٹ پہلے ہی یہ مضمون استعمال کر رہے ہیں — ان کے نمبر برقرار رہتے ہیں؛ '
     r'مضمون صرف نئے ٹیسٹ/امتحان بنانے سے چھپتا ہے۔'),
    (r'^(\d+) subjects \+(\d+) archived$', r'\1 مضامین +\2 محفوظ شدہ'),
    (r'^(\d+) active, (\d+) archived$', r'\1 فعال، \2 محفوظ شدہ'),
    (r'^(\d+) total student\(s\) including leavers$', r'چھوڑ جانے والوں سمیت کل \1 طلبہ'),
    (r'^Late arrival: (\d+) minutes?$', r'تاخیر سے آمد: \1 منٹ'),
    (r'^Batch: (.+) \u2014 (.+) \(Max: (.+)\)$',
     r'بیچ: \1 — \2 (زیادہ سے زیادہ: \3)'),
    (r'^(\d+) Absent$', r'\1 غیر حاضر'),
]


# Sentences that contain bold text, links or numbers in the middle are written once, whole.
# ``{1}``, ``{2}`` ... stand for the parts the page fills in (names, numbers, links).
HTML_SENTENCES = [
    ('{1} and any custom fields set up in Settings.',
     '{1} اور سیٹنگز میں بنائے گئے تمام کسٹم خانے۔'),
    ('A <b>class</b> is the year group (e.g. Class 5). Inside it you add <b>sections</b> '
     '(A, B…) and the <b>subjects</b> taught. Set the monthly fee on the class so student '
     'fees fill in automatically. Use the pencil to edit, the archive icon to hide '
     'something you no longer use, and <b>Grid</b> for a visual overview.',
     '<b>کلاس</b> سال کا گروپ ہوتا ہے (مثلاً Class 5)۔ اس کے اندر آپ <b>سیکشنز</b> (A, B…) '
     'اور پڑھائے جانے والے <b>مضامین</b> شامل کرتے ہیں۔ کلاس پر ماہانہ فیس مقرر کریں تاکہ طلبہ کی '
     'فیس خود بخود بھر جائے۔ ترمیم کے لیے پنسل، غیر استعمال شدہ چیز چھپانے کے لیے آرکائیو آئیکن، '
     'اور بصری جائزے کے لیے <b>گرڈ</b> استعمال کریں۔'),
    ('{1} class(es) have no standard monthly fee yet &mdash; use the <b>Set Fee</b> '
     'button inside each class.',
     '{1} کلاسز کی ابھی معیاری ماہانہ فیس مقرر نہیں &mdash; ہر کلاس کے اندر '
     '<b>فیس مقرر کریں</b> کا بٹن استعمال کریں۔'),
    ('This edits class metadata only. The standard monthly fee is managed separately '
     '&mdash; use the green <b>Set Fee</b> button.',
     'اس سے صرف کلاس کی بنیادی معلومات بدلتی ہیں۔ معیاری ماہانہ فیس الگ سے سنبھالی جاتی ہے '
     '&mdash; سبز رنگ کا <b>فیس مقرر کریں</b> بٹن استعمال کریں۔'),
    ('Sets the <b>default admission fee</b> for <b>new students</b> in {1}. '
     'Existing student records are not changed &mdash; to bulk-update <b>all</b> students, use '
     '<a href="{2}" target="_blank">Fees Management</a>.',
     'یہ {1} کے <b>نئے طلبہ</b> کے لیے <b>ڈیفالٹ داخلہ فیس</b> مقرر کرتا ہے۔ موجودہ طلبہ کے '
     'ریکارڈ تبدیل نہیں ہوتے &mdash; <b>تمام</b> طلبہ کی فیس یکمشت بدلنے کے لیے '
     '<a href="{2}" target="_blank">فیس کا انتظام</a> استعمال کریں۔'),
    ('Section <strong>{1}</strong> has <strong>{2}</strong> student(s) ({3} active).',
     'سیکشن <strong>{1}</strong> میں <strong>{2}</strong> طلبہ ہیں ({3} فعال)۔'),
    ('Delete section <strong>{1}</strong> from {2}?',
     'کیا سیکشن <strong>{1}</strong> کو {2} سے حذف کریں؟'),
    ('Hide <strong>{1}</strong> from new tests and exams in {2}?',
     'کیا <strong>{1}</strong> کو {2} کے نئے ٹیسٹ اور امتحانات سے چھپا دیں؟'),
    ('Showing <strong id="visibleCount">{1}</strong> teacher(s)',
     '<strong id="visibleCount">{1}</strong> اساتذہ دکھا رہے ہیں'),
    ('for "<strong>{1}</strong>"', '<strong>{1}</strong> کے لیے'),
    ('Archive <strong>{1}</strong> (ID: {2})?',
     'کیا <strong>{1}</strong> (شناخت: {2}) کو آرکائیو کریں؟'),
    ('A row with a mandatory value missing is <strong>skipped</strong> and reported '
     '&mdash; nothing incomplete is saved',
     'جس قطار میں کوئی لازمی قدر نہ ہو اسے <strong>چھوڑ دیا جاتا ہے</strong> اور رپورٹ کیا جاتا ہے '
     '&mdash; کوئی ادھورا ریکارڈ محفوظ نہیں ہوتا'),
    ('Dates: {1} or {2}', 'تاریخیں: {1} یا {2}'),
    ('Existing teachers are <strong>never overwritten</strong>. Rows are skipped if the '
     'Teacher ID or CNIC is already registered, or the same teacher already exists',
     'موجودہ اساتذہ <strong>کبھی تبدیل نہیں ہوتے</strong>۔ اگر استاد کی شناخت یا شناختی کارڈ '
     'پہلے سے درج ہو، یا وہی استاد پہلے سے موجود ہو تو قطار چھوڑ دی جاتی ہے'),
    ('Supports <strong>.xlsx</strong> and <strong>.csv</strong>',
     '<strong>.xlsx</strong> اور <strong>.csv</strong> فائلیں قابل قبول ہیں'),
    ('Exports follow this choice — use the Export Data menu to download '
     '<strong>current view columns</strong> or <strong>all fields</strong>.',
     'ایکسپورٹ اسی انتخاب کے مطابق ہوتا ہے — ایکسپورٹ ڈیٹا مینو سے '
     '<strong>موجودہ کالم</strong> یا <strong>تمام خانے</strong> ڈاؤن لوڈ کریں۔'),
    ('School hours: {1}–{2}. Late is automatic after start + {3} minute(s) grace. '
     'Enter each student’s actual check-in time, or use <strong>All Students at Time</strong> '
     'to mark everyone on time and only change the late ones.',
     'اسکول کے اوقات: {1}–{2}۔ آغاز + {3} منٹ کی رعایت کے بعد تاخیر خود بخود لگ جاتی ہے۔ '
     'ہر طالب علم کے آنے کا اصل وقت درج کریں، یا سب کو وقت پر حاضر کرنے اور صرف دیر سے آنے '
     'والوں کا وقت بدلنے کے لیے <strong>سب طلبہ اس وقت پر</strong> استعمال کریں۔'),
    ('Saving will <strong>lock</strong> this attendance and move to the next class.',
     'محفوظ کرنے پر یہ حاضری <strong>مقفل</strong> ہو جائے گی اور اگلی کلاس کھل جائے گی۔'),
    # the folder path after it sits in a <code> block and is put back untouched
    ('Node runtime: {1} &middot; Bridge folder:',
     'نوڈ رن ٹائم: {1} &middot; برج فولڈر:'),
]
