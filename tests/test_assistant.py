"""The offline admin assistant: access rules, answers from real data, read-only."""
import json
from datetime import date, timedelta

import pytest

from app.database import db
from app.models import (AttendanceModel, Expense, ExpenseCategory,
                        FeeTransaction, StudentModel, TeacherModel)
from app.services import assistant as assistant_service
from app.services.fee_ledger import ensure_charge, record_payment


def ask(client, question, context=None):
    params = {'q': question}
    if context is not None:
        params['c'] = json.dumps(context)
    response = client.get('/assistant/ask', query_string=params)
    assert response.status_code == 200
    data = response.get_json()
    assert data['ok'] is True
    return data


def _today_label():
    return date.today().strftime('%B %Y')


def _charge_both(seed):
    """Ali Khan owes Rs 2,500 and Sara Ali owes Rs 2,000 for this month."""
    for key in ('student_id', 'other_student_id'):
        student = db.session.get(StudentModel, seed[key])
        ensure_charge(student, _today_label())
    db.session.commit()


# --------------------------------------------------------------------------- #
# Access
# --------------------------------------------------------------------------- #

def test_page_and_endpoint_are_admin_only(client, admin_client, seed):
    assert admin_client.get('/assistant').status_code == 200
    assert admin_client.get('/assistant/ask?q=help').status_code == 200


def test_teacher_and_parent_are_refused(teacher_client, parent_client):
    for client in (teacher_client, parent_client):
        assert client.get('/assistant').status_code == 403
        assert client.get('/assistant/ask?q=help').status_code == 403


def test_anonymous_user_is_sent_to_login(client):
    response = client.get('/assistant/ask?q=help', follow_redirects=False)
    assert response.status_code in (302, 401)


def test_menu_link_is_shown_to_admin(admin_client):
    assert b'School Assistant' in admin_client.get('/students').data


def test_responses_are_not_cached(admin_client):
    response = admin_client.get('/assistant/ask?q=help')
    assert response.headers['Cache-Control'] == 'no-store'


# --------------------------------------------------------------------------- #
# Understanding questions
# --------------------------------------------------------------------------- #

def test_empty_and_gibberish_questions_get_suggestions(admin_client):
    empty = ask(admin_client, '   ')
    assert empty['intent'] == 'empty' and empty['suggestions']
    lost = ask(admin_client, 'qwerty zxcvb plmokn')
    assert lost['intent'] == 'unknown' and lost['suggestions']


def test_help_and_greeting(admin_client):
    assert ask(admin_client, 'hello')['intent'] == 'help'
    assert ask(admin_client, 'tum kya kar sakte ho?')['intent'] == 'help'


def test_very_long_question_is_cut_not_rejected(admin_client):
    data = ask(admin_client, 'kitne students hain ' + 'x' * 5000)
    assert data['intent'] == 'students_count'


def test_misspelt_words_still_match(admin_client, seed):
    data = ask(admin_client, 'attendence aaj absnt')
    assert data['intent'] == 'attendance'


@pytest.mark.parametrize('question, intent', [
    ('kitne students hain?', 'students_count'),
    ('how many students are there', 'students_count'),
    ('kitne teachers hain?', 'teachers_count'),
    ('class wise students', 'class_strength'),
    ('aaj kitne students absent hain?', 'attendance'),
    ('is mahine kitni fees collect hui?', 'fees_collected'),
    ('defaulters kaun hain?', 'fees_due'),
    ('pending fees', 'fees_due'),
    ('is mahine ka kharcha', 'expenses'),
    ('is mahine ka profit', 'profit'),
    ('financial summary', 'profit'),
    ('salary pending kitni hai?', 'salary'),
    ('aaj ka summary', 'today_summary'),
])
def test_questions_reach_the_right_intent(admin_client, seed, question, intent):
    assert ask(admin_client, question)['intent'] == intent


