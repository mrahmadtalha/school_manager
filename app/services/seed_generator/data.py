"""Name pools, picklists and weights the generator draws fabricated data from."""


CLASS_LEVELS = [  # (name, base monthly fee multiplier level, typical age)
    ('Playgroup', 0, 3), ('Nursery', 0, 4),
    ('Class 1', 1, 5), ('Class 2', 1, 6), ('Class 3', 2, 7), ('Class 4', 2, 8),
    ('Class 5', 3, 9), ('Class 6', 3, 10), ('Class 7', 4, 11), ('Class 8', 4, 12),
    ('Class 9', 5, 13), ('Class 10', 5, 14),
]


CLASS_NAMES = [name for name, _, _ in CLASS_LEVELS]


SECTION_NAMES = ('A', 'B')


SUBJECT_NAMES = ['English', 'Urdu', 'Mathematics', 'Science', 'Islamiyat']


TEST_TYPE_NAMES = ['Daily', 'Weekly', 'Monthly', 'Mid-Term', 'Final']


FIRST_NAMES_MALE = ['Ali', 'Ahmed', 'Hassan', 'Hussain', 'Bilal', 'Hamza', 'Zain',
                    'Usman', 'Adeel', 'Umar', 'Imran', 'Talha', 'Salman', 'Danish',
                    'Fahad', 'Junaid', 'Kashif', 'Naveed', 'Saad', 'Waqas']


FIRST_NAMES_FEMALE = ['Ayesha', 'Fatima', 'Maryam', 'Sana', 'Hira', 'Zainab',
                      'Rabia', 'Amna', 'Mahnoor', 'Iqra', 'Laiba', 'Noor',
                      'Hafsa', 'Iqra', 'Sadia', 'Alina', 'Mehak', 'Sidra']


LAST_NAMES = ['Khan', 'Awan', 'Malik', 'Rana', 'Qureshi', 'Abbasi', 'Butt',
              'Sheikh', 'Chaudhry', 'Nawaz', 'Iqbal', 'Farooq']


FATHER_FIRST = ['Muhammad', 'Abdul', 'Ghulam', 'Raja', 'Sheikh', 'Mian', 'Syed']


STREETS = ['Main Bazaar', 'College Road', 'Satellite Town', 'Jinnah Colony',
           'Circular Road', 'Model Town', 'Railway Road', 'Kacheri Bazaar']


CITIES = ['Sargodha', 'Faisalabad', 'Lahore', 'Rawalpindi', 'Multan']


QUALIFICATIONS = ['B.Ed', 'M.Ed', 'M.Sc Mathematics', 'MA English', 'MA Urdu',
                  'B.S Computer Science', 'M.Phil Physics', 'B.A, B.Ed']


DESIGNATIONS = ['Junior Teacher', 'Subject Teacher', 'Senior Teacher',
                'Section Coordinator', 'Head Teacher']


LEAVING_REASONS = ['Migration to another city', 'Transferred to another school',
                   'Family financial reasons', 'Personal family reasons',
                   'Relocated abroad']


TEACHER_GENDER_POOL = (['Female'] * 6) + (['Male'] * 4)


# Per-person behaviour profiles: probabilities for a school day.
STUDENT_PROFILES = [
    ('excellent', {'Present': 0.93, 'Late': 0.04, 'Absent': 0.015, 'Leave': 0.015}),
    ('regular',   {'Present': 0.86, 'Late': 0.05, 'Absent': 0.06,  'Leave': 0.03}),
    ('casual',    {'Present': 0.71, 'Late': 0.09, 'Absent': 0.14,  'Leave': 0.06}),
]


PROFILE_PICK_WEIGHTS = (35, 45, 20)


PAYMENT_PROFILES = ['prompt', 'regular', 'late', 'defaulter']


PAYMENT_PICK_WEIGHTS = (40, 35, 15, 10)


EXPENSE_AMOUNTS = {
    'Utilities': (8000, 15000),
    'Building/Rent': (15000, 25000),
    'Maintenance': (500, 8000),
    'Stationery & Printing': (500, 4000),
    'Refreshment/Events': (1000, 6000),
    'Miscellaneous': (300, 2500),
}


EXPENSE_NOTES = ['Monthly utility bill', 'Campus repair work', 'Exam stationery purchase',
                 'Staff refreshment', 'Generator diesel', 'Classroom cleaning supplies',
                 'Water supply bill', 'Furniture repair']


AVATAR_PALETTE = [(78, 115, 223), (28, 155, 135), (231, 111, 81), (246, 174, 45),
                  (105, 74, 177), (41, 128, 185), (192, 57, 43), (39, 174, 96)]


# Relative size of each stage, used only for the global progress percentage.
_STAGE_WEIGHTS = [
    ('structure', 2), ('teachers', 3), ('students', 10), ('inventory', 4),
    ('admission', 4), ('attendance', 30), ('fees', 14), ('expenses', 2),
    ('class_tests', 8), ('term_exams', 7), ('remarks', 1), ('payroll', 5),
    ('other_income', 1), ('canteen', 1), ('documents', 1), ('school_life', 2),
    ('photos', 2), ('accounts', 1),
]


_BULK_CHUNK = 4000


# --------------------------------------------------------------------------- #
# Extended demo data: admission, inventory, canteen, documents, school life
# --------------------------------------------------------------------------- #

DEFAULT_ADMISSION_FEE = 5000.0

# Classes whose admission fee differs from the school default (others follow it).
CLASS_ADMISSION_OVERRIDES = {'Playgroup': 3000.0, 'Nursery': 3000.0, 'Class 10': 7500.0}

ADMISSION_CONCESSION_NOTES = ['Sibling concession', 'Staff member\'s child', 'Merit scholarship',
                              'Principal\'s approval', 'Orphan / needy family']

