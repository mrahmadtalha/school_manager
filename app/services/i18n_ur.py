# -*- coding: utf-8 -*-
"""Urdu wording for the interface (English text -> Urdu).

Keys are the exact English text as it appears on screen (whitespace collapsed).
Words follow everyday school usage in Pakistan: داخلہ فیس، رول نمبر، کلاس، سیکشن،
حاضری، ماہانہ فیس، کتابیں، یونیفارم، رسید، رزلٹ، باقی، ادا شدہ.

Add a line here to translate more text; nothing else needs to change.
"""
import re

UR = {
    # --- common words / buttons ---
    'Class': 'کلاس', 'Classes': 'کلاسز', 'Status': 'حیثیت', 'Student': 'طالب علم',
    'Students': 'طلبہ', 'Cancel': 'منسوخ کریں', 'Date': 'تاریخ', '(optional)': '(اختیاری)',
    'Absent': 'غیر حاضر', 'Actions': 'عمل', 'Edit': 'ترمیم', 'Excel': 'ایکسل',
    'Father Name': 'والد کا نام', 'Fees': 'فیس', 'Late': 'تاخیر', 'Leave': 'رخصت',
    'Present': 'حاضر', 'Roll No': 'رول نمبر', 'Section': 'سیکشن', 'Sections': 'سیکشنز',
    'Student Name': 'طالب علم کا نام', 'Active': 'فعال', 'All classes': 'تمام کلاسز',
    'All Classes': 'تمام کلاسز', 'Amount': 'رقم', 'Archived': 'محفوظ شدہ',
    'Balance': 'باقی رقم', 'Close': 'بند کریں', 'Concession': 'رعایت', 'CSV': 'سی ایس وی',
    'Filter': 'فلٹر', 'Logo': 'لوگو', 'Method': 'طریقہ', 'Month': 'مہینہ', 'None': 'کوئی نہیں',
    'Paid': 'ادا شدہ', 'PDF': 'پی ڈی ایف', 'Reset': 'ری سیٹ', 'Save': 'محفوظ کریں',
    'Type': 'قسم', 'Roll No:': 'رول نمبر:', 'Class:': 'کلاس:', 'Absent:': 'غیر حاضر:',
    'Address': 'پتہ', 'Address:': 'پتہ:', 'All': 'سب', 'Archive': 'آرکائیو',
    'Back': 'واپس', 'Total': 'کل', 'Export': 'ایکسپورٹ', 'Import': 'امپورٹ',
    'Search': 'تلاش', 'Reason': 'وجہ', 'Reference': 'حوالہ', 'Note': 'نوٹ',
    'Gender': 'جنس', 'Male': 'مرد', 'Female': 'خاتون', 'Name:': 'نام:',
    'Phone:': 'فون:', 'Date:': 'تاریخ:', 'Month:': 'مہینہ:', 'Father:': 'والد:',
    'Father Name:': 'والد کا نام:', 'Present:': 'حاضر:', 'Late:': 'تاخیر:', 'Leave:': 'رخصت:',
    'Restore': 'بحال کریں', 'Void': 'منسوخ', 'Voided': 'منسوخ شدہ', 'void': 'منسوخ',
    'Delete': 'حذف کریں', 'Add': 'شامل کریں', 'Apply': 'لاگو کریں', 'Confirm': 'تصدیق کریں',
    'Create': 'بنائیں', 'Preview': 'پیش نظارہ', 'Show': 'دکھائیں', 'Hide': 'چھپائیں',
    'Open': 'کھولیں', 'Open →': 'کھولیں ←', 'View All': 'سب دیکھیں', 'View →': 'دیکھیں ←',
    'OK': 'ٹھیک ہے', 'Yes, Archive': 'جی ہاں، آرکائیو کریں', 'Other': 'دیگر',
    'Online': 'آن لائن', 'Cash': 'نقد', 'Bank': 'بینک', 'Card': 'کارڈ', 'Check': 'چیک',
    'Today': 'آج', 'This month': 'اس مہینے', 'Everyone': 'سب', 'Totals': 'میزان',
    'Item': 'آئٹم', 'Qty': 'تعداد', 'Price': 'قیمت', 'Rate': 'ریٹ', 'Value': 'قدر',
    'Period': 'مدت', 'Position': 'پوزیشن', 'Session': 'سیشن', 'Subject': 'مضمون',
    'Subjects': 'مضامین', 'Test': 'ٹیسٹ', 'Results': 'رزلٹ', 'Grade': 'گریڈ',
    'From': 'سے', 'To': 'تک', 'Sr': 'نمبر شمار', 'Roll': 'رول', 'Guardian': 'سرپرست',
    'Not set': 'مقرر نہیں', 'Not Set': 'مقرر نہیں', 'Pending': 'باقی', 'pending': 'باقی',
    'Partial': 'جزوی', 'Unpaid': 'غیر ادا شدہ', 'Due': 'واجب', 'Dues': 'واجبات',
    'Overview': 'جائزہ', 'History': 'ریکارڈ', 'Register': 'رجسٹر', 'Receipt': 'رسید',
    'Receipts': 'رسیدیں', 'Ledger': 'کھاتہ', 'Required field': 'ضروری خانہ',
    'Login': 'لاگ ان', 'Logout': 'لاگ آؤٹ', 'Password': 'پاس ورڈ', 'Username': 'صارف نام',
    'Sign In': 'لاگ ان کریں', 'Sign in to continue': 'جاری رکھنے کے لیے لاگ ان کریں',
    'Forgot username / password?': 'صارف نام یا پاس ورڈ بھول گئے؟',
    'Change Password': 'پاس ورڈ تبدیل کریں', 'Current Password': 'موجودہ پاس ورڈ',
    'New Password': 'نیا پاس ورڈ', 'Confirm New Password': 'نئے پاس ورڈ کی تصدیق',
    'Update Password': 'پاس ورڈ اپ ڈیٹ کریں', 'Enter username': 'صارف نام لکھیں',
    'Enter password': 'پاس ورڈ لکھیں', 'Enter full name': 'پورا نام لکھیں',
    'Enter name': 'نام لکھیں',

    # --- navigation / headings ---
    'Dashboard': 'ڈیش بورڈ', 'School Manager': 'اسکول منیجر', 'Main navigation': 'مین مینو',
    'Open navigation': 'مینو کھولیں', 'Close navigation': 'مینو بند کریں',
    'Collapse sidebar': 'سائیڈ بار سمیٹیں', 'Teachers': 'اساتذہ', 'Faculty': 'اساتذہ',
    'Classes & Subjects': 'کلاسز اور مضامین', 'Classes, Sections & Subjects': 'کلاسز، سیکشنز اور مضامین',
    'Subject Library': 'مضامین کی فہرست', 'Examination': 'امتحان', 'Timetable': 'ٹائم ٹیبل',
    'Finance': 'مالیات', 'Expenses': 'اخراجات', 'Payroll': 'تنخواہیں', 'Salaries': 'تنخواہیں',
    'Documents': 'دستاویزات', 'Audit Log': 'آڈٹ لاگ', 'License': 'لائسنس',
    'Users & Roles': 'صارفین اور اختیارات', 'School Settings': 'اسکول کی ترتیبات',
    'Executive Dashboard': 'ایگزیکٹو ڈیش بورڈ', 'Executive Command Center': 'ایگزیکٹو کمانڈ سینٹر',
    'School Assistant': 'اسکول اسسٹنٹ', 'School operations overview': 'اسکول کا مجموعی جائزہ',
    'Student Management': 'طلبہ کا انتظام', 'Student directory': 'طلبہ کی فہرست',
    'Teacher Management': 'اساتذہ کا انتظام', 'Faculty records': 'اساتذہ کا ریکارڈ',
    'Faculty tracking': 'اساتذہ کی نگرانی', 'Promote Students': 'طلبہ کو اگلی کلاس میں بھیجیں',
    'Finance overview': 'مالی جائزہ', 'Financial Overview': 'مالی جائزہ',
    'Financial Insights': 'مالی تجزیہ', 'Back to Financial Overview': 'مالی جائزے پر واپس',
    'Open Financial Overview →': 'مالی جائزہ کھولیں ←', 'Other Income': 'دیگر آمدنی',
    'Fees & Enrollment': 'فیس اور داخلہ', 'Academic & Fees': 'تعلیمی اور فیس',
    'Academic setup': 'تعلیمی ترتیب', 'Analytics & Exports': 'تجزیے اور ایکسپورٹ',
    'Inventory & Sales': 'اسٹاک اور فروخت', 'Finance & Exports': 'مالیات اور ایکسپورٹ',
    'Documents & Certificates': 'دستاویزات اور سرٹیفکیٹ', 'ID Cards & Certificates': 'شناختی کارڈ اور سرٹیفکیٹ',
    'Testing & Marks Hub': 'ٹیسٹ اور نمبروں کا مرکز', 'Student Profile Hub': 'طالب علم پروفائل',
    'Open Documents Hub': 'دستاویزات کھولیں', 'Exit Software': 'سافٹ ویئر بند کریں',
    'Close School Manager completely': 'اسکول منیجر مکمل بند کریں',
    'Yes, close School Manager': 'جی ہاں، اسکول منیجر بند کریں',
    'Are you sure you want to close School Manager?': 'کیا آپ واقعی اسکول منیجر بند کرنا چاہتے ہیں؟',
    'Users & roles': 'صارفین اور اختیارات', 'Automation settings': 'آٹومیشن کی ترتیبات',
    'WhatsApp Automation': 'واٹس ایپ آٹومیشن', 'WhatsApp Service': 'واٹس ایپ سروس',
    'WhatsApp': 'واٹس ایپ', 'Archive Bin': 'آرکائیو',
    'Staff Today': 'آج کا عملہ', 'Students Today': 'آج کے طلبہ', 'Total Students': 'کل طلبہ',
    'Total School Students': 'اسکول کے کل طلبہ', 'active students': 'فعال طلبہ',
    'Active students': 'فعال طلبہ', 'active teachers': 'فعال اساتذہ', 'Current students': 'موجودہ طلبہ',
    'Recently Enrolled Students': 'حال ہی میں داخل ہونے والے طلبہ',
    'Recent Fee Months': 'حالیہ مہینوں کی فیس', 'Recent Tests Conducted': 'حالیہ ٹیسٹ',
    'Birthdays': 'سالگرہ', '🎂 Today': '🎂 آج', 'Next 7 days': 'اگلے 7 دن',
    'Quick Actions:': 'فوری کام:', 'At Risk (< 75%)': 'خطرے میں (75% سے کم)',

    # --- students ---
    'Add Student': 'طالب علم شامل کریں', 'Save Student': 'طالب علم محفوظ کریں',
    'Edit Student:': 'طالب علم میں ترمیم:', 'Student Details': 'طالب علم کی تفصیل',
    'Personal & Guardian Information': 'ذاتی اور سرپرست کی معلومات',
    'Personal & Contact': 'ذاتی اور رابطہ', 'Identity & Work Details': 'شناخت اور ملازمت',
    'Identity': 'شناخت', 'Date of Birth': 'تاریخ پیدائش', 'Date of Birth:': 'تاریخ پیدائش:',
    'Guardian Phone': 'سرپرست کا فون', 'Guardian phone': 'سرپرست کا فون',
    'Guardian Phone Number': 'سرپرست کا فون نمبر', 'Guardian Phone:': 'سرپرست کا فون:',
    'Father CNIC Number': 'والد کا شناختی کارڈ نمبر', 'Sponsor Type': 'سرپرست کی قسم',
    'Emergency Contact': 'ہنگامی رابطہ', 'Emergency Contact Number': 'ہنگامی رابطہ نمبر',
    'Contact Number': 'رابطہ نمبر', 'Roll Number': 'رول نمبر', 'Current Roll No': 'موجودہ رول نمبر',
    'New Roll No': 'نیا رول نمبر', 'Roll number conflict': 'رول نمبر کا تصادم',
    'Section (Optional)': 'سیکشن (اختیاری)', 'No section selected': 'سیکشن منتخب نہیں',
    'No section selected (optional)': 'سیکشن منتخب نہیں (اختیاری)',
    '— All Sections —': '— تمام سیکشنز —', '— All Classes —': '— تمام کلاسز —',
    'All sections': 'تمام سیکشنز', 'All Genders': 'تمام', 'All students': 'تمام طلبہ',
    'All Students': 'تمام طلبہ', 'All School Students': 'اسکول کے تمام طلبہ',
    'Select Class:': 'کلاس منتخب کریں:', 'Select Date:': 'تاریخ منتخب کریں:',
    'Filter by class': 'کلاس کے مطابق', 'Filter by gender': 'جنس کے مطابق',
    'Filter by status': 'حیثیت کے مطابق', 'Filter by designation': 'عہدے کے مطابق',
    'Name, father or admission no': 'نام، والد یا داخلہ نمبر',
    'Clear Search': 'تلاش صاف کریں', 'Clear filters': 'فلٹر صاف کریں', 'Clear Filters': 'فلٹر صاف کریں',
    'Apply filters': 'فلٹر لگائیں', 'Admission No': 'داخلہ نمبر', 'Admission No:': 'داخلہ نمبر:',
    'Admission Date': 'داخلے کی تاریخ', 'Admission Date:': 'داخلے کی تاریخ:',
    'Admission': 'داخلہ', 'Custom Fields': 'اضافی خانے', 'Columns': 'کالم',
    'Current view columns': 'موجودہ کالم', 'Manage View': 'منظر کا انتظام',
    'Export Data': 'ڈیٹا ایکسپورٹ', 'Export CSV Sheet': 'سی ایس وی شیٹ',
    'Export Excel Sheet': 'ایکسل شیٹ', 'Export PDF': 'پی ڈی ایف', 'Export PDF Sheet': 'پی ڈی ایف شیٹ',
    'Import Excel': 'ایکسل امپورٹ', 'Import Students from Excel / CSV': 'ایکسل یا سی ایس وی سے طلبہ امپورٹ کریں',
    'Import Teachers from Excel / CSV': 'ایکسل یا سی ایس وی سے اساتذہ امپورٹ کریں',
    'Download Template': 'نمونہ ڈاؤن لوڈ کریں', 'Select File': 'فائل منتخب کریں',
    'Need an Excel template?': 'ایکسل کا نمونہ چاہیے؟', 'Mandatory columns': 'ضروری کالم',
    'Download ID card': 'شناختی کارڈ ڈاؤن لوڈ کریں', 'Student ID Card (PDF)': 'طالب علم کا کارڈ (پی ڈی ایف)',
    'Result Card (PDF)': 'رزلٹ کارڈ (پی ڈی ایف)', 'Report card PDF': 'رزلٹ کارڈ (پی ڈی ایف)',
    'Academic Transcript (PDF)': 'تعلیمی ٹرانسکرپٹ (پی ڈی ایف)', 'Transcript': 'ٹرانسکرپٹ',
    'Admission Form PDF': 'داخلہ فارم پی ڈی ایف', 'Enrollment History': 'داخلے کی تاریخ',
    'Enrolled': 'داخل', 'Graduated': 'فارغ التحصیل', 'Struck Off': 'خارج', 'SLC Issued': 'اسکول چھوڑنے کا سرٹیفکیٹ جاری',
    'Left students': 'اسکول چھوڑنے والے طلبہ', 'Left / Archived Students': 'چھوڑنے والے / آرکائیو طلبہ',
    'Left school': 'اسکول چھوڑا', 'Left on': 'چھوڑنے کی تاریخ', 'Leaving Date': 'چھوڑنے کی تاریخ',
    'School Leaving Certificate': 'اسکول چھوڑنے کا سرٹیفکیٹ', 'Character Certificate': 'کردار کا سرٹیفکیٹ',
    'Bonafide / Studentship': 'بونافائیڈ / طالب علمی سرٹیفکیٹ',
    'Merit / Achievement Certificate': 'اعزازی سرٹیفکیٹ', 'Issue certificate': 'سرٹیفکیٹ جاری کریں',
    'Archive / Status Change': 'آرکائیو / حیثیت کی تبدیلی', 'Confirm Archive': 'آرکائیو کی تصدیق',
    'Open Archived →': 'آرکائیو کھولیں ←', 'Archived Subjects': 'محفوظ شدہ مضامین',

    # --- attendance ---
    'Attendance': 'حاضری', 'Mark Attendance': 'حاضری لگائیں', 'Daily Attendance': 'روزانہ حاضری',
    'Attendance entry': 'حاضری کا اندراج', 'Attendance Summary': 'حاضری کا خلاصہ',
    'Attendance analysis': 'حاضری کا تجزیہ', 'Attendance Ledger': 'حاضری کھاتہ',
    'Attendance Status': 'حاضری کی حیثیت', 'Student Attendance': 'طلبہ کی حاضری',
    'Teacher Attendance': 'اساتذہ کی حاضری', 'Teacher Attendance Sheet': 'اساتذہ کی حاضری شیٹ',
    'Teacher Attendance Summary': 'اساتذہ کی حاضری کا خلاصہ',
    'Mark Staff Attendance': 'عملے کی حاضری لگائیں', 'Save Teacher Attendance': 'اساتذہ کی حاضری محفوظ کریں',
    'Teacher Roster & Attendance Entry': 'اساتذہ کی فہرست اور حاضری',
    'Switch to Student Attendance': 'طلبہ کی حاضری پر جائیں',
    'View Teacher Attendance Summary': 'اساتذہ کی حاضری کا خلاصہ دیکھیں',
    'Attendance Locked': 'حاضری مقفل ہے', 'Unlock': 'کھولیں', 'lock': 'مقفل',
    'Attendance is locked. Click Unlock to make changes.': 'حاضری مقفل ہے۔ تبدیلی کے لیے "کھولیں" دبائیں۔',
    'All Present': 'سب حاضر', 'All Absent': 'سب غیر حاضر', 'All students marked': 'تمام طلبہ کی حاضری لگ گئی',
    'All staff marked': 'تمام عملے کی حاضری لگ گئی', 'Send Absent Alerts': 'غیر حاضری کے پیغام بھیجیں',
    'Absentee Alert Center': 'غیر حاضری الرٹ سینٹر', 'Check-in / Late': 'آمد / تاخیر',
    'On-time check-in time': 'وقت پر آنے کا وقت', 'Use current time': 'موجودہ وقت لگائیں',
    'Late min': 'تاخیر (منٹ)', 'ABS': 'غ', 'LV': 'ر', '100% Attendance': '100% حاضری',
    'Show At-Risk Only (< 75%)': 'صرف خطرے والے (75% سے کم)',
    'Attendance below 75% — Chronic Absenteeism Risk': 'حاضری 75% سے کم — مسلسل غیر حاضری کا خطرہ',
    'No attendance recorded yet': 'ابھی حاضری درج نہیں', 'Not taken': 'نہیں لی گئی',
    'Switch to Student Attendance': 'طلبہ کی حاضری پر جائیں', 'Legend:': 'نشانات:',

    # --- fees ---
    'Fee Management Ledger': 'فیس کھاتہ', 'Fees Management': 'فیس کا انتظام', 'Fee Ledger': 'فیس کھاتہ',
    'Fee Ledger for': 'فیس کھاتہ برائے', 'Full Ledger': 'مکمل کھاتہ', 'Open Full Fee Ledger': 'مکمل فیس کھاتہ کھولیں',
    'Full transaction ledger': 'تمام لین دین کا کھاتہ', 'Fee Collection': 'فیس وصولی',
    'Fee Dues': 'فیس واجبات', 'Fee Receipt': 'فیس کی رسید', 'FEE PAYMENT RECEIPT': 'فیس کی رسید',
    'Fee Reconciliation': 'فیس کا مِلان', 'Reconciliation': 'مِلان', 'Fee Reminders': 'فیس کی یاد دہانی',
    'Fee reminders': 'فیس کی یاد دہانی', 'Fee settings': 'فیس کی ترتیبات', 'Fee Set Fee': 'فیس مقرر کریں',
    'Set Fee': 'فیس مقرر کریں', 'Save Fee': 'فیس محفوظ کریں', 'Edit Fee Set Fee': 'فیس میں ترمیم',
    'Set Monthly Fee for Entire Class': 'پوری کلاس کی ماہانہ فیس مقرر کریں',
    'Collect Fee': 'فیس وصول کریں', 'Receive payment': 'ادائیگی وصول کریں',
    'Receive & open receipt': 'وصول کریں اور رسید کھولیں', 'Record Payment': 'ادائیگی درج کریں',
    'Save Payment': 'ادائیگی محفوظ کریں', 'Payment Details': 'ادائیگی کی تفصیل',
    'Payment Date': 'ادائیگی کی تاریخ', 'Payment Method': 'ادائیگی کا طریقہ', 'Payment Type': 'ادائیگی کی قسم',
    'Receive Payment (Fees page)': 'ادائیگی وصول کریں (فیس پیج)',
    'Billing Month & Year:': 'مہینہ اور سال:', 'Billing month': 'مہینہ', 'Billing Period:': 'مدت:',
    'Billing month (blank = all months)': 'مہینہ (خالی = تمام مہینے)', 'All months': 'تمام مہینے',
    'All months (total owed)': 'تمام مہینے (کل باقی)', 'Specific month': 'مخصوص مہینہ',
    'Specific Month (if chosen)': 'مخصوص مہینہ (اگر منتخب ہو)', 'By Class': 'کلاس کے مطابق',
    'All Unpaid / Partial': 'تمام غیر ادا / جزوی', 'Unpaid & Partial — All Classes': 'غیر ادا اور جزوی — تمام کلاسز',
    'Reference / Slip No': 'حوالہ / سلپ نمبر', 'Reference / Slip': 'حوالہ / سلپ', 'Slip No:': 'سلپ نمبر:',
    'Receipt No:': 'رسید نمبر:', 'Received by:': 'وصول کنندہ:', 'Remarks:': 'ریمارکس:',
    'Remarks / Payment Note': 'ریمارکس / ادائیگی کا نوٹ', 'Amount (PKR)': 'رقم (روپے)',
    'Amount Paid': 'ادا شدہ رقم', 'Amount Paid (PKR)': 'ادا شدہ رقم (روپے)', 'Amount Paid:': 'ادا شدہ رقم:',
    'Amount Received Now (PKR)': 'ابھی وصول شدہ رقم (روپے)', 'Monthly Fee': 'ماہانہ فیس',
    'Monthly Fee:': 'ماہانہ فیس:', 'Monthly fee (PKR)': 'ماہانہ فیس (روپے)', 'Monthly Fee (PKR)': 'ماہانہ فیس (روپے)',
    'Standard Monthly Fee (PKR)': 'مقررہ ماہانہ فیس (روپے)', 'Standard fee:': 'مقررہ فیس:',
    'Enter monthly fee amount': 'ماہانہ فیس لکھیں', 'Monthly Due': 'ماہانہ واجب', 'Monthly Due (PKR)': 'ماہانہ واجب (روپے)',
    'Monthly Due:': 'ماہانہ واجب:', 'Outstanding': 'باقی', 'Outstanding (PKR)': 'باقی (روپے)',
    'Outstanding (Rs.)': 'باقی (روپے)', 'Outstanding balance': 'باقی رقم', 'Outstanding:': 'باقی:',
    'Pending Dues': 'باقی واجبات', 'Pending dues (live from fee ledger)': 'باقی واجبات (فیس کھاتے سے)',
    'Total Due:': 'کل واجب:', 'Total Collected:': 'کل وصول:', 'Total owed:': 'کل باقی:',
    'Total charged (PKR)': 'کل چارج (روپے)', 'Total paid (PKR)': 'کل ادا (روپے)',
    'Total received (PKR)': 'کل وصول (روپے)', 'Charged': 'چارج شدہ', 'Received': 'وصول شدہ',
    'Received so far': 'اب تک وصول', 'Fully Paid': 'مکمل ادا', 'Fully paid': 'مکمل ادا',
    'Fully paid ✓': 'مکمل ادا ✓', 'No dues': 'کوئی واجب نہیں', 'Has dues': 'واجبات ہیں',
    'No outstanding dues — fully paid': 'کوئی رقم باقی نہیں — مکمل ادا',
    'No outstanding dues — fully settled. Thank you!': 'کوئی رقم باقی نہیں — شکریہ!',
    'Advance credit': 'پیشگی رقم', 'Advance Payment (future months)': 'پیشگی ادائیگی (آئندہ مہینے)',
    'Apply To': 'لاگو کریں', 'Apply to Class': 'کلاس پر لاگو کریں',
    'Oldest dues first (default)': 'پرانے واجبات پہلے (طے شدہ)', 'Generate monthly charges': 'ماہانہ فیس بنائیں',
    'Write off': 'معاف کریں', 'Write off dues': 'واجبات معاف کریں', 'Written off': 'معاف شدہ',
    'Written Off': 'معاف شدہ', 'Refund': 'واپسی', 'Refund part of this payment': 'اس ادائیگی کا کچھ حصہ واپس کریں',
    'Void with reason': 'وجہ کے ساتھ منسوخ کریں', 'Print receipt': 'رسید پرنٹ کریں',
    'Print A4 Receipt': 'اے فور رسید پرنٹ کریں', 'Print / Export Sheet': 'پرنٹ / ایکسپورٹ شیٹ',
    'Cashier Signature': 'کیشیئر کے دستخط', 'Parent Signature': 'والدین کے دستخط',
    'Paid (this receipt)': 'ادا (اس رسید میں)', 'Paid up to this receipt': 'اس رسید تک ادا',
    'Balance after this receipt': 'اس رسید کے بعد باقی', 'Back to fees': 'فیس پر واپس',
    'Back to Fees': 'فیس پر واپس', 'Back to reconciliation': 'مِلان پر واپس', 'Back to register': 'رجسٹر پر واپس',
    'Student Dues': 'طلبہ کے واجبات', 'Reminders to queue': 'بھیجنے کے لیے یاد دہانیاں',
    'Already queued / sent': 'پہلے سے قطار میں / بھیجی جا چکی', 'Without a usable phone': 'قابل استعمال فون کے بغیر',
    'No Phone': 'فون نہیں', 'Call guardian': 'سرپرست کو کال کریں', 'WhatsApp guardian': 'سرپرست کو واٹس ایپ',
    'Call': 'کال', 'Filled from the class': 'کلاس سے بھرا گیا',
    'Class (optional)': 'کلاس (اختیاری)', 'Unapplied payments & write-offs': 'غیر لاگو ادائیگیاں اور معافیاں',
    'Repair unapplied payments': 'غیر لاگو ادائیگیاں درست کریں', 'Settled month': 'ادا شدہ مہینہ',
    'Student-month rows': 'طالب علم-مہینہ ریکارڈ', 'Students listed': 'درج طلبہ',
    'Stored due': 'محفوظ واجب', 'Stored paid': 'محفوظ ادا', 'MISMATCH': 'فرق',
    'Cleared': 'ادا', 'Queue status': 'قطار کی حیثیت', 'Recorded by': 'درج کنندہ',
    'Recorded on': 'درج کرنے کی تاریخ', 'Income date': 'آمدنی کی تاریخ', 'Dates:': 'تاریخیں:',
    'Start Date:': 'ابتدائی تاریخ:', 'End Date:': 'آخری تاریخ:', 'Percentage': 'فیصد',
    'Percentage (%)': 'فیصد (%)', 'Fixed Amount (PKR)': 'مقررہ رقم (روپے)', 'Fixed amount (PKR)': 'مقررہ رقم (روپے)',
    'Discount Type': 'رعایت کی قسم', 'Discount Value': 'رعایت کی مقدار', 'Concession Value': 'رعایت کی مقدار',
    'Concessions given': 'دی گئی رعایتیں', 'Full waiver': 'مکمل معافی',

    # --- admission ---
    'Admission Fees': 'داخلہ فیس', 'Admission Fee': 'داخلہ فیس', 'Admission fee': 'داخلہ فیس',
    'Admission Fee Settings': 'داخلہ فیس کی ترتیبات', 'Admission Fee Paid': 'داخلہ فیس ادا',
    'Admission Fee Receipt': 'داخلہ فیس کی رسید', 'Admission fee (net)': 'داخلہ فیس (رعایت کے بعد)',
    'Admission Fee (PKR)': 'داخلہ فیس (روپے)', 'Admission fee (PKR)': 'داخلہ فیس (روپے)',
    'Net Admission Fee (PKR)': 'داخلہ فیس رعایت کے بعد (روپے)', 'Net Fee (PKR)': 'رعایت کے بعد فیس (روپے)',
    'Agreed admission fee': 'طے شدہ داخلہ فیس', 'Agreed total': 'طے شدہ کل رقم', 'Total agreed': 'کل طے شدہ',
    'Standard admission fee': 'مقررہ داخلہ فیس', 'School admission fee (PKR)': 'اسکول کی داخلہ فیس (روپے)',
    'School fee': 'اسکول کی فیس', 'Fees for each class': 'ہر کلاس کی فیس',
    'Books': 'کتابیں', 'Books (PKR)': 'کتابیں (روپے)', 'Books + Uniform': 'کتابیں + یونیفارم',
    'Uniform sets': 'یونیفارم کے سیٹ', 'Uniform / set': 'یونیفارم فی سیٹ', 'Uniform total (PKR)': 'یونیفارم کل (روپے)',
    'Price per set (PKR)': 'فی سیٹ قیمت (روپے)', 'Sets': 'سیٹ', 'Uniform': 'یونیفارم',
    'Total to pay (admission + books + uniform)': 'کل ادائیگی (داخلہ + کتابیں + یونیفارم)',
    'Save terms': 'شرائط محفوظ کریں', 'Terms': 'شرائط', 'Reason (required)': 'وجہ (ضروری)',
    'Export the register': 'رجسٹر ایکسپورٹ کریں', 'Admission fee columns': 'داخلہ فیس کے کالم',
    'Fees → Admission Fee Settings': 'فیس ← داخلہ فیس کی ترتیبات',
    'Already queued': 'پہلے سے قطار میں', 'Shift students to make room?': 'جگہ بنانے کے لیے طلبہ آگے کریں؟',
    '· auto-fills student fees at admission': '· داخلے پر طالب علم کی فیس خود بھر دیتا ہے',
    'Auto-fills the fee when admitting a student to this class.': 'اس کلاس میں داخلے پر فیس خود بھر دیتا ہے۔',
    'Back-dating is allowed — the cash date drives all reports.': 'پچھلی تاریخ ڈالی جا سکتی ہے — رپورٹس نقد کی تاریخ سے بنتی ہیں۔',

    # --- classes / teachers ---
    'Add Class': 'کلاس شامل کریں', 'Edit Class': 'کلاس میں ترمیم', 'Class Name': 'کلاس کا نام',
    'Edit Section': 'سیکشن میں ترمیم', 'Edit Subject': 'مضمون میں ترمیم', 'Subject Name': 'مضمون کا نام',
    'Subject Teacher': 'مضمون کے استاد', 'Delete section': 'سیکشن حذف کریں', 'Section Rosters': 'سیکشن کی فہرستیں',
    'Add Teacher': 'استاد شامل کریں', 'Save Teacher': 'استاد محفوظ کریں', 'Teacher Name': 'استاد کا نام',
    'Teacher ID': 'استاد کی شناخت', 'Teacher CNIC': 'استاد کا شناختی کارڈ', 'Designation': 'عہدہ',
    'All Designations': 'تمام عہدے', 'Qualification': 'تعلیمی قابلیت', 'Joining Date': 'شمولیت کی تاریخ',
    'Monthly Salary': 'ماہانہ تنخواہ', 'Monthly Salary (PKR)': 'ماہانہ تنخواہ (روپے)', 'Salary Type': 'تنخواہ کی قسم',
    'Hourly Rate': 'فی گھنٹہ ریٹ', 'Hourly Rate (PKR)': 'فی گھنٹہ ریٹ (روپے)', 'Assigned Classes': 'مقرر کلاسز',
    'Assigned Subjects': 'مقرر مضامین', 'Previous Experience (Years)': 'سابقہ تجربہ (سال)',
    'Previous Salary (PKR)': 'سابقہ تنخواہ (روپے)', 'Move students to:': 'طلبہ کو منتقل کریں:',
    'Move to another section': 'دوسرے سیکشن میں منتقل کریں', 'Move': 'منتقل کریں',
    '— No teacher —': '— کوئی استاد نہیں —', '— Leave unassigned (no section) —': '— بغیر سیکشن چھوڑیں —',
    'Exam': 'امتحان', 'Term Exam Results': 'ٹرم امتحان کے نتائج', 'Class Results & Reports': 'کلاس کے نتائج اور رپورٹس',
    'Overall (all marks)': 'مجموعی (تمام نمبر)', 'Obtained': 'حاصل کردہ', 'Best Test:': 'بہترین ٹیسٹ:',
    'No test/exam taken yet': 'ابھی کوئی ٹیسٹ نہیں ہوا', 'No term exams yet': 'ابھی کوئی ٹرم امتحان نہیں',
    'Create Test': 'ٹیسٹ بنائیں', 'Result Card — All Marks': 'رزلٹ کارڈ — تمام نمبر',
    'Birthday data unavailable.': 'سالگرہ کا ڈیٹا دستیاب نہیں۔',
    'Archived data unavailable.': 'محفوظ ڈیٹا دستیاب نہیں۔',

    # --- sign-in / system ---
    'Login — School Manager': 'لاگ ان — اسکول منیجر', 'Checking connection...': 'کنکشن چیک ہو رہا ہے...',
    'Checking service status...': 'سروس کی حیثیت چیک ہو رہی ہے...', 'Checking...': 'چیک ہو رہا ہے...',
    'Connected Disconnected': 'منسلک / غیر منسلک', 'Refresh WhatsApp status': 'واٹس ایپ کی حیثیت تازہ کریں',
    'Test WhatsApp': 'واٹس ایپ ٹیسٹ', 'Send WhatsApp test message': 'واٹس ایپ ٹیسٹ پیغام بھیجیں',
    'View detailed report': 'تفصیلی رپورٹ دیکھیں', 'View switcher': 'منظر تبدیل کریں',
    'Grid': 'گرڈ', 'List': 'فہرست', 'Load': 'لوڈ', 'Update Changes': 'تبدیلیاں محفوظ کریں',
    'Close': 'بند کریں', 'Profile Details': 'پروفائل کی تفصیل', 'My Child': 'میرا بچہ',
    'Assistant': 'اسسٹنٹ', 'Operating Expenses': 'آپریٹنگ اخراجات', 'Operational Expenses': 'آپریشنل اخراجات',
}


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