@pytest.mark.parametrize('question, intent', [
    ('student kaise add karte hain?', 'howto_add_student'),
    ('fees kaise jama karte hain?', 'howto_collect_fee'),
    ('attendance kaise lagate hain?', 'howto_mark_attendance'),
    ('backup kaise lete hain?', 'howto_backup'),
    ('whatsapp qr kaise connect karen?', 'howto_whatsapp'),
    ('how to activate license', 'howto_license'),
])
def test_how_to_guides(admin_client, seed, question, intent):
    data = ask(admin_client, question)
    assert data['intent'] == intent
    assert '1.' in data['answer'] and data['links']


def test_reply_language_follows_the_question(admin_client, seed):
    english = ask(admin_client, 'how many students are there')
    urdu = ask(admin_client, 'kitne students hain?')
    assert 'The school has' in english['answer']
    assert 'School mein' in urdu['answer']


# --------------------------------------------------------------------------- #
# Answers come from real data
# --------------------------------------------------------------------------- #

def test_student_and_class_counts(admin_client, seed):
    assert '2 active students' in ask(admin_client, 'kitne students hain?')['answer']
    by_class = ask(admin_client, 'Class 1 mein kitne bachay hain?')
    assert 'Class 1' in by_class['answer'] and '2' in by_class['answer']
    table = ask(admin_client, 'class wise students')['table']
    assert table['rows'][0][0] == 'Class 1' and table['rows'][0][2] == 2


def test_inactive_students_are_not_counted(admin_client, app, seed):
    with app.app_context():
        student = db.session.get(StudentModel, seed['other_student_id'])
        student.is_active = False
        student.status = 'struck_off'
        db.session.commit()
    assert '1 active students' in ask(admin_client, 'kitne students hain?')['answer']


def test_teacher_count(admin_client, app, seed):
    with app.app_context():
        db.session.add(TeacherModel(teacher_id_str='T001', teacher_name='Mr Zafar',
                                    qualification='MSc', salary=30000,
                                    monthly_salary=30000))
        db.session.commit()
    assert '1 active teachers' in ask(admin_client, 'kitne teachers hain?')['answer']


def test_absent_students_today_are_listed(admin_client, app, seed):
    with app.app_context():
        db.session.add_all([
            AttendanceModel(date=date.today(), target_type='student',
                            target_id=seed['student_id'], status='Absent',
                            class_id=seed['class_id']),
            AttendanceModel(date=date.today(), target_type='student',
                            target_id=seed['other_student_id'], status='Present',
                            class_id=seed['class_id']),
        ])
        db.session.commit()
    data = ask(admin_client, 'aaj kitne students absent hain?')
    assert 'Kul 2' in data['answer'] and '1 ghair hazir' in data['answer']
    assert data['table']['rows'][0][0] == 'Ali Khan'
    english = ask(admin_client, 'how many students absent today')
    assert '1 of 2' in english['answer']


def test_attendance_not_marked_message(admin_client, seed):
    assert 'not been marked' in ask(admin_client, 'students absent today')['answer']


def test_one_student_attendance_this_month(admin_client, app, seed):
    with app.app_context():
        db.session.add(AttendanceModel(date=date.today(), target_type='student',
                                       target_id=seed['student_id'],
                                       status='Late', class_id=seed['class_id']))
        db.session.commit()
    data = ask(admin_client, 'Ali Khan attendance is mahine')
    assert 'Ali Khan' in data['answer'] and '1 late' in data['answer']


def test_fees_collected_this_month(admin_client, app, seed):
    with app.app_context():
        _charge_both(seed)
        student = db.session.get(StudentModel, seed['student_id'])
        record_payment(student, _today_label(), 1000, payment_date=date.today())
        db.session.commit()
    data = ask(admin_client, 'is mahine kitni fees collect hui?')
    assert 'Rs 1,000' in data['answer']
    today = ask(admin_client, 'aaj ki fee wasooli')
    assert 'Rs 1,000' in today['answer']


def test_defaulters_are_listed_biggest_first(admin_client, app, seed):
    with app.app_context():
        _charge_both(seed)
    data = ask(admin_client, 'defaulters kaun hain?')
    assert '2 students' in data['answer'] and 'Rs 4,500' in data['answer']
    assert [row[0] for row in data['table']['rows']] == ['Ali Khan', 'Sara Ali']


