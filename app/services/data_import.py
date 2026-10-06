"""Shared helpers for the Student / Teacher bulk import.

Everything in this module is independent of the database so it can be unit
tested on its own.  The routes (``app/routes/students.py`` and
``app/routes/teachers.py``) use it to:

* read an uploaded .xlsx / .csv file and map its column headers to fields,
* validate every cell of a row and collect *all* problems of that row,
* report the outcome (added / skipped + the reason for every skipped row),
* build the downloadable Excel templates (all current fields, one example
  row, mandatory vs optional columns clearly colour-coded).
"""

import csv
import io
import re
from datetime import date, datetime

import pandas as pd
from openpyxl import Workbook
from openpyxl.comments import Comment
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

MAX_IMPORT_ROWS = 5000
TEMPLATE_PREFILLED_ROWS = 500   # rows pre-formatted as text in the template

CNIC_PATTERN = re.compile(r'\d{5}-\d{7}-\d')
PHONE_PATTERN = re.compile(r'[\d\s+\-()]+')

_EMPTY_MARKERS = {'nan', 'none', 'null', 'nat'}


class ImportFileError(Exception):
    """The whole file cannot be imported (wrong type, missing columns...)."""


# -- field definitions --------------------------------------------------------

class FieldSpec:
    """One importable column."""

    def __init__(self, key, label, required=False, aliases=(), help_text='',
                 example='', choices=None, group='Basic', kind='text'):
        self.key = key
        self.label = label
        self.required = required
        self.aliases = tuple(aliases)
        self.help_text = help_text
        self.example = example
        self.choices = choices
        self.group = group
        self.kind = kind          # text | number | date (custom fields only)

    @property
    def header(self):
        """Header text written in the template (``*`` marks mandatory)."""
        return f'{self.label} *' if self.required else self.label


def normalize_header(value):
    """Lower-case a header and drop ``*``, '(required)', spaces and underscores."""
    text = str(value if value is not None else '').strip().lower()
    text = re.sub(r'\((required|optional|mandatory)\)', '', text)
    text = text.replace('*', '')
    text = re.sub(r'[\s_]+', ' ', text)
    return text.strip()


def _custom_specs(custom_fields, taken_headers, group_name):
    specs = []
    for field in custom_fields or ():
        if not isinstance(field, dict):
            continue
        name = (field.get('name') or '').strip()
        label = (field.get('label') or name).strip()
        if not name or not label:
            continue
        if normalize_header(label) in taken_headers:
            label = f'{label} (custom)'
        taken_headers.add(normalize_header(label))
        kind = field.get('type') or 'text'
        hint = {'date': 'Date, e.g. 2024-01-15',
                'number': 'A number'}.get(kind, 'Text')
        specs.append(FieldSpec(
            'custom:' + name, label, required=bool(field.get('is_mandatory')),
            aliases=(name,), help_text=f'School-defined field. {hint}.',
            example='', group=group_name, kind=kind))
    return specs


