from flask import Blueprint, render_template, request, session, redirect, url_for, flash
from routes.dashboard import login_required
from ext import db
from models import Account, Transaction, Payroll, Sales, Inventory, Customer, Vendor
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
        # Default to FY start (April 1 for India)
        if end_date.month >= 4:
            start_date = date(end_date.year, 4, 1)
        else:
            start_date = date(end_date.year - 1, 4, 1)

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
    from accounting_engine import get_account_balance, get_or_create_account, get_period_balance

    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')

    if end_date:
        end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
    else:
        end_date = date.today()

    if start_date:
        start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
    else:
        if end_date.month >= 4:
            start_date = date(end_date.year, 4, 1)
        else:
            start_date = date(end_date.year - 1, 4, 1)

    cgst_payable_acc = get_or_create_account('CGST Payable', 'liability')
    sgst_payable_acc = get_or_create_account('SGST Payable', 'liability')
    igst_payable_acc = get_or_create_account('IGST Payable', 'liability')
    cgst_receivable_acc = get_or_create_account('CGST Receivable', 'asset')
    sgst_receivable_acc = get_or_create_account('SGST Receivable', 'asset')
    igst_receivable_acc = get_or_create_account('IGST Receivable', 'asset')
    
    output_cgst = get_period_balance(cgst_payable_acc.id, start_date, end_date)
    output_sgst = get_period_balance(sgst_payable_acc.id, start_date, end_date)
    output_igst = get_period_balance(igst_payable_acc.id, start_date, end_date)
    
    input_cgst = get_period_balance(cgst_receivable_acc.id, start_date, end_date)
    input_sgst = get_period_balance(sgst_receivable_acc.id, start_date, end_date)
    input_igst = get_period_balance(igst_receivable_acc.id, start_date, end_date)

    # Non-ITC purchases
    input_non_itc_cgst = db.session.query(func.sum(Purchase.cgst_amount)).filter(
        Purchase.invoice_date >= start_date,
        Purchase.invoice_date <= end_date,
        Purchase.itc_eligible == False
    ).scalar() or 0

    input_non_itc_sgst = db.session.query(func.sum(Purchase.sgst_amount)).filter(
        Purchase.invoice_date >= start_date,
        Purchase.invoice_date <= end_date,
        Purchase.itc_eligible == False
    ).scalar() or 0

    input_non_itc_igst = db.session.query(func.sum(Purchase.igst_amount)).filter(
        Purchase.invoice_date >= start_date,
        Purchase.invoice_date <= end_date,
        Purchase.itc_eligible == False
    ).scalar() or 0

    # Net liabilities
    net_cgst = output_cgst - input_cgst
    net_sgst = output_sgst - input_sgst
    net_igst = output_igst - input_igst

    output_gst_total = output_cgst + output_sgst + output_igst
    input_gst_total = input_cgst + input_sgst + input_igst
    itc_non_eligible_gst = input_non_itc_cgst + input_non_itc_sgst + input_non_itc_igst
    net_gst = (net_cgst + net_sgst + net_igst)
    
    return render_template('gst_report.html',
                    output_cgst=output_cgst,
                    output_sgst=output_sgst,
                    output_igst=output_igst,
                    input_cgst=input_cgst,
                    input_sgst=input_sgst,
                    input_igst=input_igst,
                    net_cgst=net_cgst,
                    net_sgst=net_sgst,
                    net_igst=net_igst,
                    net_gst=net_gst,
                    output_gst_total=output_gst_total,
                    input_gst_total=input_gst_total,
                    itc_non_eligible_gst=itc_non_eligible_gst,
                    start_date=start_date,
                    end_date=end_date,
                    as_of_date=end_date)