def test_defaulters_can_be_limited_to_a_class(admin_client, app, seed):
    with app.app_context():
        _charge_both(seed)
    data = ask(admin_client, 'Class 1 ki pending fees')
    assert 'Class 1' in data['answer'] and len(data['table']['rows']) == 2
    none = ask(admin_client, 'Class 9 ki pending fees')
    # an unknown class is ignored, so the school-wide list is returned
    assert len(none['table']['rows']) == 2


def test_one_student_balance_by_full_name(admin_client, app, seed):
    with app.app_context():
        _charge_both(seed)
        student = db.session.get(StudentModel, seed['student_id'])
        record_payment(student, _today_label(), 1000, payment_date=date.today())
        db.session.commit()
    data = ask(admin_client, 'Ali Khan ki fees baqaya')
    assert data['intent'] == 'fees_due'
    assert 'Rs 1,500' in data['answer']
    assert data['table']['rows'][0][1] == 'Rs 1,500'


def test_shared_first_name_asks_which_student(admin_client, app, seed):
    with app.app_context():
        _charge_both(seed)
    data = ask(admin_client, 'ali ka baqaya')
    assert data['intent'] == 'fees_due'
    names = {row[0] for row in data['table']['rows']}
    assert names == {'Ali Khan', 'Sara Ali'}
    assert 'Ali Khan' in data['suggestions']


def test_student_with_nothing_due(admin_client, seed):
    data = ask(admin_client, 'Ali Khan ki fees baqaya')
    assert 'no outstanding' in data['answer'] or 'koi baqaya nahi' in data['answer']


def test_bare_student_name_shows_details(admin_client, seed):
    data = ask(admin_client, 'Ali Khan')
    assert data['intent'] == 'student_info'
    assert '03001234567' in data['answer'] and 'Imran Khan' in data['answer']
    phone = ask(admin_client, 'Sara Ali ka phone number')
    assert '03007654321' in phone['answer']


def test_expenses_this_month(admin_client, app, seed):
    with app.app_context():
        category = ExpenseCategory(name='Utility Bills')
        db.session.add(category)
        db.session.flush()
        db.session.add(Expense(category_id=category.id, amount_paisa=250000,
                               date=date.today(), payment_method='Cash'))
        db.session.commit()
    data = ask(admin_client, 'is mahine ka kharcha')
    assert 'Rs 2,500' in data['answer']
    assert data['table']['rows'][0][0] == 'Utility Bills'
    assert 'Rs 2,500' in ask(admin_client, 'aaj ka kharcha')['answer']


def test_profit_and_loss_wording(admin_client, app, seed):
    with app.app_context():
        category = ExpenseCategory(name='Rent')
        db.session.add(category)
        db.session.flush()
        db.session.add(Expense(category_id=category.id, amount_paisa=100000,
                               date=date.today(), payment_method='Cash'))
        db.session.commit()
    data = ask(admin_client, 'is mahine ka profit')
    assert 'nuqsan Rs 1,000' in data['answer']
    assert 'deficit of Rs 1,000' in ask(admin_client, 'this month profit')['answer']


def test_salary_without_payroll(admin_client, seed):
    assert 'abhi generate nahi' in ask(admin_client, 'salary pending kitni hai?')['answer']


def test_today_summary(admin_client, seed):
    data = ask(admin_client, 'aaj ka summary')
    assert '2 students' in data['answer'] and 'Rs 0' in data['answer']


def test_previous_month_is_understood(app):
    with app.test_request_context():
        ctx = assistant_service.Ctx('pichle mahine ka kharcha')
        assert ctx.month_explicit and ctx.month != assistant_service.current_month_key()
        assert assistant_service.Ctx('may i ask').month_explicit is False


# --------------------------------------------------------------------------- #
# Safety
# --------------------------------------------------------------------------- #