def student_import_fields(custom_fields=()):
    """Importable student columns, in template order."""
    specs = [
        FieldSpec('student_name', 'Student Name', True,
                  help_text='Full name of the student.', example='Ali Khan'),
        FieldSpec('father_name', 'Father Name', True,
                  aliases=('Guardian Name', 'Father / Guardian Name'),
                  help_text="Father's name (or the guardian's name when Sponsor Type is Guardian).",
                  example='Ahmad Khan'),
        FieldSpec('class_name', 'Class', True,
                  help_text='Must match one of your existing classes exactly. '
                            'See the "Your Classes" list in the Instructions sheet.',
                  example='Class 1'),
        FieldSpec('guardian_phone', 'Guardian Phone', True,
                  aliases=('Phone', 'Parent Phone'),
                  help_text='Contact number used for fee reminders and WhatsApp.',
                  example='03001234567'),
        FieldSpec('address', 'Address', True,
                  help_text='Home address.', example='Main Bazaar, Multan'),
        FieldSpec('roll_number', 'Roll Number', False, aliases=('Roll No',),
                  help_text='Whole number, starting at 1001 in each class. '
                            'LEAVE BLANK to assign the next free number automatically.',
                  example='', group='Class'),
        FieldSpec('section', 'Section', False,
                  help_text='Must already exist inside the chosen class. Leave blank if not used.',
                  example='A', group='Class'),
        FieldSpec('gender', 'Gender', False, choices=('Male', 'Female', 'Other'),
                  help_text='Male, Female or Other.', example='Male'),
        FieldSpec('date_of_birth', 'Date of Birth', False, aliases=('DOB',),
                  help_text='Format YYYY-MM-DD (or DD/MM/YYYY).', example='2015-04-20'),
        FieldSpec('admission_number', 'Admission No',
                  False, aliases=('Admission Number', 'Admission No.'),
                  help_text='School admission / registration number. Must be unique.',
                  example='ADM-2024-001'),
        FieldSpec('admission_date', 'Admission Date', False,
                  help_text='Format YYYY-MM-DD (or DD/MM/YYYY).', example='2024-04-01'),
        FieldSpec('sponsor_type', 'Sponsor Type', False, choices=('Father', 'Guardian'),
                  help_text='Father or Guardian. Leave blank for Father.', example='Father'),
        FieldSpec('sponsor_cnic', 'Sponsor CNIC', False, aliases=('CNIC',),
                  help_text='Format 12345-1234567-1.', example='36302-1234567-1'),
        FieldSpec('monthly_fee', 'Monthly Fee', False, aliases=('Fee', 'Class Fee'),
                  help_text='Fee in PKR before discount. Leave blank to use the class fee.',
                  example='2500', group='Fees'),
        FieldSpec('discount_type', 'Discount Type', False,
                  choices=('percentage', 'fixed'),
                  help_text='percentage or fixed. Only needed when there is a discount.',
                  example='percentage', group='Fees'),
        FieldSpec('discount_value', 'Discount Value', False,
                  help_text='Percent (e.g. 10) or PKR amount, matching Discount Type.',
                  example='10', group='Fees'),
    ]
    taken = {normalize_header(s.label) for s in specs}
    for spec in specs:
        taken.update(normalize_header(a) for a in spec.aliases)
    specs.extend(_custom_specs(custom_fields, taken, 'Custom'))
    return specs


def teacher_import_fields(custom_fields=()):
    """Importable teacher columns, in template order."""
    specs = [
        FieldSpec('teacher_name', 'Teacher Name', True,
                  help_text='Full name of the teacher.', example='Ayesha Malik'),
        FieldSpec('joining_date', 'Joining Date', True,
                  help_text='Format YYYY-MM-DD (or DD/MM/YYYY).', example='2024-01-15'),
        FieldSpec('qualification', 'Qualification', True,
                  help_text='Highest qualification, e.g. M.A English.', example='M.A English'),
        FieldSpec('teacher_id_str', 'Teacher ID', False, aliases=('Teacher Id', 'ID'),
                  help_text='Unique ID such as T001. LEAVE BLANK to assign the next free ID '
                            'automatically.', example=''),
        FieldSpec('designation', 'Designation', False,
                  help_text='e.g. Senior Teacher, Head Teacher, Principal.',
                  example='Senior Teacher'),
        FieldSpec('gender', 'Gender', False, choices=('Male', 'Female', 'Other'),
                  help_text='Male, Female or Other.', example='Female'),
        FieldSpec('salary_type', 'Salary Type', False, choices=('monthly', 'hourly'),
                  help_text='monthly or hourly. Leave blank for monthly.',
                  example='monthly', group='Salary'),
        FieldSpec('monthly_salary', 'Monthly Salary', False, aliases=('Salary',),
                  help_text='PKR per month (used when Salary Type is monthly).',
                  example='45000', group='Salary'),
        FieldSpec('hourly_rate', 'Hourly Rate', False,
                  help_text='PKR per hour (used when Salary Type is hourly).',
                  example='', group='Salary'),
        FieldSpec('date_of_birth', 'Date of Birth', False, aliases=('DOB',),
                  help_text='Format YYYY-MM-DD (or DD/MM/YYYY).', example='1990-06-10'),
        FieldSpec('cnic', 'CNIC', False,
                  help_text='Format 12345-1234567-1. Must be unique.',
                  example='36302-7654321-0'),
        FieldSpec('address', 'Address', False,
                  help_text='Home address.', example='Gulgasht Colony, Multan'),
        FieldSpec('contact_number', 'Contact Number', False, aliases=('Phone', 'Contact'),
                  help_text="Teacher's phone number.", example='03211234567'),
        FieldSpec('emergency_contact_number', 'Emergency Contact Number', False,
                  aliases=('Emergency Contact',),
                  help_text='Phone number of a relative to call in an emergency.',
                  example='03007654321'),
        FieldSpec('assigned_classes', 'Assigned Classes', False,
                  aliases=('Assigned Class',),
                  help_text='One or more existing classes, separated by commas.',
                  example='Class 1, Class 2', group='Assignment'),
        FieldSpec('assigned_subjects', 'Assigned Subjects', False,
                  help_text='One or more existing subjects, separated by commas.',
                  example='English', group='Assignment'),
        FieldSpec('previous_experience_years', 'Previous Experience (Years)', False,
                  aliases=('Previous Experience',),
                  help_text='Years of earlier teaching experience.', example='3',
                  group='History'),
        FieldSpec('previous_salary', 'Previous Salary', False,
                  help_text='Salary at the previous job (PKR).', example='35000',
                  group='History'),
    ]
    taken = {normalize_header(s.label) for s in specs}
    for spec in specs:
        taken.update(normalize_header(a) for a in spec.aliases)
    specs.extend(_custom_specs(custom_fields, taken, 'Custom'))
    return specs