@bp.route('/reports/gst/pay', methods=['GET', 'POST'])
@login_required
def gst_pay():
    """Pay GST to Government."""
    from accounting_engine import record_gst_payment, get_or_create_account, get_account_balance

    if request.method == 'POST':
        amount = float(request.form.get('amount', 0))
        payment_mode = request.form.get('payment_mode', 'bank')
        notes = request.form.get('notes', '')
        gst_type = request.form.get('gst_type', 'all')

        if amount <= 0:
            flash('Amount must be positive', 'error')
            return redirect(url_for('reports.gst_report'))

        record_gst_payment(date.today(), amount, payment_mode, notes, gst_type)
        flash(f'GST payment of ₹{amount:.2f} recorded', 'success')
        return redirect(url_for('reports.gst_report'))

    # GET - show payment form
    cgst_acc = get_or_create_account('CGST Payable', 'liability')
    sgst_acc = get_or_create_account('SGST Payable', 'liability')
    igst_acc = get_or_create_account('IGST Payable', 'liability')
    
    cgst_itc_acc = get_or_create_account('CGST Receivable', 'asset')
    sgst_itc_acc = get_or_create_account('SGST Receivable', 'asset')
    igst_itc_acc = get_or_create_account('IGST Receivable', 'asset')

    cgst_balance = get_account_balance(cgst_acc.id)
    sgst_balance = get_account_balance(sgst_acc.id)
    igst_balance = get_account_balance(igst_acc.id)
    total_liability = cgst_balance + sgst_balance + igst_balance
    
    cgst_itc = get_account_balance(cgst_itc_acc.id)
    sgst_itc = get_account_balance(sgst_itc_acc.id)
    igst_itc = get_account_balance(igst_itc_acc.id)
    total_itc = cgst_itc + sgst_itc + igst_itc
    
    itc_to_setoff = min(total_itc, total_liability)

    return render_template('gst_payment.html',
                    total_liability=total_liability,
                    cgst_balance=cgst_balance,
                    sgst_balance=sgst_balance,
                    igst_balance=igst_balance,
                    cgst_itc=cgst_itc,
                    sgst_itc=sgst_itc,
                    igst_itc=igst_itc,
                    total_itc=total_itc,
                    itc_to_setoff=itc_to_setoff)

@bp.route('/reports/payroll-summary')
@login_required
def payroll_summary():
    payrolls = Payroll.query.order_by(Payroll.created_at.desc()).all()
    total = db.session.query(func.sum(Payroll.net_salary)).scalar() or 0
    
    return render_template('payroll_summary.html', payrolls=payrolls, total=total)

@bp.route('/reports/aging')
@login_required
def aging_report():
    from models import Purchase, Customer, Vendor, Payment, PurchasePayment
    
    today = date.today()
    
    customer_model = Customer.query
    sales_credit = Sales.query.filter(
        Sales.payment_type == 'credit'
    ).all()
    
    ar_items = []
    for sale in sales_credit:
        customer = db.session.get(Customer, sale.customer_id) if sale.customer_id else None
        days_outstanding = (today - sale.invoice_date).days if sale.invoice_date else 0
        
        already_paid = sum(float(p.amount or 0) for p in sale.payments)
        outstanding = float(sale.total_amount or 0) - already_paid
        
        if outstanding <= 0:
            continue
        
        if days_outstanding <= 30:
            bucket = 'current'
        elif days_outstanding <= 60:
            bucket = '30-60'
        elif days_outstanding <= 90:
            bucket = '61-90'
        else:
            bucket = 'over_90'
        
        ar_items.append({
            'party_name': customer.name if customer else 'Unknown',
            'invoice_number': sale.invoice_number,
            'invoice_date': sale.invoice_date,
            'amount': outstanding,
            'days_outstanding': days_outstanding,
            'bucket': bucket
        })
    
    purchases_credit = Purchase.query.filter(
        Purchase.payment_type == 'credit'
    ).all()
    
    ap_items = []
    for purchase in purchases_credit:
        vendor = db.session.get(Vendor, purchase.vendor_id) if purchase.vendor_id else None
        days_outstanding = (today - purchase.invoice_date).days if purchase.invoice_date else 0
        
        already_paid = sum(float(p.amount or 0) for p in purchase.payments)
        outstanding = float(purchase.total_amount or 0) - already_paid
        
        if outstanding <= 0:
            continue
        
        if days_outstanding <= 30:
            bucket = 'current'
        elif days_outstanding <= 60:
            bucket = '30-60'
        elif days_outstanding <= 90:
            bucket = '61-90'
        else:
            bucket = 'over_90'
        
        ap_items.append({
            'party_name': vendor.name if vendor else purchase.vendor_name or 'Unknown',
            'invoice_number': purchase.invoice_number,
            'invoice_date': purchase.invoice_date,
            'amount': outstanding,
            'days_outstanding': days_outstanding,
            'bucket': bucket
        })
    
    ar_by_bucket = {'current': 0, '30-60': 0, '61-90': 0, 'over_90': 0}
    for item in ar_items:
        ar_by_bucket[item['bucket']] += item['amount']
    
    ap_by_bucket = {'current': 0, '30-60': 0, '61-90': 0, 'over_90': 0}
    for item in ap_items:
        ap_by_bucket[item['bucket']] += item['amount']
    
    return render_template('aging_report.html',
                         ar_items=ar_items,
                         ap_items=ap_items,
                         ar_by_bucket=ar_by_bucket,
                         ap_by_bucket=ap_by_bucket)