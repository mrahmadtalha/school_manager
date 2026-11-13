"""More Urdu phrases: fees, receipts and payments."""

from .part01 import UR
from .part04 import PATTERNS
from .part07 import HTML_SENTENCES


# --- Attendance Summary page, redesigned (Oct 2026) ---
UR.update({
    'Whole-School Attendance Summary': 'پورے اسکول کی حاضری کا خلاصہ',
    'Class Attendance Summary': 'کلاس کی حاضری کا خلاصہ',
    'Take Attendance': 'حاضری لگائیں',
    'Teacher Attendance Summary': 'اساتذہ کی حاضری کا خلاصہ',
    'All School Students': 'اسکول کے تمام طلبہ',
    'This Month': 'اس مہینے', 'Last Month': 'پچھلا مہینہ',
    'From': 'سے', 'To': 'تک',
    'Students in the school': 'اسکول کے طلبہ',
    'Never absent (100%)': 'کبھی غیر حاضر نہیں (100%)',
    'Need attention (below 75%)': 'توجہ درکار (75% سے کم)',
    'Nobody is below 75%': 'کوئی بھی 75% سے کم نہیں',
    'All students': 'تمام طلبہ',
    'Need attention': 'توجہ درکار',
    'Never absent': 'کبھی غیر حاضر نہیں',
    'Attendance': 'حاضری',
    'Student': 'طالب علم',
    'How to read the boxes:': 'خانوں کو کیسے پڑھیں:',
    'Not taken': 'حاضری نہیں لگی',
    'Go to Students': 'طلبہ پر جائیں',
    'No attendance logs found for this class and date range.': 'اس کلاس اور تاریخوں کی کوئی حاضری نہیں ملی۔',
})


HTML_SENTENCES.extend([
    ('See how often each student came to school between two dates. Students who came to school on '
     'fewer than <b>75%</b> of the days are marked in red, so you can talk to their parents.',
     'دیکھیں ہر طالب علم دو تاریخوں کے درمیان کتنی بار اسکول آیا۔ جو طلبہ <b>75%</b> سے کم دن آئے '
     'انہیں سرخ نشان لگایا گیا ہے تاکہ آپ ان کے والدین سے بات کر سکیں۔'),
    ('Press <b>Need attention</b> to see only the students below 75%, then talk to their parents. '
     'The coloured boxes on the right show every school day.',
     '<b>توجہ درکار</b> دبائیں تاکہ صرف 75% سے کم والے طلبہ نظر آئیں، پھر ان کے والدین سے بات کریں۔ '
     'دائیں طرف رنگین خانے ہر اسکول کا دن دکھاتے ہیں۔'),
    ('<strong>No attendance has been saved</strong> for these dates yet, so every box below shows a dash. '
     'Take attendance first, or choose other dates.',
     '<strong>ان تاریخوں کی حاضری ابھی محفوظ نہیں ہوئی</strong>، اس لیے نیچے ہر خانے میں لکیر ہے۔ '
     'پہلے حاضری لگائیں، یا دوسری تاریخیں چنیں۔'),
    ('Average attendance &middot; {1} school day(s) recorded',
     'اوسط حاضری &middot; {1} اسکول کے دن درج'),
])


# --- Teacher Attendance Summary page, redesigned (Oct 2026) ---
UR.update({
    'Take Teacher Attendance': 'اساتذہ کی حاضری لگائیں',
    'Student Attendance Summary': 'طلبہ کی حاضری کا خلاصہ',
    'All teachers': 'تمام اساتذہ',
    'Teacher': 'استاد',
    'Find a teacher by name or ID…': 'نام یا شناخت سے استاد تلاش کریں…',
    'No teacher matches your search.': 'آپ کی تلاش سے کوئی استاد نہیں ملا۔',
    'No teachers found.': 'کوئی استاد نہیں ملا۔',
    'Go to Teachers': 'اساتذہ پر جائیں',
    'No attendance logs found for teachers in this date range.': 'ان تاریخوں میں اساتذہ کی کوئی حاضری نہیں ملی۔',
})


HTML_SENTENCES.extend([
    ('See how often each teacher came to school between two dates. Teachers who came on '
     'fewer than <b>75%</b> of the days are marked in red, so you can talk to them.',
     'دیکھیں ہر استاد دو تاریخوں کے درمیان کتنی بار اسکول آیا۔ جو اساتذہ <b>75%</b> سے کم دن آئے '
     'انہیں سرخ نشان لگایا گیا ہے تاکہ آپ ان سے بات کر سکیں۔'),
    ('Press <b>Need attention</b> to see only the teachers below 75%, then talk to them. '
     'The coloured boxes on the right show every school day.',
     '<b>توجہ درکار</b> دبائیں تاکہ صرف 75% سے کم والے اساتذہ نظر آئیں، پھر ان سے بات کریں۔ '
     'دائیں طرف رنگین خانے ہر اسکول کا دن دکھاتے ہیں۔'),
    ('Showing <strong id="tsVisible">{1}</strong> of <strong>{2}</strong> teachers',
     'کل <strong>{2}</strong> میں سے <strong id="tsVisible">{1}</strong> اساتذہ دکھائے جا رہے ہیں'),
])


