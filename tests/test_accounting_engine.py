"""Unit tests for accounting_engine.py."""

import os
import sys
import pytest
from decimal import Decimal
from datetime import date, datetime

# Set environment BEFORE imports
os.environ['REDIS_URL'] = 'memory://'
os.environ['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
os.environ['SKIP_INIT_DEFAULT_DATA'] = 'true'

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app, init_default_data
from ext import db
from models import Account, Transaction, JournalEntry, Customer, Inventory, Sales
from accounting_engine import (
    record_sale, record_purchase, record_salary_payment, record_expense,
    get_account_balance, get_balance_sheet, get_income_statement,
    reverse_journal_entry, record_gst_payment, get_trial_balance
)


@pytest.fixture
def app_context():
    """Create fresh app context for each test."""
    app = create_app('development')
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False
    
    with app.app_context():
        db.drop_all()
        db.create_all()
        init_default_data()
        yield app
        db.drop_all()


@pytest.fixture
def client(app_context):
    """Return test client."""
    return app_context.test_client()


def test_double_entry_always_balanced(app_context):
    """After any transaction, total debits == total credits."""
    from decimal import Decimal
    
    # Record a sale
    record_sale(date.today(), 'Test Customer', Decimal('1000'), Decimal('50'), 
               payment_type='cash', description='Test Sale')
    
    # Record a purchase
    record_purchase(date.today(), 'Test Vendor', Decimal('500'), Decimal('25'),
                   itc_eligible=True, payment_type='cash', description='Test Purchase')
    
    # Record salary
    record_salary_payment(date.today(), 'Employee 1', Decimal('10000'), 
                      pf_deduction=Decimal('1200'), employer_pf=Decimal('1200'),
                      tax_deduction=Decimal('500'))
    
    # Record expense
    record_expense(date.today(), 'Rent', Decimal('5000'), description='Monthly Rent')
    
    # Query all transactions
    transactions = Transaction.query.all()
    total_debit = sum(t.debit or 0 for t in transactions)
    total_credit = sum(t.credit or 0 for t in transactions)
    
    assert abs(total_debit - total_credit) < Decimal('0.01'), \
        f"Debits {total_debit} != Credits {total_credit}"


def test_record_sale_cash(app_context):
    """Cash sale increases Cash account."""
    from decimal import Decimal
    
    amount = Decimal('1000')
    gst = Decimal('50')
    
    result = record_sale(date.today(), 'Test Customer', amount, gst,
                       payment_type='cash', description='Cash Sale')
    
    cash_acc = Account.query.filter_by(name='Cash').first()
    sales_acc = Account.query.filter_by(name='Sales Revenue').first()
    cgst_acc = Account.query.filter_by(name='CGST Payable').first()
    
    cash_balance = get_account_balance(cash_acc.id)
    sales_balance = get_account_balance(sales_acc.id)
    cgst_balance = get_account_balance(cgst_acc.id)
    
    assert cash_balance == amount + gst, f"Cash should be {amount+gst}, got {cash_balance}"
    assert sales_balance == amount, f"Sales should be {amount}, got {sales_balance}"
    assert cgst_balance == gst / 2, f"CGST should be {gst/2}, got {cgst_balance}"


def test_record_sale_credit(app_context):
    """Credit sale increases Accounts Receivable, not Cash."""
    from decimal import Decimal
    
    amount = Decimal('1000')
    gst = Decimal('50')
    
    result = record_sale(date.today(), 'Test Customer', amount, gst,
                       payment_type='credit', description='Credit Sale')
    
    ar_acc = Account.query.filter_by(name='Accounts Receivable').first()
    sales_acc = Account.query.filter_by(name='Sales Revenue').first()
    cgst_acc = Account.query.filter_by(name='CGST Payable').first()
    
    ar_balance = get_account_balance(ar_acc.id)
    cash_acc = Account.query.filter_by(name='Cash').first()
    cash_balance = get_account_balance(cash_acc.id)
    sales_balance = get_account_balance(sales_acc.id)
    cgst_balance = get_account_balance(cgst_acc.id)
    
    assert ar_balance == amount + gst, f"AR should be {amount+gst}, got {ar_balance}"
    assert cash_balance == 0, f"Cash should be 0, got {cash_balance}"
    assert sales_balance == amount, f"Sales should be {amount}, got {sales_balance}"
    assert cgst_balance == gst / 2, f"CGST should be {gst/2}, got {cgst_balance}"


def test_salary_expense_equals_gross(app_context):
    """Salary Expense equals gross salary (not 3×)."""
    from decimal import Decimal
    
    result = record_salary_payment(
        date.today(), 'Test Employee',
        gross_salary=Decimal('10000'),
        pf_deduction=Decimal('1200'),
        employer_pf=Decimal('1200'),
        tax_deduction=Decimal('500')
    )
    
    salary_expense = Account.query.filter_by(name='Salary Expense').first()
    balance = get_account_balance(salary_expense.id)
    
    assert balance == Decimal('10000'), \
        f"Salary Expense should be 10000, got {balance}"


def test_balance_sheet_balances(app_context):
    """Balance sheet equation: Assets = Liabilities + Capital."""
    from decimal import Decimal
    
    # Record a sale (creates asset: Cash, revenue: Sales)
    record_sale(date.today(), 'Customer1', Decimal('50000'), Decimal('2500'),
               payment_type='cash')
    
    # Record a purchase (creates asset: Inventory)
    record_purchase(date.today(), 'Vendor1', Decimal('20000'), Decimal('1000'),
                  itc_eligible=True, payment_type='cash')
    
    # Record salary expense (creates liability)
    record_salary_payment(date.today(), 'Employee1', Decimal('10000'))
    
    # Get balance sheet
    bs = get_balance_sheet(date.today())
    
    assert bs['is_balanced'], \
        f"Assets={bs['total_assets']}, Liab+Cap={bs['total_liabilities'] + bs['total_capital']}"


def test_income_statement_period_isolation(app_context):
    """Income statement for a period only includes transactions in that period."""
    from decimal import Decimal
    from datetime import date
    
    # Sale in January
    jan_date = date(2026, 1, 15)
    record_sale(jan_date, 'Customer1', Decimal('10000'), Decimal('500'),
               payment_type='cash')
    
    # Sale in March
    mar_date = date(2026, 3, 15)
    record_sale(mar_date, 'Customer2', Decimal('20000'), Decimal('1000'),
               payment_type='cash')
    
    # Get income statement for March only
    mar_start = date(2026, 3, 1)
    mar_end = date(2026, 3, 31)
    income = get_income_statement(mar_start, mar_end)
    
    assert income['total_income'] == Decimal('20000'), \
        f"March income should be 20000, got {income['total_income']}"


def test_reversal_entry_nets_to_zero(app_context):
    """Reversal entry brings account balance back to zero."""
    from decimal import Decimal
    
    cash = Account.query.filter_by(name='Cash').first()
    sales = Account.query.filter_by(name='Sales Revenue').first()
    
    # Create a journal entry: debit Cash, credit Sales Revenue, amount=1000
    journal = JournalEntry(
        date=date.today(),
        description='Test Sale',
        debit_account_id=cash.id,
        credit_account_id=sales.id,
        amount=Decimal('1000')
    )
    db.session.add(journal)
    db.session.flush()
    
    # Add Transaction rows manually
    db.session.add(Transaction(
        date=date.today(), description='Test Sale',
        account_id=cash.id, debit=Decimal('1000'), credit=0,
        entry_type='debit', is_posted=True, original_entry_id=journal.id
    ))
    db.session.add(Transaction(
        date=date.today(), description='Test Sale',
        account_id=sales.id, debit=0, credit=Decimal('1000'),
        entry_type='credit', is_posted=True, original_entry_id=journal.id
    ))
    db.session.commit()
    
    # Assert Sales Revenue balance == 1000 before reversal
    sales_balance_before = get_account_balance(sales.id)
    assert sales_balance_before == Decimal('1000'), f"Sales should be 1000 before reversal, got {sales_balance_before}"
    
    # Reverse it
    reverse_journal_entry(journal.id)
    
    # Assert Sales Revenue balance == 0 after reversal (reversal debited Sales Revenue)
    sales_balance_after = get_account_balance(sales.id)
    assert sales_balance_after == 0, f"Sales should be 0 after reversal, got {sales_balance_after}"


def test_gst_payment_reduces_liability(app_context):
    """Recording GST payment reduces CGST/SGST liabilities."""
    from decimal import Decimal
    
    record_sale(date.today(), 'Customer1', Decimal('10000'), Decimal('1800'),
               payment_type='cash', supply_type='intra')
    
    cgst_acc = Account.query.filter_by(name='CGST Payable').first()
    sgst_acc = Account.query.filter_by(name='SGST Payable').first()
    
    cgst_before = get_account_balance(cgst_acc.id)
    sgst_before = get_account_balance(sgst_acc.id)
    
    assert cgst_before == Decimal('900'), f"CGST should be 900, got {cgst_before}"
    assert sgst_before == Decimal('900'), f"SGST should be 900, got {sgst_before}"
    
    record_gst_payment(date.today(), Decimal('1800'), payment_mode='cash', gst_type='all')
    
    cgst_after = get_account_balance(cgst_acc.id)
    sgst_after = get_account_balance(sgst_acc.id)
    
    assert cgst_after == Decimal('0'), f"CGST should be 0, got {cgst_after}"
    assert sgst_after == Decimal('0'), f"SGST should be 0, got {sgst_after}"


def test_oversell_raises_error(app_context):
    """Selling more than available stock raises ValueError."""
    with app_context.app_context():
        from decimal import Decimal
        from models import Inventory
        Inventory.query.filter_by(stone_type='Granite', size='20mm').delete()
        item = Inventory(
            stone_type='Granite', size='20mm',
            opening_stock=Decimal('10'), closing_stock=Decimal('10'),
            rate_per_ton=Decimal('1000')
        )
        db.session.add(item)
        db.session.commit()
        
        try:
            record_sale(
                date.today(), 'Customer', Decimal('5000'), Decimal('250'),
                payment_type='cash', quantity=50,
                stone_type='Granite', size='20mm'
            )
            assert False, "Expected ValueError was not raised"
        except ValueError as e:
            assert "Insufficient stock" in str(e)


def test_monthly_revenue_no_crash_in_january(app_context):
    """get_monthly_revenue_expense must not crash in any month."""
    with app_context.app_context():
        from accounting_engine import get_monthly_revenue_expense
        from unittest.mock import patch
        import datetime
        with patch('accounting_engine.date') as mock_date:
            mock_date.today.return_value = datetime.date(2026, 1, 15)
            mock_date.side_effect = lambda *a, **kw: datetime.date(*a, **kw)
            result = get_monthly_revenue_expense(months=6)
        assert len(result['labels']) == 6
        assert len(result['revenue']) == 6


def test_record_sale_inter_state_uses_igst(app_context):
    """Inter-state sale posts IGST only — no CGST/SGST split."""
    from decimal import Decimal

    with app_context.app_context():
        from accounting_engine import record_sale, get_or_create_account, get_account_balance
        from models import Account

        amount = Decimal('10000')
        gst = Decimal('1800')

        record_sale(date.today(), 'Out-State Customer', amount, gst,
                    payment_type='cash', supply_type='inter')

        igst_acc = Account.query.filter_by(name='IGST Payable').first()
        cgst_acc = Account.query.filter_by(name='CGST Payable').first()
        sgst_acc = Account.query.filter_by(name='SGST Payable').first()

        assert get_account_balance(igst_acc.id) == gst, \
            f"IGST Payable should be {gst}"
        assert get_account_balance(cgst_acc.id) == Decimal('0'), \
            "CGST Payable should be 0 for inter-state sale"
        assert get_account_balance(sgst_acc.id) == Decimal('0'), \
            "SGST Payable should be 0 for inter-state sale"


def test_record_purchase_inter_state_itc_uses_igst(app_context):
    """Inter-state purchase with ITC posts IGST receivable only — no CGST/SGST."""
    from decimal import Decimal

    with app_context.app_context():
        from accounting_engine import record_purchase, get_account_balance
        from models import Account

        amount = Decimal('5000')
        gst = Decimal('900')

        record_purchase(date.today(), 'Out-State Vendor', amount, gst,
                        itc_eligible=True, payment_type='cash', supply_type='inter')

        igst_rec = Account.query.filter_by(name='IGST Receivable').first()
        cgst_rec = Account.query.filter_by(name='CGST Receivable').first()
        sgst_rec = Account.query.filter_by(name='SGST Receivable').first()

        assert get_account_balance(igst_rec.id) == gst, \
            f"IGST Receivable should be {gst}"
        assert get_account_balance(cgst_rec.id) == Decimal('0'), \
            "CGST Receivable should be 0 for inter-state purchase"
        assert get_account_balance(sgst_rec.id) == Decimal('0'), \
            "SGST Receivable should be 0 for inter-state purchase"


def test_record_purchase_non_itc_adds_gst_to_expense(app_context):
    """Non-ITC purchase includes GST in the expense amount, no ITC receivable posted."""
    from decimal import Decimal

    with app_context.app_context():
        from accounting_engine import record_purchase, get_account_balance
        from models import Account

        amount = Decimal('2000')
        gst = Decimal('360')
        total = amount + gst

        record_purchase(date.today(), 'Local Vendor', amount, gst,
                        itc_eligible=False, payment_type='cash', supply_type='intra')

        purchases_acc = Account.query.filter_by(name='Purchases').first()
        cgst_rec = Account.query.filter_by(name='CGST Receivable').first()
        sgst_rec = Account.query.filter_by(name='SGST Receivable').first()

        assert get_account_balance(purchases_acc.id) == total, \
            f"Non-ITC purchase expense should include GST: expected {total}"
        assert get_account_balance(cgst_rec.id) == Decimal('0'), \
            "No CGST Receivable for non-ITC purchase"
        assert get_account_balance(sgst_rec.id) == Decimal('0'), \
            "No SGST Receivable for non-ITC purchase"
    """get_monthly_revenue_expense must not crash in any month."""
    with app_context.app_context():
        from accounting_engine import get_monthly_revenue_expense
        from unittest.mock import patch
        import datetime
        with patch('accounting_engine.date') as mock_date:
            mock_date.today.return_value = datetime.date(2026, 1, 15)
            mock_date.side_effect = lambda *a, **kw: datetime.date(*a, **kw)
            result = get_monthly_revenue_expense(months=6)
        assert len(result['labels']) == 6
        assert len(result['revenue']) == 6
    """get_monthly_revenue_expense must not crash in any month."""
    with app_context.app_context():
        from accounting_engine import get_monthly_revenue_expense
        from unittest.mock import patch
        import datetime
        with patch('accounting_engine.date') as mock_date:
            mock_date.today.return_value = datetime.date(2026, 1, 15)
            mock_date.side_effect = lambda *a, **kw: datetime.date(*a, **kw)
            result = get_monthly_revenue_expense(months=6)
        assert len(result['labels']) == 6
        assert len(result['revenue']) == 6