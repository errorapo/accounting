"""
Double-Entry Accounting Engine
Handles automated journal entries for business events and financial reports.

FIXED: Income Statement now uses period transactions (not cumulative)
FIXED: Balance Sheet retained earnings accumulates all prior profits
FIXED: Support for credit sales (Accounts Receivable)
"""
from ext import db
from models import Account, Transaction, JournalEntry
from datetime import datetime, date
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
    ('Accounts Payable', 'liability'),
    ('Loans Payable', 'liability'),
    ('PF Payable', 'liability'),
    ('TDS Payable', 'liability'),
    ('GST Payable', 'liability'),
    ('GST Receivable', 'asset'),
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

def create_journal_entry(date, description, debit_account_id, credit_account_id, amount, is_posted=True):
    """Create a journal entry with debit and credit."""
    if amount <= 0:
        raise ValueError("Amount must be positive")

    journal = JournalEntry(
        date=date,
        description=description,
        debit_account_id=debit_account_id,
        credit_account_id=credit_account_id,
        amount=amount,
        is_posted=is_posted
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
        original_entry_id=journal.id
    )
    credit_txn = Transaction(
        date=date,
        description=description,
        account_id=credit_account_id,
        debit=0,
        credit=amount,
        entry_type='credit',
        is_posted=is_posted,
        original_entry_id=journal.id
    )
    db.session.add(debit_txn)
    db.session.add(credit_txn)

    db.session.commit()
    return journal

