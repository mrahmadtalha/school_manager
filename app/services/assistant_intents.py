"""Question catalogue for the offline admin assistant.

This file is *data only*.  To teach the assistant a new question, add a new
entry to ``INTENTS`` (and, for a data question, a handler with the same id in
``app/services/assistant.py``).

An intent has:

``id``        unique name (also the handler name: ``h_<id>``; how-to intents
              share the single ``howto`` handler).
``title``     short label shown in the help list.
``examples``  sample questions (shown as clickable suggestions).
``keywords``  ``{word: weight}``.  Every distinct keyword found in the question
              adds its weight to the intent's score.  Misspellings are matched
              fuzzily, so ``fess`` still finds ``fees``.
``phrases``   ``{"two words": weight}`` for multi-word hints.
``min_score`` the intent only wins when its score reaches this value.
``howto``     True for "how do I ...?" guides.  They only fire when the
              question contains a how-marker (kaise, how, tarika ...).

Both English and Roman-Urdu words (plus a few Urdu-script words) are listed.
"""

# Words that turn a question into a "how do I ...?" question.
HOW_MARKERS = {
    'kaise', 'kese', 'kaisay', 'kaisey', 'kasay', 'kaisy', 'how', 'tarika',
    'tareeqa', 'tarikay', 'steps', 'guide', 'kahan', 'kidhar', 'where',
    'procedure', 'karte', 'karen', 'karein', 'karun', 'karoon', 'krna',
    'karna', 'kese', 'banate', 'banana', 'lagana', 'lagayen', 'lagaye',
    'طریقہ', 'کیسے',
}

# Words that tell us the question is written in Roman Urdu / Urdu (reply
# language is chosen from this).
URDU_MARKERS = {
    'kitne', 'kitni', 'kitna', 'hain', 'hai', 'aaj', 'mein', 'main', 'ka',
    'ki', 'ke', 'ko', 'kya', 'kaise', 'kese', 'batao', 'bata', 'btao',
    'dikhao', 'nahi', 'nahin', 'hui', 'hua', 'huay', 'wala', 'wali', 'liye',
    'bachay', 'bache', 'bachon', 'talib', 'mahine', 'mahina', 'pichle',
    'kharcha', 'baqaya', 'wasooli', 'hazir', 'ghair', 'tankhwah', 'ustad',
    'kal', 'abhi', 'sab', 'koi', 'kis', 'kon', 'kaun', 'karte', 'karna',
    'chahiye', 'agar', 'tarika', 'madad', 'salam', 'assalam', 'shukriya',
}

STOPWORDS = {
    'hai', 'hain', 'ka', 'ki', 'ke', 'ko', 'me', 'mein', 'main', 'kya', 'is',
    'the', 'a', 'an', 'of', 'in', 'on', 'at', 'to', 'and', 'or', 'aur', 'ye',
    'yeh', 'wo', 'woh', 'please', 'plz', 'pls', 'batao', 'bata', 'btao',
    'dikhao', 'show', 'tell', 'me', 'give', 'list', 'are', 'you', 'can',
    'what', 'whats', 'who', 'which', 'when', 'how', 'many', 'much', 'for',
    'with', 'from', 'by', 'this', 'that', 'was', 'has', 'have', 'does', 'do',
    'did', 'kis', 'kon', 'kaun', 'kab', 'kitna', 'kitne', 'kitni', 'hui',
    'hua', 'huay', 'kar', 'karo', 'dena', 'dein', 'diya', 'di', 'liye', 'se',
    'tak', 'bhi', 'sirf', 'abhi', 'sab', 'saray', 'saare', 'koi', 'ek', 'wala',
    'wali', 'mera', 'meri', 'hamara', 'hamari', 'our', 'my', 'all', 'ab',
    'class', 'section', 'student', 'students', 'teacher', 'teachers',
}

# ---------------------------------------------------------------------------
# Data questions
# ---------------------------------------------------------------------------

_COUNT_WORDS = {
    'kitne': 1.2, 'kitna': 1.2, 'kitni': 1.0, 'total': 1.3, 'count': 1.2,
    'number': 1.0, 'strength': 1.5, 'tadad': 1.5, 'کتنے': 1.2, 'کتنی': 1.0,
}