def test_assistant_never_changes_data(admin_client, app, seed):
    with app.app_context():
        _charge_both(seed)
        before = (FeeTransaction.query.count(), StudentModel.query.count(),
                  AttendanceModel.query.count(), Expense.query.count())
    for question in ('defaulters kaun hain?', 'delete Ali Khan', 'aaj ka summary',
                     'Ali Khan ka phone number', 'fees collect kar do 5000'):
        ask(admin_client, question)
    with app.app_context():
        after = (FeeTransaction.query.count(), StudentModel.query.count(),
                 AttendanceModel.query.count(), Expense.query.count())
    assert before == after


def test_post_is_not_accepted(admin_client):
    assert admin_client.post('/assistant/ask', data={'q': 'help'}).status_code == 405


# --------------------------------------------------------------------------- #
# Follow-up memory ("aur kal?", "uska phone number?", a bare name after
# "which student?")
# --------------------------------------------------------------------------- #

def test_every_answer_carries_a_small_json_memory(admin_client, seed):
    data = ask(admin_client, 'aaj class 1 ki attendance')
    assert data['context']['intent'] == 'attendance'
    assert data['context']['class_id'] == seed['class_id']
    json.dumps(data['context'])      # must survive the round trip to the browser


def test_follow_up_keeps_the_topic_and_class(admin_client, app, seed):
    yesterday = date.today() - timedelta(days=1)
    with app.app_context():
        db.session.add(AttendanceModel(date=yesterday, target_type='student',
                                       target_id=seed['student_id'],
                                       status='Absent', class_id=seed['class_id']))
        db.session.commit()
    first = ask(admin_client, 'aaj class 1 ki attendance')
    second = ask(admin_client, 'aur kal?', first['context'])
    assert second['intent'] == 'attendance'
    assert '1 ghair hazir' in second['answer'] and 'Class 1' in second['answer']
    # without the memory the same short question is not understood
    assert ask(admin_client, 'aur kal?')['intent'] == 'unknown'


def test_follow_up_with_previous_month(admin_client, seed):
    first = ask(admin_client, 'is mahine kitni fees collect hui?')
    second = ask(admin_client, 'pichle mahine?', first['context'])
    assert second['intent'] == 'fees_collected'
    previous = date.today().replace(day=1) - timedelta(days=1)
    assert previous.strftime('%B %Y') in second['answer']


def test_explicit_question_is_never_hijacked_by_the_memory(admin_client, seed):
    first = ask(admin_client, 'aaj class 1 ki attendance')
    assert ask(admin_client, 'is mahine ka kharcha',
               first['context'])['intent'] == 'expenses'


def test_pronoun_follow_up_refers_to_the_last_student(admin_client, app, seed):
    with app.app_context():
        _charge_both(seed)
    first = ask(admin_client, 'Ali Khan ka phone number')
    assert first['context']['student_id'] == seed['student_id']
    second = ask(admin_client, 'uska baqaya?', first['context'])
    assert second['intent'] == 'fees_due'
    assert 'Ali Khan' in second['answer'] and 'Rs 2,500' in second['answer']


def test_bare_name_answers_the_pending_which_student_question(admin_client, app, seed):
    with app.app_context():
        _charge_both(seed)
    asked = ask(admin_client, 'ali ka baqaya')
    assert asked['context']['awaiting'] == 'fees_due'
    answered = ask(admin_client, 'Ali Khan', asked['context'])
    assert answered['intent'] == 'fees_due' and 'Rs 2,500' in answered['answer']
    # the same bare name with nothing pending still shows the details
    assert ask(admin_client, 'Ali Khan')['intent'] == 'student_info'


def test_memory_from_the_browser_is_never_trusted(admin_client, seed):
    for bad in ({'intent': 'evil', 'class_id': 'x', 'month': '2026-13',
                 'day': 'garbage', 'status': 'Hax'},
                {'intent': 'attendance', 'class_id': 987654, 'student_id': 987654},
                ['not', 'a', 'dict'], 'text', 123):
        data = ask(admin_client, 'aur kal?', bad)
        assert data['ok'] is True
    for raw in ('{not json', '{"intent": "' + 'a' * 2000 + '"}'):
        response = admin_client.get('/assistant/ask',
                                    query_string={'q': 'help', 'c': raw})
        assert response.status_code == 200
        assert response.get_json()['intent'] == 'help'