PATTERNS += [
    (r'^(%s), (\d{1,2}) (%s) (\d{4}) \u00b7 Session (.+)$' % ('|'.join(_W), '|'.join(_MONTHS)),
     lambda m: '%s، %s %s %s · سیشن %s' % (WEEKDAY_UR[m.group(1)], m.group(2), MONTH_UR[m.group(3)],
                                         m.group(4), m.group(5))),
    (r'^Operating View \u2014 (%s) (\d{4}) \(estimated\)$' % '|'.join(_MONTHS),
     lambda m: 'آپریٹنگ منظر \u2014 %s %s (اندازاً)' % (MONTH_UR[m.group(1)], m.group(2))),
    (r'^Session Net \((.+)\)$', _isolate('سیشن کا خالص ({1})')),
    (r'^collected \u00b7 billed (%s)$' % _RS, _isolate('وصول \u00b7 بل شدہ {1}')),
    (r'^settled %s%%$' % _PC, _isolate('ادا {1}%')),
    (r'^vs previous month %s%%$' % _PC, _isolate('پچھلے مہینے کے مقابلے میں {1}%')),
    (r'^(\d+) student\(s\) left this session \((.+)\)$', _isolate('{1} طلبہ نے اس سیشن ({2}) میں اسکول چھوڑا')),
    (r'^(\d+) item\(s\) low on stock$', _isolate('{1} آئٹم کا اسٹاک کم ہے')),
    (r'^%s of older arrears is still recoverable\.$' % _RS, _isolate('{1} کا پرانا بقایا ابھی وصول ہو سکتا ہے۔')),
    (r'^%s of older arrears was recovered this month\.$' % _RS, _isolate('اس مہینے {1} کا پرانا بقایا وصول ہوا۔')),
    (r'^(\d+) former student\(s\) owe %s\.$' % _RS, _isolate('{1} سابق طلبہ کے ذمے {2} واجب ہیں۔')),
    (r'^%s of salary is still unpaid( \(estimated\))?\.$' % _RS,
     lambda m: '%s کی تنخواہ ابھی ادا نہیں ہوئی%s۔' % (_n(m.group(1)), ' (اندازاً)' if m.group(2) else '')),
    (r'^Fee collection is %s%% (higher|lower) than last month\.$' % _PC,
     lambda m: 'فیس وصولی پچھلے مہینے سے %s%% %s ہے۔' % (_n(m.group(1)), 'زیادہ' if m.group(2) == 'higher' else 'کم')),
    (r'^Fee collection rate (improved|dropped) by %s percentage points \(this month %s%%, last month %s%%\)\.$' % (_PC, _PC, _PC),
     lambda m: 'فیس وصولی کی شرح %s %s فیصد پوائنٹ (اس مہینے %s%%، پچھلے مہینے %s%%)۔' % (
         'میں بہتری آئی' if m.group(1) == 'improved' else 'میں کمی آئی', _n(m.group(2)), _n(m.group(3)), _n(m.group(4)))),
    (r'^Cash In was %s%% (higher|lower) than last month \((%s) vs (%s)\)\.$' % (_PC, _RS, _RS),
     lambda m: 'آمد پچھلے مہینے سے %s%% %s رہی (%s کے مقابلے میں %s)۔' % (
         _n(m.group(1)), 'زیادہ' if m.group(2) == 'higher' else 'کم', _n(m.group(3)), _n(m.group(4)))),
    (r'^Net Position (improved|fell) by %s \(cash basis\)\.$' % _RS,
     lambda m: ('خالص پوزیشن %s بہتر ہوئی (نقد کی بنیاد پر)۔' if m.group(1) == 'improved'
                else 'خالص پوزیشن %s کم ہوئی (نقد کی بنیاد پر)۔') % _n(m.group(2))),
    (r'^(.+) expenses rose %s%% vs last month \(\+%s\)\.$' % (_PC, _RS),
     lambda m: '%s کے اخراجات پچھلے مہینے سے %s%% بڑھے (%s)۔' % (m.group(1), _n(m.group(2)), _n('+' + m.group(3).lstrip('+')))),
    (r'^(.+) expenses are up %s%% vs last month \(\+%s\)$' % (_PC, _RS),
     lambda m: '%s کے اخراجات پچھلے مہینے سے %s%% زیادہ ہیں (%s)' % (m.group(1), _n(m.group(2)), _n('+' + m.group(3).lstrip('+')))),
    (r'^Inventory sales were %s with cost of goods sold %s \(gross profit %s\)\.$' % (_RS, _RS, _RS),
     _isolate('اسٹاک کی فروخت {1} رہی، فروخت شدہ مال کی لاگت {2} (مجموعی منافع {3})۔')),
    (r'^Stock purchases of %s are part of Cash Out but not expenses; their cost enters Cost of Goods Sold when the items sell\.$' % _RS,
     _isolate('{1} کی اسٹاک خریداری نقد اخراج کا حصہ ہے مگر خرچ نہیں؛ اس کی لاگت چیز بکنے پر فروخت شدہ مال کی لاگت میں شامل ہوگی۔')),
    (r'^Estimated Net Operating Position was %s \(Revenue minus Salaries, Operating Expenses and Cost of Goods Sold \u2014 an operating estimate, not money movement\)\.$' % _RS,
     _isolate('اندازاً خالص آپریٹنگ پوزیشن {1} رہی (آمدنی منفی تنخواہیں، آپریٹنگ اخراجات اور فروخت شدہ مال کی لاگت \u2014 اندازہ ہے، نقد کی نقل و حرکت نہیں)۔')),
    (r'^Students who left reduce estimated monthly revenue by %s \(estimate\)\.$' % _RS,
     _isolate('چھوڑنے والے طلبہ کی وجہ سے ماہانہ آمدنی اندازاً {1} کم ہوئی۔')),
    (r'^Recover older arrears: %s from earlier months is still unpaid \u2014 see the dues list\.$' % _RS,
     _isolate('پرانا بقایا وصول کریں: پچھلے مہینوں کے {1} ابھی ادا نہیں ہوئے \u2014 واجبات کی فہرست دیکھیں۔')),
    (r'^%s in fees is outstanding in total \u2014 send reminders to the largest dues first\.$' % _RS,
     _isolate('کل {1} فیس باقی ہے \u2014 سب سے بڑے واجبات والوں کو پہلے یاد دہانی بھیجیں۔')),
    (r'^(.+) expenses rose %s%% vs last month \u2014 check for unusual usage or one-off purchases\.$' % _PC,
     lambda m: '%s کے اخراجات پچھلے مہینے سے %s%% بڑھے \u2014 غیر معمولی استعمال یا ایک بار کی خریداری دیکھیں۔' % (m.group(1), _n(m.group(2)))),
    (r'^Restock soon: (.+) (is|are) below minimum stock\.$',
     lambda m: 'جلد اسٹاک بھریں: %s کم از کم اسٹاک سے نیچے %s۔' % (m.group(1), 'ہے' if m.group(2) == 'is' else 'ہیں')),
    (r'^Low stock: (.+)\.$', lambda m: 'اسٹاک کم ہے: %s۔' % m.group(1)),
    (r"^This month's fee collection is at %s%% \u2014 follow up with pending payers\.$" % _PC,
     lambda m: 'اس مہینے کی فیس وصولی %s%% ہے \u2014 باقی ادائیگی والوں سے رابطہ کریں۔' % _n(m.group(1))),
    (r'^Net Position is negative this month\.$', r'اس مہینے خالص پوزیشن منفی ہے۔'),
    (r'^Cash In minus Cash Out: %s this month vs %s last month$' % (_RS, _RS),
     _isolate('آمد منفی اخراج: اس مہینے {1}، پچھلے مہینے {2}')),
    (r'^salaries paid \((%s)\) as a share of Cash In \((%s)\)$' % (_RS, _RS),
     _isolate('ادا شدہ تنخواہیں ({1}) آمد ({2}) کے حصے کے طور پر')),
    (r'^inventory sales in (%s) (\d{4}) \u00b7 already inside Cash In$' % '|'.join(_MONTHS),
     lambda m: 'اسٹاک کی فروخت %s %s میں \u00b7 آمد میں پہلے سے شامل' % (MONTH_UR[m.group(1)], m.group(2))),
]

