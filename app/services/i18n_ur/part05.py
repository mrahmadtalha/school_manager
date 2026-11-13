"""Case-insensitive folding of Urdu/English text (diacritics-insensitive lookup)."""

from .part01 import UR
from .part04 import MONTH_UR, PATTERNS, WEEKDAY_UR, _MONTHS, _PC, _RS, _W, _isolate, _n


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
