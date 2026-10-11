"""Inventory / sales models (Phase 3a+3b).

The school sells items (uniforms, books, stationery) in volume.  Purchases
are stock replenishment — NOT expenses; the cost of a purchased item moves
into Cost of Goods Sold when the item is SOLD, using weighted-average cost
recalculated on every purchase.  Money is stored as integer paisa, like the
rest of the financial modules.
"""
from datetime import datetime

from app.database import db


class Product(db.Model):
    __tablename__ = 'products'
    __table_args__ = (
        # Backstop for the service-level check: stock can never go negative.
        db.CheckConstraint('stock_qty >= 0', name='ck_products_stock_non_negative'),
        {'extend_existing': True},
    )

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    category = db.Column(db.String(80), nullable=False, default='Other')
    sale_price_paisa = db.Column(db.Integer, nullable=False, default=0)
    stock_qty = db.Column(db.Integer, nullable=False, default=0)
    min_stock_qty = db.Column(db.Integer, nullable=False, default=0)
    supplier = db.Column(db.String(120), nullable=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    # Weighted-average unit cost (paisa), recalculated on every purchase.
    cost_paisa = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    purchases = db.relationship('Purchase', backref='product', lazy=True)
    sales = db.relationship('Sale', backref='product', lazy=True)

    def __repr__(self):
        return f'<Product {self.name} stock={self.stock_qty}>'


class Purchase(db.Model):
    __tablename__ = 'inventory_purchases'
    __table_args__ = {'extend_existing': True}

    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    unit_cost_paisa = db.Column(db.Integer, nullable=False, default=0)
    total_cost_paisa = db.Column(db.Integer, nullable=False, default=0)
    supplier = db.Column(db.String(120), nullable=True)
    purchase_date = db.Column(db.Date, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    created_by_name = db.Column(db.String(80), nullable=True, default='system')


class Sale(db.Model):
    __tablename__ = 'inventory_sales'
    __table_args__ = (
        db.CheckConstraint('quantity > 0', name='ck_inventory_sales_qty_positive'),
        {'extend_existing': True},
    )

    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    # Price and cost are snapshotted at sale time; later price changes never
    # alter historical sales.
    unit_price_paisa = db.Column(db.Integer, nullable=False, default=0)
    unit_cost_paisa = db.Column(db.Integer, nullable=False, default=0)
    total_price_paisa = db.Column(db.Integer, nullable=False, default=0)
    total_cost_paisa = db.Column(db.Integer, nullable=False, default=0)
    gross_profit_paisa = db.Column(db.Integer, nullable=False, default=0)
    sale_date = db.Column(db.Date, nullable=False)
    note = db.Column(db.String(200), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    created_by_name = db.Column(db.String(80), nullable=True, default='system')
