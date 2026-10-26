"""Books: more than one set per student (price per set x number of sets)."""
from app.database import db
from app.services import admission_fee as adm
from tests.test_admission_fee import (  # noqa: F401  (fixtures are used by name)
    StudentModel, accountant_client, admin_client, teacher_client, _add_student, _student)
from tests.test_admission_items import _class_items


def test_two_sets_of_books_cost_twice_the_class_price(admin_client, seed):
    _class_items(seed, admission=2000, books=3000, uniform=1500, sets=2)
    _add_student(admin_client, seed, 3001, 'Two Sets', books_qty='2')
    student = _student(3001)
    assert (student.books_fee_paisa, student.books_qty) == (300000, 2)   # price per set, sets
    info = adm.summary(student)
    assert info['books'] == 600000 and info['books_qty'] == 2 and info['books_unit'] == 300000
    assert info['total'] == 200000 + 600000 + 300000      # admission + 2 x books + 2 x uniform


def test_zero_sets_means_no_books_and_blank_means_one(admin_client, seed):
    _class_items(seed)
    _add_student(admin_client, seed, 3002, 'No Books', books_qty='0')
    assert _student(3002).books_fee_paisa is None and adm.summary(_student(3002))['books'] == 0
    _add_student(admin_client, seed, 3003, 'Blank Sets')                   # nothing sent: one set
    assert adm.summary(_student(3003))['books'] == 300000


def test_older_forms_that_send_books_taken_still_work(admin_client, seed):
    _class_items(seed)
    _add_student(admin_client, seed, 3004, 'Old Form', books_taken='0')
    assert adm.summary(_student(3004))['books'] == 0


def test_too_many_book_sets_are_refused(admin_client, seed):
    _class_items(seed)
    _add_student(admin_client, seed, 3005, 'Too Many', books_qty='25')
    # the save is refused (and rolled back): no student with 25 sets of books is created
    assert StudentModel.query.filter_by(roll_number=3005).count() == 0


def test_payment_settles_all_book_sets_before_uniform(admin_client, seed):
    _class_items(seed, admission=2000, books=3000, uniform=1500, sets=2)
    _add_student(admin_client, seed, 3006, 'Pays Part', books_qty='2',
                 admission_received_now='1', admission_received_amount='9000')
    lines = {line['key']: line for line in adm.summary(_student(3006))['lines']}
    assert lines['books']['qty'] == 2 and lines['books']['unit'] == 300000
    assert (lines['admission']['paid'], lines['books']['paid'], lines['uniform']['paid']) == (
        200000, 600000, 100000)


def test_admin_can_change_the_number_of_book_sets_later(admin_client, seed):
    _class_items(seed)
    _add_student(admin_client, seed, 3007, 'Later')
    student = _student(3007)
    resp = admin_client.post('/admission-fees/student/%d/terms' % student.id, data={
        'admission_fee': '2000', 'books_fee': '3000', 'books_qty': '3',
        'uniform_qty': '2', 'uniform_price': '1500'})
    assert resp.status_code == 302
    db.session.expire_all()
    info = adm.summary(_student(3007))
    assert info['books'] == 900000 and info['books_qty'] == 3


def test_a_student_without_a_set_count_counts_as_one_set(admin_client, seed):
    _class_items(seed)
    _add_student(admin_client, seed, 3008, 'Legacy')
    student = _student(3008)
    student.books_qty = None                       # a record made before sets existed
    db.session.commit()
    assert adm.books_qty(student) == 1 and adm.summary(student)['books'] == 300000