def create_journal_entry_no_commit(date, description, debit_account_id, credit_account_id, amount):
    if amount <= 0:
        raise ValueError("Amount must be positive")

    journal = JournalEntry(
        date=date,
        description=description,
        debit_account_id=debit_account_id,
        credit_account_id=credit_account_id,
        amount=amount,
        is_posted=True
    )
    db.session.add(journal)
    db.session.flush()

    db.session.add(Transaction(
        date=date, description=description,
        account_id=debit_account_id,
        debit=amount, credit=0, entry_type='debit',
        is_posted=True, original_entry_id=journal.id
    ))
    db.session.add(Transaction(
        date=date, description=description,
        account_id=credit_account_id,
        debit=0, credit=amount, entry_type='credit',
        is_posted=True, original_entry_id=journal.id
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
                continue
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
    
    # FIX: Accumulate ALL prior profits from start of FY, not just current month
    retained_earnings = get_income_statement(fy_start, report_date)['net_profit']
    if retained_earnings != 0:
        capital.append({'name': 'Retained Earnings', 'balance': retained_earnings})
        total_capital += retained_earnings
    
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

def record_sale(date, customer_name, amount, gst_amount, payment_type='cash', description="Sale", quantity=0, stone_type=None, size=None):
    """Record a sales transaction with journal entry.

    Journal Entry:
        Cash Sale:  Debit Cash, Credit Sales Revenue + Credit GST Payable
        Credit Sale: Debit Accounts Receivable, Credit Sales Revenue + Credit GST Payable

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

    FIXED: Now posts GST Payable liability.
    FIXED: Now supports credit sales (Accounts Receivable).
    FIXED: Now records COGS based on inventory cost rate.
    """
    from models import Inventory

    sales_acc = get_or_create_account('Sales Revenue', 'income')
    gst_payable_acc = get_or_create_account('GST Payable', 'liability')

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

    # Debit: Cash or AR for the taxable amount
    create_journal_entry(date, desc, debit_account.id, sales_acc.id, amount)

    # Credit: GST Payable (output GST collected from customer)
    if gst_amount > 0:
        gst_desc = f"GST Collected - {description}"
        create_journal_entry(date, gst_desc, debit_account.id, gst_payable_acc.id, gst_amount)

    if quantity > 0 and stone_type and size:
        item = Inventory.query.filter_by(stone_type=stone_type, size=size).first()
        if item and item.rate_per_ton > 0:
            cogs_acc = get_or_create_account('COGS', 'expense')
            inventory_acc = get_or_create_account('Inventory', 'asset')
            cogs_amount = quantity * item.rate_per_ton
            cogs_desc = f"COGS - {description}"
            create_journal_entry(date, cogs_desc, cogs_acc.id, inventory_acc.id, cogs_amount)

    return {
        'type': 'sale',
        'customer': customer_name,
        'amount': amount,
        'gst_amount': gst_amount,
        'payment_type': payment_type,
        'description': desc
    }

def record_purchase(date, vendor_name, amount, gst_amount, itc_eligible=True, payment_type='cash', description="Purchase", quantity=0, stone_type=None, size=None):
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

    Journal Entry for ITC purchase (credit):
        Inventory (cost) + GST Receivable (ITC) → Accounts Payable (total)
    Journal Entry for non-ITC purchase (credit):
        Inventory (total incl. GST) → Accounts Payable (total)
    """
    from models import Inventory

    if isinstance(date, str):
        date = datetime.strptime(date, '%Y-%m-%d').date()

    total_invoice = amount + gst_amount

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

        gst_recv_acc = get_or_create_account('GST Receivable', 'asset')
        gst_itc_desc = f"ITC GST - {description}"
        create_journal_entry(date, gst_itc_desc, gst_recv_acc.id, credit_account.id, gst_amount)
    elif is_inventory_purchase and item and item.rate_per_ton > 0:
        # Non-ITC but inventory-tracked: GST added to inventory cost
        inventory_acc = get_or_create_account('Inventory', 'asset')
        create_journal_entry(date, desc, inventory_acc.id, credit_account.id, total_invoice)
    else:
        # Non-ITC expense purchase: GST added to expense
        purchases_acc = get_or_create_account('Purchases', 'expense')
        create_journal_entry(date, desc, purchases_acc.id, credit_account.id, total_invoice)

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
    """Record salary payment with proper journal entry.

    Journal Entry:
        Debit:  Salary Expense (gross)
        Credit: Cash (net pay)
        Credit: PF Payable (employee PF deduction)
        Credit: PF Payable (employer PF contribution)
        Credit: TDS Payable (TDS deducted)

    Args:
        date: Transaction date
        employee_name: Employee name
        gross_salary: Gross salary amount
        pf_deduction: Employee PF deduction (to be held in PF Payable)
        employer_pf: Employer PF contribution
        tax_deduction: TDS deducted from employee salary
        description: Additional description
    """
    salary_expense = get_or_create_account('Salary Expense', 'expense')
    pf_expense = get_or_create_account('PF Expense', 'expense')
    cash_acc = get_or_create_account('Cash', 'asset')
    pf_payable = get_or_create_account('PF Payable', 'liability')
    tds_payable = get_or_create_account('TDS Payable', 'liability')

    if isinstance(date, str):
        date = datetime.strptime(date, '%Y-%m-%d').date()

    net_salary = gross_salary - pf_deduction - tax_deduction

    # Dr Salary Expense (gross), Cr Cash (net pay)
    if net_salary > 0:
        create_journal_entry(date, f"Salary - {employee_name} - Net", salary_expense.id, cash_acc.id, net_salary)

    # Dr Salary Expense, Cr PF Payable (employee deduction)
    if pf_deduction > 0:
        create_journal_entry(date, f"PF Deducted - {employee_name}", salary_expense.id, pf_payable.id, pf_deduction)

    # Dr Salary Expense, Cr TDS Payable (TDS deducted)
    if tax_deduction > 0:
        create_journal_entry(date, f"TDS Deducted - {employee_name}", salary_expense.id, tds_payable.id, tax_deduction)

    # Employer PF: Dr PF Expense, Cr PF Payable (employer contribution)
    if employer_pf > 0:
        create_journal_entry(date, f"Employer PF - {employee_name}", pf_expense.id, pf_payable.id, employer_pf)

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

def record_gst_payment(date, amount, payment_mode='bank', notes=''):
    """Record GST paid to Government.

    Journal Entry:
        Debit:  GST Payable (reduces liability)
        Credit: Bank/Cash (payment method)

    Args:
        date: Payment date
        amount: GST amount being paid
        payment_mode: 'bank', 'cash', 'upi'
        notes: Optional notes

    Returns:
        dict with payment details
    """
    if isinstance(date, str):
        date = datetime.strptime(date, '%Y-%m-%d').date()

    if amount <= 0:
        raise ValueError("Amount must be positive")

    gst_payable = get_or_create_account('GST Payable', 'liability')

    if payment_mode == 'cash':
        credit_account = get_or_create_account('Cash', 'asset')
    else:
        credit_account = get_or_create_account('Bank', 'asset')

    desc = "GST Paid to Government"

    create_journal_entry(date, desc, gst_payable.id, credit_account.id, amount)

    return {
        'type': 'gst_payment',
        'amount': amount,
        'payment_mode': payment_mode,
        'notes': notes,
        'description': desc
    }
