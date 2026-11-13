"""More Urdu phrases (page headers, buttons, form labels)."""

from .part01 import UR


UR.update({
    # phase 2: dashboard, finance pages, student form hints
    'Category': 'زمرہ', 'Change': 'تبدیلی', 'Alerts': 'انتباہات', 'Compare': 'موازنہ کریں',
    'Compare periods': 'مدتوں کا موازنہ', 'Compare selected': 'منتخب کا موازنہ', 'Custom': 'اپنی مرضی',
    'Difference': 'فرق', 'Entries': 'اندراجات', 'Metric': 'پیمائش', 'Net': 'خالص', 'Next month': 'اگلا مہینہ',
    'Previous': 'پچھلا', 'Previous month': 'پچھلا مہینہ', 'Quick comparisons': 'فوری موازنے',
    'Recommendations': 'سفارشات', 'Teacher': 'استاد', 'Payslip': 'تنخواہ کی پرچی', 'Payslip PDF': 'تنخواہ کی پرچی (پی ڈی ایف)',
    'Read-only': 'صرف دیکھنے کے لیے', 'Full': 'مکمل', 'Half': 'آدھا', 'Last 12 months': 'پچھلے 12 مہینے',
    'Last 3 months': 'پچھلے 3 مہینے', 'Last 6 months': 'پچھلے 6 مہینے', 'Last session': 'پچھلا سیشن',
    'Last year': 'پچھلا سال', 'This year': 'اس سال', 'This session (Apr–Mar)': 'اس سیشن (اپریل–مارچ)',
    'This month vs last month': 'اس مہینے کا پچھلے مہینے سے موازنہ',
    'This month vs same month last year': 'اس مہینے کا پچھلے سال کے اسی مہینے سے موازنہ',
    'Clear comparison': 'موازنہ صاف کریں', 'Choose months…': 'مہینے منتخب کریں…',
    'Or tick any months (then Apply)': 'یا کوئی بھی مہینے منتخب کریں (پھر لاگو کریں)',
    'Pick two or more months, whole years or sessions to see them side by side.':
        'دو یا زیادہ مہینے، پورے سال یا سیشن منتخب کریں تاکہ ساتھ ساتھ دیکھ سکیں۔',
    'Pick a date range to compare it with the preceding range of equal length.':
        'تاریخوں کی حد منتخب کریں تاکہ اس کا پچھلی برابر مدت سے موازنہ ہو۔',
    'Custom range vs preceding period': 'منتخب مدت بمقابلہ پچھلی مدت', 'Side-by-side comparison': 'ساتھ ساتھ موازنہ',
    'Fee Collection Trend': 'فیس وصولی کا رجحان', 'Outstanding Fees Trend': 'باقی فیس کا رجحان',
    'Cash In vs Cash Out — last 12 months': 'آمد بمقابلہ اخراج — پچھلے 12 مہینے',
    'Fee Collections': 'فیس وصولیاں', 'Monthly fees': 'ماہانہ فیس', 'Outstanding Dues': 'باقی واجبات',
    'Staff Payroll': 'عملے کی تنخواہیں', 'Total (salaries excluded)': 'کل (تنخواہیں شامل نہیں)',
    'Arrears recovery': 'پرانے بقایا کی وصولی', 'Salary burden': 'تنخواہوں کا بوجھ',
    'Sales revenue': 'فروخت کی آمدنی', 'Stock purchases': 'اسٹاک کی خریداری', 'Net Position change': 'خالص پوزیشن میں تبدیلی',
    'Executive overview': 'ایگزیکٹو جائزہ', "Principal's Dashboard": 'پرنسپل ڈیش بورڈ',
    'Executive Summary PDF': 'ایگزیکٹو خلاصہ (پی ڈی ایف)', 'Class Performance Snapshot': 'کلاس کارکردگی کی جھلک',
    'Class Performance (Average %)': 'کلاس کی کارکردگی (اوسط %)', 'Average Class Performance': 'کلاس کی اوسط کارکردگی',
    'Average %': 'اوسط %', 'Financial Health (Collected vs Dues)': 'مالی صحت (وصول بمقابلہ واجب)',
    'Money that actually moved': 'جو رقم حقیقت میں آئی یا گئی', 'Amounts owed or expected, not money movement': 'واجب یا متوقع رقم، نقد کی نقل و حرکت نہیں',
    'Cash In minus Cash Out — actual money movement': 'آمد منفی اخراج — اصل نقد کی نقل و حرکت',
    'cost of items actually sold': 'فروخت شدہ اشیا کی اصل لاگت',
    'expenses other than salaries (part of Cash Out)': 'تنخواہوں کے علاوہ اخراجات (اخراج کا حصہ)',
    'all fees still owed by students, school-wide · not money movement': 'طلبہ کے ذمے تمام باقی فیس، پورے اسکول کی · نقد کی نقل و حرکت نہیں',
    'salaries still owed to staff, including the running month · not part of Cash Out or Net Position':
        'عملے کی باقی تنخواہیں، موجودہ مہینے سمیت · اخراج یا خالص پوزیشن کا حصہ نہیں',
    'revenue-based estimate · Net Cash Position above stays the real-money figure':
        'آمدنی پر مبنی اندازہ · اوپر کی خالص نقد پوزیشن ہی اصل رقم ہے',
    'Revenue minus Salaries, Operating Expenses and Cost of Goods Sold — an operating estimate, not money movement':
        'آمدنی منفی تنخواہیں، آپریٹنگ اخراجات اور فروخت شدہ مال کی لاگت — اندازہ ہے، نقد کی نقل و حرکت نہیں',
    'An estimate of monthly fees no longer being billed — not a loss claim.': 'ان ماہانہ فیسوں کا اندازہ جو اب نہیں لی جا رہیں — نقصان کا دعویٰ نہیں۔',
    'Students who left — estimated monthly revenue impact': 'چھوڑنے والے طلبہ — ماہانہ آمدنی پر اندازاً اثر',
    'Monthly fee collection against payroll and expenses, with period comparison.': 'ماہانہ فیس وصولی بمقابلہ تنخواہیں اور اخراجات، مدتوں کے موازنے کے ساتھ۔',
    'Estimated monthly revenue impact:': 'ماہانہ آمدنی پر اندازاً اثر:', 'View their dues': 'ان کے واجبات دیکھیں',
    'open inventory': 'اسٹاک کھولیں', 'record other income': 'دیگر آمدنی درج کریں', 'new this month': 'اس مہینے نیا',
    'unchanged': 'کوئی تبدیلی نہیں', 'of which admission fees:': 'جس میں داخلہ فیس:',
    'No upcoming birthdays in the coming weeks.': 'آنے والے ہفتوں میں کوئی سالگرہ نہیں۔',
    'Tip: add dates of birth on student and teacher profiles to see upcoming birthdays here.':
        'مشورہ: طلبہ اور اساتذہ کی پروفائل میں تاریخ پیدائش لکھیں تاکہ سالگرہ یہاں نظر آئے۔',
    'No expenses logged this month.': 'اس مہینے کوئی خرچ درج نہیں۔', 'No expenses recorded in these months.': 'ان مہینوں میں کوئی خرچ درج نہیں۔',
    'No classes yet.': 'ابھی کوئی کلاس نہیں۔', 'No students yet.': 'ابھی کوئی طالب علم نہیں۔',
    'Financial data unavailable.': 'مالی ڈیٹا دستیاب نہیں۔', 'Fee data unavailable.': 'فیس کا ڈیٹا دستیاب نہیں۔',
    'Expense data unavailable.': 'اخراجات کا ڈیٹا دستیاب نہیں۔', 'Set on student record.': 'طالب علم کے ریکارڈ میں مقرر ہے۔',
    'Street / locality': 'گلی / علاقہ', 'Net Salary (Rs.)': 'خالص تنخواہ (روپے)', 'New Status': 'نئی حیثیت',
    'Read-only view for the Principal / Owner — no editing, deleting, or settings access from this account.':
        'پرنسپل / مالک کے لیے صرف دیکھنے کا منظر — اس اکاؤنٹ سے ترمیم، حذف یا ترتیبات کی اجازت نہیں۔',
    # student form hints
    'Filled from the class fee; you can change it.': 'کلاس کی فیس سے بھرا گیا؛ آپ بدل سکتے ہیں۔',
    'Filled from the class; you can change it. 0 = no books.': 'کلاس سے بھرا گیا؛ آپ بدل سکتے ہیں۔ 0 = کتابیں نہیں۔',
    'Filled in automatically. You can change it, but each number can only be used once.':
        'خود بھرا گیا۔ آپ بدل سکتے ہیں، لیکن ہر نمبر صرف ایک بار استعمال ہو سکتا ہے۔',
    'Final amount after any concession.': 'رعایت کے بعد حتمی رقم۔', 'Given automatically when you save.': 'محفوظ کرنے پر خود مل جائے گا۔',
    'Less than the total? The rest stays pending and is received later; one receipt shows everything.':
        'کل سے کم دیے؟ باقی رقم بعد میں وصول ہوگی؛ ایک ہی رسید میں سب کچھ دکھایا جاتا ہے۔',
    'Received now (record the money and print a receipt)': 'ابھی رقم وصول ہوئی (رقم درج کریں اور رسید پرنٹ کریں)',
    'Also record “Admission Fee Paid” as income (numbered receipts are created)': 'ادا شدہ داخلہ فیس کو آمدنی کے طور پر بھی درج کریں (نمبر والی رسیدیں بنتی ہیں)',
    'Used for every class that does not have its own fee below.': 'ہر اس کلاس کے لیے جس کی نیچے اپنی فیس نہیں۔',
    'No monthly fee set. Enter it here — it will be saved to the student record.': 'ماہانہ فیس مقرر نہیں۔ یہاں لکھیں — طالب علم کے ریکارڈ میں محفوظ ہو جائے گی۔',
    'e.g. 5000 (leave empty for none)': 'مثلاً 5000 (نہیں ہے تو خالی چھوڑیں)',
    'e.g. Cash / Bank Transfer / Cheque': 'مثلاً نقد / بینک ٹرانسفر / چیک',
    'e.g. Family moved to another city': 'مثلاً خاندان دوسرے شہر چلا گیا',
    'e.g. sibling of a current student': 'مثلاً موجودہ طالب علم کا بہن بھائی',
    'e.g. SLIP-20261002-0001': 'مثلاً SLIP-20261002-0001',
    'The student will move to the Archive Bin with this status and can be restored later.': 'طالب علم اس حیثیت کے ساتھ آرکائیو میں چلا جائے گا اور بعد میں بحال ہو سکتا ہے۔',
    'Confirm shift & save': 'منتقلی کی تصدیق کریں اور محفوظ کریں',
    'No other student needs to move; the record can be saved directly.': 'کسی اور طالب علم کو منتقل کرنے کی ضرورت نہیں؛ ریکارڈ سیدھا محفوظ ہو سکتا ہے۔',
    'No former students with a monthly fee.': 'ماہانہ فیس والا کوئی سابق طالب علم نہیں۔',
    'No student fee data available for this class.': 'اس کلاس کے طلبہ کی فیس کا ڈیٹا دستیاب نہیں۔',
})