# -- reading the uploaded file -----------------------------------------------

class ParsedFile:
    def __init__(self, rows, ignored_columns, recognised_columns):
        self.rows = rows                          # [(sheet_row_number, {key: str})]
        self.ignored_columns = ignored_columns    # headers we did not recognise
        self.recognised_columns = recognised_columns


def _clean_cell(value):
    if value is None:
        return ''
    if isinstance(value, float) and value != value:       # NaN
        return ''
    if isinstance(value, (datetime, pd.Timestamp)):
        return value.strftime('%Y-%m-%d')
    if isinstance(value, date):
        return value.isoformat()
    text = str(value).strip()
    return '' if text.lower() in _EMPTY_MARKERS else text


def _read_raw_rows(file_storage):
    """Return (grid, header_row_index) from an .xlsx/.csv upload."""
    filename = (file_storage.filename or '').strip()
    ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''
    if ext == 'csv':
        raw = file_storage.stream.read()
        try:
            text = raw.decode('utf-8-sig')
        except UnicodeDecodeError:
            text = raw.decode('cp1252', errors='replace')
        grid = list(csv.reader(io.StringIO(text)))
    elif ext in ('xlsx', 'xls'):
        # Read the first sheet only, every cell as text so that phone numbers,
        # roll numbers and IDs are never altered (1001 -> 1001.0, 0300 -> 300).
        frame = pd.read_excel(file_storage, sheet_name=0, header=None,
                              dtype=str, keep_default_na=False)
        grid = frame.values.tolist()
    else:
        raise ImportFileError('Only .xlsx or .csv files are supported.')

    grid = [[_clean_cell(cell) for cell in row] for row in grid]
    header_index = next((i for i, row in enumerate(grid) if any(row)), None)
    if header_index is None:
        raise ImportFileError('The file is empty. Please download the template and fill it in.')
    return grid, header_index


def read_import_file(file_storage, specs):
    """Parse an upload into ``ParsedFile`` or raise ``ImportFileError``.

    Header names are matched case-insensitively and ignore ``*`` / "(required)"
    markers, so the downloaded template, an older template and the students /
    teachers *export* files are all accepted.
    """
    try:
        grid, header_index = _read_raw_rows(file_storage)
    except ImportFileError:
        raise
    except Exception as exc:                               # corrupt / wrong file
        raise ImportFileError(f'Could not read the file: {exc}')

    headers = grid[header_index]
    lookup = {}
    for spec in specs:
        for name in (spec.label, spec.header, *spec.aliases):
            lookup.setdefault(normalize_header(name), spec.key)

    column_keys = []            # index -> field key (or None when unknown)
    seen = set()
    ignored = []
    for header in headers:
        key = lookup.get(normalize_header(header)) if header else None
        if key and key in seen:                            # repeated column: first wins
            key = None
        if key:
            seen.add(key)
        elif header:
            ignored.append(header)
        column_keys.append(key)

    missing = [s.label for s in specs if s.required and s.key not in seen]
    if missing:
        raise ImportFileError(
            'Your file is missing the required column(s): ' + ', '.join(missing) +
            '. Please download the template again and keep its column headings.')

    rows = []
    for offset, cells in enumerate(grid[header_index + 1:], start=header_index + 2):
        if not any(cells):
            continue                                       # completely blank row
        record = {}
        for index, key in enumerate(column_keys):
            if key and index < len(cells):
                record[key] = cells[index]
        rows.append((offset, record))

    if not rows:
        raise ImportFileError('The file has headings but no data rows.')
    if len(rows) > MAX_IMPORT_ROWS:
        raise ImportFileError(
            f'The file has {len(rows)} rows; please import at most {MAX_IMPORT_ROWS} at a time.')
    return ParsedFile(rows, ignored, seen)


