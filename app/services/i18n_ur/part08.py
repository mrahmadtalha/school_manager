"""More Urdu phrases: dues, fee reminders and report wording."""

from .part01 import UR


# --- WhatsApp Center, Documents and Analytics & Exports screens -------------------------
UR.update({
    # WhatsApp Center: header, badges, sending limits
    'Messages & delivery': 'پیغامات اور ترسیل', 'WhatsApp Center': 'واٹس ایپ سینٹر',
    'Automation on': 'آٹومیشن آن', 'Automation off': 'آٹومیشن آف',
    'Cloud API selected': 'Cloud API منتخب', 'QR Scan selected': 'QR اسکین منتخب',
    'Approval required': 'منظوری درکار', 'Delayed sending': 'تاخیر سے ارسال',
    'Automatic sending': 'خودکار ارسال',
    'Sending limits (set by your license to protect your WhatsApp number)':
        'ارسال کی حدود (آپ کے لائسنس کے مطابق، آپ کے واٹس ایپ نمبر کی حفاظت کے لیے)',
    'Today:': 'آج:', '\u00b7 This month:': '\u00b7 اس مہینے:',
    'Connection & Settings': 'کنکشن اور ترتیبات',
    'Message Queue & Logs': 'پیغامات کی قطار اور لاگ',
    # WhatsApp Center: bridge notice (these hints come from the server)
    'WhatsApp notifications': 'واٹس ایپ نوٹیفکیشنز',
    'The WhatsApp component is missing on this computer. Everything else keeps working; '
    'queued messages will wait here until School Manager is reinstalled with the WhatsApp '
    'component.':
        'اس کمپیوٹر پر واٹس ایپ کا جزو موجود نہیں۔ باقی سب کچھ معمول کے مطابق چلتا رہے گا؛ '
        'قطار میں لگے پیغامات اس وقت تک رکے رہیں گے جب تک اسکول منیجر واٹس ایپ جزو کے ساتھ '
        'دوبارہ انسٹال نہ کیا جائے۔',
    'The WhatsApp bridge is installed, but no Node.js runtime was found on this computer. '
    'Install the WhatsApp component again (it bundles its own Node runtime) to enable sending.':
        'واٹس ایپ برج انسٹال ہے، مگر اس کمپیوٹر پر Node.js رن ٹائم نہیں ملا۔ پیغامات بھیجنے کے '
        'لیے واٹس ایپ جزو دوبارہ انسٹال کریں (اس کے ساتھ اپنا Node رن ٹائم شامل ہوتا ہے)۔',
    'The WhatsApp bridge is installed but not running. Start it (or restart the app with the '
    'WhatsApp component enabled) to send queued messages.':
        'واٹس ایپ برج انسٹال ہے مگر چل نہیں رہا۔ قطار کے پیغامات بھیجنے کے لیے اسے شروع کریں '
        '(یا واٹس ایپ جزو فعال کر کے ایپ دوبارہ چلائیں)۔',
    'The WhatsApp bridge is running - scan the QR code below to pair the school phone.':
        'واٹس ایپ برج چل رہا ہے - اسکول کا فون جوڑنے کے لیے نیچے دیا گیا QR کوڈ اسکین کریں۔',
    'WhatsApp bridge is running and the school phone is paired.':
        'واٹس ایپ برج چل رہا ہے اور اسکول کا فون جڑا ہوا ہے۔',
    'Without it, attendance/result notifications stay queued and can be sent later once '
    'School Manager is reinstalled \u2014 no messages are lost.':
        'اس کے بغیر حاضری اور رزلٹ کے پیغامات قطار میں رکے رہتے ہیں اور اسکول منیجر دوبارہ '
        'انسٹال ہونے پر بعد میں بھیجے جا سکتے ہیں \u2014 کوئی پیغام ضائع نہیں ہوتا۔',
    # WhatsApp Center: status cards
    'Checking QR...': 'QR کی جانچ ہو رہی ہے...',
    'Checking latest activity...': 'تازہ ترین سرگرمی کی جانچ ہو رہی ہے...',
    'Refresh': 'ریفریش', 'Send Test Message': 'ٹیسٹ پیغام بھیجیں',
    'Status detail': 'حالت کی تفصیل', 'QR status': 'QR کی حالت',
    'Last successful send': 'آخری کامیاب ارسال',
    'No successful send yet': 'ابھی تک کوئی کامیاب ارسال نہیں',
    'Last event': 'آخری واقعہ', 'Latest queue item:': 'قطار کا تازہ ترین اندراج:',
    'No message activity yet.': 'ابھی تک پیغامات کی کوئی سرگرمی نہیں۔',
    'Send a test message': 'ٹیسٹ پیغام بھیجیں',
    'Recipient phone number': 'وصول کنندہ کا فون نمبر',
    'Enter a recipient number to test Cloud API delivery.':
        'Cloud API سے ارسال جانچنے کے لیے وصول کنندہ کا نمبر لکھیں۔',
    'Leave blank to send to your connected WhatsApp account.':
        'خالی چھوڑیں تو پیغام آپ کے منسلک واٹس ایپ اکاؤنٹ کو بھیجا جائے گا۔',
    'Send test': 'ٹیسٹ بھیجیں',
    # WhatsApp Center: settings form
    'Enable WhatsApp automation': 'واٹس ایپ آٹومیشن فعال کریں',
    'Delivery mode': 'ارسال کا طریقہ', 'Fully automatic': 'مکمل خودکار',
    'One-by-one delayed sending': 'ایک ایک کر کے تاخیر سے ارسال',
    'Integration Method': 'کنکشن کا طریقہ',
    'QR Scan (Baileys Web API)': 'QR اسکین (Baileys Web API)',
    'Official WhatsApp Cloud API': 'سرکاری واٹس ایپ Cloud API',
    'Access Token': 'ایکسیس ٹوکن', 'Phone Number ID': 'فون نمبر آئی ڈی',
    'WhatsApp Business Account ID (WABA ID)': 'واٹس ایپ بزنس اکاؤنٹ آئی ڈی (WABA ID)',
    'Saved token retained when blank': 'خالی چھوڑنے پر محفوظ شدہ ٹوکن برقرار رہے گا',
    'Enter Meta access token': 'Meta کا ایکسیس ٹوکن لکھیں',
    'Attendance alerts': 'حاضری کے الرٹس',
    'Tell guardians when a student is absent.': 'طالب علم غیر حاضر ہو تو سرپرست کو بتائیں۔',
    'Late arrival': 'دیر سے آمد',
    'Let guardians know about late arrivals.': 'دیر سے آنے پر سرپرست کو آگاہ کریں۔',
    'Academic alerts': 'تعلیمی الرٹس', 'Results & exam cards': 'رزلٹ اور امتحانی کارڈ',
    'Notify guardians when results are published.': 'رزلٹ شائع ہونے پر سرپرست کو اطلاع دیں۔',
    'Published exam messages use the current delivery mode and queue.':
        'شائع شدہ امتحانی پیغامات موجودہ ارسال کے طریقے اور قطار کے مطابق جاتے ہیں۔',
    'Finance alerts': 'مالی الرٹس', 'Payment slips': 'ادائیگی کی رسیدیں',
    'Allow fee reminders to be added to the queue.':
        'فیس کی یاد دہانیوں کو قطار میں شامل ہونے کی اجازت دیں۔',
    'Send a WhatsApp receipt after collecting a payment.':
        'ادائیگی وصول کرنے کے بعد واٹس ایپ پر رسید بھیجیں۔',
    'Edit message wording': 'پیغام کے الفاظ تبدیل کریں', 'Absent alert': 'غیر حاضری کا الرٹ',
    'Save Settings': 'ترتیبات محفوظ کریں',
    'Connect by QR code': 'QR کوڈ سے منسلک کریں', 'QR Scan': 'QR اسکین',
    'Only needed when QR Scan is the selected integration.':
        'صرف اس وقت درکار ہے جب کنکشن کا طریقہ QR اسکین ہو۔',
    'QR will appear here when the service is ready.':
        'سروس تیار ہونے پر QR یہاں نظر آئے گا۔',
    'Open WhatsApp on your phone and scan this code to connect.':
        'اپنے فون پر واٹس ایپ کھولیں اور منسلک ہونے کے لیے یہ کوڈ اسکین کریں۔',
    # WhatsApp Center: message queue tab
    'Waiting': 'انتظار میں', 'Approved': 'منظور شدہ', 'Delivered': 'ارسال شدہ',
    'Rejected': 'مسترد', 'Sending': 'ارسال ہو رہا ہے', 'Sent': 'بھیجا گیا', 'Failed': 'ناکام',
    'Waiting approval': 'منظوری کا انتظار', 'Retries': 'دوبارہ کوششیں',
    'All statuses': 'تمام حالتیں', 'All triggers': 'تمام اقسام',
    'Search phone, message, or category': 'فون، پیغام یا زمرہ تلاش کریں',
    'ID': 'آئی ڈی', 'Trigger': 'پیغام کی قسم', 'Created': 'بنایا گیا',
    'Action': 'عمل', 'Approve': 'منظور کریں', 'Reject': 'مسترد کریں', 'Retry': 'دوبارہ کوشش',
    'No action': 'کوئی عمل نہیں', 'Not sent yet': 'ابھی نہیں بھیجا گیا',
    'No queued messages yet.': 'ابھی تک کوئی پیغام قطار میں نہیں۔',
    'attendance_absent': 'غیر حاضری', 'attendance_late': 'دیر سے آمد',
    'attendance_correction': 'حاضری کی درستی',
    'fee_due': 'فیس واجب', 'fee_overdue': 'فیس کی تاخیر', 'fee_reminder': 'فیس کی یاد دہانی',
    'school_notice': 'اسکول کا نوٹس',
    # Documents
    'Print & export': 'پرنٹ اور ایکسپورٹ',
    'Create ready-to-print ID cards and certificates.':
        'پرنٹ کے لیے تیار شناختی کارڈ اور سرٹیفکیٹ بنائیں۔',
    'Student ID Cards': 'طلبہ کے شناختی کارڈ', 'Staff ID Cards': 'عملے کے شناختی کارڈ',
    'Choose a student or class. Leave both blank to print cards for all active students.':
        'کوئی طالب علم یا کلاس منتخب کریں۔ دونوں خالی چھوڑنے پر تمام فعال طلبہ کے کارڈ بنیں گے۔',
    'Export a single teacher card or the full staff set.':
        'ایک استاد کا کارڈ یا پورے عملے کے کارڈ ایکسپورٹ کریں۔',
    'Whole Class': 'پوری کلاس', 'Single student': 'ایک طالب علم',
    '\u2014 All students \u2014': '\u2014 تمام طلبہ \u2014',
    '\u2014 All active teachers \u2014': '\u2014 تمام فعال اساتذہ \u2014',
    '\u2014 Optional class filter \u2014': '\u2014 کلاس فلٹر (اختیاری) \u2014',
    '\u2014 Select a student \u2014': '\u2014 طالب علم منتخب کریں \u2014',
    'Download student cards': 'طلبہ کے کارڈ ڈاؤن لوڈ کریں',
    'Download staff cards': 'عملے کے کارڈ ڈاؤن لوڈ کریں',
    'Certificates': 'سرٹیفکیٹس',
    'Choose a certificate type, then a student or a whole class. School name, logo, address, '
    'and phone from Settings are printed automatically.':
        'سرٹیفکیٹ کی قسم منتخب کریں، پھر کوئی طالب علم یا پوری کلاس۔ سیٹنگز میں درج اسکول کا نام، '
        'لوگو، پتہ اور فون نمبر خود بخود چھپ جاتے ہیں۔',
    'Certificate type': 'سرٹیفکیٹ کی قسم', 'Issue date': 'اجرا کی تاریخ',
    'Remarks / achievement': 'ریمارکس / کامیابی',
    'Download certificates PDF': 'سرٹیفکیٹس پی ڈی ایف ڈاؤن لوڈ کریں',
    'Available records': 'دستیاب ریکارڈ',
    'Leave blank to include every class.': 'خالی چھوڑنے پر ہر کلاس شامل ہوگی۔',
    'e.g. 1st position in Class 8 annual exams, 92%':
        'مثلاً کلاس 8 کے سالانہ امتحان میں پہلی پوزیشن، 92%',
    # Analytics & Exports (reports hub)
    'Analytics hub': 'تجزیاتی مرکز', 'Year': 'سال', 'Analytics': 'تجزیات',
    'Finance & Fees': 'مالیات اور فیس', 'Academic & Examinations': 'تعلیمی اور امتحانات',
    'Students, Staff & Operations': 'طلبہ، عملہ اور انتظامی امور',
    'Attendance Rate': 'حاضری کی شرح', 'Exam Pass Rate': 'امتحان میں کامیابی کی شرح',
    'Fee Recovery vs Outstanding': 'فیس کی وصولی بمقابلہ باقی',
    'Attendance Trend (Present %)': 'حاضری کا رجحان (حاضر %)',
    'Academic Performance (Average %)': 'تعلیمی کارکردگی (اوسط %)',
    'Universal Financial & Fee Exports': 'مالی اور فیس کی تمام ایکسپورٹس',
    'Available': 'دستیاب',
    'Monthly Fee Ledgers': 'ماہانہ فیس کھاتے',
    'Per-student ledger (charges, payments, balance) for the selected month.':
        'منتخب مہینے کے لیے ہر طالب علم کا کھاتہ (فیس، ادائیگیاں، باقی رقم)۔',
    'Defaulter Lists': 'نادہندگان کی فہرستیں',
    'Students with pending balances, with parent contact details.':
        'باقی رقم والے طلبہ، سرپرست کے رابطہ کی تفصیل کے ساتھ۔',
    'Collection Summaries': 'وصولی کے خلاصے',
    'Expected vs collected vs outstanding by class for the period.':
        'مدت کے لیے کلاس کے لحاظ سے متوقع، وصول شدہ اور باقی رقم۔',
    'Discount Summaries': 'رعایت کے خلاصے',
    'Students receiving fee discounts, by type and total value.':
        'فیس میں رعایت پانے والے طلبہ، قسم اور کل مالیت کے لحاظ سے۔',
    'Admission Fees Register': 'داخلہ فیس رجسٹر',
    'One-time admission fees: agreed, concessions given, received and pending.':
        'یکمشت داخلہ فیس: طے شدہ، دی گئی رعایت، وصول شدہ اور باقی۔',
    'Staff Salary Register': 'عملے کی تنخواہ کا رجسٹر',
    'Monthly payroll register with base, deductions and net pay.':
        'ماہانہ تنخواہوں کا رجسٹر: بنیادی تنخواہ، کٹوتیاں اور خالص ادائیگی۔',
    'Financial Summary': 'مالی خلاصہ',
    'Collections, expenses and payroll snapshot for the month.':
        'مہینے کی وصولیوں، اخراجات اور تنخواہوں کا مختصر جائزہ۔',
    'Expense Reports': 'اخراجات کی رپورٹس',
    'All recorded expenses with categories and payment methods.':
        'درج شدہ تمام اخراجات، زمرے اور ادائیگی کے طریقے کے ساتھ۔',
    'Insights': 'تجزیاتی رپورٹ',
    'Collection rate, arrears recovery, salary burden and expense trends with plain-language '
    'analysis.':
        'وصولی کی شرح، بقایا جات کی وصولی، تنخواہوں کا بوجھ اور اخراجات کے رجحانات، آسان زبان کے '
        'تجزیے کے ساتھ۔',
    'Open insights': 'تجزیہ کھولیں', 'Summary': 'خلاصہ',
    'Academic & Examination Exports': 'تعلیمی اور امتحانی ایکسپورٹس',
    'Select a class to enable class exports': 'کلاس ایکسپورٹس کے لیے کلاس منتخب کریں',
    'Select a class to enable class-specific exports':
        'کلاس کے مطابق ایکسپورٹس کے لیے کلاس منتخب کریں',
    'Select a class first': 'پہلے کلاس منتخب کریں', 'Reset filters': 'فلٹر ری سیٹ کریں',
    'Select term examination': 'ٹرم امتحان منتخب کریں',
    'Consolidated Class Result': 'کلاس کا مجموعی رزلٹ',
    'Official single-page matrix: subjects, totals, %, positions.':
        'سرکاری ایک صفحے کا میٹرکس: مضامین، کل نمبر، فیصد، پوزیشنیں۔',
    'Whole Class Result Matrix': 'پوری کلاس کا رزلٹ میٹرکس',
    'Every test column with marks, totals and grades.':
        'ہر ٹیسٹ کا کالم، نمبر، کل نمبر اور گریڈ کے ساتھ۔',
    'All Report Cards': 'تمام رپورٹ کارڈ',
    'Bulk individual report cards for every student in the class.':
        'کلاس کے ہر طالب علم کے انفرادی رپورٹ کارڈ ایک ساتھ۔',
    'Term Examination Documents': 'ٹرم امتحان کی دستاویزات',
    'Pick an exam, then download its tabulation sheet or open the exam hub.':
        'امتحان منتخب کریں، پھر اس کی ٹیبولیشن شیٹ ڈاؤن لوڈ کریں یا امتحان کا مرکز کھولیں۔',
    'No term examinations yet \u2014 create one from the Examinations page.':
        'ابھی کوئی ٹرم امتحان نہیں \u2014 امتحانات کے صفحے سے بنائیں۔',
    'Open Examinations': 'امتحانات کھولیں',
    'Merit / Position List': 'میرٹ / پوزیشن لسٹ',
    'Ranked list of students by total marks for the class.':
        'کلاس کے طلبہ کی کل نمبروں کے لحاظ سے درجہ بندی۔',
    'Broad Sheets': 'براڈ شیٹس',
    'Class-wide grades sheet with remarks column for printing.':
        'پوری کلاس کی گریڈ شیٹ، ریمارکس کے کالم کے ساتھ، پرنٹ کے لیے۔',
    'Student, Staff & Operational Exports': 'طلبہ، عملہ اور انتظامی ایکسپورٹس',
    'Student Enrolment Roster': 'طلبہ کا اندراج رجسٹر',
    'Active students with roll numbers, class, section and contacts.':
        'فعال طلبہ، رول نمبر، کلاس، سیکشن اور رابطہ نمبروں کے ساتھ۔',
    'Staff Directory': 'عملے کی ڈائریکٹری',
    'Active staff with designations, contacts and joining dates.':
        'فعال عملہ، عہدے، رابطہ نمبر اور شمولیت کی تاریخوں کے ساتھ۔',
    'Class Attendance (Daily)': 'کلاس کی حاضری (روزانہ)',
    "Attendance sheet for the selected class (today's register).":
        'منتخب کلاس کی حاضری شیٹ (آج کا رجسٹر)۔',
    'Staff Attendance': 'عملے کی حاضری',
    'Daily staff attendance register across all teachers.':
        'تمام اساتذہ کی روزانہ حاضری کا رجسٹر۔',
    'Monthly present/absent matrix for the selected class & period.':
        'منتخب کلاس اور مدت کے لیے ماہانہ حاضر/غیر حاضر میٹرکس۔',
    'Subject-Teacher Allocation': 'مضمون اور استاد کی تقسیم',
    'Matrix of every class \u00d7 subject with its assigned teacher.':
        'ہر کلاس \u00d7 مضمون کا میٹرکس، مقرر کردہ استاد کے ساتھ۔',
})
