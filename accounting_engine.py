"""
Double-Entry Accounting Engine
Handles automated journal entries for business events and financial reports.

FIXED: Income Statement now uses period transactions (not cumulative)
FIXED: Balance Sheet retained earnings accumulates all prior profits
FIXED: Support for credit sales (Accounts Receivable)
"""
from decimal import Decimal
from ext import db
from models import Account, Transaction, JournalEntry
from datetime import datetime, date, timedelta
from sqlalchemy import func

ACCOUNT_TYPES = {
    'asset': {'normal_balance': 'debit', 'increases_with': 'debit'},
    'liability': {'normal_balance': 'credit', 'increases_with': 'credit'},
    'capital': {'normal_balance': 'credit', 'increases_with': 'credit'},
    'income': {'normal_balance': 'credit', 'increases_with': 'credit'},
    'expense': {'normal_balance': 'debit', 'increases_with': 'debit'}
}

DEFAULT_ACCOUNTS = [
    ('Cash', 'asset'),
    ('Bank', 'asset'),
    ('Accounts Receivable', 'asset'),
    ('Inventory', 'asset'),
    ('Fixed Assets', 'asset'),
    ('Accumulated Depreciation', 'asset'),  # Contra-asset - reduces fixed asset value
    ('CGST Receivable', 'asset'),
    ('SGST Receivable', 'asset'),
    ('IGST Receivable', 'asset'),
    ('Accounts Payable', 'liability'),
    ('Loans Payable', 'liability'),
    ('PF Payable', 'liability'),
    ('TDS Payable', 'liability'),
    ('GST Payable', 'liability'),
    ('CGST Payable', 'liability'),
    ('SGST Payable', 'liability'),
    ('IGST Payable', 'liability'),
    ('Capital', 'capital'),
    ('Retained Earnings', 'capital'),
    ('Opening Balance Equity', 'capital'),
    ('Sales Revenue', 'income'),
    ('Service Revenue', 'income'),
    ('Purchases', 'expense'),
    ('COGS', 'expense'),
    ('Salary Expense', 'expense'),
    ('PF Expense', 'expense'),
    ('Rent Expense', 'expense'),
    ('Utilities Expense', 'expense'),
    ('Transport Expense', 'expense'),
    ('Office Expenses', 'expense'),
    ('Interest Expense', 'expense'),
    ('Depreciation Expense', 'expense'),
]

def get_or_create_account(name, account_type):
    """Get existing account or create new one."""
    account = Account.query.filter_by(name=name, is_active=True).first()
    if not account:
        account = Account(name=name, account_type=account_type)
        db.session.add(account)
        db.session.flush()
    return account

def initialize_default_accounts():
    """Create default chart of accounts if not exists."""
    for name, acc_type in DEFAULT_ACCOUNTS:
        get_or_create_account(name, acc_type)
    db.session.commit()

def get_period_balance(account_id, start_date=None, end_date=None):
    """Calculate balance for a specific PERIOD (not cumulative).
    
    Args:
        account_id: The account ID to calculate balance for
        start_date: Start of period (None = beginning)
        end_date: End of period (None = today)
    
    Returns:
        Net balance for the period
    """
    q = Transaction.query.filter(Transaction.account_id == account_id)
    
    if start_date:
        q = q.filter(Transaction.date >= start_date)
    if end_date:
        q = q.filter(Transaction.date <= end_date)
    
    total_debit = q.with_entities(func.sum(Transaction.debit)).scalar() or 0
    total_credit = q.with_entities(func.sum(Transaction.credit)).scalar() or 0
    
    account = Account.query.get(account_id)
    account_type = account.account_type if account else 'asset'
    
    if account_type in ['asset', 'expense']:
        return total_debit - total_credit
    else:
        return total_credit - total_debit

def create_journal_entry(date, description, debit_account_id, credit_account_id, amount, is_posted=True, created_by=None):
    """Create a journal entry with debit and credit."""
    if amount <= 0:
        raise ValueError("Amount must be positive")

    journal = JournalEntry(
        date=date,
        description=description,
        debit_account_id=debit_account_id,
        credit_account_id=credit_account_id,
        amount=amount,
        is_posted=is_posted,
        created_by=created_by
    )
    db.session.add(journal)
    db.session.flush()

    debit_txn = Transaction(
        date=date,
        description=description,
        account_id=debit_account_id,
        debit=amount,
        credit=0,
        entry_type='debit',
        is_posted=is_posted,
        original_entry_id=journal.id,
        created_by=created_by
    )
    credit_txn = Transaction(
        date=date,
        description=description,
        account_id=credit_account_id,
        debit=0,
        credit=amount,
        entry_type='credit',
        is_posted=is_posted,
        original_entry_id=journal.id,
        created_by=created_by
    )
    db.session.add(debit_txn)
    db.session.add(credit_txn)

    db.session.commit()
    return journal

