"""Sets (bundles): stock is kept per item; a set is bought / sold in one entry."""
from datetime import date

import pytest

from app.database import db
from app.models import Product, ProductSet, Purchase, Sale
from app.services import financial_summary as fs, inventory_service as inv


@pytest.fixture()
def world(app):
    with app.app_context():
        english = Product(name='English Class 1', category='Books', sale_price_paisa=30000)
        maths = Product(name='Maths Class 1', category='Books', sale_price_paisa=20000)
        urdu = Product(name='Urdu Class 1', category='Books', sale_price_paisa=10000)
        db.session.add_all([english, maths, urdu])
        db.session.commit()
        return {'english': english.id, 'maths': maths.id, 'urdu': urdu.id}


def _make_set(world, name='Class 1 Books'):
    return inv.create_set(name, [(world['english'], 1), (world['maths'], 1),
                                 (world['urdu'], 1)], kind='books')


def test_buying_a_set_fills_every_item_and_shares_the_bill(app, world):
    with app.app_context():
        target = _make_set(world)
        db.session.commit()
        # 10 sets for Rs 6,000: shared 3 : 2 : 1 by selling value.
        rows = inv.purchase_set(target, 10, 6000, supplier='Book House',
                                purchase_date=date(2026, 10, 1), paid_rupees=4000)
        db.session.commit()
        assert len(rows) == 3
        assert {db.session.get(Product, world[k]).stock_qty for k in world} == {10}
        assert sum(r.total_cost_paisa for r in rows) == 600000
        assert sum(r.paid_total_paisa for r in rows) == 400000
        assert sum(r.balance_paisa for r in rows) == 200000
        assert all(r.balance_paisa >= 0 for r in rows)
        by_name = {r.product.name: r for r in rows}
        assert by_name['English Class 1'].total_cost_paisa == 300000
        assert by_name['Maths Class 1'].total_cost_paisa == 200000
        assert by_name['Urdu Class 1'].total_cost_paisa == 100000
        assert {r.bill_label for r in rows} == {'Set: Class 1 Books x 10'}
        # The unpaid part is one supplier due.
        assert inv.supplier_dues()[0]['balance'] == 200000


def test_bill_split_never_loses_a_paisa(app, world):
    with app.app_context():
        target = _make_set(world)
        rows = inv.purchase_set(target, 7, 1000.01, paid_rupees=333.33)
        db.session.commit()
        assert sum(r.total_cost_paisa for r in rows) == 100001
        assert sum(r.paid_total_paisa for r in rows) == 33333
        assert all(0 <= r.paid_total_paisa <= r.total_cost_paisa for r in rows)


def test_one_item_can_still_be_bought_and_sold_alone(app, world):
    with app.app_context():
        target = _make_set(world)
        inv.purchase_set(target, 10, 6000)
        english = db.session.get(Product, world['english'])
        inv.record_purchase(english, 10, 280.0)               # 10 extra English books
        inv.record_sale(english, 3)                            # one student, one book
        db.session.commit()
        assert english.stock_qty == 17
        assert db.session.get(Product, world['maths']).stock_qty == 10
        assert inv.sets_available(target) == 10


def test_selling_a_set_takes_one_of_each_and_books_revenue(app, world):
    with app.app_context():
        target = _make_set(world)
        inv.purchase_set(target, 10, 6000, purchase_date=date(2026, 10, 1))
        db.session.commit()
        sales = inv.sell_set(target, 2, note='Ali Khan', sale_date=date(2026, 10, 5))
        db.session.commit()
        assert len(sales) == 3
        assert inv.sets_available(target) == 8
        assert sum(s.total_price_paisa for s in sales) == 2 * 60000     # 2 sets x Rs 600
        assert all('Set: Class 1 Books x 2' in s.note for s in sales)
        snap = fs.month_snapshot('2026-10')
        assert snap['sales'] == 1200.0
        # 10 sets cost Rs 6,000 -> Rs 600 a set -> 2 sets cost Rs 1,200.
        assert snap['sales_cogs'] == 1200.0
        assert snap['gross_profit'] == 0.0