UNIFORM_SETS_AT_ADMISSION = 2

SUPPLIERS = ['Ali Book Depot', 'Madina Stationers', 'Al-Noor Uniform House',
             'Paramount Traders', 'City Paper Mart']

# (name, category, sale price, cost, reorder level, supplier)
UNIFORM_PRODUCTS = [
    ('Junior Shirt', 'Uniform', 650, 470, 15, 'Al-Noor Uniform House'),
    ('Junior Trouser / Shalwar', 'Uniform', 750, 540, 15, 'Al-Noor Uniform House'),
    ('Senior Shirt', 'Uniform', 850, 610, 15, 'Al-Noor Uniform House'),
    ('Senior Trouser / Shalwar', 'Uniform', 950, 690, 15, 'Al-Noor Uniform House'),
    ('School Tie', 'Uniform', 150, 95, 20, 'Al-Noor Uniform House'),
    ('School Sweater', 'Uniform', 1400, 1020, 10, 'Al-Noor Uniform House'),
]

STATIONERY_PRODUCTS = [
    ('Notebook 200 pages', 'Stationery', 120, 85, 40, 'City Paper Mart'),
    ('Notebook 100 pages', 'Stationery', 70, 48, 40, 'City Paper Mart'),
    ('Geometry Box', 'Stationery', 250, 170, 15, 'Madina Stationers'),
    ('Ball Pen (pack of 10)', 'Stationery', 100, 65, 25, 'Madina Stationers'),
    ('Pencil Box', 'Stationery', 180, 120, 15, 'Madina Stationers'),
    ('School Diary', 'Stationery', 160, 105, 20, 'City Paper Mart'),
    ('Water Bottle', 'Accessories', 350, 240, 12, 'Paramount Traders'),
    ('School Bag', 'Accessories', 1800, 1300, 8, 'Paramount Traders'),
]

RETIRED_PRODUCT = ('Old Edition Pencil Case', 'Stationery', 150, 100, 0, 'Madina Stationers')

OTHER_INCOME_ITEMS = [
    ('Events', 'Annual Sports Day - stall rent', (8000, 25000)),
    ('Events', 'Parents\' day - tickets', (5000, 15000)),
    ('Trips', 'Educational trip - transport share', (12000, 45000)),
    ('Activities', 'Science exhibition - registration', (3000, 12000)),
    ('Activities', 'Art competition - entry fee', (2000, 8000)),
    ('Miscellaneous', 'Old newspaper / scrap sale', (800, 3500)),
    ('Miscellaneous', 'Photocopy service', (500, 2500)),
    ('Miscellaneous', 'Playground booking by local club', (3000, 9000)),
]

EXTRA_CHARGE_EVENTS = [('Annual Function', 500.0), ('Picnic', 800.0), ('Sports Day', 300.0),
                       ('Science Fair', 400.0), ('Milad Gathering', 200.0)]

CANTEEN_SUPPLIERS = ['Lahori Bakers', 'Fresh Fruit Corner', 'Punjab Dairy', 'Mian Juice & Snacks']

CANTEEN_PURCHASE_NOTES = ['Biscuits and chips', 'Juice cartons', 'Samosa / roll supplies',
                          'Milk and yoghurt', 'Fruit chaat items', 'Cold drinks']

DOCUMENT_FEES = {'id_card': '200', 'id_card_dup': '300', 'cert': '300', 'cert_dup': '500'}

REMARK_TEXT = {
    'excellent': ['Outstanding performance. Keep it up!', 'Very hardworking and attentive in class.',
                  'Excellent results; a role model for classmates.'],
    'good': ['Good effort this term. Can do even better with regular revision.',
             'Satisfactory progress. Needs a little more practice in Mathematics.',
             'Well behaved and polite. Keep working steadily.'],
    'weak': ['Needs to improve attendance and homework regularity.',
             'Weak in written work. Parents are requested to meet the class teacher.',
             'Should give more time to studies at home.'],
}

CUSTOM_FIELDS = {
    'student': [
        {'name': 'blood_group', 'label': 'Blood Group', 'type': 'text'},
        {'name': 'bus_route', 'label': 'Bus Route', 'type': 'text'},
        {'name': 'previous_school', 'label': 'Previous School', 'type': 'text'},
        {'name': 'siblings_in_school', 'label': 'Siblings in School', 'type': 'number'},
    ],
    'teacher': [
        {'name': 'blood_group', 'label': 'Blood Group', 'type': 'text'},
        {'name': 'marital_status', 'label': 'Marital Status', 'type': 'text'},
    ],
}

CUSTOM_FIELD_VALUES = {
    'blood_group': ['A+', 'B+', 'O+', 'AB+', 'A-', 'B-', 'O-'],
    'bus_route': ['Route 1 - Satellite Town', 'Route 2 - College Road', 'Route 3 - Model Town',
                  'Route 4 - Railway Road', 'Walks to school'],
    'previous_school': ['Beaconhouse', 'City School', 'Govt. Primary School', 'Al-Huda Academy',
                        'First admission'],
    'marital_status': ['Married', 'Single'],
}

# Public holidays used for the demo calendar: (month, day, label).
DEMO_HOLIDAYS = [(8, 14, 'Independence Day'), (11, 9, 'Iqbal Day'), (12, 25, 'Quaid-e-Azam Day'),
                 (3, 23, 'Pakistan Day'), (5, 1, 'Labour Day')]

DEMO_USERS = [
    ('accountant1', 'accountant', 'Demo Accountant'),
    ('principal1', 'owner', 'Demo Principal'),
    ('guard1', 'guard', 'Demo Gate Guard'),
]

PAYMENT_METHODS_MIX = ['cash', 'cash', 'cash', 'bank', 'online']