def create_journal_entry_no_commit(date, description, debit_account_id, credit_account_id, amount, created_by=None):
    if amount <= 0:
        raise ValueError("Amount must be positive")

    journal = JournalEntry(
        date=date,
        description=description,
        debit_account_id=debit_account_id,
        credit_account_id=credit_account_id,
        amount=amount,
        is_posted=True,
        created_by=created_by
    )
    db.session.add(journal)
    db.session.flush()

    db.session.add(Transaction(
        date=date, description=description,
        account_id=debit_account_id,
        debit=amount, credit=0, entry_type='debit',
        is_posted=True, original_entry_id=journal.id,
        created_by=created_by
    ))
    db.session.add(Transaction(
        date=date, description=description,
        account_id=credit_account_id,
        debit=0, credit=amount, entry_type='credit',
        is_posted=True, original_entry_id=journal.id,
        created_by=created_by
    ))
    return journal


def reverse_journal_entry(entry_id, reversal_date=None, reversal_reason=""):
    """Reverse a posted journal entry.
    
    In accounting, posted entries cannot be edited or deleted - they must be reversed.
    This creates a reversal entry with opposite debit/credit accounts.
    """
    original = JournalEntry.query.get(entry_id)
    if not original:
        raise ValueError(f"Journal entry {entry_id} not found")
    
    if not original.is_posted:
        raise ValueError("Cannot reverse an unposted entry")
    
    if original.is_reversal:
        raise ValueError("This entry is already a reversal")
    
    # Prevent reversal of opening balance entries
    if original.description and 'Opening Balance' in original.description:
        raise ValueError("Cannot reverse opening balance entries. Use the Opening Balances form to correct them.")

    date = reversal_date or datetime.now().date()
    reason = reversal_reason or f"Reversal of {original.description}"
    
    reversal_journal = JournalEntry(
        date=date,
        description=reason,
        debit_account_id=original.credit_account_id,
        credit_account_id=original.debit_account_id,
        amount=original.amount,
        is_posted=True,
        is_reversal=True,
        original_entry_id=original.id
    )
    db.session.add(reversal_journal)
    db.session.flush()
    
    reversal_debit_txn = Transaction(
        date=date,
        description=reason,
        account_id=original.credit_account_id,
        debit=original.amount,
        credit=0,
        entry_type='debit',
        is_posted=True,
        is_reversal=True,
        original_entry_id=original.id
    )
    reversal_credit_txn = Transaction(
        date=date,
        description=reason,
        account_id=original.debit_account_id,
        debit=0,
        credit=original.amount,
        entry_type='credit',
        is_posted=True,
        is_reversal=True,
        original_entry_id=original.id
    )
    db.session.add(reversal_debit_txn)
    db.session.add(reversal_credit_txn)
    
    db.session.commit()
    return reversal_journal

def get_account_balance(account_id, as_of_date=None):
    """Calculate current balance of an account."""
    query = Transaction.query.filter_by(account_id=account_id)
    
    if as_of_date:
        query = query.filter(Transaction.date <= as_of_date)
    
    total_debit = db.session.query(func.sum(Transaction.debit)).filter(
        Transaction.account_id == account_id
    ).filter(
        Transaction.date <= (as_of_date or datetime.now().date())
    ).scalar() or 0
    
    total_credit = db.session.query(func.sum(Transaction.credit)).filter(
        Transaction.account_id == account_id
    ).filter(
        Transaction.date <= (as_of_date or datetime.now().date())
    ).scalar() or 0

    account = Account.query.get(account_id)
    account_type = account.account_type if account else 'asset'
    
    if account_type in ['asset', 'expense']:
        return total_debit - total_credit
    else:
        return total_credit - total_debit