# --- Class Tests page, redesigned (Oct 2026) ---
UR.update({
    'Class Tests': 'کلاس ٹیسٹ',
    'Add Test': 'ٹیسٹ شامل کریں',
    'Add a Test': 'ٹیسٹ شامل کریں',
    'Test Categories': 'ٹیسٹ کی اقسام',
    'Make a test, then enter the marks of every student.': 'ٹیسٹ بنائیں، پھر ہر طالب علم کے نمبر لگائیں۔',
    'Term Examinations': 'ٹرم امتحانات',
    'Tests in all': 'کل ٹیسٹ',
    'Tests this month': 'اس مہینے کے ٹیسٹ',
    'Marks complete': 'نمبر مکمل',
    'Marks still to enter': 'نمبر لگانا باقی',
    'Nothing waiting for marks': 'کسی ٹیسٹ کے نمبر باقی نہیں',
    'All tests': 'تمام ٹیسٹ',
    'Marks to enter': 'نمبر لگانے ہیں',
    'Find a test': 'ٹیسٹ تلاش کریں',
    'Find a test by name…': 'نام سے ٹیسٹ تلاش کریں…',
    'No test matches your search.': 'آپ کی تلاش سے کوئی ٹیسٹ نہیں ملا۔',
    'Total Marks': 'کل نمبر',
    'Marks entered': 'لگے ہوئے نمبر',
    'No date': 'تاریخ نہیں',
    'No marks yet': 'ابھی نمبر نہیں لگے',
    'No students': 'کوئی طالب علم نہیں',
    'Enter Marks': 'نمبر لگائیں',
    'Edit Marks': 'نمبر درست کریں',
    'Delete this test': 'یہ ٹیسٹ حذف کریں',
    'Show tests as': 'ٹیسٹ اس طرح دکھائیں',
    'Clear filters': 'فلٹر ہٹائیں',
    'Cards': 'کارڈ',
})


PATTERNS += [
    (r'^Marks (\d+)/(\d+) \((\d+)%\)$', r'نمبر \1/\2 (\3%)'),
]


HTML_SENTENCES.extend([
    ('Term exams (mid-term, final) are in <b>Term Examinations</b>. This page shows Class Tests only.',
     'ٹرم امتحانات (مڈ ٹرم، فائنل) <b>ٹرم امتحانات</b> میں ہیں۔ اس صفحے پر صرف کلاس ٹیسٹ ہیں۔'),
    ('Press <b>Marks to enter</b> to see the tests that are waiting for marks, then press <b>Enter Marks</b> on a test.',
     '<b>نمبر لگانے ہیں</b> دبائیں تاکہ وہ ٹیسٹ نظر آئیں جن کے نمبر باقی ہیں، پھر ٹیسٹ پر <b>نمبر لگائیں</b> دبائیں۔'),
    ('Showing <strong id="testCount">{1}</strong> of <strong>{2}</strong> tests',
     'کل <strong>{2}</strong> میں سے <strong id="testCount">{1}</strong> ٹیسٹ دکھائے جا رہے ہیں'),
    ('No tests yet. Press <strong>Add Test</strong> to make your first one.',
     'ابھی کوئی ٹیسٹ نہیں۔ پہلا ٹیسٹ بنانے کے لیے <strong>ٹیسٹ شامل کریں</strong> دبائیں۔'),
])


# --- Term Examinations page, redesigned (Oct 2026) ---
UR.update({
    'Add Term Exam': 'ٹرم امتحان شامل کریں',
    'Official term exams with schedules, marks and results.': 'سرکاری ٹرم امتحانات: شیڈول، نمبر اور رزلٹ۔',
    'Term exams in all': 'کل ٹرم امتحانات',
    'Results published': 'رزلٹ شائع ہو چکے',
    'All term exams': 'تمام ٹرم امتحانات',
    'Find an exam': 'امتحان تلاش کریں',
    'Find an exam by name…': 'نام سے امتحان تلاش کریں…',
    'No exam matches your search.': 'آپ کی تلاش سے کوئی امتحان نہیں ملا۔',
    'All Status': 'تمام حیثیتیں',
    'All Sessions': 'تمام سیشن',
    'Scheduled': 'طے شدہ',
    'Ongoing': 'جاری',
    'Published': 'شائع شدہ',
    'Date sheet': 'ڈیٹ شیٹ',
    'No dates': 'تاریخیں نہیں',
    'Show exams as': 'امتحانات اس طرح دکھائیں',
    'No term exams yet.': 'ابھی کوئی ٹرم امتحان نہیں۔',
})


HTML_SENTENCES.extend([
    ('Press <b>Marks to enter</b> to see the exams that are waiting for marks, then press <b>Enter Marks</b> on an exam.',
     '<b>نمبر لگانے ہیں</b> دبائیں تاکہ وہ امتحانات نظر آئیں جن کے نمبر باقی ہیں، پھر امتحان پر <b>نمبر لگائیں</b> دبائیں۔'),
    ('Showing <strong id="examCount">{1}</strong> of <strong>{2}</strong> term exams',
     'کل <strong>{2}</strong> میں سے <strong id="examCount">{1}</strong> ٹرم امتحانات دکھائے جا رہے ہیں'),
    ('No term exams yet. Press <strong>Add Term Exam</strong> to schedule one.',
     'ابھی کوئی ٹرم امتحان نہیں۔ امتحان طے کرنے کے لیے <strong>ٹرم امتحان شامل کریں</strong> دبائیں۔'),
])
