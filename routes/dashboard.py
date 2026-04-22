from flask import Blueprint, render_template, session, redirect, url_for, jsonify
from functools import wraps

bp = Blueprint('dashboard', __name__)

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function

@bp.route('/')
@login_required
def index():
    if session.get('role') == 'admin':
        return redirect(url_for('dashboard.admin_dashboard'))
    elif session.get('role') == 'accountant':
        return redirect(url_for('dashboard.accountant_dashboard'))
    from models import Employee, Inventory, Sales, Transaction, Payroll, Customer
    from ext import db
    from sqlalchemy import func
    
    total_employees = Employee.query.filter_by(is_active=True).count()
    total_inventory = Inventory.query.count()
    
    monthly_sales = db.session.query(func.sum(Sales.total_amount)).scalar() or 0
    
    today = db.session.query(func.sum(Transaction.debit)).filter(
        Transaction.entry_type == 'debit'
    ).scalar() or 0
    
    return render_template('dashboard.html', 
                         total_employees=total_employees,
                         total_inventory=total_inventory,
                         monthly_sales=monthly_sales)

@bp.route('/admin')
@login_required
def admin_dashboard():
    if session.get('role') != 'admin':
        return redirect(url_for('dashboard.index'))
    
    from models import Employee, Inventory, Sales, Payroll, Customer
    from ext import db
    from sqlalchemy import func
    from datetime import datetime
    
    total_employees = Employee.query.filter_by(is_active=True).count()
    total_customers = Customer.query.count()
    total_inventory = Inventory.query.count()
    
    monthly_sales = db.session.query(func.sum(Sales.total_amount)).scalar() or 0
    total_salary = db.session.query(func.sum(Payroll.net_salary)).scalar() or 0
    
    recent_sales = Sales.query.order_by(Sales.created_at.desc()).limit(5).all()
    recent_payroll = Payroll.query.order_by(Payroll.created_at.desc()).limit(5).all()
    
    customers = Customer.query.all()
    customer_sales = []
    for c in customers:
        total = db.session.query(func.sum(Sales.total_amount)).filter(Sales.customer_id == c.id).scalar() or 0
        customer_sales.append({'name': c.name, 'total': total})
    customer_sales = sorted(customer_sales, key=lambda x: x['total'], reverse=True)[:5]
    
    inventory_low = Inventory.query.filter(Inventory.closing_stock < 20).all()
    
    sales_by_month_raw = db.session.query(
        func.strftime('%Y-%m', Sales.invoice_date),
        func.sum(Sales.total_amount)
    ).group_by(func.strftime('%Y-%m', Sales.invoice_date)).all()
    sales_by_month = [[row[0], float(row[1] or 0)] for row in sales_by_month_raw] if sales_by_month_raw else []
    
    salary_by_month_raw = db.session.query(
        Payroll.month,
        func.sum(Payroll.net_salary)
    ).group_by(Payroll.month).all()
    salary_by_month = [[row[0], float(row[1] or 0)] for row in salary_by_month_raw] if salary_by_month_raw else []
    
    return render_template('admin_dashboard.html',
                         total_employees=total_employees,
                         total_customers=total_customers,
                         total_inventory=total_inventory,
                         monthly_sales=monthly_sales,
                         total_salary=total_salary,
                         recent_sales=recent_sales,
                         recent_payroll=recent_payroll,
                         customer_sales=customer_sales,
                         inventory_low=inventory_low,
                         sales_by_month=sales_by_month,
                         salary_by_month=salary_by_month)

@bp.route('/accountant')
@login_required
def accountant_dashboard():
    if session.get('role') != 'accountant':
        return redirect(url_for('dashboard.admin_dashboard'))

    from models import Employee, Inventory, Sales, Payroll, Customer, Transaction, Account
    from ext import db
    from sqlalchemy import func

    total_employees = Employee.query.filter_by(is_active=True).count()
    total_customers = Customer.query.count()
    total_inventory = Inventory.query.count()

    monthly_sales = db.session.query(func.sum(Sales.total_amount)).scalar() or 0
    total_salary = db.session.query(func.sum(Payroll.net_salary)).scalar() or 0

    recent_sales = Sales.query.order_by(Sales.created_at.desc()).limit(5).all()

    customers = Customer.query.all()
    customer_sales = []
    for c in customers:
        total = db.session.query(func.sum(Sales.total_amount)).filter(Sales.customer_id == c.id).scalar() or 0
        customer_sales.append({'name': c.name, 'total': total})
    customer_sales = sorted(customer_sales, key=lambda x: x['total'], reverse=True)[:5]

    inventory_low = Inventory.query.filter(Inventory.closing_stock < 20).all()

    sales_by_month_raw = db.session.query(
        func.strftime('%Y-%m', Sales.invoice_date),
        func.sum(Sales.total_amount)
    ).group_by(func.strftime('%Y-%m', Sales.invoice_date)).all()
    sales_by_month = [[row[0], float(row[1] or 0)] for row in sales_by_month_raw] if sales_by_month_raw else []

    salary_by_month_raw = db.session.query(
        Payroll.month,
        func.sum(Payroll.net_salary)
    ).group_by(Payroll.month).all()
    salary_by_month = [[row[0], float(row[1] or 0)] for row in salary_by_month_raw] if salary_by_month_raw else []

    total_expenses = db.session.query(func.sum(Transaction.debit)).join(
        Account, Transaction.account_id == Account.id
    ).filter(
        Account.account_type == 'expense',
        Transaction.entry_type == 'debit'
    ).scalar() or 0

    revenue_vs_expenses = [
        {'label': 'Revenue', 'value': float(monthly_sales)},
        {'label': 'Expenses', 'value': float(total_expenses)}
    ]

    inventory_items = Inventory.query.all()

    return render_template('accountant_dashboard.html',
                         total_employees=total_employees,
                         total_customers=total_customers,
                         total_inventory=total_inventory,
                         monthly_sales=monthly_sales,
                         total_salary=total_salary,
                         recent_sales=recent_sales,
                         customer_sales=customer_sales,
                         inventory_low=inventory_low,
                         sales_by_month=sales_by_month,
                         salary_by_month=salary_by_month,
                         revenue_vs_expenses=revenue_vs_expenses,
                         inventory_items=inventory_items)