def get_trial_balance(as_of_date=None):
    """Generate trial balance report."""
    accounts = Account.query.filter_by(is_active=True).all()
    
    trial_balance = []
    total_debits = 0
    total_credits = 0
    
    for account in accounts:
        balance = get_account_balance(account.id, as_of_date)
        
        if balance != 0:
            if balance > 0:
                debit = balance if account.account_type in ['asset', 'expense'] else 0
                credit = balance if account.account_type not in ['asset', 'expense'] else 0
            else:
                debit = abs(balance) if account.account_type not in ['asset', 'expense'] else 0
                credit = abs(balance) if account.account_type in ['asset', 'expense'] else 0
            
            trial_balance.append({
                'account': account.name,
                'account_type': account.account_type,
                'debit': debit,
                'credit': credit
            })
            total_debits += debit
            total_credits += credit
    
    return {
        'accounts': trial_balance,
        'total_debits': total_debits,
        'total_credits': total_credits,
        'is_balanced': abs(total_debits - total_credits) < 0.01,
        'as_of_date': as_of_date or datetime.now().date()
    }

def get_balance_sheet(as_of_date=None):
    """Generate balance sheet report.
    
    FIXED: Retained earnings now accumulates ALL prior profits from start of FY.
    FIXED: Variable name collision - renamed date to report_date to avoid shadowing datetime.date.
    """
    report_date = as_of_date or datetime.now().date()
    
    # Calculate FY start (April 1st for India) using date class
    fy_start_month = 4  # April
    if report_date.month >= fy_start_month:
        fy_start = date(report_date.year, fy_start_month, 1)
    else:
        fy_start = date(report_date.year - 1, fy_start_month, 1)
    
    assets = []
    liabilities = []
    capital = []
    
    total_assets = 0
    total_liabilities = 0
    total_capital = 0
    
    for acc_type in ['asset', 'liability', 'capital']:
        accounts = Account.query.filter_by(account_type=acc_type, is_active=True).all()

        for account in accounts:
            if acc_type == 'capital' and account.name == 'Retained Earnings':
                continue  # handled below via consolidated prior + current calculation
            balance = get_account_balance(account.id, report_date)
            if balance != 0:
                if acc_type == 'asset':
                    assets.append({'name': account.name, 'balance': balance})
                    total_assets += balance
                elif acc_type == 'liability':
                    liabilities.append({'name': account.name, 'balance': balance})
                    total_liabilities += balance
                elif acc_type == 'capital':
                    capital.append({'name': account.name, 'balance': balance})
                    total_capital += balance
    
    # Retained Earnings: prior-year balance + current-year profit
    retained_acc = Account.query.filter_by(name='Retained Earnings', is_active=True).first()
    prior_retained = get_account_balance(retained_acc.id, fy_start - timedelta(days=1)) if retained_acc else 0
    current_year_profit = get_income_statement(fy_start, report_date)['net_profit']
    total_retained = prior_retained + current_year_profit
    if total_retained != 0:
        capital.append({'name': 'Retained Earnings', 'balance': total_retained})
        total_capital += total_retained
    
    return {
        'assets': assets,
        'liabilities': liabilities,
        'capital': capital,
        'total_assets': total_assets,
        'total_liabilities': total_liabilities,
        'total_capital': total_capital,
        'is_balanced': abs(total_assets - (total_liabilities + total_capital)) < 0.01,
        'as_of_date': report_date
    }

def get_income_statement(start_date, end_date):
    """Generate income statement (profit & loss) report for a specific PERIOD.
    
    FIXED: Now uses period-specific transactions, not cumulative balances.
    """
    income_accounts = Account.query.filter_by(account_type='income', is_active=True).all()
    expense_accounts = Account.query.filter_by(account_type='expense', is_active=True).all()
    
    income = []
    expenses = []
    total_income = 0
    total_expenses = 0
    
    for account in income_accounts:
        # FIX: Use period-specific balance, not cumulative
        balance = get_period_balance(account.id, start_date, end_date)
        if balance > 0:
            income.append({'name': account.name, 'amount': balance})
            total_income += balance
    
    for account in expense_accounts:
        # FIX: Use period-specific balance, not cumulative
        balance = get_period_balance(account.id, start_date, end_date)
        if balance > 0:
            expenses.append({'name': account.name, 'amount': balance})
            total_expenses += balance
    
    net_profit = total_income - total_expenses
    
    return {
        'income': income,
        'expenses': expenses,
        'total_income': total_income,
        'total_expenses': total_expenses,
        'net_profit': net_profit,
        'start_date': start_date,
        'end_date': end_date,
        'is_profitable': net_profit >= 0
    }

