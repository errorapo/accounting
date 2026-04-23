from ext import db
from datetime import datetime

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(20), default='accountant')

class Employee(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    employee_type = db.Column(db.String(50), nullable=False)
    base_salary = db.Column(db.Numeric(precision=15, scale=2), default=0)
    hourly_rate = db.Column(db.Numeric(precision=15, scale=2), default=0)
    pf_rate = db.Column(db.Numeric(precision=5, scale=2), default=12)
    transport_allowance = db.Column(db.Numeric(precision=15, scale=2), default=0)
    food_allowance = db.Column(db.Numeric(precision=15, scale=2), default=0)
    housing_allowance = db.Column(db.Numeric(precision=15, scale=2), default=0)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Attendance(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey('employee.id'))
    date = db.Column(db.Date, default=datetime.utcnow().date)
    status = db.Column(db.String(20))
    half_day = db.Column(db.Boolean, default=False)
    overtime_hours = db.Column(db.Numeric(precision=8, scale=2), default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Payroll(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey('employee.id'))
    month = db.Column(db.String(7))
    year = db.Column(db.Integer)
    base_salary = db.Column(db.Numeric(precision=15, scale=2), default=0)
    overtime_hours = db.Column(db.Numeric(precision=8, scale=2), default=0)
    overtime_amount = db.Column(db.Numeric(precision=15, scale=2), default=0)
    transport_allowance = db.Column(db.Numeric(precision=15, scale=2), default=0)
    food_allowance = db.Column(db.Numeric(precision=15, scale=2), default=0)
    housing_allowance = db.Column(db.Numeric(precision=15, scale=2), default=0)
    bonus = db.Column(db.Numeric(precision=15, scale=2), default=0)
    gross_salary = db.Column(db.Numeric(precision=15, scale=2), default=0)
    pf_employee = db.Column(db.Numeric(precision=15, scale=2), default=0)
    pf_employer = db.Column(db.Numeric(precision=15, scale=2), default=0)
    tax_deduction = db.Column(db.Numeric(precision=15, scale=2), default=0)
    insurance = db.Column(db.Numeric(precision=15, scale=2), default=0)
    total_deductions = db.Column(db.Numeric(precision=15, scale=2), default=0)
    net_salary = db.Column(db.Numeric(precision=15, scale=2), default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    employee = db.relationship('Employee', backref='payroll_records')

class Inventory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    stone_type = db.Column(db.String(50), nullable=False)
    size = db.Column(db.String(20), nullable=False)
    opening_stock = db.Column(db.Numeric(precision=15, scale=3), default=0)
    purchases = db.Column(db.Numeric(precision=15, scale=3), default=0)
    sales = db.Column(db.Numeric(precision=15, scale=3), default=0)
    closing_stock = db.Column(db.Numeric(precision=15, scale=3), default=0)
    rate_per_ton = db.Column(db.Numeric(precision=15, scale=2), default=0)
    total_cost = db.Column(db.Numeric(precision=15, scale=2), default=0)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow)

class Customer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(20))
    address = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Vendor(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(20))
    address = db.Column(db.Text)
    gstin = db.Column(db.String(20))
    state = db.Column(db.String(50))
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Sales(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    invoice_number = db.Column(db.String(50), unique=True)
    customer_id = db.Column(db.Integer, db.ForeignKey('customer.id'))
    stone_type = db.Column(db.String(50))
    size = db.Column(db.String(20))
    quantity = db.Column(db.Numeric(precision=15, scale=3))
    rate = db.Column(db.Numeric(precision=15, scale=2))
    amount = db.Column(db.Numeric(precision=15, scale=2))
    gst_rate = db.Column(db.Numeric(precision=5, scale=2), default=5)
    gst_amount = db.Column(db.Numeric(precision=15, scale=2), default=0)
    cgst_amount = db.Column(db.Numeric(precision=15, scale=2), default=0)
    sgst_amount = db.Column(db.Numeric(precision=15, scale=2), default=0)
    igst_amount = db.Column(db.Numeric(precision=15, scale=2), default=0)
    supply_type = db.Column(db.String(10), default='intra')  # 'intra' or 'inter'
    total_amount = db.Column(db.Numeric(precision=15, scale=2))
    payment_type = db.Column(db.String(20), default='cash')
    payment_status = db.Column(db.String(20), default='paid')
    invoice_date = db.Column(db.Date, default=datetime.utcnow().date)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    customer = db.relationship('Customer', backref='sales_records')

class Purchase(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    invoice_number = db.Column(db.String(50), unique=True)
    vendor_id = db.Column(db.Integer, db.ForeignKey('vendor.id'))
    vendor_name = db.Column(db.String(100))
    stone_type = db.Column(db.String(50))
    size = db.Column(db.String(20))
    quantity = db.Column(db.Numeric(precision=15, scale=3))
    rate = db.Column(db.Numeric(precision=15, scale=2))
    amount = db.Column(db.Numeric(precision=15, scale=2))
    gst_rate = db.Column(db.Numeric(precision=5, scale=2), default=5)
    gst_amount = db.Column(db.Numeric(precision=15, scale=2), default=0)
    cgst_amount = db.Column(db.Numeric(precision=15, scale=2), default=0)
    sgst_amount = db.Column(db.Numeric(precision=15, scale=2), default=0)
    igst_amount = db.Column(db.Numeric(precision=15, scale=2), default=0)
    supply_type = db.Column(db.String(10), default='intra')  # 'intra' or 'inter'
    payment_type = db.Column(db.String(20), default='cash')
    payment_status = db.Column(db.String(20), default='paid')
    itc_eligible = db.Column(db.Boolean, default=True)
    invoice_date = db.Column(db.Date, default=datetime.utcnow().date)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    vendor = db.relationship('Vendor', backref='purchase_records')

class Payment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sale_id = db.Column(db.Integer, db.ForeignKey('sales.id'))
    amount = db.Column(db.Numeric(precision=15, scale=2))
    payment_date = db.Column(db.Date, default=datetime.utcnow().date)
    payment_mode = db.Column(db.String(20), default='cash')
    notes = db.Column(db.String(200))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    sale = db.relationship('Sales', backref='payments')

class PurchasePayment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    purchase_id = db.Column(db.Integer, db.ForeignKey('purchase.id'))
    amount = db.Column(db.Numeric(precision=15, scale=2))
    payment_date = db.Column(db.Date, default=datetime.utcnow().date)
    payment_mode = db.Column(db.String(20), default='cash')
    notes = db.Column(db.String(200))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    purchase = db.relationship('Purchase', backref='payments')

class Account(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    account_type = db.Column(db.String(20), nullable=False)
    is_active = db.Column(db.Boolean, default=True)

class Transaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, default=datetime.utcnow().date)
    description = db.Column(db.String(200))
    account_id = db.Column(db.Integer, db.ForeignKey('account.id'))
    debit = db.Column(db.Numeric(precision=15, scale=2), default=0)
    credit = db.Column(db.Numeric(precision=15, scale=2), default=0)
    entry_type = db.Column(db.String(10))
    is_posted = db.Column(db.Boolean, default=True)
    is_reversal = db.Column(db.Boolean, default=False)
    original_entry_id = db.Column(db.Integer, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class FixedAsset(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    purchase_date = db.Column(db.Date)
    cost = db.Column(db.Numeric(precision=15, scale=2), nullable=False)
    salvage_value = db.Column(db.Numeric(precision=15, scale=2), default=0)
    useful_life_years = db.Column(db.Integer, nullable=False)
    accumulated_depreciation = db.Column(db.Numeric(precision=15, scale=2), default=0)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class JournalEntry(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, default=datetime.utcnow().date)
    description = db.Column(db.String(200))
    debit_account_id = db.Column(db.Integer, db.ForeignKey('account.id'))
    credit_account_id = db.Column(db.Integer, db.ForeignKey('account.id'))
    amount = db.Column(db.Numeric(precision=15, scale=2))
    is_posted = db.Column(db.Boolean, default=True)
    is_reversal = db.Column(db.Boolean, default=False)
    original_entry_id = db.Column(db.Integer, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class InvoiceSequence(db.Model):
    id          = db.Column(db.Integer, primary_key=True)
    prefix      = db.Column(db.String(20), unique=True, nullable=False)
    last_number = db.Column(db.Integer, default=0, nullable=False)