UR.update({
    'Disconnected': 'منسلک نہیں', 'Connected': 'منسلک',
    'Taking books': 'کتابیں لے رہا ہے', 'Not taking books': 'کتابیں نہیں لے رہا',
    'Books amount (PKR)': 'کتابوں کی رقم (روپے)', 'Fixed from the class.': 'کلاس سے مقرر۔',
    'Price per set': 'فی سیٹ قیمت', 'Uniform total': 'یونیفارم کل',
})


def _fold(text):
    return ' '.join(text.split()).lower()


UR.update({
    # --- books in more than one set, floating assistant, inspection mode, license reminders ---
    'Book sets': 'کتابوں کے سیٹ', '0 = not taking books.': '0 = کتابیں نہیں لے رہا۔',
    'Price per set is fixed by the class.': 'ایک سیٹ کی قیمت کلاس سے مقرر ہے۔',
    'Books price per set (PKR)': 'کتابوں کی فی سیٹ قیمت (روپے)',
    'Clear chat': 'چیٹ صاف کریں',
    'Inspection mode.': 'معائنہ موڈ۔', 'Inspection mode': 'معائنہ موڈ',
    'License renewal reminder': 'لائسنس تجدید کی یاد دہانی',
    'Remind me later': 'بعد میں یاد دلائیں', 'Manage license': 'لائسنس کا انتظام',
    'Notice from your software provider:': 'سافٹ ویئر فراہم کنندہ کی طرف سے اطلاع:',
    'Inspection mode is on': 'معائنہ موڈ فعال ہے',
    'End inspection now': 'معائنہ ابھی ختم کریں',
})
UR.update({
    # --- Class result matrix ---
    'Results matrix': 'نتائج کا میٹرکس',
    'Class Result Matrix': 'کلاس نتائج میٹرکس',
    'Compare performance across students and subjects for the selected class.':
        'منتخب کلاس کے طلبہ اور مضامین کی کارکردگی کا موازنہ کریں۔',
    'Export Whole Class Result (PDF)': 'پوری کلاس کا نتیجہ (پی ڈی ایف)',
    'All Report Cards PDF': 'تمام رپورٹ کارڈ (پی ڈی ایف)',
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


def _period_ur(text):
    """\"October 2026\" -> Urdu month name; anything else (\"All months\") is left as is."""
    found = re.match(r'^(%s) (\d{4})$' % '|'.join(_MONTHS), text.strip())
    return '%s %s' % (MONTH_UR[found.group(1)], found.group(2)) if found else text


def _dues_title(match):
    title = 'کل باقی واجبات'
    return title + ' (%s)' % _period_ur(match.group(1)) if match.group(1) else title


def _current_filters(match):
    text = 'موجودہ فلٹر: ' + _period_ur(match.group(1))
    return text + ' \u00b7 منتخب کلاس' if match.group(2) else text


PATTERNS += [
    (r'^Node runtime: (.+?) \u00b7 Bridge folder:$', _isolate('نوڈ رن ٹائم: {1} \u00b7 برج فولڈر:')),
    (r'^(\d{1,2}) (%s) (\d{4}), (\d{1,2}:\d{2})$' % _M3,
     lambda m: '%s %s %s، %s' % (m.group(1), _M3_UR[m.group(2)], m.group(3), _n(m.group(4)))),
    (r'^(\d+) total$', r'کل \1'),
    (r'^Showing the newest (\d+) of (\d+) messages\. Use the filters above to narrow it down\.$',
     r'\2 میں سے تازہ ترین \1 پیغامات دکھائے جا رہے ہیں۔ تعداد کم کرنے کے لیے اوپر کے فلٹر استعمال کریں۔'),
    (r'^Session: (.+)$', r'سیشن: \1'),
    (r'^Total Outstanding Dues(?: \((.+)\))?$', _dues_title),
    (r'^current filters: (.+?)( \u00b7 selected class)?$', _current_filters),
    (r'^(%s) (\d{4}) \u00b7 All classes$' % '|'.join(_MONTHS),
     lambda m: '%s %s \u00b7 تمام کلاسز' % (MONTH_UR[m.group(1)], m.group(2))),
]

# students page redesign
UR.update({
    'On this list': 'اس فہرست میں', 'Boys': 'لڑکے', 'Girls': 'لڑکیاں',
    'With dues': 'واجبات والے', 'Total due': 'کل واجب',
    'Open full report': 'مکمل رپورٹ کھولیں',
    'Show everyone': 'سب کو دکھائیں',
    'Show only students with dues': 'صرف واجبات والے طلبہ دکھائیں',
})

# teachers page redesign
UR.update({
    'Leadership': 'قیادت', 'Senior staff': 'سینئر عملہ', 'Admin staff': 'انتظامی عملہ',
    'Other / not set': 'دیگر / مقرر نہیں',
    'Principal': 'پرنسپل', 'Vice Principal': 'وائس پرنسپل', 'Head Teacher': 'ہیڈ ٹیچر',
    'Senior Teacher': 'سینئر ٹیچر', 'Admin Staff': 'انتظامی عملہ',
    'In school today': 'آج اسکول میں', 'Not marked': 'درج نہیں',
    'Staff attendance is not marked yet today': 'آج عملے کی حاضری ابھی درج نہیں ہوئی',
    'Classes with a teacher': 'استاد والی کلاسیں',
    'No teacher yet:': 'ابھی کوئی استاد نہیں:',
    'No classes created yet': 'ابھی کوئی کلاس نہیں بنی',
    'Open staff attendance': 'عملے کی حاضری کھولیں',
    'Staff by role': 'عہدے کے لحاظ سے عملہ', 'Staff attendance today': 'آج عملے کی حاضری',
    'Cards': 'کارڈز', 'Table': 'جدول',
    'Present today': 'آج حاضر', 'Late today': 'آج دیر سے', 'On leave today': 'آج چھٹی پر',
    'Absent today': 'آج غیر حاضر', 'Attendance not marked today': 'آج حاضری درج نہیں',
    'No classes assigned yet': 'ابھی کوئی کلاس تفویض نہیں',
})
PATTERNS.extend([
    (r'^Since (\d{4})$', r'\1 سے'),
    (r'^Call (.+)$', r'کال کریں \1'),
])

# --- Student attendance page, redesigned (Oct 2026) ---
UR.update({
    'Attendance Sheet': 'حاضری شیٹ',
    'Students in this class': 'اس کلاس کے طلبہ',
    'Saved. Nobody can change it by mistake.': 'محفوظ ہو گئی۔ غلطی سے کوئی تبدیل نہیں کر سکتا۔',
    'Press Save when you are done.': 'کام مکمل ہونے پر محفوظ کریں دبائیں۔',
    'Find a student by name or roll no…': 'نام یا رول نمبر سے طالب علم تلاش کریں…',
    'Find a student': 'طالب علم تلاش کریں',
    'Previous day': 'پچھلا دن',
    'Next day': 'اگلا دن',
    'Arrival time': 'آمد کا وقت',
    'Save Attendance': 'حاضری محفوظ کریں',
    'Not marked': 'نشان زد نہیں',
    'Not marked yet': 'ابھی نشان زد نہیں',
    'No student matches your search.': 'آپ کی تلاش سے کوئی طالب علم نہیں ملا۔',
    'Go to Students': 'طلبہ پر جائیں',
    'Go to Classes': 'کلاسز پر جائیں',
    'There are no classes yet. Add a class first, then its students will appear here.':
        'ابھی کوئی کلاس نہیں ہے۔ پہلے کلاس بنائیں، پھر اس کے طلبہ یہاں نظر آئیں گے۔',
    'Mark every student of this class as Absent?': 'کیا اس کلاس کے تمام طلبہ کو غیر حاضر لگانا ہے؟',
    'Mark all Absent': 'سب کو غیر حاضر لگائیں',
})
HTML_SENTENCES.extend([
    ('Mark who came to school. Everyone starts as <b>Present</b>, so you only need to touch '
     'the students who are absent, late or on leave.',
     'دیکھیں کون اسکول آیا۔ سب پہلے سے <b>حاضر</b> ہوتے ہیں، اس لیے صرف غیر حاضر، '
     'دیر سے آنے والے یا رخصت والے طلبہ کو بدلیں۔'),
    ('Tap <b>Absent</b>, <b>Late</b> or <b>Leave</b> for the students who need it, then press '
     '<b>Save Attendance</b> at the bottom.',
     'جن طلبہ کو ضرورت ہو ان کے لیے <b>غیر حاضر</b>، <b>تاخیر</b> یا <b>رخصت</b> دبائیں، '
     'پھر نیچے <b>حاضری محفوظ کریں</b> دبائیں۔'),
    ('This day is saved. To correct a mistake press <b>Unlock</b>, change the student and save again.',
     'یہ دن محفوظ ہے۔ غلطی ٹھیک کرنے کے لیے <b>کھولیں</b> دبائیں، طالب علم بدلیں اور دوبارہ محفوظ کریں۔'),
    ('Showing <strong id="saVisible">{1}</strong> of <strong>{2}</strong> students',
     'کل <strong>{2}</strong> میں سے <strong id="saVisible">{1}</strong> طلبہ دکھائے جا رہے ہیں'),
    ('Ready to save: <b id="sumPresent">{1}</b> present · <b id="sumAbsent">{2}</b> absent · '
     '<b id="sumLate">{3}</b> late · <b id="sumLeave">{4}</b> on leave',
     'محفوظ کرنے کے لیے تیار: <b id="sumPresent">{1}</b> حاضر · <b id="sumAbsent">{2}</b> غیر حاضر · '
     '<b id="sumLate">{3}</b> تاخیر · <b id="sumLeave">{4}</b> رخصت پر'),
])

UR_FOLDED = {_fold(k): v for k, v in UR.items()}

UR.update({
    # QR gate scans tab
    'QR Scans': 'کیو آر اسکین',
    'Print QR ID cards': 'کیو آر شناختی کارڈ پرنٹ کریں',
    'Guard phone is ready': 'گارڈ کا فون تیار ہے',
    'Connect the guard\u2019s phone': 'گارڈ کا فون جوڑیں',
    'Just 3 easy steps. Nothing to type on the phone.': 'صرف 3 آسان مراحل۔ فون میں کچھ لکھنے کی ضرورت نہیں۔',
    'Allow guard phones to reach this computer': 'گارڈ کے فون کو اس کمپیوٹر سے جڑنے کی اجازت دیں',
    'Guard phones are allowed': 'گارڈ کے فون کی اجازت ہے',
    'Guard account': 'گارڈ اکاؤنٹ',
    'Create guard account': 'گارڈ اکاؤنٹ بنائیں',
    'Connect the phone with a code': 'کوڈ سے فون جوڑیں',
    'Show the connection code': 'کنکشن کوڈ دکھائیں',
    'New code': 'نیا کوڈ',
    'Update by itself': 'خود بخود اپڈیٹ',
    'Update now': 'ابھی اپڈیٹ کریں',
    'Arrived': 'پہنچ گئے', 'Not arrived': 'نہیں پہنچے', 'Not arrived yet': 'ابھی نہیں پہنچے',
    'Not scanned': 'اسکین نہیں ہوئے', 'Marked absent': 'غیر حاضر لگا دیا',
    'On leave': 'رخصت پر', 'Arrived on time': 'وقت پر پہنچے', 'Everyone': 'سب',
    'Scanned at': 'اسکین کا وقت', 'Roll': 'رول',
    'Students in this class': 'اس کلاس کے طلبہ', 'Students in the school': 'اسکول کے طلبہ',
    'Find a student': 'طالب علم تلاش کریں',
    'Mark absent by itself': 'خود بخود غیر حاضر لگائیں',
    'At what time?': 'کس وقت؟',
    'Should it ask you first?': 'کیا پہلے آپ سے پوچھے؟',
    'Safety check (%)': 'حفاظتی جانچ (%)',
    'Save these settings': 'یہ ترتیبات محفوظ کریں',
    'No, do not mark anyone': 'نہیں، کسی کو غیر حاضر نہ لگائیں',
    'Auto-absent is waiting for approval': 'خودکار غیر حاضری آپ کی منظوری کی منتظر ہے',
})


# --- Financial Insights page (plain-language redesign) ---------------------------------
UR.update({
    'What changed since last month, and what to do about it.':
        'پچھلے مہینے کے بعد کیا بدلا، اور آپ کو کیا کرنا ہے۔',
    'Show month': 'مہینہ دکھائیں',
    'What to do': 'کیا کرنا ہے',
    'The list below says what to do.': 'نیچے فہرست میں لکھا ہے کہ کیا کرنا ہے۔',
    'Insights compare this month with last month. When last month has records, the comparison will appear here.':
        'یہ صفحہ اس مہینے کا پچھلے مہینے سے موازنہ کرتا ہے۔ جب پچھلے مہینے کا ریکارڈ ہوگا تو موازنہ یہاں نظر آئے گا۔',
    'Nothing needs your attention.': 'کسی چیز پر توجہ کی ضرورت نہیں۔',
    'Fees paid this month': 'اس مہینے ادا ہونے والی فیس',
    'Old dues paid this month': 'اس مہینے ادا ہونے والے پرانے بقایا',
    'Unpaid fees from earlier months that were paid this month.':
        'پچھلے مہینوں کی غیر ادا شدہ فیس جو اس مہینے ادا ہوئی۔',
    'No old dues are left unpaid.': 'کوئی پرانا بقایا باقی نہیں۔',
    'Salaries vs money received': 'تنخواہیں اور موصول رقم',
    'No money was received this month.': 'اس مہینے کوئی رقم موصول نہیں ہوئی۔',
    'Net Position': 'خالص پوزیشن',
    'Money received minus money paid out.': 'موصول رقم منفی ادا کی گئی رقم۔',
    "Simple steps, based on this month's records": 'اس مہینے کے ریکارڈ کی بنیاد پر آسان اقدامات',
    'See who owes': 'دیکھیں کس کے ذمے ہے',
    'Send reminders': 'یاد دہانی بھیجیں',
    'Open expenses': 'اخراجات کھولیں',
    'Open inventory': 'اسٹاک کھولیں',
    'Open Financial Overview': 'مالی جائزہ کھولیں',
    'What changed since last month': 'پچھلے مہینے کے بعد کیا بدلا',
    'Shop and stock': 'دکان اور اسٹاک',
    'Shop sales': 'دکان کی فروخت',
    'Already included in the money received.': 'موصول رقم میں پہلے سے شامل۔',
    'Cost of items sold': 'بکنے والی اشیاء کی لاگت',
    'What the items that left the shelf cost you.': 'جو اشیاء بک گئیں ان کی اپنی خرید کی لاگت۔',
    'What the school earned minus salaries, running costs and the cost of items sold. An estimate, not money moved.':
        'اسکول نے جو کمایا، منفی تنخواہیں، روزمرہ اخراجات اور بکنے والی اشیاء کی لاگت۔ یہ اندازہ ہے، رقم کی نقل و حرکت نہیں۔',
    'Stock bought': 'خریدا گیا اسٹاک',
    'Money paid out, but not an expense. The cost is counted when items sell.':
        'ادا کی گئی رقم، مگر خرچ نہیں۔ لاگت تب گنی جاتی ہے جب اشیاء بکتی ہیں۔',
    'See more details': 'مزید تفصیل دیکھیں',
    '\u00b7 spending by type, students who left': '\u00b7 قسم کے لحاظ سے اخراجات، چھوڑ جانے والے طلبہ',
    'Spending by type': 'قسم کے لحاظ سے اخراجات',
    'Last month': 'پچھلا مہینہ',
    'Salaries are not included here.': 'تنخواہیں اس میں شامل نہیں۔',
    'Students who have left': 'چھوڑ جانے والے طلبہ',
    'Fees no longer coming in': 'جو فیس اب نہیں آ رہی',
    'A guess of the monthly fees that are no longer being billed. It is not a loss.':
        'ان ماہانہ فیسوں کا اندازہ جو اب بل نہیں ہو رہیں۔ یہ نقصان نہیں ہے۔',
})

HTML_SENTENCES.append(
    ('Read the <b>short answer</b> first, then do what is listed under <b>What to do</b>.',
     'پہلے <b>مختصر جواب</b> پڑھیں، پھر <b>کیا کرنا ہے</b> میں لکھے کام کریں۔'))

_MONTH_YEAR = r'(%s) (\d{4})' % '|'.join(_MONTHS)


def _my(month, year):
    return '%s %s' % (MONTH_UR[month], year)


def _better(word):
    return 'بہتر' if word in ('better', 'Better than') else 'کم'


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
# --- Software License page (redesign) ---
UR.update({
    'Software License': 'سافٹ ویئر لائسنس',
    'Activate your license to begin setting up the school.': 'اسکول کی سیٹنگ شروع کرنے کے لیے اپنا لائسنس فعال کریں۔',
    'See whether your program is up to date, and enter a new key to renew.':
        'دیکھیں کہ آپ کا پروگرام درست چل رہا ہے یا نہیں، اور تجدید کے لیے نئی کلید درج کریں۔',
    'Licensed to': 'لائسنس یافتہ', 'Valid until': 'درست تاریخ تک', 'Ended': 'ختم ہو گیا',
    'After this date the program only opens': 'اس تاریخ کے بعد پروگرام صرف کھلے گا',
    'You can still look at everything, but nothing can be changed.': 'آپ سب کچھ دیکھ سکتے ہیں، مگر کچھ بدلا نہیں جا سکے گا۔',
    'Technical details (for your software provider)': 'تکنیکی تفصیل (آپ کے سافٹ ویئر فراہم کنندہ کے لیے)',
    'License ID': 'لائسنس آئی ڈی', 'Issued': 'جاری ہوا', 'Key revision': 'کلید کا ورژن',
    'Message from your software provider:': 'آپ کے سافٹ ویئر فراہم کنندہ کا پیغام:', 'Time to renew:': 'تجدید کا وقت:',
    'Contact your software provider and enter the new key below.': 'اپنے سافٹ ویئر فراہم کنندہ سے رابطہ کریں اور نئی کلید نیچے درج کریں۔',
    'Inspection mode is on': 'معائنہ موڈ آن ہے', 'End inspection now': 'معائنہ ابھی ختم کریں',
    'Activate your license': 'اپنا لائسنس فعال کریں', 'Renew or enter a new key': 'تجدید کریں یا نئی کلید درج کریں',
    'Three simple steps. The key comes from your software provider.': 'تین آسان مراحل۔ کلید آپ کے سافٹ ویئر فراہم کنندہ سے ملتی ہے۔',
    "This computer's code": 'اس کمپیوٹر کا کوڈ', 'Copy': 'کاپی', 'Copied': 'کاپی ہو گیا',
    'License key': 'لائسنس کلید', '…or choose the key file': '…یا کلید کی فائل چنیں',
    'Activate': 'فعال کریں', 'Included features': 'شامل خصوصیات',
    'Your features will be listed here once a license is activated.': 'لائسنس فعال ہونے کے بعد آپ کی خصوصیات یہاں نظر آئیں گی۔',
    'WhatsApp messages': 'واٹس ایپ پیغامات', 'This month': 'اس مہینے',
    "How many messages you have sent against your plan's limit.": 'آپ کے پلان کی حد کے مقابلے میں کتنے پیغامات بھیجے گئے۔',
    'No message limit on this license.': 'اس لائسنس میں پیغامات کی کوئی حد نہیں۔',
})
# --- Change Password window + Documents page (redesign) ---
UR.update({
    'Choose a new password for your own login.': 'اپنے لاگ ان کے لیے نیا پاس ورڈ چنیں۔',
    'Your current password': 'آپ کا موجودہ پاس ورڈ', 'New password': 'نیا پاس ورڈ',
    'At least 8 characters': 'کم از کم 8 حروف', 'At least one letter': 'کم از کم ایک حرف',
    'At least one number': 'کم از کم ایک ہندسہ', 'Type the new password again': 'نیا پاس ورڈ دوبارہ لکھیں',
    'Both passwords are the same': 'دونوں پاس ورڈ ایک جیسے ہیں', 'The two passwords are different': 'دونوں پاس ورڈ مختلف ہیں',
    'Documents': 'دستاویزات',
    'Print ID cards and certificates for your students and staff.': 'اپنے طلبہ اور عملے کے آئی ڈی کارڈ اور سرٹیفکیٹ پرنٹ کریں۔',
    'Pick what you want to print, say who it is for, then press the download button.':
        'چنیں کیا پرنٹ کرنا ہے، بتائیں کس کے لیے ہے، پھر ڈاؤن لوڈ کا بٹن دبائیں۔',
    'You get a PDF that is ready to print. School name, logo and address from Settings are added for you.':
        'آپ کو پرنٹ کے لیے تیار پی ڈی ایف ملتی ہے۔ اسکول کا نام، لوگو اور پتہ ترتیبات سے خود شامل ہو جاتے ہیں۔',
    'Available records': 'دستیاب ریکارڈ', 'Staff': 'عملہ', '1. What do you want to print?': '1. آپ کیا پرنٹ کرنا چاہتے ہیں؟',
    'For one student, a class or everyone': 'ایک طالب علم، کلاس یا سب کے لیے', 'For one teacher or all staff': 'ایک استاد یا تمام عملے کے لیے',
    'Bonafide, character, leaving, merit': 'بونافائڈ، کردار، اسکول چھوڑنا، اعزازی',
    "Choose who the cards are for. Each card carries the student's photo, name, class and roll number.":
        'چنیں کارڈ کس کے لیے ہیں۔ ہر کارڈ پر طالب علم کی تصویر، نام، کلاس اور رول نمبر ہوتا ہے۔',
    'Who is it for?': 'یہ کس کے لیے ہے؟', 'Everyone': 'سب', 'A whole class': 'پوری کلاس', 'One student': 'ایک طالب علم',
    'All staff': 'تمام عملہ', 'One teacher': 'ایک استاد', 'Teacher': 'استاد', '(helps you find the student)': '(طالب علم تلاش کرنے میں مدد)',
    '— Choose a student —': '— طالب علم چنیں —', '— Choose a teacher —': '— استاد چنیں —', '— Choose a class —': '— کلاس چنیں —',
    'Academic session': 'تعلیمی سیشن', 'Student': 'طالب علم', 'Download student cards': 'طلبہ کے کارڈ ڈاؤن لوڈ کریں',
    'Download staff cards': 'عملے کے کارڈ ڈاؤن لوڈ کریں', 'Download certificates PDF': 'سرٹیفکیٹ پی ڈی ایف ڈاؤن لوڈ کریں',
    'Print one teacher\'s card, or the cards of all active staff at once.': 'ایک استاد کا کارڈ پرنٹ کریں، یا تمام فعال عملے کے کارڈ ایک ساتھ۔',
    'Pick the kind of certificate, then who it is for. School name, logo, address and phone from Settings are printed automatically.':
        'سرٹیفکیٹ کی قسم چنیں، پھر بتائیں کس کے لیے ہے۔ اسکول کا نام، لوگو، پتہ اور فون ترتیبات سے خود چھپ جاتے ہیں۔',
    'Please choose a class.': 'براہ کرم کلاس چنیں۔', 'Please choose a student.': 'براہ کرم طالب علم چنیں۔',
    'Please choose a teacher.': 'براہ کرم استاد چنیں۔', 'For the school office': 'اسکول آفس کے لیے',
})
# --- School Settings page (redesign) ---
UR.update({
    'School Settings': 'اسکول کی ترتیبات',
    "Your school's details, timings, extra form fields and connected services.": 'آپ کے اسکول کی تفصیل، اوقات، اضافی فارم خانے اور منسلک سروسز۔',
    'Pick a tab, change what you need, then press the green Save button of that section.':
        'ایک ٹیب چنیں، جو بدلنا ہے بدلیں، پھر اسی حصے کا سبز محفوظ کریں بٹن دبائیں۔',
    'Each section saves on its own, so a change is only kept after you press its Save.':
        'ہر حصہ الگ محفوظ ہوتا ہے، اس لیے تبدیلی تبھی رہتی ہے جب آپ اس کا محفوظ بٹن دبائیں۔',
    'General School Info': 'اسکول کی عمومی معلومات', 'Academic Timings': 'تعلیمی اوقات',
    'Custom Fields Manager': 'اضافی خانوں کا انتظام', 'System Integrations': 'سسٹم کنکشنز',
    'School Identity': 'اسکول کی شناخت',
    'Your name and logo appear on the sidebar, receipts, report cards, ID cards and certificates.':
        'آپ کا نام اور لوگو سائیڈ بار، رسیدوں، رپورٹ کارڈ، آئی ڈی کارڈ اور سرٹیفکیٹ پر آتا ہے۔',
    'School name': 'اسکول کا نام', 'Tagline / Motto': 'نعرہ / مقصد', 'School logo': 'اسکول کا لوگو',
    '(PNG, JPG or WEBP — optional)': '(پی این جی، جے پی جی یا ویب پی — اختیاری)', 'Your current logo': 'آپ کا موجودہ لوگو',
    'Choose a new picture only if you want to replace the current logo.': 'نئی تصویر تب چنیں جب موجودہ لوگو بدلنا ہو۔',
    'Brand Colors': 'برانڈ کے رنگ', 'The whole program, and your printed papers, use these two colors.': 'پورا پروگرام اور آپ کے پرنٹ شدہ کاغذات یہی دو رنگ استعمال کرتے ہیں۔',
    'Main color': 'بنیادی رنگ', 'Second color': 'دوسرا رنگ', 'Go back to the standard colors': 'معیاری رنگوں پر واپس جائیں',
    'Contact Details': 'رابطے کی تفصیل', 'Printed at the top of receipts and certificates. All three are optional.':
        'رسیدوں اور سرٹیفکیٹ کے اوپر چھپتی ہے۔ تینوں اختیاری ہیں۔',
    'Phone': 'فون', 'Email': 'ای میل', 'Admission Numbers': 'داخلہ نمبر',
    'Every student gets a number like': 'ہر طالب علم کو اس طرح کا نمبر ملتا ہے:',
    'Starts with (prefix)': 'شروع میں (پریفکس)', 'Digits': 'ہندسے', 'Start from': 'یہاں سے شروع',
    'Press Save to keep your changes in this tab.': 'اس ٹیب کی تبدیلیاں رکھنے کے لیے محفوظ کریں دبائیں۔',
    'Save School Info': 'اسکول کی معلومات محفوظ کریں', 'Students without an Admission No': 'بغیر داخلہ نمبر والے طلبہ',
    'Every student already has an Admission No.': 'ہر طالب علم کے پاس پہلے سے داخلہ نمبر ہے۔',
    'Sidebar Preview': 'سائیڈ بار کا نمونہ', 'This is how your school looks on the left menu. It changes as you type.':
        'بائیں مینو میں آپ کا اسکول ایسا نظر آئے گا۔ لکھتے ہی یہ بدلتا ہے۔',
    'School Day': 'اسکول کا دن',
    'The session and the daily timing are used to pre-fill reports, documents and attendance.':
        'سیشن اور روزانہ کا وقت رپورٹس، دستاویزات اور حاضری میں پہلے سے بھرے جاتے ہیں۔',
    'Attendance Rules': 'حاضری کے اصول',
    'How late arrivals are shown and how the attendance percentage is worked out.': 'دیر سے آنے والے کیسے دکھیں اور حاضری کا فیصد کیسے نکلے۔',
    'Days Off & Holidays': 'چھٹیوں کے دن اور تعطیلات',
    'The school is closed on these days. They are never counted as attendance days.': 'ان دنوں اسکول بند ہوتا ہے۔ یہ حاضری کے دنوں میں شمار نہیں ہوتے۔',
    'School is closed every Saturday.': 'اسکول ہر ہفتے بند رہتا ہے۔', 'School is closed every Sunday.': 'اسکول ہر اتوار بند رہتا ہے۔',
    'Name (e.g. Summer Vacations)': 'نام (مثلاً گرمیوں کی چھٹیاں)', 'From': 'از', 'To': 'تا', 'Remove': 'ہٹائیں',
    'Timetable Periods': 'ٹائم ٹیبل کے پیریڈ', 'Saved here once so the timetable can use them automatically.': 'یہاں ایک بار محفوظ کریں تاکہ ٹائم ٹیبل خود استعمال کرے۔',
    'Save Academic Settings': 'تعلیمی ترتیبات محفوظ کریں', 'Grading Scale': 'گریڈنگ اسکیل',
    'Write the lowest percentage needed for each grade. For example, A+ from 85 means anyone with 85% or more gets A+.':
        'ہر گریڈ کے لیے کم از کم فیصد لکھیں۔ مثلاً A+ کے لیے 85 کا مطلب ہے 85% یا زیادہ پر A+ ملے گا۔',
    'Save Grading Scale': 'گریڈنگ اسکیل محفوظ کریں', 'Add Grade': 'گریڈ شامل کریں', 'Add Field': 'خانہ شامل کریں',
    'Add Holiday Range': 'چھٹیوں کی مدت شامل کریں',
    'Short name': 'مختصر نام', 'Label on form': 'فارم پر عنوان', 'Required': 'لازمی',
    'Student Custom Fields': 'طلبہ کے اضافی خانے', 'Teacher Custom Fields': 'اساتذہ کے اضافی خانے',
    'Save Student Fields': 'طلبہ کے خانے محفوظ کریں', 'Save Teacher Fields': 'اساتذہ کے خانے محفوظ کریں',
    'WhatsApp Messaging': 'واٹس ایپ پیغامات', 'Open WhatsApp Center': 'واٹس ایپ سینٹر کھولیں',
    'Connect WhatsApp to send fee reminders and attendance messages, and to approve messages before they go out.':
        'فیس کی یاد دہانی اور حاضری کے پیغامات بھیجنے، اور بھیجنے سے پہلے پیغامات منظور کرنے کے لیے واٹس ایپ جوڑیں۔',
    'Backups': 'بیک اپ', 'Back up now': 'ابھی بیک اپ لیں',
    'A backup is a safe copy of all your school data. Keep a recent one on a USB drive or another computer.':
        'بیک اپ آپ کے اسکول کے تمام ڈیٹا کی محفوظ کاپی ہے۔ ایک حالیہ کاپی یو ایس بی یا دوسرے کمپیوٹر میں رکھیں۔',
    'File': 'فائل', 'Created (local)': 'بنایا گیا (مقامی)', 'Size': 'سائز', 'Download': 'ڈاؤن لوڈ',
})
UR.update({
    'Choose a topic on the left, change what you need, then press Save.': 'بائیں طرف سے موضوع چنیں، جو بدلنا ہے بدلیں، پھر محفوظ کریں دبائیں۔',
    'You have unsaved changes': 'آپ کی تبدیلیاں محفوظ نہیں ہوئیں', 'Name, logo, colors, address': 'نام، لوگو، رنگ، پتہ',
    'Session, timings, holidays, grades': 'سیشن، اوقات، تعطیلات، گریڈ', 'Extra boxes on student and teacher forms': 'طلبہ اور اساتذہ کے فارم کے اضافی خانے',
    'WhatsApp and backups': 'واٹس ایپ اور بیک اپ', 'School': 'اسکول', 'Contact': 'رابطہ', 'Printed at the top of every paper.': 'ہر کاغذ کے اوپر چھپتا ہے۔',
    'How it looks on the menu': 'مینو میں کیسا نظر آتا ہے', 'Changes as you type.': 'لکھتے ہی بدلتا ہے۔', 'Standard colors': 'معیاری رنگ',
    'Pattern': 'پیٹرن', 'Preview': 'پیش نظارہ', 'School timings': 'اسکول کے اوقات', 'Back up your data': 'اپنا ڈیٹا بیک اپ کریں',
    'Automatic backups': 'خودکار بیک اپ', 'Lowest percentage for each grade': 'ہر گریڈ کے لیے کم از کم فیصد',
})
UR.update({
    # Sidebar group headings and the keyboard "skip" link
    'Academics': 'تعلیم', 'Assessment': 'امتحانات اور نتائج', 'Documents & Messages': 'دستاویزات اور پیغامات',
    'System': 'سسٹم', 'Skip to main content': 'مرکزی صفحے پر جائیں',
})
UR.update({
    # Sidebar quick find
    'Find a page': 'صفحہ تلاش کریں', 'Find a page in the menu': 'مینو میں صفحہ تلاش کریں', 'No page found': 'کوئی صفحہ نہیں ملا',
})
UR.update({
    # Admission Fees register: phone card labels
    'Joined': 'شمولیت', 'Total fee': 'کل فیس', 'Still to collect': 'ابھی وصول کرنا باقی',
})