def record_sale(date, customer_name, amount, gst_amount, payment_type='cash', description="Sale", quantity=0, stone_type=None, size=None, supply_type='intra'):
    """Record a sales transaction with journal entry.

    Journal Entry (intra-state):
        Debit Cash/AR, Credit Sales Revenue
        Debit Cash/AR, Credit CGST Payable
        Debit Cash/AR, Credit SGST Payable

    Journal Entry (inter-state):
        Debit Cash/AR, Credit Sales Revenue
        Debit Cash/AR, Credit IGST Payable

    Args:
        date: Transaction date
        customer_name: Customer name or invoice ref
        amount: Sale amount (before GST)
        gst_amount: GST amount collected
        payment_type: 'cash' or 'credit' - determines debit account
        description: Additional description
        quantity: Quantity sold (for COGS calculation)
        stone_type: Stone type (for COGS lookup from inventory)
        size: Stone size (for COGS lookup from inventory)
        supply_type: 'intra' (CGST+SGST) or 'inter' (IGST only)

    FIXED: Now posts CGST/SGST or IGST based on supply_type.
    FIXED: Now supports credit sales (Accounts Receivable).
    FIXED: Now records COGS based on inventory cost rate.
    """
    from models import Inventory

    sales_acc = get_or_create_account('Sales Revenue', 'income')
    cgst_payable = get_or_create_account('CGST Payable', 'liability')
    sgst_payable = get_or_create_account('SGST Payable', 'liability')
    igst_payable = get_or_create_account('IGST Payable', 'liability')

    if isinstance(date, str):
        date = datetime.strptime(date, '%Y-%m-%d').date()

    if payment_type == 'credit':
        receivable_acc = get_or_create_account('Accounts Receivable', 'asset')
        debit_account = receivable_acc
        desc = f"Sale (Credit) - {customer_name} - {description}"
    else:
        cash_acc = get_or_create_account('Cash', 'asset')
        debit_account = cash_acc
        desc = f"Sale (Cash) - {customer_name} - {description}"

    create_journal_entry(date, desc, debit_account.id, sales_acc.id, amount)

    if gst_amount > 0:
        if supply_type == 'inter':
            igst_desc = f"IGST Collected - {description}"
            create_journal_entry(date, igst_desc, debit_account.id, igst_payable.id, gst_amount)
        else:
            half_gst = gst_amount / 2
            cgst_desc = f"CGST Collected - {description}"
            create_journal_entry(date, cgst_desc, debit_account.id, cgst_payable.id, half_gst)
            sgst_desc = f"SGST Collected - {description}"
            create_journal_entry(date, sgst_desc, debit_account.id, sgst_payable.id, half_gst)

    if quantity > 0 and stone_type and size:
        item = Inventory.query.filter_by(stone_type=stone_type, size=size).first()
        if item and item.rate_per_ton > 0:
            cogs_acc = get_or_create_account('COGS', 'expense')
            inventory_acc = get_or_create_account('Inventory', 'asset')
            cogs_amount = quantity * item.rate_per_ton
            cogs_desc = f"COGS - {description}"
            create_journal_entry(date, cogs_desc, cogs_acc.id, inventory_acc.id, cogs_amount)

            # Update inventory for weighted average cost
            if item.closing_stock < quantity:
                raise ValueError(
                    f"Insufficient stock: only {item.closing_stock} tons "
                    f"of {stone_type} {size} available, cannot sell {quantity}."
                )
            item.closing_stock = (item.closing_stock or 0) - quantity
            item.sales = (item.sales or 0) + quantity
            if item.closing_stock > 0:
                item.total_cost = item.closing_stock * item.rate_per_ton
            else:
                item.total_cost = 0

    return {
        'type': 'sale',
        'customer': customer_name,
        'amount': amount,
        'gst_amount': gst_amount,
        'payment_type': payment_type,
        'description': desc
    }