def is_example_row(record, example, keys):
    """True when ``record`` is the untouched dummy row from the template."""
    for key in keys:
        if normalize_header(record.get(key, '')) != normalize_header(example.get(key, '')):
            return False
    return True


# -- per-row validation -------------------------------------------------------

class RowChecker:
    """Collects every problem found in one row (instead of stopping at the first)."""

    def __init__(self, record, specs):
        self.record = record
        self.labels = {s.key: s.label for s in specs}
        self.missing = []
        self.problems = []

    def raw(self, key):
        return (self.record.get(key) or '').strip()

    def _label(self, key):
        return self.labels.get(key, key)

    def text(self, key, required=False, max_len=None):
        value = ' '.join(self.raw(key).split())
        if not value:
            if required:
                self.missing.append(self._label(key))
            return ''
        if max_len and len(value) > max_len:
            self.problems.append(f'{self._label(key)} is too long (maximum {max_len} characters)')
            return ''
        return value

    def long_text(self, key, required=False):
        value = self.raw(key)
        if not value and required:
            self.missing.append(self._label(key))
        return value

    def date(self, key, required=False):
        value = self.raw(key)
        if not value:
            if required:
                self.missing.append(self._label(key))
            return None
        parsed = parse_date(value)
        if parsed is None:
            self.problems.append(
                f'{self._label(key)} "{value}" is not a valid date (use YYYY-MM-DD, e.g. 2024-01-15)')
        return parsed

    def number(self, key, minimum=0.0, required=False):
        value = self.raw(key).replace(',', '')
        if not value:
            if required:
                self.missing.append(self._label(key))
            return None
        try:
            number = float(value)
        except ValueError:
            self.problems.append(f'{self._label(key)} "{self.raw(key)}" must be a number')
            return None
        if number != number or number in (float('inf'), float('-inf')):
            self.problems.append(f'{self._label(key)} "{self.raw(key)}" must be a number')
            return None
        if minimum is not None and number < minimum:
            self.problems.append(f'{self._label(key)} cannot be negative')
            return None
        return round(number, 2)

    def cnic(self, key):
        value = self.raw(key)
        if not value:
            return None
        cleaned = parse_cnic(value)
        if cleaned is None:
            self.problems.append(
                f'{self._label(key)} "{value}" is not valid (use 12345-1234567-1)')
        return cleaned

    def phone(self, key, required=False, max_len=30):
        value = ' '.join(self.raw(key).split())
        if not value:
            if required:
                self.missing.append(self._label(key))
            return ''
        if not PHONE_PATTERN.fullmatch(value) or sum(ch.isdigit() for ch in value) < 7:
            self.problems.append(f'{self._label(key)} "{value}" is not a valid phone number')
            return ''
        if len(value) > max_len:
            self.problems.append(f'{self._label(key)} is too long')
            return ''
        return value

    def choice(self, key, choices, default=None, aliases=None):
        value = self.raw(key)
        if not value:
            return default
        lookup = {c.lower(): c for c in choices}
        lookup.update({k.lower(): v for k, v in (aliases or {}).items()})
        found = lookup.get(value.lower())
        if found is None:
            self.problems.append(
                f'{self._label(key)} "{value}" must be one of: {", ".join(choices)}')
            return default
        return found

    def add_problem(self, message):
        self.problems.append(message)

    def reason(self):
        """Single human-readable sentence describing everything wrong, or ''."""
        parts = []
        if self.missing:
            parts.append('Missing required value(s): ' + ', '.join(self.missing))
        parts.extend(self.problems)
        return '; '.join(parts)


