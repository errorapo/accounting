from flask import Blueprint, render_template, request, redirect, url_for, flash
from routes.dashboard import login_required
from routes.auth_utils import admin_required
from ext import db
from models import Account, Transaction, JournalEntry
from datetime import datetime, date
from accounting_engine import create_journal_entry, reverse_journal_entry, get_or_create_account, get_account_balance
from models import Transaction

bp = Blueprint('accounts', __name__)

@bp.route('/accounts')
@login_required
def index():
    accounts = Account.query.all()
    account_types = ['asset', 'liability', 'capital', 'income', 'expense']
    balances = {}
    for account in accounts:
        balances[account.id] = get_account_balance(account.id)
    return render_template('accounts.html', accounts=accounts, account_types=account_types, balances=balances)

@bp.route('/accounts/add', methods=['GET', 'POST'])
@login_required
def add_account():
    if request.method == 'POST':
        account = Account(
            name=request.form.get('name'),
            account_type=request.form.get('account_type')
        )
        db.session.add(account)
        db.session.commit()
        flash('Account added successfully', 'success')
        return redirect(url_for('accounts.index'))
    return render_template('add_account.html')

@bp.route('/accounts/delete/<int:id>')
@login_required
@admin_required
def delete_account(id):
    account = Account.query.get_or_404(id)
    account.is_active = False
    db.session.commit()
    flash('Account deleted successfully', 'success')
    return redirect(url_for('accounts.index'))

@bp.route('/ledger')
@login_required
def ledger():
    transactions = Transaction.query.order_by(Transaction.date.desc()).all()
    journal_entries = JournalEntry.query.order_by(JournalEntry.date.desc()).all()
    return render_template('ledger.html', transactions=transactions, journal_entries=journal_entries)

@bp.route('/journal/add', methods=['GET', 'POST'])
@login_required
@admin_required
def add_journal():
    accounts = Account.query.filter_by(is_active=True).all()

    if request.method == 'POST':
        date_str = request.form.get('date')
        description = request.form.get('description')
        debit_account_id = int(request.form.get('debit_account_id'))
        credit_account_id = int(request.form.get('credit_account_id'))
        amount = float(request.form.get('amount', 0))

        if amount <= 0:
            flash('Amount must be greater than zero', 'error')
            return render_template('add_journal.html', accounts=accounts)

        if debit_account_id == credit_account_id:
            flash('Debit and credit accounts must be different', 'error')
            return render_template('add_journal.html', accounts=accounts)

        date = datetime.strptime(date_str, '%Y-%m-%d').date()
        create_journal_entry(date, description, debit_account_id, credit_account_id, amount)

        flash('Journal entry added', 'success')
        return redirect(url_for('accounts.ledger'))

    return render_template('add_journal.html', accounts=accounts)

@bp.route('/journal/reverse/<int:id>', methods=['GET', 'POST'])
@login_required
@admin_required
def reverse_journal(id):
    journal = JournalEntry.query.get_or_404(id)
    
    if journal.is_reversal:
        flash('This entry is already a reversal', 'error')
        return redirect(url_for('accounts.ledger'))
    
    if not journal.is_posted:
        flash('Cannot reverse an unposted entry', 'error')
        return redirect(url_for('accounts.ledger'))
    
    if request.method == 'POST':
        reversal_reason = request.form.get('reason', '')
        try:
            reverse_journal_entry(id, datetime.now().date(), reversal_reason)
            flash('Journal entry reversed successfully', 'success')
        except ValueError as e:
            flash(str(e), 'error')
        return redirect(url_for('accounts.ledger'))
    
    return render_template('reverse_journal.html', journal=journal)

