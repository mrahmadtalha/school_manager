"""Urdu wording for the interface (English text -> Urdu).

Keys are the exact English text as it appears on screen (whitespace collapsed).
This is a package of small files purely because of file-size limits in the
product build's obfuscator; it is one dictionary built the same way as before
(a literal plus a long sequence of ``.update()`` calls), just spread over
several files that run in order. Add a line to any part file to translate
more text; nothing else needs to change.
"""

from . import (  # noqa: F401  (each import runs that part's updates, in order)
    part01, part02, part03, part04, part05, part06, part07, part08, part09, part10, 
    part11, part12, part13, part14, part15, part16
)

UR = part01.UR
PATTERNS = part04.PATTERNS
HTML_SENTENCES = part07.HTML_SENTENCES
MONTH_UR = part04.MONTH_UR
WEEKDAY_UR = part04.WEEKDAY_UR
UR_FOLDED = part09.UR_FOLDED
_MONTHS = part04._MONTHS
_MONTHS_UR = part04._MONTHS_UR
_M = part04._M
_RS = part04._RS
_PC = part04._PC
_n = part04._n
_isolate = part04._isolate
_fold = part05._fold
_M3 = part06._M3
_M3_UR = part06._M3_UR
_per_month = part06._per_month
_period_ur = part09._period_ur
_dues_title = part09._dues_title
_current_filters = part09._current_filters
_MONTH_YEAR = part10._MONTH_YEAR
_my = part10._my
_better = part10._better
_W = part04._W
_W_UR = part04._W_UR