# --------------------------------------------------------------------------- #
# New questions
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize('question, intent', [
    ('aaj kya kaam baqi hain?', 'attention'),
    ('what needs attention?', 'attention'),
    ('aaj kis ki birthday hai?', 'birthdays'),
    ('kam attendance wale students', 'low_attendance'),
    ('class wise fees baqaya', 'class_fees'),
    ('is mahine ka pichle mahine se muqabla', 'compare'),
    ('is mahine kitne naye admissions hue?', 'new_admissions'),
    ('aaj kis kis ne fees di?', 'fees_payments'),
    ('who paid fees today', 'fees_payments'),
])
def test_new_questions_reach_the_right_intent(admin_client, seed, question, intent):
    assert ask(admin_client, question)['intent'] == intent


def test_old_questions_were_not_taken_over(admin_client, seed):
    for question, intent in (('class wise students', 'class_strength'),
                             ('defaulters kaun hain?', 'fees_due'),
                             ('aaj ki fee wasooli', 'fees_collected'),
                             ('student kaise add karte hain?', 'howto_add_student')):
        assert ask(admin_client, question)['intent'] == intent


def test_absent_list_shows_guardian_phone(admin_client, app, seed):
    with app.app_context():
        db.session.add(AttendanceModel(date=date.today(), target_type='student',
                                       target_id=seed['student_id'],
                                       status='Absent', class_id=seed['class_id']))
        db.session.commit()
    data = ask(admin_client, 'aaj kitne students absent hain?')
    assert data['table']['columns'][2] in ('Phone',)
    assert data['table']['rows'][0][0] == 'Ali Khan'
    assert data['table']['rows'][0][2] == '03001234567'


def test_who_paid_today_lists_payments(admin_client, app, seed):
    with app.app_context():
        _charge_both(seed)
        student = db.session.get(StudentModel, seed['student_id'])
        record_payment(student, _today_label(), 1000, method='cash',
                       payment_date=date.today())
        db.session.commit()
    data = ask(admin_client, 'aaj kis kis ne fees di?')
    assert data['intent'] == 'fees_payments'
    assert '1 payments' in data['answer'] and 'Rs 1,000' in data['answer']
    assert data['table']['rows'][0][:3] == ['Ali Khan', 'Class 1', 'Rs 1,000']
    nobody = ask(admin_client, 'kal kis kis ne fees di?')
    assert 'nahi hui' in nobody['answer'] and not nobody['table']


def test_class_wise_fees(admin_client, app, seed):
    with app.app_context():
        _charge_both(seed)
    data = ask(admin_client, 'class wise fees baqaya')
    assert data['intent'] == 'class_fees'
    assert data['table']['rows'][0] == ['Class 1', 2, 'Rs 4,500']
    assert 'Rs 4,500' in data['answer']


def test_compare_with_last_month(admin_client, app, seed):
    with app.app_context():
        _charge_both(seed)
        student = db.session.get(StudentModel, seed['student_id'])
        record_payment(student, _today_label(), 1000, payment_date=date.today())
        db.session.commit()
    data = ask(admin_client, 'is mahine ka pichle mahine se muqabla')
    assert data['intent'] == 'compare'
    labels = [row[0] for row in data['table']['rows']]
    assert labels == ['Fees wasooli', 'Kharcha', 'Bachat (aamdani - kharcha)']
    assert data['table']['rows'][0][1] == 'Rs 1,000'     # this month
    assert data['table']['rows'][0][2] == 'Rs 0'         # last month
    assert 'Rs 1,000' in data['answer']
    # "pichle" must not shift the base month: the table starts with THIS month
    assert data['table']['columns'][1] == date.today().strftime('%B %Y')


