"""More Urdu phrases: reports and exports."""

from .part01 import UR


# --- Forgot username / password page, redesigned (Oct 2026) ---
UR.update({
    'Forgot username or password?': 'صارف نام یا پاس ورڈ بھول گئے؟',
    "Don't worry. We will help you get back in.": 'فکر نہ کریں۔ ہم آپ کو دوبارہ اندر آنے میں مدد دیں گے۔',
    'Your vendor will help you in three easy steps.': 'آپ کا وینڈر تین آسان مراحل میں آپ کی مدد کرے گا۔',
    'Last step: choose the account and type a new password.': 'آخری مرحلہ: اکاؤنٹ چنیں اور نیا پاس ورڈ لکھیں۔',
    'Send your request code to your vendor': 'اپنا ریکویسٹ کوڈ وینڈر کو بھیجیں',
    'WhatsApp or SMS is fine.': 'واٹس ایپ یا ایس ایم ایس سے بھیج سکتے ہیں۔',
    'Wait for your reset token': 'ری سیٹ ٹوکن کا انتظار کریں',
    'Your vendor confirms it is really you, then sends the token back.':
        'وینڈر تصدیق کرتا ہے کہ یہ واقعی آپ ہیں، پھر ٹوکن واپس بھیجتا ہے۔',
    'Paste the token in the box below': 'ٹوکن نیچے والے خانے میں پیسٹ کریں',
    'Then press the green button.': 'پھر سبز بٹن دبائیں۔',
    'Your request code': 'آپ کا ریکویسٹ کوڈ',
    'Copy code': 'کوڈ کاپی کریں',
    'Copied!': 'کاپی ہو گیا!',
    'Send on WhatsApp': 'واٹس ایپ پر بھیجیں',
    'Need a new request code?': 'نیا ریکویسٹ کوڈ چاہیے؟',
    'Only do this if your vendor asks. The old code stops working.':
        'یہ صرف تب کریں جب وینڈر کہے۔ پرانا کوڈ کام کرنا بند کر دے گا۔',
    'Generate a new request code': 'نیا ریکویسٹ کوڈ بنائیں',
    'Reset token from your vendor': 'وینڈر کی طرف سے ری سیٹ ٹوکن',
    'Check token and continue': 'ٹوکن جانچیں اور آگے بڑھیں',
    'Checking…': 'جانچ ہو رہی ہے…',
    'Back to sign in': 'لاگ ان پر واپس جائیں',
    'Administrator account': 'ایڈمن اکاؤنٹ',
    'This also shows you your username.': 'اس سے آپ کا صارف نام بھی نظر آتا ہے۔',
    'At least 8 characters, with a letter and a number.': 'کم از کم 8 حروف، جن میں ایک حرف اور ایک ہندسہ ہو۔',
    'Set new password': 'نیا پاس ورڈ لگائیں',
    'Saving…': 'محفوظ ہو رہا ہے…',
    'Type a new password': 'نیا پاس ورڈ لکھیں',
    'Type the same password again': 'وہی پاس ورڈ دوبارہ لکھیں',
})


UR.update({
    'Passwords do not match.': 'پاس ورڈ آپس میں نہیں ملتے۔',
    'Choose which administrator account to recover.': 'چنیں کون سا ایڈمن اکاؤنٹ بحال کرنا ہے۔',
    'Enter the reset token from your vendor first.': 'پہلے وینڈر کا دیا ہوا ری سیٹ ٹوکن لکھیں۔',
    'A new request code was generated. Send the NEW code to your vendor.': 'نیا ریکویسٹ کوڈ بن گیا ہے۔ وینڈر کو نیا کوڈ بھیجیں۔',
})