def record_purchase(date, vendor_name, amount, gst_amount, itc_eligible=True, payment_type='cash', description="Purchase", quantity=0, stone_type=None, size=None, supply_type='intra'):
    """Record a purchase with journal entry.

    Args:
        date: Transaction date
        vendor_name: Vendor/supplier name
        amount: Base purchase amount (BEFORE GST - pre-GST subtotal)
        gst_amount: GST amount paid
        itc_eligible: Whether Input Tax Credit can be claimed
        payment_type: 'cash' or 'credit'
        description: Additional description
        quantity: Quantity purchased (for inventory tracking)
        stone_type: Stone type (for inventory lookup)
        size: Stone size (for inventory lookup)
        supply_type: 'intra' (CGST+SGST) or 'inter' (IGST only)

    Journal Entry for ITC purchase (credit):
        Inventory (cost) + CGST/SGST or IGST Receivable → Accounts Payable (total)
    Journal Entry for non-ITC purchase (credit):
        Inventory (total incl. GST) → Accounts Payable (total)
    """
    from models import Inventory

    if isinstance(date, str):
        date = datetime.strptime(date, '%Y-%m-%d').date()

    total_invoice = amount + gst_amount
    cgst_receivable = get_or_create_account('CGST Receivable', 'asset')
    sgst_receivable = get_or_create_account('SGST Receivable', 'asset')
    igst_receivable = get_or_create_account('IGST Receivable', 'asset')

    # Check if this is an inventory-tracking purchase
    is_inventory_purchase = quantity > 0 and stone_type and size
    item = None
    if is_inventory_purchase:
        item = Inventory.query.filter_by(stone_type=stone_type, size=size).first()

    if payment_type == 'credit':
        payable_acc = get_or_create_account('Accounts Payable', 'liability')
        credit_account = payable_acc
        desc = f"Purchase (Credit) - {vendor_name} - {description}"
    else:
        cash_acc = get_or_create_account('Cash', 'asset')
        credit_account = cash_acc
        desc = f"Purchase (Cash) - {vendor_name} - {description}"

    if itc_eligible and gst_amount > 0:
        if item and item.rate_per_ton > 0:
            inventory_acc = get_or_create_account('Inventory', 'asset')
            create_journal_entry(date, desc, inventory_acc.id, credit_account.id, amount)
        else:
            purchases_acc = get_or_create_account('Purchases', 'expense')
            create_journal_entry(date, desc, purchases_acc.id, credit_account.id, amount)

        # Split ITC by supply type
        if supply_type == 'inter':
            gst_itc_desc = f"ITC IGST - {description}"
            create_journal_entry(date, gst_itc_desc, igst_receivable.id, credit_account.id, gst_amount)
        else:
            half_gst = gst_amount / 2
            cgst_itc_desc = f"ITC CGST - {description}"
            create_journal_entry(date, cgst_itc_desc, cgst_receivable.id, credit_account.id, half_gst)
            sgst_itc_desc = f"ITC SGST - {description}"
            create_journal_entry(date, sgst_itc_desc, sgst_receivable.id, credit_account.id, half_gst)
    elif is_inventory_purchase and item and item.rate_per_ton > 0:
        # Non-ITC but inventory-tracked: GST added to inventory cost
        inventory_acc = get_or_create_account('Inventory', 'asset')
        create_journal_entry(date, desc, inventory_acc.id, credit_account.id, total_invoice)
    else:
        # Non-ITC expense purchase: GST added to expense
        purchases_acc = get_or_create_account('Purchases', 'expense')
        create_journal_entry(date, desc, purchases_acc.id, credit_account.id, total_invoice)

    # Update inventory weighted average cost
    if is_inventory_purchase and item:
        unit_cost = amount / Decimal(str(quantity)) if quantity > 0 else Decimal('0')
        new_stock = (item.closing_stock or 0) + Decimal(str(quantity))
        new_total_cost = (item.closing_stock or 0) * (item.rate_per_ton or 0) + Decimal(str(quantity)) * unit_cost
        if new_stock > 0:
            item.rate_per_ton = new_total_cost / new_stock
        item.total_cost = new_total_cost
        item.closing_stock = new_stock
        item.purchases = (item.purchases or 0) + Decimal(str(quantity))

    return {
        'type': 'purchase',
        'vendor': vendor_name,
        'amount': amount,
        'gst_amount': gst_amount,
        'itc_eligible': itc_eligible,
        'payment_type': payment_type,
        'description': desc
    }

