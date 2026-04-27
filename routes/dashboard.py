from flask import Blueprint, render_template, session, redirect, url_for, jsonify
from datetime import datetime, date
from decimal import Decimal
from sqlalchemy import func

from routes.auth_utils import login_required
from accounting_engine import get_income_statement, get_account_balance, get_monthly_revenue_expense

bp = Blueprint('dashboard', __name__)

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
    
    monthly_sales = db.session.query(func.sum(Sales.total_amount)).filter(
        func.strftime('%Y-%m', Sales.invoice_date) == func.strftime('%Y-%m', datetime.now())
    ).scalar() or 0
    
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
    
    from models import Employee, Inventory, Sales, Payroll, Customer, Account
    from ext import db
    from sqlalchemy import func
    from datetime import datetime, date
    
    total_employees = Employee.query.filter_by(is_active=True).count()
    total_customers = Customer.query.count()
    total_inventory = Inventory.query.count()
    
    monthly_sales = db.session.query(func.sum(Sales.total_amount)).filter(
        func.strftime('%Y-%m', Sales.invoice_date) == func.strftime('%Y-%m', datetime.now())
    ).scalar() or 0
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
    
    today = date.today()
    start_of_month = date(today.year, today.month, 1)
    
    income_stmt = get_income_statement(start_of_month, today)
    revenue_mtd = income_stmt.get('total_income', 0)
    expenses_mtd = income_stmt.get('total_expenses', 0)
    profit_mtd = income_stmt.get('net_profit', 0)
    
    ar_acc = Account.query.filter_by(name='Accounts Receivable').first()
    ar_outstanding = get_account_balance(ar_acc.id) if ar_acc else 0
    
    cgst_acc = Account.query.filter_by(name='CGST Payable').first()
    sgst_acc = Account.query.filter_by(name='SGST Payable').first()
    igst_acc = Account.query.filter_by(name='IGST Payable').first()
    gst_payable = 0
    if cgst_acc:
        gst_payable += get_account_balance(cgst_acc.id)
    if sgst_acc:
        gst_payable += get_account_balance(sgst_acc.id)
    if igst_acc:
        gst_payable += get_account_balance(igst_acc.id)
    
    monthly_data = get_monthly_revenue_expense(months=6)
    
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
                         salary_by_month=salary_by_month,
                         revenue_mtd=revenue_mtd,
                         profit_mtd=profit_mtd,
                         ar_outstanding=ar_outstanding,
                         gst_payable=gst_payable,
                         monthly_data=monthly_data)

@bp.route('/accountant')
@login_required
def accountant_dashboard():
    if session.get('role') != 'accountant':
        return redirect(url_for('dashboard.admin_dashboard'))

    from models import Employee, Inventory, Sales, Payroll, Customer, Transaction, Account
    from ext import db
    from sqlalchemy import func
    from datetime import date

    total_employees = Employee.query.filter_by(is_active=True).count()
    total_customers = Customer.query.count()
    total_inventory = Inventory.query.count()

    monthly_sales = db.session.query(func.sum(Sales.total_amount)).filter(
        func.strftime('%Y-%m', Sales.invoice_date) == func.strftime('%Y-%m', datetime.now())
    ).scalar() or 0
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
    
    today = date.today()
    start_of_month = date(today.year, today.month, 1)
    
    income_stmt = get_income_statement(start_of_month, today)
    revenue_mtd = income_stmt.get('total_income', 0)
    profit_mtd = income_stmt.get('net_profit', 0)
    
    ar_acc = Account.query.filter_by(name='Accounts Receivable').first()
    ar_outstanding = get_account_balance(ar_acc.id) if ar_acc else 0
    
    cgst_acc = Account.query.filter_by(name='CGST Payable').first()
    sgst_acc = Account.query.filter_by(name='SGST Payable').first()
    igst_acc = Account.query.filter_by(name='IGST Payable').first()
    gst_payable = 0
    if cgst_acc:
        gst_payable += get_account_balance(cgst_acc.id)
    if sgst_acc:
        gst_payable += get_account_balance(sgst_acc.id)
    if igst_acc:
        gst_payable += get_account_balance(igst_acc.id)
    
    monthly_data = get_monthly_revenue_expense(months=6)

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
                         inventory_items=inventory_items,
                         revenue_mtd=revenue_mtd,
                         profit_mtd=profit_mtd,
                         ar_outstanding=ar_outstanding,
                         gst_payable=gst_payable,
                         monthly_data=monthly_data)