def test_a_set_is_never_sold_half(app, world):
    with app.app_context():
        target = _make_set(world)
        inv.purchase_set(target, 5, 3000)
        maths = db.session.get(Product, world['maths'])
        inv.record_sale(maths, 4)                              # only 1 maths book left
        db.session.commit()
        with pytest.raises(ValueError) as error:
            inv.sell_set(target, 2)
        assert 'Maths Class 1' in str(error.value)
        db.session.rollback()
        assert db.session.get(Product, world['english']).stock_qty == 5
        assert Sale.query.count() == 1


def test_edit_set_keeps_history_and_rejects_bad_input(app, world):
    with app.app_context():
        target = _make_set(world)
        inv.purchase_set(target, 2, 600)
        db.session.commit()
        inv.update_set(target, 'Class 1 Books (new)',
                       [(world['english'], 2), (world['maths'], 1)], 'books')
        db.session.commit()
        assert [(i.product.name, i.quantity) for i in target.items] == [
            ('English Class 1', 2), ('Maths Class 1', 1)]
        assert Purchase.query.count() == 3                      # history untouched
        with pytest.raises(ValueError):
            inv.create_set('', [(world['english'], 1)])
        with pytest.raises(ValueError):
            inv.create_set('Empty', [])
        with pytest.raises(ValueError):
            inv.create_set('Zero', [(world['english'], 0)])
        with pytest.raises(ValueError):
            inv.create_set('class 1 books (NEW)', [(world['english'], 1)])
        db.session.rollback()


def test_set_price_cost_and_availability(app, world):
    with app.app_context():
        target = _make_set(world)
        inv.purchase_set(target, 4, 2400)                       # Rs 600 a set
        db.session.commit()
        assert inv.set_price_paisa(target) == 60000
        assert inv.set_cost_paisa(target) == 60000
        assert inv.sets_available(target) == 4


def test_pages_and_posts_end_to_end(admin_client, app, world):
    response = admin_client.post('/inventory/sets/add', data={
        'name': 'Class 1 Books', 'kind': 'books',
        'item_product': [str(world['english']), str(world['maths'])],
        'item_qty': ['1', '1']}, follow_redirects=True)
    body = response.get_data(as_text=True)
    assert 'Set &#34;Class 1 Books&#34; added' in body or 'Set "Class 1 Books" added' in body
    assert '1 &times; English Class 1' in body

    with app.app_context():
        set_id = ProductSet.query.first().id

    response = admin_client.post('/inventory/sets/%d/buy' % set_id, data={
        'number_of_sets': '10', 'total_bill': '5000', 'paid_now': '3000',
        'supplier': 'Book House', 'purchase_date': '2026-10-01'},
        follow_redirects=True)
    body = response.get_data(as_text=True)
    assert 'Set stock added: Set: Class 1 Books x 10' in body
    assert 'still owed to Book House: Rs 2,000.00' in body

    response = admin_client.post('/inventory/sets/%d/sell' % set_id, data={
        'number_of_sets': '2', 'sale_date': '2026-10-05'}, follow_redirects=True)
    assert 'Sold Set: Class 1 Books x 2' in response.get_data(as_text=True)

    response = admin_client.post('/inventory/sets/%d/sell' % set_id, data={
        'number_of_sets': '99', 'sale_date': '2026-10-05'}, follow_redirects=True)
    assert 'Not enough stock for' in response.get_data(as_text=True)

    with app.app_context():
        assert db.session.get(Product, world['english']).stock_qty == 8


def test_teacher_cannot_touch_sets(teacher_client, app, world):
    response = teacher_client.post('/inventory/sets/add', data={
        'name': 'X', 'item_product': [str(world['english'])], 'item_qty': ['1']})
    assert response.status_code in (302, 403)
    with app.app_context():
        assert ProductSet.query.count() == 0
