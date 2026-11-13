"""Limits, the logger and the word lists the assistant's NLU and handlers share."""

import logging


MAX_QUESTION_LENGTH = 300


MAX_LIST_ROWS = 15


MAX_CONTEXT_LENGTH = 600        # the follow-up memory the browser sends back


AT_RISK_PERCENT = 75.0          # same line the attendance summary page uses


PAYROLL_REMINDER_DAY = 25       # "payroll not generated" is only nagged late in the month


log = logging.getLogger(__name__)


MONTHS = {
    'january': 1, 'february': 2, 'march': 3, 'april': 4, 'may': 5, 'june': 6,
    'july': 7, 'august': 8, 'september': 9, 'october': 10, 'november': 11,
    'december': 12,
    'jan': 1, 'feb': 2, 'apr': 4, 'jun': 6, 'jul': 7, 'aug': 8, 'sep': 9,
    'sept': 9, 'oct': 10, 'nov': 11, 'dec': 12,
}


PREVIOUS_WORDS = {'pichle', 'pichla', 'pichlay', 'pichli', 'previous', 'last',
                  'guzishta', 'guzra', 'guzri'}


MONTH_WORDS = {'mahine', 'mahina', 'month', 'mah', 'maheena', 'maheene'}


THIS_WORDS = {'is', 'this', 'isi', 'current', 'maujooda', 'iss'}


TODAY_WORDS = {'aaj', 'today', 'ajj', 'آج'}


YESTERDAY_WORDS = {'kal', 'yesterday', 'کل'}


TEACHER_WORDS = {'teacher', 'teachers', 'ustad', 'ustaad', 'asatza',
                 'asatiza', 'staff', 'استاد', 'اساتذہ'}


MALE_WORDS = {'boys', 'boy', 'larkay', 'larke', 'ladkay', 'ladke', 'larka',
              'male'}


FEMALE_WORDS = {'girls', 'girl', 'larkiyan', 'ladkiyan', 'larki', 'ladki',
                'female'}


STUDENT_WORDS = {'student', 'students', 'bachay', 'bache', 'bachon', 'talib',
                 'talaba', 'children', 'kids', 'pupils'}


# --- follow-up memory -------------------------------------------------------
# "aur kal?", "class 6 ka?", "uska phone number?" only make sense with the
# previous answer in mind.  The browser sends back the small ``context`` dict
# every answer carries, so the server itself stays stateless.
PRONOUN_WORDS = {'us', 'uska', 'uski', 'uske', 'usko', 'iska', 'iski', 'iske',
                 'unka', 'unki', 'unke', 'his', 'her', 'their', 'him', 'them'}


FOLLOW_WORDS = {'aur', 'and', 'also', 'phir', 'about', 'or'}


FOLLOWABLE = {'attendance', 'fees_collected', 'fees_due', 'expenses', 'profit',
              'salary', 'students_count', 'low_attendance', 'new_admissions',
              'class_fees', 'compare', 'fees_payments'}


STUDENT_INTENTS = {'student_info', 'fees_due', 'attendance'}