def test_new_admissions_this_month(admin_client, app, seed):
    with app.app_context():
        db.session.get(StudentModel, seed['student_id']).admission_date = date.today()
        db.session.get(StudentModel, seed['other_student_id']).admission_date = date(2020, 1, 1)
        db.session.commit()
    data = ask(admin_client, 'is mahine kitne naye admissions hue?')
    assert data['intent'] == 'new_admissions'
    assert [row[0] for row in data['table']['rows']] == ['Ali Khan']
    assert ask(admin_client, 'new admissions pichle mahine')['table'] is None


def test_birthdays_today(admin_client, app, seed):
    with app.app_context():
        db.session.get(StudentModel, seed['student_id']).date_of_birth = \
            date(2016, date.today().month, date.today().day)
        db.session.commit()
    data = ask(admin_client, 'aaj kis ki birthday hai?')
    assert data['intent'] == 'birthdays' and 'Ali Khan' in data['answer']


def test_birthdays_without_any_date_of_birth(admin_client, seed):
    data = ask(admin_client, 'upcoming birthdays')
    assert data['intent'] == 'birthdays' and 'date of birth' in data['answer']


def test_low_attendance_students_are_listed(admin_client, app, seed):
    first_of_month = date.today().replace(day=1)
    last_month_end = first_of_month - timedelta(days=1)
    days = [last_month_end - timedelta(days=n) for n in range(last_month_end.day)]
    with app.app_context():
        for day in days:
            db.session.add_all([
                AttendanceModel(date=day, target_type='student',
                                target_id=seed['student_id'], status='Absent',
                                class_id=seed['class_id']),
                AttendanceModel(date=day, target_type='student',
                                target_id=seed['other_student_id'],
                                status='Present', class_id=seed['class_id']),
            ])
        db.session.commit()
    data = ask(admin_client, 'kam attendance wale students pichle mahine')
    assert data['intent'] == 'low_attendance'
    assert [row[0] for row in data['table']['rows']] == ['Ali Khan']
    assert data['table']['rows'][0][4] == '03001234567'


def test_low_attendance_when_nothing_is_marked(admin_client, seed):
    data = ask(admin_client, 'low attendance students pichle mahine')
    assert data['intent'] == 'low_attendance' and not data['table']


def test_attention_list_mentions_outstanding_fees(admin_client, app, seed):
    with app.app_context():
        _charge_both(seed)
    data = ask(admin_client, 'aaj kya kaam baqi hain?')
    assert data['intent'] == 'attention'
    assert 'remaining' in data['answer']
    assert data['links']


def test_teacher_details_by_name(admin_client, app, seed):
    with app.app_context():
        db.session.add(TeacherModel(teacher_id_str='T001', teacher_name='Mr Zafar',
                                    qualification='MSc', salary=30000,
                                    monthly_salary=30000,
                                    contact_number='03111234567'))
        db.session.commit()
    first = ask(admin_client, 'Zafar ka phone number')
    assert first['intent'] == 'teacher_info'
    assert '03111234567' in first['answer'] and 'Mr Zafar' in first['answer']
    second = ask(admin_client, 'uski salary?', first['context'])
    assert second['intent'] == 'teacher_info' and 'Rs 30,000' in second['answer']
    # a plain salary question is still the whole-school payroll
    assert ask(admin_client, 'salary pending kitni hai?',
               first['context'])['intent'] == 'salary'


def test_teacher_phone_without_a_name_asks_which_teacher(admin_client, seed):
    data = ask(admin_client, 'teacher phone number')
    assert 'teacher' in data['answer'].lower()


def test_new_questions_never_change_data(admin_client, app, seed):
    with app.app_context():
        _charge_both(seed)
        before = (FeeTransaction.query.count(), StudentModel.query.count(),
                  AttendanceModel.query.count(), Expense.query.count())
    for question in ('aaj kya kaam baqi hain?', 'class wise fees baqaya',
                     'aaj kis kis ne fees di?', 'kam attendance wale students',
                     'is mahine ka pichle mahine se muqabla', 'naye admissions',
                     'aaj kis ki birthday hai?'):
        ask(admin_client, question)
    with app.app_context():
        after = (FeeTransaction.query.count(), StudentModel.query.count(),
                 AttendanceModel.query.count(), Expense.query.count())
    assert before == after
