from flask import Blueprint, render_template, request, session, redirect, url_for
from routes.dashboard import login_required
from ext import db
from models import Account, Transaction, Payroll, Sales, Inventory
from sqlalchemy import func
from datetime import datetime, date
from accounting_engine import get_trial_balance, get_balance_sheet, get_income_statement, initialize_default_accounts

bp = Blueprint('reports', __name__)

@bp.route('/reports')
@login_required
def index():
    initialize_default_accounts()
    return render_template('reports.html')

@bp.route('/reports/trial-balance')
@login_required
def trial_balance():
    as_of_date = request.args.get('date')
    if as_of_date:
        as_of_date = datetime.strptime(as_of_date, '%Y-%m-%d').date()
    else:
        as_of_date = date.today()
    
    trial_balance = get_trial_balance(as_of_date)
    
    return render_template('trial_balance.html', 
                         data=trial_balance['accounts'],
                         total_dr=trial_balance['total_debits'],
                         total_cr=trial_balance['total_credits'],
                         is_balanced=trial_balance['is_balanced'],
                         as_of_date=as_of_date)

@bp.route('/reports/profit-loss')
@login_required
def profit_loss():
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    
    if end_date:
        end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
    else:
        end_date = date.today()
    
    if start_date:
        start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
    else:
        start_date = date(end_date.year, 1, 1)
    
    income_stmt = get_income_statement(start_date, end_date)
    
    return render_template('profit_loss.html', 
                         income=income_stmt['income'],
                         expenses=income_stmt['expenses'],
                         total_income=income_stmt['total_income'],
                         total_expenses=income_stmt['total_expenses'],
                         net_profit=income_stmt['net_profit'],
                         is_profitable=income_stmt['is_profitable'],
                         start_date=start_date,
                         end_date=end_date)

@bp.route('/reports/balance-sheet')
@login_required
def balance_sheet():
    as_of_date = request.args.get('date')
    if as_of_date:
        as_of_date = datetime.strptime(as_of_date, '%Y-%m-%d').date()
    else:
        as_of_date = date.today()
    
    bs = get_balance_sheet(as_of_date)
    
    return render_template('balance_sheet.html', 
                     assets=bs['assets'],
                     liabilities=bs['liabilities'],
                     capital=bs['capital'],
                     total_assets=bs['total_assets'],
                     total_liabilities=bs['total_liabilities'],
                     total_capital=bs['total_capital'],
                     is_balanced=bs['is_balanced'],
                     as_of_date=as_of_date)

@bp.route('/reports/gst')
@login_required
def gst_report():
    from models import Purchase

    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')

    if end_date:
        end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
    else:
        end_date = date.today()

    if start_date:
        start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
    else:
        start_date = date(end_date.year, 1, 1)

    output_gst = db.session.query(func.sum(Sales.gst_amount)).filter(
        Sales.invoice_date >= start_date,
        Sales.invoice_date <= end_date
    ).scalar() or 0

    input_gst_total = db.session.query(func.sum(Purchase.gst_amount)).filter(
        Purchase.invoice_date >= start_date,
        Purchase.invoice_date <= end_date
    ).scalar() or 0

    itc_eligible_gst = db.session.query(func.sum(Purchase.gst_amount)).filter(
        Purchase.invoice_date >= start_date,
        Purchase.invoice_date <= end_date,
        Purchase.itc_eligible == True
    ).scalar() or 0

    itc_non_eligible_gst = input_gst_total - itc_eligible_gst
    net_gst = output_gst - itc_eligible_gst

    return render_template('gst_report.html',
                    output_gst=output_gst,
                    input_gst_total=input_gst_total,
                    itc_eligible_gst=itc_eligible_gst,
                    itc_non_eligible_gst=itc_non_eligible_gst,
                    net_gst=net_gst,
                    start_date=start_date,
                    end_date=end_date,
                    as_of_date=end_date)

@bp.route('/reports/payroll-summary')
@login_required
def payroll_summary():
    payrolls = Payroll.query.order_by(Payroll.created_at.desc()).all()
    total = db.session.query(func.sum(Payroll.net_salary)).scalar() or 0
    
    return render_template('payroll_summary.html', payrolls=payrolls, total=total)