def record_salary_payment(date, employee_name, gross_salary, pf_deduction=0, employer_pf=0, tax_deduction=0, description="Salary"):
    """Record salary payment with proper compound journal entry.

    Compound Journal Entry:
        Dr Salary Expense   (gross_salary)
            Cr Cash         (net = gross - pf_deduction - tax_deduction)
            Cr PF Payable   (employee pf deduction)
            Cr TDS Payable  (tax deducted)
        Dr PF Expense     (employer_pf)
            Cr PF Payable   (employer contribution)

    Args:
        date: Transaction date
        employee_name: Employee name
        gross_salary: Gross salary amount
        pf_deduction: Employee PF deduction (to be held in PF Payable)
        employer_pf: Employer PF contribution
        tax_deduction: TDS deducted from employee salary
        description: Additional description
    """
    from models import JournalEntry, Transaction

    salary_expense = get_or_create_account('Salary Expense', 'expense')
    pf_expense = get_or_create_account('PF Expense', 'expense')
    cash_acc = get_or_create_account('Cash', 'asset')
    pf_payable = get_or_create_account('PF Payable', 'liability')
    tds_payable = get_or_create_account('TDS Payable', 'liability')

    if isinstance(date, str):
        date = datetime.strptime(date, '%Y-%m-%d').date()

    net_salary = gross_salary - pf_deduction - tax_deduction
    base_desc = f"Salary - {employee_name} - {description}"

    # Create compound journal entry using no_commit version
    journal = JournalEntry(
        date=date,
        description=base_desc,
        debit_account_id=salary_expense.id,
        credit_account_id=cash_acc.id,
        amount=gross_salary,
        is_posted=True
    )
    db.session.add(journal)
    db.session.flush()

    # Line 1: Dr Salary Expense, Cr Cash (net pay)
    txn1 = Transaction(date=date, description=base_desc + " (Net)",
        account_id=salary_expense.id, debit=net_salary, credit=0, entry_type='debit',
        is_posted=True, original_entry_id=journal.id)
    txn2 = Transaction(date=date, description=base_desc + " (Net)",
        account_id=cash_acc.id, debit=0, credit=net_salary, entry_type='credit',
        is_posted=True, original_entry_id=journal.id)
    db.session.add(txn1)
    db.session.add(txn2)

    # Line 2: Dr Salary Expense, Cr PF Payable (employee deduction)
    if pf_deduction > 0:
        txn3 = Transaction(date=date, description=base_desc + " (PF Deducted)",
            account_id=salary_expense.id, debit=pf_deduction, credit=0, entry_type='debit',
            is_posted=True, original_entry_id=journal.id)
        txn4 = Transaction(date=date, description=base_desc + " (PF Deducted)",
            account_id=pf_payable.id, debit=0, credit=pf_deduction, entry_type='credit',
            is_posted=True, original_entry_id=journal.id)
        db.session.add(txn3)
        db.session.add(txn4)

    # Line 3: Dr Salary Expense, Cr TDS Payable (TDS deducted)
    if tax_deduction > 0:
        txn5 = Transaction(date=date, description=base_desc + " (TDS Deducted)",
            account_id=salary_expense.id, debit=tax_deduction, credit=0, entry_type='debit',
            is_posted=True, original_entry_id=journal.id)
        txn6 = Transaction(date=date, description=base_desc + " (TDS Deducted)",
            account_id=tds_payable.id, debit=0, credit=tax_deduction, entry_type='credit',
            is_posted=True, original_entry_id=journal.id)
        db.session.add(txn5)
        db.session.add(txn6)

    # Line 4: Dr PF Expense, Cr PF Payable (employer contribution)
    if employer_pf > 0:
        employer_desc = f"Employer PF - {employee_name}"
        journal2 = JournalEntry(
            date=date,
            description=employer_desc,
            debit_account_id=pf_expense.id,
            credit_account_id=pf_payable.id,
            amount=employer_pf,
            is_posted=True
        )
        db.session.add(journal2)
        db.session.flush()

        txn7 = Transaction(date=date, description=employer_desc,
            account_id=pf_expense.id, debit=employer_pf, credit=0, entry_type='debit',
            is_posted=True, original_entry_id=journal2.id)
        txn8 = Transaction(date=date, description=employer_desc,
            account_id=pf_payable.id, debit=0, credit=employer_pf, entry_type='credit',
            is_posted=True, original_entry_id=journal2.id)
        db.session.add(txn7)
        db.session.add(txn8)

    db.session.commit()

    return {
        'type': 'salary',
        'employee': employee_name,
        'gross_salary': gross_salary,
        'net_salary': net_salary,
        'pf_deduction': pf_deduction,
        'employer_pf': employer_pf,
        'tax_deduction': tax_deduction,
        'description': description
    }

def record_expense(date, expense_name, amount, description="Expense"):
    """Record a general expense with journal entry."""
    expense_acc = get_or_create_account(expense_name if expense_name.endswith(' Expense') else f'{expense_name} Expense', 'expense')
    cash_acc = get_or_create_account('Cash', 'asset')

    if isinstance(date, str):
        date = datetime.strptime(date, '%Y-%m-%d').date()

    desc = f"{expense_name} - {description}"

    create_journal_entry(date, desc, expense_acc.id, cash_acc.id, amount)

    return {
        'type': 'expense',
        'expense': expense_name,
        'amount': amount,
        'description': desc
    }

