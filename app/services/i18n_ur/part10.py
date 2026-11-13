"""Month-year labels and a helper that prefers the richer of two translations."""

from .part01 import UR
from .part04 import MONTH_UR, _MONTHS
from .part07 import HTML_SENTENCES


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