def collect_custom_values(chk, specs):
    """Validate the school-defined custom columns of a row -> ``{field_name: value}``."""
    values = {}
    for spec in specs:
        if not spec.key.startswith('custom:'):
            continue
        name = spec.key.split(':', 1)[1]
        if spec.kind == 'date':
            parsed = chk.date(spec.key, required=spec.required)
            value = parsed.isoformat() if parsed else ''
        elif spec.kind == 'number':
            number = chk.number(spec.key, minimum=None, required=spec.required)
            value = ('%g' % number) if number is not None else ''
        else:
            value = chk.text(spec.key, required=spec.required)
        if value:
            values[name] = value
    return values


def parse_date(value):
    """Parse YYYY-MM-DD, DD/MM/YYYY, DD-MM-YYYY (optionally with a time)."""
    text = str(value or '').strip()
    if not text:
        return None
    text = text.split(' ')[0].split('T')[0]
    for fmt in ('%Y-%m-%d', '%d/%m/%Y', '%d-%m-%Y', '%Y/%m/%d', '%d.%m.%Y'):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def parse_cnic(value):
    """Return CNIC as 12345-1234567-1 (accepts 13 plain digits) or ``None``."""
    text = str(value or '').strip()
    if CNIC_PATTERN.fullmatch(text):
        return text
    digits = re.sub(r'[\s-]', '', text)
    if re.fullmatch(r'\d{13}', digits):
        return f'{digits[:5]}-{digits[5:12]}-{digits[12]}'
    return None


def parse_whole_number(value):
    """``'1001'`` / ``'1001.0'`` -> 1001; anything else raises ``ValueError``."""
    text = str(value or '').strip().replace(',', '')
    if not text:
        raise ValueError('empty')
    number = float(text)
    if number != int(number):
        raise ValueError('not whole')
    return int(number)


def norm_name(value):
    """Case/space-insensitive comparison key for names."""
    return ' '.join(str(value or '').lower().split())


def split_list(value):
    """Split ``"A, B; C"`` into a de-duplicated, order-preserving list."""
    seen, items = set(), []
    for part in re.split(r'[,;\n]', str(value or '')):
        part = part.strip()
        if part and part.lower() not in seen:
            seen.add(part.lower())
            items.append(part)
    return items


# -- outcome report -----------------------------------------------------------

class ImportResult:
    def __init__(self, kind):
        self.kind = kind                 # 'student' | 'teacher'
        self.total_rows = 0
        self.added = []                  # [(row, label)]
        self.skipped = []                # [{'row', 'name', 'reason', 'type'}]
        self.warnings = []               # [(row, label, message)]
        self.ignored_columns = []
        self.example_rows = 0

    def skip(self, row, name, reason, kind='invalid'):
        self.skipped.append({'row': row, 'name': name or '—', 'reason': reason, 'type': kind})

    def warn(self, row, name, message):
        self.warnings.append({'row': row, 'name': name or '—', 'message': message})

    def count(self, kind):
        return sum(1 for item in self.skipped if item['type'] == kind)

    @property
    def added_count(self):
        return len(self.added)

    @property
    def skipped_count(self):
        return len(self.skipped)


# -- template workbook --------------------------------------------------------

_REQUIRED_FILL = PatternFill('solid', fgColor='C0392B')
_OPTIONAL_FILL = PatternFill('solid', fgColor='5D6D7E')
_EXAMPLE_FILL = PatternFill('solid', fgColor='FFF8DC')
_HEADER_FONT = Font(bold=True, color='FFFFFF', size=11)
_THIN = Side(style='thin', color='BBBBBB')
_BORDER = Border(left=_THIN, right=_THIN, top=_THIN, bottom=_THIN)