INTENTS = [
    {
        'id': 'help',
        'title': 'Madad / Help',
        'examples': ['help', 'tum kya kar sakte ho?', 'what can you do?'],
        'keywords': {
            'hello': 3, 'hi': 3, 'hey': 3, 'salam': 3, 'salaam': 3,
            'assalam': 3, 'assalamualaikum': 3, 'aoa': 3, 'help': 3,
            'madad': 3, 'thanks': 3, 'thank': 3, 'shukriya': 3, 'shukria': 3,
            'commands': 3, 'مدد': 3, 'سلام': 3,
        },
        'phrases': {'kya kar sakte': 4, 'what can you': 4, 'kya puch': 4,
                    'kya pooch': 4, 'how are you': 3},
        'min_score': 3,
    },
    {
        'id': 'today_summary',
        'title': 'Aaj ka khulasa / Summary',
        'examples': ['aaj ka summary', 'school ka haal batao', 'overview'],
        'keywords': {
            'summary': 2, 'overview': 3, 'khulasa': 3, 'dashboard': 2,
            'haal': 2, 'status': 2, 'khulaasa': 3,
        },
        'phrases': {'aaj ka haal': 3, 'daily summary': 3, 'school ka haal': 3,
                    'all over': 2},
        'min_score': 2,
    },
    {
        'id': 'students_count',
        'title': 'Students ki tadad',
        'examples': ['kitne students hain?', 'class 5 mein kitne bachay hain?',
                     'kitne larkay aur larkiyan hain?'],
        'keywords': dict({
            'student': 1, 'students': 1, 'talib': 1, 'talaba': 1,
            'bachay': 1.2, 'bache': 1.2, 'bachon': 1.2, 'bachcha': 1.2,
            'children': 1, 'kids': 1, 'pupils': 1, 'larkay': 1, 'larke': 1,
            'ladkay': 1, 'ladke': 1, 'larkiyan': 1, 'ladkiyan': 1,
            'boys': 1, 'girls': 1, 'طلبہ': 1, 'بچے': 1.2,
        }, **_COUNT_WORDS),
        'phrases': {'how many': 2},
        'min_score': 2.2,
    },
    {
        'id': 'teachers_count',
        'title': 'Teachers ki tadad',
        'examples': ['kitne teachers hain?', 'total staff'],
        'keywords': dict({
            'teacher': 1, 'teachers': 1, 'ustad': 1, 'ustaad': 1,
            'asatza': 1, 'asatiza': 1, 'staff': 1, 'استاد': 1, 'اساتذہ': 1,
        }, **_COUNT_WORDS),
        'phrases': {'how many': 2},
        'min_score': 2.2,
    },
    {
        'id': 'class_strength',
        'title': 'Class-wise strength',
        'examples': ['class wise students', 'kitni classes hain?'],
        'keywords': {
            'classes': 2, 'sections': 1.5, 'wise': 1.5, 'classwise': 3,
            'strength': 1.5, 'kitni': 0.8, 'kitne': 0.8, 'list': 1,
            'class': 0.5,
        },
        'phrases': {'class wise': 3, 'class-wise': 3},
        'min_score': 2.8,
    },
    {
        'id': 'attendance',
        'title': 'Attendance (aaj / kal)',
        'examples': ['aaj kitne students absent hain?',
                     'class 5 ki attendance', 'aaj kaun se teachers absent hain?',
                     'kal kitne bachay late the?'],
        'keywords': {
            'absent': 3, 'absentees': 3, 'ghayab': 3, 'ghair': 1.5,
            'gair': 1.5, 'hazir': 3, 'hazri': 3, 'attendance': 3,
            'present': 3, 'late': 2.5, 'leave': 2.5, 'chutti': 2,
            'aaj': 0.5, 'today': 0.5, 'kal': 0.5, 'yesterday': 0.5,
            'حاضر': 3, 'غیر': 1.5, 'آج': 0.5,
        },
        'phrases': {},
        'min_score': 2.5,
    },
    {
        'id': 'fees_collected',
        'title': 'Fees collection',
        'examples': ['is mahine kitni fees collect hui?', 'aaj ki fee wasooli',
                     'pichle mahine ki fees collection'],
        'keywords': {
            'fee': 1.5, 'fees': 1.5, 'fess': 1.5, 'collected': 2.5, 'collection': 2.5,
            'collect': 2, 'wasool': 2.5, 'wasooli': 2.5, 'jama': 2,
            'received': 2, 'receive': 1.5, 'income': 1.5, 'aamdani': 2,
            'kamai': 1.5, 'revenue': 2, 'payments': 2, 'payment': 1.5,
            'mili': 1.5, 'mila': 1.5, 'فیس': 1.5, 'وصولی': 2.5,
        },
        'phrases': {},
        'min_score': 3,
    },
    {
        'id': 'fees_due',
        'title': 'Baqaya fees / Defaulters',
        'examples': ['defaulters kaun hain?', 'Ali Khan ki fees baqaya?',
                     'class 5 ki pending fees'],
        'keywords': {
            'defaulter': 3, 'defaulters': 3, 'baqaya': 2.5, 'baqiya': 2.5,
            'baqya': 2.5, 'bakaya': 2.5, 'baqi': 2.5, 'pending': 2,
            'outstanding': 3, 'dues': 3, 'due': 2, 'unpaid': 3,
            'remaining': 1.5, 'balance': 2, 'arrears': 3, 'fee': 1,
            'fees': 1, 'fess': 1, 'بقایا': 2.5, 'فیس': 1,
        },
        'phrases': {'fees nahi di': 3, 'fee nahi di': 3, 'nahi diya': 2,
                    'fees nahi': 2, 'fee nahi': 2},
        'min_score': 2.5,
    },
    {
        'id': 'expenses',
        'title': 'Kharcha / Expenses',
        'examples': ['is mahine ka kharcha', 'expenses this month',
                     'aaj kitna kharcha hua?'],
        'keywords': {
            'expense': 3, 'expenses': 3, 'kharcha': 3, 'kharch': 3,
            'kharche': 3, 'kharchay': 3, 'akhrajat': 3, 'spending': 3,
            'spent': 2.5, 'bills': 2, 'cost': 1.5, 'خرچ': 3, 'اخراجات': 3,
        },
        'phrases': {},
        'min_score': 2.5,
    },
    {
        'id': 'profit',
        'title': 'Munafa / Net position',
        'examples': ['is mahine ka profit', 'financial summary',
                     'income aur kharcha ka hisab'],
        'keywords': {
            'profit': 3, 'munafa': 3, 'nafa': 3, 'loss': 2.5, 'nuqsan': 2.5,
            'net': 1.5, 'financial': 2.5, 'finance': 2, 'maali': 2,
            'position': 2, 'hisab': 1.5, 'income': 1, 'cash': 1,
        },
        'phrases': {'financial summary': 4, 'net position': 4,
                    'income aur kharcha': 3},
        'min_score': 2.5,
    },
    {
        'id': 'salary',
        'title': 'Salary / Payroll',
        'examples': ['salary pending kitni hai?', 'is mahine ki payroll'],
        'keywords': {
            'salary': 2.5, 'salaries': 2.5, 'tankhwah': 2.5, 'tankhwa': 2.5,
            'tankha': 2.5, 'payroll': 3, 'wages': 2.5, 'pending': 1,
            'baqaya': 1, 'unpaid': 1, 'تنخواہ': 2.5,
        },
        'phrases': {},
        'min_score': 2.5,
    },
    {
        'id': 'student_info',
        'title': 'Student ki maloomat',
        'examples': ['Ali Khan ka phone number', 'Sara Ali ki details'],
        'keywords': {
            'phone': 2, 'contact': 2, 'number': 0.8, 'father': 2, 'walid': 2,
            'rabta': 2, 'roll': 2, 'info': 2, 'information': 2, 'detail': 2,
            'details': 2, 'address': 2, 'profile': 2, 'mobile': 2,
            'pata': 1.5, 'maloomat': 2,
        },
        'phrases': {},
        'min_score': 2.5,
    },
    # -----------------------------------------------------------------
    # How-to guides (only answered when the question has a how-marker)
    # -----------------------------------------------------------------
    {
        'id': 'howto_add_student',
        'howto': True,
        'title': 'Student add karna',
        'examples': ['student kaise add karte hain?'],
        'keywords': {
            'student': 1.5, 'students': 1.5, 'bacha': 1.5, 'bachay': 1.5,
            'add': 1.5, 'new': 1, 'naya': 1, 'nayi': 1, 'admission': 2,
            'dakhila': 2, 'dakhil': 2, 'enroll': 2, 'register': 1.5,
        },
        'phrases': {},
        'min_score': 3,
        'guide': {
            'title_en': 'Add a new student', 'title_ur': 'Naya student add karna',
            'steps_en': [
                'Open "Students" from the left menu.',
                'Click the Add Student button.',
                'Fill in name, father name, guardian phone, address and class (section is optional).',
                'Save. The roll number and fee setup are created automatically.',
            ],
            'steps_ur': [
                'Left menu se "Students" kholein.',
                'Add Student ka button dabayein.',
                'Naam, walid ka naam, guardian phone, address aur class bharein (section zaroori nahi).',
                'Save karein. Roll number aur fee setup khud ban jata hai.',
            ],
            'endpoint': 'main.students_list', 'link_label': 'Students',
        },
    },
    {
        'id': 'howto_import_students',
        'howto': True,
        'title': 'Excel se students import',
        'examples': ['students excel se import kaise karen?'],
        'keywords': {
            'import': 3, 'excel': 1.5, 'csv': 1.5, 'bulk': 2, 'upload': 1.5,
            'students': 1, 'student': 1, 'template': 1.5,
        },
        'phrases': {},
        'min_score': 3,
        'guide': {
            'title_en': 'Import students from Excel/CSV',
            'title_ur': 'Excel/CSV se students import karna',
            'steps_en': [
                'Open "Students" and download the Excel template (it is offered inside the Import Excel window).',
                'Fill one row per student and save the file.',
                'On the Students page click Import Excel and choose your file.',
                'Review the import result page; rows with problems are listed with the reason.',
            ],
            'steps_ur': [
                '"Students" kholein aur Excel template download karein (Import Excel wali window mein milta hai).',
                'Har student ki ek row bharein aur file save karein.',
                'Students page par Import Excel dabayein aur apni file chunein.',
                'Import result page dekhein; jin rows mein masla ho wo wajah ke saath dikhti hain.',
            ],
            'endpoint': 'main.students_list', 'link_label': 'Students',
        },
    },
    {
        'id': 'howto_add_teacher',
        'howto': True,
        'title': 'Teacher add karna',
        'examples': ['teacher kaise add karte hain?'],
        'keywords': {
            'teacher': 1.5, 'teachers': 1.5, 'ustad': 1.5, 'staff': 1,
            'add': 1.5, 'new': 1, 'naya': 1, 'nayi': 1, 'hire': 1.5,
        },
        'phrases': {},
        'min_score': 3,
        'guide': {
            'title_en': 'Add a teacher', 'title_ur': 'Teacher add karna',
            'steps_en': [
                'Open "Teachers" from the left menu.',
                'Click Add Teacher.',
                'Enter name, qualification, joining date and salary (monthly or hourly).',
                'Save. The teacher then appears in attendance and payroll.',
            ],
            'steps_ur': [
                'Left menu se "Teachers" kholein.',
                'Add Teacher dabayein.',
                'Naam, qualification, joining date aur salary (monthly ya hourly) likhein.',
                'Save karein. Teacher attendance aur payroll mein aa jata hai.',
            ],
            'endpoint': 'main.teachers_list', 'link_label': 'Teachers',
        },
    },
    {
        'id': 'howto_mark_attendance',
        'howto': True,
        'title': 'Attendance lagana',
        'examples': ['attendance kaise lagate hain?'],
        'keywords': {
            'attendance': 2.5, 'hazri': 2.5, 'mark': 1.5, 'lagana': 1.5,
            'lagani': 1.5, 'lagayen': 1.5, 'lagain': 1.5, 'lagaye': 1.5,
            'lagate': 1.5, 'lock': 1,
        },
        'phrases': {},
        'min_score': 3,
        'guide': {
            'title_en': 'Mark attendance', 'title_ur': 'Attendance lagana',
            'steps_en': [
                'Open "Daily Attendance".',
                'Pick the class and the date.',
                'Set Present / Absent / Late / Leave for each student and save.',
                'Teacher attendance is on its own page. Locked attendance cannot be edited.',
            ],
            'steps_ur': [
                '"Daily Attendance" kholein.',
                'Class aur date chunein.',
                'Har student ke liye Present / Absent / Late / Leave chunein aur save karein.',
                'Teachers ki attendance alag page par hoti hai. Lock hui attendance edit nahi hoti.',
            ],
            'endpoint': 'main.student_attendance', 'link_label': 'Daily Attendance',
        },
    },
    {
        'id': 'howto_collect_fee',
        'howto': True,
        'title': 'Fees jama karna',
        'examples': ['fees kaise jama karte hain?'],
        'keywords': {
            'fee': 1.5, 'fees': 1.5, 'jama': 2, 'collect': 2, 'receive': 1.5,
            'payment': 1.5, 'pay': 1, 'wasool': 2, 'voucher': 1.5,
            'receipt': 2,
        },
        'phrases': {},
        'min_score': 3,
        'guide': {
            'title_en': 'Collect a fee payment',
            'title_ur': 'Fees jama karna',
            'steps_en': [
                'Open "Fees Management".',
                'Find the student and click Collect Fee.',
                'Enter the amount, method and date, then save.',
                'A receipt is created; print it from the same page.',
            ],
            'steps_ur': [
                '"Fees Management" kholein.',
                'Student dhoondein aur Collect Fee dabayein.',
                'Raqam, tareeqa aur tareekh likhein, phir save karein.',
                'Receipt ban jati hai; usi page se print karein.',
            ],
            'endpoint': 'main.fees_list', 'link_label': 'Fees Management',
        },
    },
    {
        'id': 'howto_generate_fee',
        'howto': True,
        'title': 'Monthly fee charges banana',
        'examples': ['monthly fee charges kaise generate karte hain?'],
        'keywords': {
            'charge': 2, 'charges': 2, 'generate': 2, 'monthly': 1.5,
            'bill': 1.5, 'fee': 1, 'fees': 1, 'banana': 1,
        },
        'phrases': {},
        'min_score': 3,
        'guide': {
            'title_en': 'Generate monthly fee charges',
            'title_ur': 'Monthly fee charges banana',
            'steps_en': [
                'Open "Fees Management".',
                'Type the billing month (for example September 2026) and click "Generate monthly charges".',
                'Charges are created explicitly, so nothing is billed until you do this.',
                'If numbers look off, check the month on the Fee Reconciliation page.',
            ],
            'steps_ur': [
                '"Fees Management" kholein.',
                'Billing month likhein (maslan September 2026) aur "Generate monthly charges" dabayein.',
                'Charges aap ke kehne par hi bante hain, is se pehle kuch bill nahi hota.',
                'Agar figures ghalat lagein to Fee Reconciliation page par mahina check karein.',
            ],
            'endpoint': 'main.fees_list', 'link_label': 'Fees Management',
        },
    },
    {
        'id': 'howto_backup',
        'howto': True,
        'title': 'Backup / Restore',
        'examples': ['backup kaise lete hain?'],
        'keywords': {
            'backup': 3, 'backups': 3, 'restore': 3, 'bakup': 3, 'data': 0.5,
        },
        'phrases': {},
        'min_score': 3,
        'guide': {
            'title_en': 'Back up or restore data',
            'title_ur': 'Backup ya restore karna',
            'steps_en': [
                'Open "School Settings" and find the Backups card.',
                'Create a backup now, or download an existing one and keep a copy on a USB drive.',
                'Automatic backups also run daily while the app is open.',
                'To restore, use scripts/restore_db.py or ask your software provider.',
            ],
            'steps_ur': [
                '"School Settings" kholein aur Backups wala hissa dekhein.',
                'Abhi backup banayein, ya mojooda backup download karke USB mein copy rakhein.',
                'App khuli ho to automatic backup roz bhi khud ban jata hai.',
                'Restore ke liye scripts/restore_db.py istemal karein ya software provider se poochein.',
            ],
            'endpoint': 'main.school_settings', 'link_label': 'School Settings',
        },
    },
    {
        'id': 'howto_whatsapp',
        'howto': True,
        'title': 'WhatsApp setup',
        'examples': ['whatsapp qr kaise connect karen?'],
        'keywords': {
            'whatsapp': 3, 'qr': 2.5, 'pair': 2, 'message': 1, 'messages': 1,
            'bhejna': 1.5, 'send': 1.5, 'connect': 1.5,
        },
        'phrases': {},
        'min_score': 3,
        'guide': {
            'title_en': 'Connect WhatsApp', 'title_ur': 'WhatsApp connect karna',
            'steps_en': [
                'Open "WhatsApp Automation".',
                'Scan the QR code with WhatsApp: Linked devices > Link a device.',
                'Choose the delivery mode (auto, approval or delayed).',
                'Queued messages are sent from that page.',
            ],
            'steps_ur': [
                '"WhatsApp Automation" kholein.',
                'WhatsApp mein Linked devices > Link a device se QR scan karein.',
                'Delivery mode chunein (auto, approval ya delayed).',
                'Queue ke messages isi page se bheje jate hain.',
            ],
            'endpoint': 'main.automation_panel', 'link_label': 'WhatsApp Automation',
        },
    },
    {
        'id': 'howto_license',
        'howto': True,
        'title': 'License activate karna',
        'examples': ['license kaise activate karte hain?'],
        'keywords': {
            'license': 3, 'licence': 3, 'activate': 2.5, 'activation': 2.5,
            'key': 1.5, 'expire': 2, 'expired': 2, 'renew': 2,
        },
        'phrases': {},
        'min_score': 3,
        'guide': {
            'title_en': 'Activate or renew the license',
            'title_ur': 'License activate ya renew karna',
            'steps_en': [
                'Open "License" from the left menu.',
                'Send your machine code to your software provider.',
                'Paste the license key you receive and activate.',
                'Expired licenses keep read-only access, so your data stays visible.',
            ],
            'steps_ur': [
                'Left menu se "License" kholein.',
                'Apna machine code software provider ko bhejein.',
                'Mila hua license key paste karke activate karein.',
                'License expire hone par bhi data sirf parha ja sakta hai, ghayab nahi hota.',
            ],
            'endpoint': 'main.license_page', 'link_label': 'License',
        },
    },
    {
        'id': 'howto_report_card',
        'howto': True,
        'title': 'Result card / Reports',
        'examples': ['result card kaise nikalte hain?'],
        'keywords': {
            'report': 2, 'card': 1.5, 'result': 2, 'results': 2, 'marks': 1.5,
            'natija': 2, 'tabulation': 2, 'transcript': 2,
        },
        'phrases': {},
        'min_score': 3,
        'guide': {
            'title_en': 'Print result cards and reports',
            'title_ur': 'Result card aur reports nikalna',
            'steps_en': [
                'Enter marks in "Testing & Marks Hub" first.',
                'Open "Class Results & Reports" and choose the class.',
                'Download the class result PDF or a single student report card.',
                'More exports are on "Analytics & Exports".',
            ],
            'steps_ur': [
                'Pehle "Testing & Marks Hub" mein marks darj karein.',
                '"Class Results & Reports" kholein aur class chunein.',
                'Class result ka PDF ya kisi ek student ka report card download karein.',
                'Mazeed exports "Analytics & Exports" mein hain.',
            ],
            'endpoint': 'main.class_results_matrix', 'link_label': 'Class Results',
        },
    },
    {
        'id': 'howto_id_card',
        'howto': True,
        'title': 'ID card / Certificate',
        'examples': ['id card kaise banate hain?'],
        'keywords': {
            'id': 2, 'card': 1.5, 'cards': 1.5, 'certificate': 2.5,
            'certificates': 2.5,
        },
        'phrases': {},
        'min_score': 3,
        'guide': {
            'title_en': 'Make ID cards and certificates',
            'title_ur': 'ID card aur certificate banana',
            'steps_en': [
                'Open "ID Cards & Certificates".',
                'Choose students or teachers, and a class if needed.',
                'Download the PDF and print.',
            ],
            'steps_ur': [
                '"ID Cards & Certificates" kholein.',
                'Students ya teachers chunein (zaroorat ho to class bhi).',
                'PDF download karke print karein.',
            ],
            'endpoint': 'main.documents_hub', 'link_label': 'ID Cards & Certificates',
        },
    },
    {
        'id': 'howto_timetable',
        'howto': True,
        'title': 'Timetable',
        'examples': ['timetable kaise banate hain?'],
        'keywords': {
            'timetable': 3, 'schedule': 2, 'periods': 1.5, 'period': 1.5,
        },
        'phrases': {},
        'min_score': 3,
        'guide': {
            'title_en': 'Create a timetable', 'title_ur': 'Timetable banana',
            'steps_en': [
                'Set periods per day in School Settings > Academic > Timetable Periods.',
                'Make sure teachers are assigned to subjects in "Classes & Subjects".',
                'Open "Timetables", tick the classes and use Generate.',
                'Edit any cell by hand and save.',
            ],
            'steps_ur': [
                'School Settings > Academic > Timetable Periods mein roz ke periods set karein.',
                '"Classes & Subjects" mein teachers ko subjects par lagayein.',
                '"Timetables" kholein, classes tick karein aur Generate dabayein.',
                'Kisi bhi cell ko hath se badal kar save karein.',
            ],
            'endpoint': 'main.timetables_hub', 'link_label': 'Timetables',
        },
    },
    {
        'id': 'howto_users',
        'howto': True,
        'title': 'Users / Password',
        'examples': ['naya user kaise banate hain?', 'password kaise badlen?'],
        'keywords': {
            'user': 2, 'users': 2, 'password': 2.5, 'role': 2, 'roles': 2,
            'login': 2, 'account': 1.5, 'badalna': 1.5, 'change': 1,
        },
        'phrases': {},
        'min_score': 3,
        'guide': {
            'title_en': 'Manage users and passwords',
            'title_ur': 'Users aur password sambhalna',
            'steps_en': [
                'Open "Users & Roles" to create a user and choose the role.',
                'Roles: Administrator, Teacher, Parent, Owner, Accountant.',
                'Use the password option on a user to reset it.',
                'Your own password: "Change Password" in the left menu.',
            ],
            'steps_ur': [
                '"Users & Roles" kholein, user banayein aur role chunein.',
                'Roles: Administrator, Teacher, Parent, Owner, Accountant.',
                'Password reset ke liye user ke password option ko istemal karein.',
                'Apna password: left menu mein "Change Password".',
            ],
            'endpoint': 'main.users_list', 'link_label': 'Users & Roles',
        },
    },
    {
        'id': 'howto_promote',
        'howto': True,
        'title': 'Promotion (agli class)',
        'examples': ['students ko agli class mein kaise promote karen?'],
        'keywords': {
            'promote': 3, 'promotion': 3, 'promotions': 3, 'agli': 1.5,
            'next': 1, 'upgrade': 2,
        },
        'phrases': {},
        'min_score': 3,
        'guide': {
            'title_en': 'Promote students', 'title_ur': 'Students ko promote karna',
            'steps_en': [
                'Open the Promotions page.',
                'Choose the class to promote.',
                'Review the list and apply. Each move is kept in the student history.',
            ],
            'steps_ur': [
                'Promotions page kholein.',
                'Jis class ko promote karna hai wo chunein.',
                'List dekh kar apply karein. Har tabdeeli student ki history mein mehfooz rehti hai.',
            ],
            'endpoint': 'main.promotions_page', 'link_label': 'Promotions',
        },
    },
]

INTENTS_BY_ID = {intent['id']: intent for intent in INTENTS}

# Questions shown when the assistant is opened or does not understand.
STARTER_QUESTIONS = [
    'aaj ka summary',
    'aaj kitne students absent hain?',
    'is mahine kitni fees collect hui?',
    'defaulters kaun hain?',
    'is mahine ka kharcha',
    'salary pending kitni hai?',
    'kitne students hain?',
    'attendance kaise lagate hain?',
]
