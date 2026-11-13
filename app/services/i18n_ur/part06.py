"""Short month names and an amount-per-month formatter."""

from .part01 import UR
from .part04 import MONTH_UR, _MONTHS, _n


UR.update({
    # --- Class result matrix ---
    'Results matrix': 'نتائج کا میٹرکس',
    'Class Result Matrix': 'کلاس نتائج میٹرکس',
    'Compare performance across students and subjects for the selected class.':
        'منتخب کلاس کے طلبہ اور مضامین کی کارکردگی کا موازنہ کریں۔',
    'Export Whole Class Result (PDF)': 'پوری کلاس کا نتیجہ (پی ڈی ایف)',
    'All Report Cards PDF': 'تمام رپورٹ کارڈ (پی ڈی ایف)',
    'Clear month': 'مہینہ صاف کریں',
    'Test Type': 'ٹیسٹ کی قسم', 'All Types': 'تمام اقسام', '— All Types —': '— تمام اقسام —',
    'Academic Session': 'تعلیمی سیشن', 'Academic Session:': 'تعلیمی سیشن:',
    'e.g. 2025-2026': 'مثلاً 2025-2026',
    'Announcement Date': 'اعلان کی تاریخ',
    'Exam Type:': 'امتحان کی قسم:',
    'Result Announcement Date:': 'نتیجے کے اعلان کی تاریخ:',
    'Clear': 'صاف کریں', 'Clear filter': 'فلٹر ہٹائیں',
    'Tests': 'ٹیسٹ', 'Class Avg': 'کلاس اوسط', 'Pass Rate': 'کامیابی کی شرح',
    'Top Scorer': 'سب سے زیادہ نمبر لینے والا',
    'Hover over marks to see grade': 'گریڈ دیکھنے کے لیے نمبروں پر ماؤس رکھیں',
    'Click column headers to sort': 'ترتیب دینے کے لیے کالم کے عنوان پر کلک کریں',
    'Type teacher remarks in the table below, then save.':
        'نیچے جدول میں استاد کے ریمارکس لکھیں، پھر محفوظ کریں۔',
    'Save Remarks': 'ریمارکس محفوظ کریں',
    'Rank': 'پوزیشن', 'Teacher Remarks': 'استاد کے ریمارکس', 'Report': 'رپورٹ',
    'Result': 'نتیجہ', 'Pass': 'پاس', 'Fail': 'فیل', 'Remark...': 'ریمارک...',
    'Absent — not counted in total or grade': 'غیر حاضر — کل نمبر یا گریڈ میں شمار نہیں',
    'Individual Report Card PDF': 'انفرادی رپورٹ کارڈ (پی ڈی ایف)',
    'Report Card PDF': 'رپورٹ کارڈ (پی ڈی ایف)',
    'Document': 'دستاویز',
    'Paid by': 'ادائیگی بذریعہ', 'Receipt No': 'رسید نمبر', 'Entered by': 'درج کرنے والا',
    'No results found.': 'کوئی نتیجہ نہیں ملا۔',
    'Create tests and enter student marks to see results here.':
        'نتائج یہاں دیکھنے کے لیے ٹیسٹ بنائیں اور طلبہ کے نمبر درج کریں۔',

    # --- Attendance summary / matrix ---
    'Class Attendance Summary & Matrix': 'کلاس حاضری کا خلاصہ اور میٹرکس',
    'Monitor class-level attendance patterns and at-risk students.':
        'کلاس کی سطح پر حاضری کے رجحانات اور خطرے میں موجود طلبہ کی نگرانی کریں۔',
    'Whole-School Attendance Summary & Matrix': 'پورے اسکول کی حاضری کا خلاصہ اور میٹرکس',
    'All school students in one view — monitor attendance patterns and at-risk students.':
        'اسکول کے تمام طلبہ ایک نظر میں — حاضری کے رجحانات اور خطرے میں موجود طلبہ کی نگرانی کریں۔',
    'Class Avg Rate': 'کلاس اوسط شرح', 'School Avg Rate': 'اسکول اوسط شرح',
    'Red badge (< 75%) indicates Chronic Absenteeism':
        'سرخ نشان (< 75%) مستقل غیر حاضری کو ظاہر کرتا ہے',
    'No attendance logs found for this class and date range.':
        'اس کلاس اور تاریخوں کے لیے حاضری کا کوئی ریکارڈ نہیں ملا۔',

    # --- Student attendance ---
    'Track, verify, and export daily student attendance records.':
        'طلبہ کی روزانہ حاضری کا ریکارڈ درج، تصدیق اور ایکسپورٹ کریں۔',
    'Open — Not Yet Saved': 'کھلا — ابھی محفوظ نہیں ہوا',
    'All Students at Time': 'سب طلبہ اس وقت پر',
    'Save & Next Class': 'محفوظ کریں اور اگلی کلاس',
    'No students found in this class.': 'اس کلاس میں کوئی طالب علم نہیں ملا۔',
    'Paper register? Mark everyone on time with one click, then only edit the late students.':
        'کاغذی رجسٹر؟ ایک کلک میں سب کو وقت پر حاضر کریں، پھر صرف دیر سے آنے والوں کو بدلیں۔',

    # --- Teachers ---
    'Name': 'نام',
    'Manage teaching staff, assignments, and salary information in one place.':
        'تدریسی عملہ، ذمہ داریاں اور تنخواہ کی معلومات ایک ہی جگہ سنبھالیں۔',
    'Name, ID, qualification, class…': 'نام، شناخت، قابلیت، کلاس…',
    'Street / city': 'گلی / شہر', 'e.g. 3': 'مثلاً 3', 'e.g. 35000': 'مثلاً 35000',
    'e.g. 35202-1234567-8': 'مثلاً 35202-1234567-8', 'e.g. 45000': 'مثلاً 45000',
    'e.g. 500': 'مثلاً 500', 'e.g. Ayesha Bibi': 'مثلاً عائشہ بی بی',
    'e.g. M.A English': 'مثلاً ایم اے انگلش', 'e.g. T005': 'مثلاً T005',
    'Pay & Assignments': 'تنخواہ اور ذمہ داریاں',
    'Assignments & Previous Work': 'ذمہ داریاں اور سابقہ کام',
    'Generated automatically — you can change it.': 'خود بخود بنتا ہے — آپ بدل سکتے ہیں۔',
    'Optional — hold Ctrl (Cmd) to select multiple.':
        'اختیاری — ایک سے زیادہ منتخب کرنے کے لیے Ctrl (Cmd) دبائے رکھیں۔',
    'Can be restored from Archive Bin.': 'آرکائیو بن سے بحال کیا جا سکتا ہے۔',
    '/hr': '/گھنٹہ',
    '(red in the template):': '(ٹیمپلیٹ میں سرخ رنگ میں):',
    'and any custom fields set up in Settings.': 'اور سیٹنگز میں بنائے گئے تمام کسٹم خانے۔',
    'download the template below, fill one teacher per row, then upload it here.':
        'نیچے دیا گیا ٹیمپلیٹ ڈاؤن لوڈ کریں، ہر قطار میں ایک استاد بھریں، پھر یہاں اپ لوڈ کریں۔',
    'Teacher ID is optional:': 'استاد کی شناخت اختیاری ہے:',
    'leave it blank and the next free ID (T001, T002 …) is given automatically':
        'اسے خالی چھوڑ دیں تو اگلی خالی شناخت (T001، T002 …) خود بخود دی جائے گی',
    'Assigned Classes / Subjects must already exist; separate several with commas':
        'مقرر کلاسز / مضامین پہلے سے موجود ہونے چاہییں؛ ایک سے زیادہ ہوں تو کاما سے الگ کریں',
    'After the import you see exactly which rows were skipped and why':
        'امپورٹ کے بعد آپ کو بالکل نظر آ جاتا ہے کہ کون سی قطاریں اور کیوں چھوڑی گئیں',

    # --- Classes, sections and subjects ---
    'Manage academic structure, teacher groups, and class assignments.':
        'تعلیمی ڈھانچہ، اساتذہ کے گروپ اور کلاس کی ذمہ داریاں سنبھالیں۔',
    'Edit Fee': 'فیس میں ترمیم', 'Fee not set': 'فیس مقرر نہیں', 'No fee set': 'فیس مقرر نہیں',
    'not set': 'مقرر نہیں', 'Fee': 'فیس',
    'Archive Subject': 'مضمون آرکائیو کریں', 'Archive Subject?': 'مضمون آرکائیو کریں؟',
    'Clear section (unassign)': 'سیکشن ہٹائیں (غیر مقرر کریں)',
    'Delete Section?': 'سیکشن حذف کریں؟',
    'Move & Delete': 'منتقل کریں اور حذف کریں',
    'Move Students & Delete Section?': 'طلبہ منتقل کریں اور سیکشن حذف کریں؟',
    'I confirm updating the default admission fee':
        'میں ڈیفالٹ داخلہ فیس تبدیل کرنے کی تصدیق کرتا ہوں',
    'Manage': 'انتظام', 'View': 'دیکھیں',
    'No sections yet.': 'ابھی کوئی سیکشن نہیں۔', 'No subjects yet.': 'ابھی کوئی مضمون نہیں۔',
    'No students in this section.': 'اس سیکشن میں کوئی طالب علم نہیں۔',
    'Past records are unaffected. You can restore it anytime.':
        'پرانا ریکارڈ متاثر نہیں ہوتا۔ آپ اسے کسی بھی وقت بحال کر سکتے ہیں۔',
    'The Subject Library is empty — the class will start with no subjects. Add subjects inside the class after creating it; they join the library automatically.':
        'مضامین کی لائبریری خالی ہے — کلاس بغیر مضامین کے شروع ہوگی۔ کلاس بنانے کے بعد اس کے اندر مضامین شامل کریں؛ وہ خود بخود لائبریری میں شامل ہو جائیں گے۔',
    'You can add or remove subjects for this class later at any time.':
        'آپ اس کلاس کے مضامین بعد میں کسی بھی وقت شامل یا ختم کر سکتے ہیں۔',
    '(from the Subject Library — starred ones are pre-selected)':
        '(مضامین کی لائبریری سے — ستارے والے پہلے سے منتخب ہیں)',
    'Archive (hide from new tests)': 'آرکائیو (نئے ٹیسٹوں سے چھپائیں)',
    'Show students': 'طلبہ دکھائیں', 'Default subject': 'ڈیفالٹ مضمون',
    'Applies to NEW admissions only. To change the fee for ALL existing students, use Fees Management.':
        'صرف نئے داخلوں پر لاگو ہوتی ہے۔ تمام موجودہ طلبہ کی فیس بدلنے کے لیے فیس کا انتظام استعمال کریں۔',
    'This sets the default fee for NEW admissions only. To bulk-update ALL existing students, use Fees Management.':
        'یہ صرف نئے داخلوں کی ڈیفالٹ فیس مقرر کرتا ہے۔ تمام موجودہ طلبہ کو یکمشت اپ ڈیٹ کرنے کے لیے فیس کا انتظام استعمال کریں۔',
    'e.g. 2500': 'مثلاً 2500', 'e.g. 3500': 'مثلاً 3500', 'e.g. A': 'مثلاً A',
    'e.g. Class 11': 'مثلاً Class 11', 'e.g. Physics': 'مثلاً فزکس',
})


_M3 = '|'.join(m[:3] for m in _MONTHS)


_M3_UR = dict((m[:3], MONTH_UR[m]) for m in _MONTHS)


def _per_month(match):
    return 'ماہانہ ' + _n('Rs. ' + match.group(1))