def record_payment(date, sale_id, amount, payment_mode='cash', notes='', description=""):
    """Record a payment against a credit sale (partial or full).

    Journal Entry:
        Cash Payment: Debit Cash, Credit Accounts Receivable
        Bank Payment:  Debit Bank,  Credit Accounts Receivable
        UPI Payment:   Debit Bank,  Credit Accounts Receivable
        Cheque:        Debit Bank,  Credit Accounts Receivable

    Args:
        date: Transaction date
        sale_id: The sale ID this payment is against
        amount: Payment amount
        payment_mode: 'cash', 'bank', 'upi', 'cheque'
        notes: Optional notes
        description: Additional description

    Returns:
        dict with payment details
    """
    if isinstance(date, str):
        date = datetime.strptime(date, '%Y-%m-%d').date()

    receivable_acc = get_or_create_account('Accounts Receivable', 'asset')

    if payment_mode == 'cash':
        debit_account = get_or_create_account('Cash', 'asset')
    else:
        # bank, upi, cheque - all go to Bank account
        debit_account = get_or_create_account('Bank', 'asset')

    desc = description or f"Payment received against Sale #{sale_id}"

    create_journal_entry(date, desc, debit_account.id, receivable_acc.id, amount)

    return {
        'type': 'payment',
        'sale_id': sale_id,
        'amount': amount,
        'payment_mode': payment_mode,
        'notes': notes,
        'description': desc
    }

def record_purchase_payment(date, purchase_id, amount, payment_mode='cash', notes='', description=""):
    """Record a payment against a credit purchase (partial or full).

    Journal Entry:
        Cash Payment: Debit Accounts Payable, Credit Cash
        Bank Payment:  Debit Accounts Payable, Credit Bank

    Args:
        date: Transaction date
        purchase_id: The purchase ID this payment is against
        amount: Payment amount
        payment_mode: 'cash', 'bank', 'upi', 'cheque'
        notes: Optional notes
        description: Additional description

    Returns:
        dict with payment details
    """
    if isinstance(date, str):
        date = datetime.strptime(date, '%Y-%m-%d').date()

    payable_acc = get_or_create_account('Accounts Payable', 'liability')

    if payment_mode == 'cash':
        credit_account = get_or_create_account('Cash', 'asset')
    else:
        credit_account = get_or_create_account('Bank', 'asset')

    desc = description or f"Payment made against Purchase #{purchase_id}"

    create_journal_entry(date, desc, payable_acc.id, credit_account.id, amount)

    return {
        'type': 'purchase_payment',
        'purchase_id': purchase_id,
        'amount': amount,
        'payment_mode': payment_mode,
        'notes': notes,
        'description': desc
    }

def record_gst_payment(date, amount, payment_mode='bank', notes='', gst_type='all'):
    """Record GST paid to Government.

    Journal Entry:
        Debit:  CGST/SGST/IGST Payable (reduces liability)
        Credit: Bank/Cash (payment method)

    Args:
        date: Payment date
        amount: GST amount being paid
        payment_mode: 'bank', 'cash', 'upi'
        notes: Optional notes
        gst_type: 'cgst', 'sgst', 'igst', 'all', or 'legacy'

    Returns:
        dict with payment details
    """
    if isinstance(date, str):
        date = datetime.strptime(date, '%Y-%m-%d').date()

    if amount <= 0:
        raise ValueError("Amount must be positive")

    if payment_mode == 'cash':
        credit_account = get_or_create_account('Cash', 'asset')
    else:
        credit_account = get_or_create_account('Bank', 'asset')

    desc = "GST Paid to Government"

    if gst_type == 'legacy':
        gst_payable = get_or_create_account('GST Payable', 'liability')
        create_journal_entry(date, desc, gst_payable.id, credit_account.id, amount)
    elif gst_type == 'all':
        split_amount = amount / 2
        cgst_payable = get_or_create_account('CGST Payable', 'liability')
        sgst_payable = get_or_create_account('SGST Payable', 'liability')
        create_journal_entry(date, desc + " - CGST", cgst_payable.id, credit_account.id, split_amount)
        create_journal_entry(date, desc + " - SGST", sgst_payable.id, credit_account.id, split_amount)
    elif gst_type == 'cgst':
        cgst_payable = get_or_create_account('CGST Payable', 'liability')
        create_journal_entry(date, desc + " - CGST", cgst_payable.id, credit_account.id, amount)
    elif gst_type == 'sgst':
        sgst_payable = get_or_create_account('SGST Payable', 'liability')
        create_journal_entry(date, desc + " - SGST", sgst_payable.id, credit_account.id, amount)
    elif gst_type == 'igst':
        igst_payable = get_or_create_account('IGST Payable', 'liability')
        create_journal_entry(date, desc + " - IGST", igst_payable.id, credit_account.id, amount)
    else:
        raise ValueError("Invalid gst_type: must be 'cgst', 'sgst', 'igst', 'all', or 'legacy'")

    return {
        'type': 'gst_payment',
        'amount': amount,
        'payment_mode': payment_mode,
        'gst_type': gst_type,
        'notes': notes,
        'description': desc
    }