@bp.route('/opening-balances', methods=['GET', 'POST'])
@login_required
@admin_required
def opening_balances():
    existing = Transaction.query.filter(Transaction.description.like('Opening Balance%')).first()
    if existing and request.method == 'GET':
        flash('Opening balances already set. Use date filter in reports for historical view.', 'info')

    if request.method == 'POST':
        balance_date = request.form.get('balance_date')
        if balance_date:
            balance_date = datetime.strptime(balance_date, '%Y-%m-%d').date()
        else:
            balance_date = date.today()

        capital = float(request.form.get('capital', 0))
        cash = float(request.form.get('cash', 0))
        bank = float(request.form.get('bank', 0))
        receivables = float(request.form.get('receivables', 0))
        inventory = float(request.form.get('inventory', 0))
        payables = float(request.form.get('payables', 0))
        loans = float(request.form.get('loans', 0))

        # Use Opening Balance Equity clearing account for all opening balances
        opening_eq = get_or_create_account('Opening Balance Equity', 'capital')

        # Owner equity (non-cash): Dr Opening Balance Equity, Cr Capital
        if capital > 0:
            create_journal_entry(balance_date, "Opening Balance - Capital",
                opening_eq.id,
                get_or_create_account('Capital', 'capital').id, capital)
        if cash > 0:
            create_journal_entry(balance_date, "Opening Balance - Cash",
                get_or_create_account('Cash', 'asset').id,
                opening_eq.id, cash)
        if bank > 0:
            create_journal_entry(balance_date, "Opening Balance - Bank",
                get_or_create_account('Bank', 'asset').id,
                opening_eq.id, bank)
        if receivables > 0:
            create_journal_entry(balance_date, "Opening Balance - Receivables",
                get_or_create_account('Accounts Receivable', 'asset').id,
                opening_eq.id, receivables)
        if inventory > 0:
            create_journal_entry(balance_date, "Opening Balance - Inventory",
                get_or_create_account('Inventory', 'asset').id,
                opening_eq.id, inventory)

        # Liabilities: Dr Opening Balance Equity, Cr Liability
        if payables > 0:
            create_journal_entry(balance_date, "Opening Balance - Accounts Payable",
                opening_eq.id,
                get_or_create_account('Accounts Payable', 'liability').id, payables)
        if loans > 0:
            create_journal_entry(balance_date, "Opening Balance - Loans Payable",
                opening_eq.id,
                get_or_create_account('Loans Payable', 'liability').id, loans)

        flash('Opening balances entered successfully', 'success')
        return redirect(url_for('reports.index'))

    return render_template('opening_balances.html')

@bp.route('/depreciation/run', methods=['POST'])
@admin_required
def run_depreciation():
    from accounting_engine import run_monthly_depreciation
    from datetime import date

    result = run_monthly_depreciation(date.today())

    if result['total_depreciation'] > 0:
        flash(f"Depreciation run: ₹{result['total_depreciation']:.2f} for {len(result['assets_processed'])} assets", 'success')
    elif result['errors']:
        for err in result['errors']:
            flash(err, 'error')
    else:
        flash('No depreciation to run (already processed this month)', 'info')

    return redirect(url_for('accounts.fixed_assets'))

@bp.route('/fixed-assets')
@login_required
def fixed_assets():
    from models import FixedAsset
    assets = FixedAsset.query.filter_by(is_active=True).all()
    return render_template('fixed_assets.html', assets=assets)

@bp.route('/fixed-assets/add', methods=['GET', 'POST'])
@admin_required
def add_fixed_asset():
    from models import FixedAsset
    from ext import db

    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        purchase_date = request.form.get('purchase_date')
        cost = float(request.form.get('cost', 0))
        salvage_value = float(request.form.get('salvage_value', 0))
        useful_life = int(request.form.get('useful_life_years', 0))

        if not name or cost <= 0 or useful_life <= 0:
            flash('Name, cost, and useful life are required', 'error')
            return redirect(url_for('accounts.add_fixed_asset'))

        asset = FixedAsset(
            name=name,
            purchase_date=datetime.strptime(purchase_date, '%Y-%m-%d').date() if purchase_date else date.today(),
            cost=cost,
            salvage_value=salvage_value,
            useful_life_years=useful_life
        )
        db.session.add(asset)
        db.session.commit()

        flash(f'Fixed asset "{name}" added', 'success')
        return redirect(url_for('accounts.fixed_assets'))

    return render_template('add_fixed_asset.html')