def build_template_workbook(sheet_title, specs, example, instructions_title,
                            intro_lines, lists=None, dropdowns=None):
    """Return a BytesIO holding the import template.

    * Sheet 1 - header row (red = mandatory, grey = optional), one example row,
      every cell pre-formatted as text so Excel never changes phone numbers.
    * Sheet 2 - plain-language instructions and a column-by-column guide.
    * Sheet 3 - "Lists" (classes, sections...) feeding the drop-downs.

    ``lists``     {'Classes': ['Class 1', ...]}  (written to the Lists sheet)
    ``dropdowns`` {field_key: ('list', [..])} or {field_key: ('range', 'Classes')}
    """
    wb = Workbook()
    ws = wb.active
    ws.title = sheet_title

    for col, spec in enumerate(specs, start=1):
        cell = ws.cell(row=1, column=col, value=spec.header)
        cell.fill = _REQUIRED_FILL if spec.required else _OPTIONAL_FILL
        cell.font = _HEADER_FONT
        cell.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
        cell.border = _BORDER
        status = 'MANDATORY - must be filled' if spec.required else 'Optional - may be left blank'
        note = f'{status}\n{spec.help_text}' if spec.help_text else status
        comment = Comment(note, 'School Manager')
        comment.width, comment.height = 300, 110
        cell.comment = comment

        ex = ws.cell(row=2, column=col, value=example.get(spec.key, '') or None)
        ex.fill = _EXAMPLE_FILL
        ex.font = Font(italic=True, color='7F6000')
        ex.border = _BORDER

        for row in range(2, TEMPLATE_PREFILLED_ROWS + 2):
            ws.cell(row=row, column=col).number_format = '@'

        width = max(len(spec.header), len(str(example.get(spec.key, '') or ''))) + 4
        ws.column_dimensions[get_column_letter(col)].width = max(14, min(width, 34))

    ws.row_dimensions[1].height = 34
    ws.freeze_panes = 'A2'

    # drop-downs
    if lists:
        lists_ws = wb.create_sheet('Lists')
        for col, (title, items) in enumerate(lists.items(), start=1):
            lists_ws.cell(row=1, column=col, value=title).font = Font(bold=True)
            for row, item in enumerate(items, start=2):
                lists_ws.cell(row=row, column=col, value=item)
            lists_ws.column_dimensions[get_column_letter(col)].width = 28
    list_columns = {title: get_column_letter(i)
                    for i, title in enumerate((lists or {}).keys(), start=1)}

    column_of = {spec.key: get_column_letter(i) for i, spec in enumerate(specs, start=1)}
    for key, (mode, source) in (dropdowns or {}).items():
        letter = column_of.get(key)
        if not letter:
            continue
        if mode == 'list':
            formula = '"' + ','.join(source) + '"'
        else:
            items = (lists or {}).get(source) or []
            if not items:
                continue
            formula = f"=Lists!${list_columns[source]}$2:${list_columns[source]}${len(items) + 1}"
        validation = DataValidation(type='list', formula1=formula, allow_blank=True,
                                    showErrorMessage=False)
        validation.add(f'{letter}2:{letter}{TEMPLATE_PREFILLED_ROWS + 1}')
        ws.add_data_validation(validation)

    # instructions sheet
    guide = wb.create_sheet(instructions_title, 1)
    guide['A1'] = instructions_title
    guide['A1'].font = Font(bold=True, size=16)
    row = 3
    for line in intro_lines:
        guide.cell(row=row, column=1, value=line).alignment = Alignment(wrap_text=True, vertical='top')
        guide.merge_cells(start_row=row, start_column=1, end_row=row, end_column=4)
        guide.row_dimensions[row].height = 32 if len(line) > 95 else 18
        row += 1
    row += 1
    legend_req = guide.cell(row=row, column=1, value='RED heading')
    legend_req.fill, legend_req.font = _REQUIRED_FILL, _HEADER_FONT
    guide.cell(row=row, column=2, value='MANDATORY - the row is skipped if this is empty.')
    row += 1
    legend_opt = guide.cell(row=row, column=1, value='GREY heading')
    legend_opt.fill, legend_opt.font = _OPTIONAL_FILL, _HEADER_FONT
    guide.cell(row=row, column=2, value='Optional - you may leave it blank.')
    row += 2

    for col, title in enumerate(('Column', 'Mandatory?', 'What to enter', 'Example'), start=1):
        cell = guide.cell(row=row, column=col, value=title)
        cell.font, cell.fill = _HEADER_FONT, PatternFill('solid', fgColor='2D3748')
        cell.border = _BORDER
    row += 1
    for spec in specs:
        values = (spec.label, 'YES' if spec.required else 'optional',
                  spec.help_text, example.get(spec.key, '') or '')
        for col, value in enumerate(values, start=1):
            cell = guide.cell(row=row, column=col, value=value)
            cell.border = _BORDER
            cell.alignment = Alignment(wrap_text=True, vertical='top')
            if col == 2:
                cell.font = Font(bold=spec.required, color='C0392B' if spec.required else '5D6D7E')
        row += 1

    for letter, width in zip('ABCD', (28, 13, 70, 24)):
        guide.column_dimensions[letter].width = width

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    return output