# --- Users & Roles page (redesign) ---
UR.update({
    'Users & Roles': 'صارفین اور اختیارات',
    'Give your staff and parents their own login, and choose what each person can see.':
        'اپنے عملے اور والدین کو الگ لاگ ان دیں، اور طے کریں کہ ہر شخص کیا دیکھ سکتا ہے۔',
    'Activity Log': 'سرگرمی کا ریکارڈ', 'Add User': 'نیا صارف شامل کریں',
    'Logins in all': 'کل لاگ ان', 'Login in all': 'کل لاگ ان', 'Can sign in': 'لاگ ان کر سکتے ہیں',
    'switched off': 'بند', 'Find by name or username…': 'نام یا صارف نام سے تلاش کریں…',
    '— All roles —': '— تمام کردار —', 'Switched off': 'بند', 'Person': 'شخص', 'Role': 'کردار',
    'Connected to': 'منسلک', 'Can sign in?': 'لاگ ان کر سکتا ہے؟', 'Last signed in': 'آخری لاگ ان',
    'Never signed in': 'کبھی لاگ ان نہیں ہوا', 'No child linked yet': 'ابھی کوئی بچہ منسلک نہیں',
    'You': 'آپ', 'Yes': 'جی ہاں', 'Tip: click a row to edit that person': 'مشورہ: ترمیم کے لیے شخص کی قطار پر کلک کریں',
    'No one matches your search.': 'آپ کی تلاش سے کوئی میل نہیں کھاتا۔', 'Clear filters': 'فلٹر ہٹائیں',
    'What can each role do?': 'ہر کردار کیا کر سکتا ہے؟',
    'Full control: every page, all settings, and creating other users.':
        'مکمل اختیار: تمام صفحات، تمام ترتیبات، اور دوسرے صارفین بنانا۔',
    'Daily class work: attendance, marks, class tests and exams.':
        'روزانہ کلاس کا کام: حاضری، نمبر، کلاس ٹیسٹ اور امتحانات۔',
    'Sees only their own child: attendance, fees and results.':
        'صرف اپنے بچے کو دیکھتا ہے: حاضری، فیس اور رزلٹ۔',
    'Principal / owner: read-only overview of the whole school.':
        'پرنسپل / مالک: پورے اسکول کا صرف دیکھنے والا خلاصہ۔',
    'Money matters: fees, expenses, salaries and financial reports.':
        'مالی امور: فیس، اخراجات، تنخواہیں اور مالی رپورٹس۔',
    'Gate phone app only: scans student QR cards at the gate.':
        'صرف گیٹ کی فون ایپ: گیٹ پر طلبہ کے کیو آر کارڈ اسکین کرتا ہے۔',
    'Not in your plan': 'آپ کے پلان میں شامل نہیں', 'Recent activity': 'حالیہ سرگرمی',
    'See everything': 'سب دیکھیں', 'Nothing yet. Changes to logins will show up here.':
        'ابھی کچھ نہیں۔ لاگ ان میں تبدیلیاں یہاں نظر آئیں گی۔',
    'Add a new user': 'نیا صارف شامل کریں',
    'Fill in the details. The person signs in with the username and password you set.':
        'تفصیل بھریں۔ شخص آپ کے دیے ہوئے صارف نام اور پاس ورڈ سے لاگ ان کرے گا۔',
    'Full name': 'پورا نام', 'What will this person do?': 'یہ شخص کیا کام کرے گا؟',
    'What they type to sign in. No spaces is easiest.': 'لاگ ان کے لیے جو وہ لکھیں گے۔ خالی جگہ کے بغیر بہتر ہے۔',
    'At least 8 characters with letters and numbers. Write it down and tell the person.':
        'کم از کم 8 حروف، حروف اور ہندسوں کے ساتھ۔ اسے لکھ لیں اور شخص کو بتا دیں۔',
    'Suggest': 'تجویز', 'Which teacher is this?': 'یہ کون سا استاد ہے؟', '(optional)': '(اختیاری)',
    '— Not linked to a staff record —': '— عملے کے ریکارڈ سے منسلک نہیں —',
    "Linking shows this login on the teacher's profile and reports.":
        'منسلک کرنے سے یہ لاگ ان استاد کی پروفائل اور رپورٹس میں نظر آئے گا۔',
    'Which children does this parent have?': 'اس والد/والدہ کے کون سے بچے ہیں؟',
    'Tick every child. A parent sees only the children ticked here.':
        'ہر بچے پر نشان لگائیں۔ والدین صرف یہاں نشان زد بچوں کو دیکھیں گے۔',
    'Please tick at least one child for a parent login.': 'والدین کے لاگ ان کے لیے کم از کم ایک بچے پر نشان لگائیں۔',
    'Please tick at least one child.': 'کم از کم ایک بچے پر نشان لگائیں۔',
    'Type a name or roll number…': 'نام یا رول نمبر لکھیں…',
    'No student matches your search.': 'کوئی طالب علم نہیں ملا۔',
    'Create User': 'صارف بنائیں', 'Edit': 'ترمیم',
    'Change the name or the role. The username and password stay the same.':
        'نام یا کردار بدلیں۔ صارف نام اور پاس ورڈ وہی رہیں گے۔',
    'You cannot change your own role. This keeps you from locking yourself out.':
        'آپ اپنا کردار نہیں بدل سکتے۔ اس سے آپ خود لاک ہونے سے بچتے ہیں۔',
    'New password for': 'نیا پاس ورڈ برائے', 'The old password stops working right away.':
        'پرانا پاس ورڈ فوراً کام کرنا بند کر دے گا۔',
    'New password': 'نیا پاس ورڈ', 'Save Password': 'پاس ورڈ محفوظ کریں',
    'Children of': 'بچے:', 'Tick every child this parent should see.':
        'ہر اس بچے پر نشان لگائیں جو اس والد/والدہ کو نظر آنا چاہیے۔',
    'Save Children': 'بچے محفوظ کریں', 'Cancel': 'منسوخ کریں', 'Save': 'محفوظ کریں',
    'Created': 'بنایا گیا', 'Signed in': 'لاگ ان ہوا', 'Wrong password': 'غلط پاس ورڈ',
    'Changed': 'تبدیل', 'Account change': 'اکاؤنٹ میں تبدیلی',
})