def run_monthly_depreciation(as_of_date=None):
    """Run monthly depreciation for all fixed assets (straight-line method).

    Calculates: monthly_dep = (cost - salvage_value) / (useful_life_years * 12)
    Creates journal entry: Dr Depreciation Expense, Cr Accumulated Depreciation.
    Avoids duplicate entries by checking for existing depreciation for asset+month.

    Args:
        as_of_date: Date for depreciation (defaults to today)

    Returns:
        dict with assets_processed, total_depreciation, errors
    """
    from datetime import date
    from models import FixedAsset

    if as_of_date is None:
        as_of_date = date.today()

    month_key = f"{as_of_date.year}-{as_of_date.month:02d}"

    dep_expense = get_or_create_account('Depreciation Expense', 'expense')
    accum_dep = get_or_create_account('Accumulated Depreciation', 'asset')

    assets = FixedAsset.query.filter_by(is_active=True).all()

    processed = []
    total_dep = 0
    errors = []

    for asset in assets:
        desc = f"Depreciation - {asset.name} - {month_key}"

        existing = JournalEntry.query.filter(
            JournalEntry.description.like(f"Depreciation - {asset.name}%")
        ).all()
        if any(month_key in (je.description or '') for je in existing):
            continue

        monthly_dep = (asset.cost - asset.salvage_value) / (asset.useful_life_years * 12)

        if monthly_dep <= 0:
            errors.append(f"{asset.name}: invalid depreciation calculation")
            continue

        create_journal_entry(as_of_date, desc, dep_expense.id, accum_dep.id, monthly_dep)

        asset.accumulated_depreciation = (asset.accumulated_depreciation or 0) + monthly_dep

        processed.append({'name': asset.name, 'depreciation': float(monthly_dep)})
        total_dep += monthly_dep

    return {
        'assets_processed': processed,
        'total_depreciation': float(total_dep),
        'month': month_key,
        'errors': errors
    }

def get_monthly_revenue_expense(months=6):
    """Get monthly revenue and expense data for charts.
    
    Args:
        months: Number of months to return (default 6)
    
    Returns:
        dict with labels (month names), revenue list, expense list
    """
    from datetime import date, timedelta
    from dateutil.relativedelta import relativedelta
    from models import Transaction, Account
    from decimal import Decimal
    
    today = date.today()
    result = {
        'labels': [],
        'revenue': [],
        'expenses': []
    }
    
    sales_acc = Account.query.filter_by(name='Sales Revenue').first()
    expense_accounts = Account.query.filter_by(account_type='expense').all()
    expense_ids = [a.id for a in expense_accounts]
    
    for i in range(months - 1, -1, -1):
        month_start = today.replace(day=1) - relativedelta(months=i)
        if i == 0:
            month_end = today
        else:
            month_end = month_start + relativedelta(months=1) - timedelta(days=1)
        
        month_name = month_start.strftime('%b')
        result['labels'].append(month_name)
        
        revenue = 0
        expenses = 0
        
        if sales_acc:
            rev_trans = Transaction.query.filter(
                Transaction.account_id == sales_acc.id,
                Transaction.date >= month_start,
                Transaction.date <= month_end,
                Transaction.is_posted == True
            ).all()
            revenue = sum(t.credit or 0 for t in rev_trans)
        
        exp_trans = Transaction.query.filter(
            Transaction.account_id.in_(expense_ids),
            Transaction.date >= month_start,
            Transaction.date <= month_end,
            Transaction.is_posted == True
        ).all()
        expenses = sum(t.debit or 0 for t in exp_trans)
        
        result['revenue'].append(float(revenue))
        result['expenses'].append(float(expenses))
    
    return result
