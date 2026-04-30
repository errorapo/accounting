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
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    
    with app.app_context():
        db.drop_all()
        db.create_all()
        init_default_data()
        yield app
        db.session.rollback()
        db.drop_all()
        db.session.close()


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


def test_health_endpoint_returns_ok(app_context):
    """GET /health returns 200 with status ok."""
    client = app_context.test_client()
    response = client.get('/health')
    assert response.status_code == 200
    assert response.get_json() == {'status': 'ok'}


def test_ready_endpoint_db_check(app_context):
    """GET /ready returns 200 when DB is reachable."""
    client = app_context.test_client()
    response = client.get('/ready')
    assert response.status_code == 200
    assert response.get_json() == {'status': 'ready'}


def test_request_id_in_response_headers(app_context):
    """Every response includes X-Request-ID header."""
    client = app_context.test_client()
    response = client.get('/health')
    assert 'X-Request-ID' in response.headers
    assert len(response.headers['X-Request-ID']) == 8


def test_record_expense_creates_debit_entry(app_context):
    """record_expense creates a debit entry to the expense account."""
    from decimal import Decimal
    from accounting_engine import record_expense, get_account_balance

    rent_acc = Account.query.filter_by(name='Rent Expense').first()

    record_expense(date.today(), 'Rent', Decimal('15000'), description='Monthly Rent')

    assert get_account_balance(rent_acc.id) == Decimal('15000'), \
        f"Rent Expense should be 15000, got {get_account_balance(rent_acc.id)}"


def test_royalty_payment_journal_entry(app_context):
    """record_royalty_payment creates Dr Royalty Expense, Cr Royalty Payable."""
    from decimal import Decimal
    from accounting_engine import record_royalty_payment, get_account_balance

    royalty_exp = Account.query.filter_by(name='Royalty Expense').first()
    royalty_pay = Account.query.filter_by(name='Royalty Payable').first()

    record_royalty_payment(
        date.today(),
        amount=Decimal('5000'),
        quantity=Decimal('100'),
        stone_type='Granite',
        description='Royalty'
    )

    assert get_account_balance(royalty_exp.id) == Decimal('5000'), \
        "Royalty Expense should be 5000"
    assert get_account_balance(royalty_pay.id) == Decimal('0'), \
        "Royalty Payable should be 0 after payment"


def test_run_monthly_depreciation_creates_entry(app_context):
    """run_monthly_depreciation creates Dr Depreciation Expense, Cr Accumulated Depreciation."""
    from decimal import Decimal
    from accounting_engine import run_monthly_depreciation, get_account_balance
    from models import FixedAsset

    asset = FixedAsset(
        name='Excavator',
        purchase_date=date.today(),
        cost=Decimal('600000'),
        salvage_value=Decimal('60000'),
        useful_life_years=10
    )
    db.session.add(asset)
    db.session.commit()

    result = run_monthly_depreciation()

    dep_exp = Account.query.filter_by(name='Depreciation Expense').first()
    accum_dep = Account.query.filter_by(name='Accumulated Depreciation').first()

    monthly_dep = (Decimal('600000') - Decimal('60000')) / (10 * 12)
    assert result['total_depreciation'] > 0, "Should have depreciation"
    assert get_account_balance(dep_exp.id) == monthly_dep, \
        f"Depreciation Expense should be {monthly_dep}"


def test_purchase_payment_partial(app_context):
    """Partial payment against credit purchase reduces Accounts Payable."""
    from decimal import Decimal
    from accounting_engine import record_purchase, record_purchase_payment, get_account_balance

    payable_acc = Account.query.filter_by(name='Accounts Payable').first()

    record_purchase(
        date.today(), 'Vendor X', Decimal('20000'), Decimal('3600'),
        itc_eligible=True, payment_type='credit',
        description='Stone Supply'
    )

    full_balance = get_account_balance(payable_acc.id)
    assert full_balance == Decimal('23600'), f"AP should be 23600, got {full_balance}"

    record_purchase_payment(date.today(), purchase_id=1, amount=Decimal('10000'),
                           payment_mode='bank')

    remaining = get_account_balance(payable_acc.id)
    assert remaining == Decimal('13600'), f"AP should be 13600 after partial, got {remaining}"


def test_gst_payment_igst_only(app_context):
    """record_gst_payment with gst_type='igst' pays only IGST."""
    from decimal import Decimal
    from accounting_engine import record_sale, record_gst_payment, get_account_balance

    record_sale(date.today(), 'Outstate Customer', Decimal('20000'), Decimal('3600'),
                payment_type='cash', supply_type='inter')

    igst_acc = Account.query.filter_by(name='IGST Payable').first()
    cgst_acc = Account.query.filter_by(name='CGST Payable').first()
    sgst_acc = Account.query.filter_by(name='SGST Payable').first()

    assert get_account_balance(igst_acc.id) == Decimal('3600')
    assert get_account_balance(cgst_acc.id) == Decimal('0')
    assert get_account_balance(sgst_acc.id) == Decimal('0')

    record_gst_payment(date.today(), Decimal('3600'), payment_mode='bank', gst_type='igst')

    assert get_account_balance(igst_acc.id) == Decimal('0'), "IGST should be 0 after payment"
    assert get_account_balance(cgst_acc.id) == Decimal('0'), "CGST untouched"


def test_trial_balance_zero_when_no_transactions(app_context):
    """Trial balance with no transactions shows zero balances."""
    from accounting_engine import get_trial_balance

    tb = get_trial_balance()

    assert tb['total_debits'] == 0, "No transactions → zero debits"
    assert tb['total_credits'] == 0, "No transactions → zero credits"
    assert tb['is_balanced'] is True


def test_balance_sheet_empty_when_no_transactions(app_context):
    """Balance sheet with no opening balances shows zero totals."""
    from accounting_engine import get_balance_sheet

    bs = get_balance_sheet()

    assert bs['total_assets'] == 0, "No transactions → zero assets"
    assert bs['total_liabilities'] == 0, "No transactions → zero liabilities"
    assert bs['total_capital'] == 0, "No transactions → zero capital"
    assert bs['is_balanced'] is True


def test_income_statement_zero_when_no_transactions(app_context):
    """Income statement with no transactions shows zero income and expenses."""
    from accounting_engine import get_income_statement

    stmt = get_income_statement(date.today(), date.today())

    assert stmt['total_income'] == 0, "No transactions → zero income"
    assert stmt['total_expenses'] == 0, "No transactions → zero expenses"
    assert stmt['net_profit'] == 0


def test_payroll_auto_tds_on_15l_employee(app_context):
    """TDS auto-computed for 15L annual salary = 20800/year, 1733.33/month."""
    from decimal import Decimal
    from routes.payroll import compute_tds_on_salary

    annual_tds, monthly_tds = compute_tds_on_salary(Decimal('1500000'))

    assert annual_tds == Decimal('20800'), \
        f"Annual TDS should be 20800, got {annual_tds}"
    assert monthly_tds == Decimal('1733.33'), \
        f"Monthly TDS should be 1733.33, got {monthly_tds}"


def test_payroll_auto_tds_on_20l_employee(app_context):
    """TDS auto-computed for 20L annual — tests higher slabs."""
    from decimal import Decimal
    from routes.payroll import compute_tds_on_salary

    # 20L annual: excess over 12L = 8L
    # 2L @ 5% = 10,000
    # 3L @ 10% = 30,000
    # 2L @ 15% = 30,000
    # 1L @ 20% = 20,000
    # Total tax = 90,000 + 4% cess = 93,600
    annual_tds, monthly_tds = compute_tds_on_salary(Decimal('2000000'))

    assert annual_tds == Decimal('93600'), \
        f"Annual TDS should be 93600, got {annual_tds}"


def test_opening_balance_cannot_be_reversed(app_context):
    """Attempting to reverse an opening balance entry raises ValueError."""
    from decimal import Decimal
    from accounting_engine import reverse_journal_entry

    cash = Account.query.filter_by(name='Cash').first()

    journal = JournalEntry(
        date=date.today(),
        description='Opening Balance - Cash',
        debit_account_id=cash.id,
        credit_account_id=Account.query.filter_by(name='Opening Balance Equity').first().id,
        amount=Decimal('100000')
    )
    db.session.add(journal)
    db.session.flush()

    db.session.add(Transaction(
        date=date.today(), description='Opening Balance - Cash',
        account_id=cash.id, debit=Decimal('100000'), credit=0,
        entry_type='debit', is_posted=True, original_entry_id=journal.id
    ))
    db.session.add(Transaction(
        date=date.today(), description='Opening Balance - Cash',
        account_id=Account.query.filter_by(name='Opening Balance Equity').first().id,
        debit=0, credit=Decimal('100000'),
        entry_type='credit', is_posted=True, original_entry_id=journal.id
    ))
    db.session.commit()

    with pytest.raises(ValueError) as exc:
        reverse_journal_entry(journal.id)

    assert "Opening Balance" in str(exc.value)


def test_zero_amount_journal_entry_rejected(app_context):
    """create_journal_entry raises ValueError for zero or negative amount."""
    from decimal import Decimal
    from accounting_engine import create_journal_entry

    cash = Account.query.filter_by(name='Cash').first()
    sales = Account.query.filter_by(name='Sales Revenue').first()

    with pytest.raises(ValueError) as exc:
        create_journal_entry(date.today(), "Test", cash.id, sales.id, Decimal('0'))

    assert "Amount must be positive" in str(exc.value)

    with pytest.raises(ValueError) as exc:
        create_journal_entry(date.today(), "Test", cash.id, sales.id, Decimal('-100'))

    assert "Amount must be positive" in str(exc.value)


def test_same_account_debit_credit_rejected(app_context):
    """Journal entry where debit and credit account are the same is rejected."""
    from decimal import Decimal
    from accounting_engine import create_journal_entry

    cash = Account.query.filter_by(name='Cash').first()

    with pytest.raises(ValueError):
        create_journal_entry(date.today(), "Test", cash.id, cash.id, Decimal('1000'))


def test_accumulated_depreciation_is_contra(app_context):
    """Accumulated Depreciation is a contra-asset that reduces total assets on balance sheet."""
    from decimal import Decimal
    from accounting_engine import run_monthly_depreciation, get_balance_sheet, initialize_default_accounts
    from models import FixedAsset, Account

    with app_context.app_context():
        initialize_default_accounts()
        db.session.commit()
        db.session.expire_all()
        
        accum_dep_acc = Account.query.filter_by(name='Accumulated Depreciation').first()
        assert accum_dep_acc is not None, "Accumulated Depreciation account should exist"
        assert accum_dep_acc.is_contra is True, "Accumulated Depreciation should be marked as contra"

        asset = FixedAsset(
            name='Excavator',
            purchase_date=date.today(),
            cost=Decimal('600000'),
            salvage_value=Decimal('60000'),
            useful_life_years=10
        )
        db.session.add(asset)
        db.session.commit()

        result = run_monthly_depreciation()
        assert result['total_depreciation'] > 0, "Depreciation should be calculated"

        db.session.commit()
        db.session.expire_all()
        
        initialize_default_accounts()
        db.session.commit()
        db.session.expire_all()
        
        bs = get_balance_sheet(date.today())

        accum_dep_balance = abs(bs.get('accumulated_depreciation', 0))
        assert accum_dep_balance > 0, "Accumulated Depreciation should have a balance"
        
        assert bs['total_assets'] < Decimal('600000'), "Total assets should be reduced by accumulated depreciation"


def test_gst_itc_setoff_order(app_context):
    """Test ITC utilization follows Section 49 order: IGST→IGST/CGST/SGST, then CGST→CGST, then SGST→SGST."""
    from decimal import Decimal
    from accounting_engine import (
        record_purchase, record_sale, record_gst_payment, apply_itc_setoff,
        get_account_balance, get_or_create_account
    )
    
    with app_context.app_context():
        db.session.commit()
        db.session.expire_all()
        
        # Setup: Create ITC via inter-state purchase (IGST ITC)
        record_purchase(date.today(), 'Vendor A', Decimal('10000'), Decimal('1800'),
                       itc_eligible=True, payment_type='cash', description='IGST Purchase',
                       supply_type='inter')
        
        # Create CGST/SGST ITC via intra-state purchase
        record_purchase(date.today(), 'Vendor B', Decimal('5000'), Decimal('450'),
                       itc_eligible=True, payment_type='cash', description='CGST/SGST Purchase',
                       supply_type='intra')
        
        db.session.commit()
        db.session.expire_all()
        
        # Create output liability via inter-state sale
        record_sale(date.today(), 'Customer A', Decimal('8000'), Decimal('1440'),
                   payment_type='cash', description='IGST Sale', supply_type='inter')
        
        # Create output liability via intra-state sale
        record_sale(date.today(), 'Customer B', Decimal('4000'), Decimal('360'),
                   payment_type='cash', description='CGST/SGST Sale', supply_type='intra')
        
        db.session.commit()
        db.session.expire_all()
        
        igst_payable = get_or_create_account('IGST Payable', 'liability')
        cgst_payable = get_or_create_account('CGST Payable', 'liability')
        sgst_payable = get_or_create_account('SGST Payable', 'liability')
        
        igst_receivable = get_or_create_account('IGST Receivable', 'asset')
        cgst_receivable = get_or_create_account('CGST Receivable', 'asset')
        sgst_receivable = get_or_create_account('SGST Receivable', 'asset')
        
        # Verify liabilities: IGST=1440, CGST=180, SGST=180
        assert get_account_balance(igst_payable.id) == Decimal('1440'), "IGST liability should be 1440"
        assert get_account_balance(cgst_payable.id) == Decimal('180'), "CGST liability should be 180"
        assert get_account_balance(sgst_payable.id) == Decimal('180'), "SGST liability should be 180"
        
        # Verify ITC: IGST=1800, CGST=225, SGST=225
        assert get_account_balance(igst_receivable.id) == Decimal('1800'), "IGST ITC should be 1800"
        assert get_account_balance(cgst_receivable.id) == Decimal('225'), "CGST ITC should be 225"
        assert get_account_balance(sgst_receivable.id) == Decimal('225'), "SGST ITC should be 225"
        
        # Apply ITC setoff
        igst_liability = get_account_balance(igst_payable.id)
        cgst_liability = get_account_balance(cgst_payable.id)
        sgst_liability = get_account_balance(sgst_payable.id)
        result = apply_itc_setoff(date.today(), cgst_liability, sgst_liability, igst_liability)
        
        db.session.commit()
        db.session.expire_all()
        
        # Per Section 49 order:
        # IGST ITC (1800) → IGST liab (1440) = 360 remaining
        # Remaining IGST ITC (360) → CGST liab (180) = 180 remaining
        # Remaining IGST ITC (180) → SGST liab (180) = 0 remaining
        # CGST ITC (225) → CGST liab (0 after IGST setoff) = 225 remaining
        # SGST ITC (225) → SGST liab (0 after IGST setoff) = 225 remaining
        
        # After setoff:
        assert get_account_balance(igst_payable.id) == Decimal('0'), "IGST liability should be 0 after ITC setoff"
        assert get_account_balance(cgst_payable.id) == Decimal('0'), "CGST liability should be 0 after ITC setoff"
        assert get_account_balance(sgst_payable.id) == Decimal('0'), "SGST liability should be 0 after ITC setoff"
        
        # Per Section 49, IGST ITC (1800) should be used first:
        # - IGST liability (1440) fully set off
        # - Remaining IGST ITC (360) → CGST liability (180), SGST liability (180)
        # Total ITC used: 1440 + 180 + 180 = 1800
        assert result['total_itc_used'] == Decimal('1800'), "Total ITC used should be 1800"
        
        # Verify ITC remaining
        assert get_account_balance(igst_receivable.id) == Decimal('0'), "IGST ITC should be fully used"
        assert get_account_balance(cgst_receivable.id) == Decimal('225'), "CGST ITC should remain unused"
        assert get_account_balance(sgst_receivable.id) == Decimal('225'), "SGST ITC should remain unused"


def test_gst_report_matches_ledger(app_context):
    """Test GST report totals match ledger balances (not Sales/Purchase table queries)."""
    from decimal import Decimal
    from accounting_engine import (
        record_purchase, record_sale, get_period_balance, get_or_create_account
    )
    from datetime import timedelta
    
    with app_context.app_context():
        db.session.commit()
        db.session.expire_all()
        
        start_date = date.today()
        end_date = date.today()
        
        # Record sales and purchases
        record_sale(date.today(), 'Customer A', Decimal('10000'), Decimal('900'),
                   payment_type='cash', description='Sale 1', supply_type='intra')
        record_sale(date.today(), 'Customer B', Decimal('20000'), Decimal('3600'),
                   payment_type='cash', description='Sale 2', supply_type='inter')
        record_purchase(date.today(), 'Vendor A', Decimal('5000'), Decimal('450'),
                       itc_eligible=True, payment_type='cash', description='Purchase 1',
                       supply_type='intra')
        record_purchase(date.today(), 'Vendor B', Decimal('8000'), Decimal('1440'),
                       itc_eligible=True, payment_type='cash', description='Purchase 2',
                       supply_type='inter')
        
        db.session.commit()
        db.session.expire_all()
        
        # Get ledger balances using get_period_balance
        cgst_payable = get_or_create_account('CGST Payable', 'liability')
        sgst_payable = get_or_create_account('SGST Payable', 'liability')
        igst_payable = get_or_create_account('IGST Payable', 'liability')
        cgst_receivable = get_or_create_account('CGST Receivable', 'asset')
        sgst_receivable = get_or_create_account('SGST Receivable', 'asset')
        igst_receivable = get_or_create_account('IGST Receivable', 'asset')
        
        output_cgst = get_period_balance(cgst_payable.id, start_date, end_date)
        output_sgst = get_period_balance(sgst_payable.id, start_date, end_date)
        output_igst = get_period_balance(igst_payable.id, start_date, end_date)
        
        input_cgst = get_period_balance(cgst_receivable.id, start_date, end_date)
        input_sgst = get_period_balance(sgst_receivable.id, start_date, end_date)
        input_igst = get_period_balance(igst_receivable.id, start_date, end_date)
        
        # From sales: intra (10000*9%) = 900 = CGST 450 + SGST 450; inter (20000*18%) = 3600 = IGST 3600
        # From purchases (ITC): intra (5000*9%) = 450 = CGST 225 + SGST 225; inter (8000*18%) = 1440 = IGST 1440
        
        assert output_cgst == Decimal('450'), f"Output CGST should be 450, got {output_cgst}"
        assert output_sgst == Decimal('450'), f"Output SGST should be 450, got {output_sgst}"
        assert output_igst == Decimal('3600'), f"Output IGST should be 3600, got {output_igst}"
        
        assert input_cgst == Decimal('225'), f"Input CGST should be 225, got {input_cgst}"
        assert input_sgst == Decimal('225'), f"Input SGST should be 225, got {input_sgst}"
        assert input_igst == Decimal('1440'), f"Input IGST should be 1440, got {input_igst}"


def test_record_sale_inter_state_uses_igst_not_cgst_sgst(app_context):
    """Inter-state sale uses IGST only, not CGST/SGST split."""
    from decimal import Decimal
    from accounting_engine import record_sale, get_account_balance, get_or_create_account
    from datetime import date
    
    with app_context.app_context():
        db.session.commit()
        db.session.expire_all()
        
        record_sale(date.today(), 'InterState Customer', Decimal('10000'), Decimal('1000'),
                   payment_type='cash', description='Inter State Sale', supply_type='inter')
        
        db.session.commit()
        db.session.expire_all()
        
        igst_payable = get_or_create_account('IGST Payable', 'liability')
        cgst_payable = get_or_create_account('CGST Payable', 'liability')
        sgst_payable = get_or_create_account('SGST Payable', 'liability')
        
        assert get_account_balance(igst_payable.id) == Decimal('1000'), \
            f"IGST Payable should be 1000, got {get_account_balance(igst_payable.id)}"
        assert get_account_balance(cgst_payable.id) == Decimal('0'), \
            f"CGST Payable should be 0, got {get_account_balance(cgst_payable.id)}"
        assert get_account_balance(sgst_payable.id) == Decimal('0'), \
            f"SGST Payable should be 0, got {get_account_balance(sgst_payable.id)}"


def test_weighted_average_cost_recalculates_correctly(app_context):
    """WAC recalculates after new purchase: (10*1000+10*2000)/20 = 1500."""
    from decimal import Decimal
    from accounting_engine import record_purchase
    from models import Inventory
    from datetime import date
    
    with app_context.app_context():
        db.session.commit()
        db.session.expire_all()
        
        item = Inventory(
            stone_type='Test Stone',
            size='30mm',
            opening_stock=Decimal('10'),
            closing_stock=Decimal('10'),
            rate_per_ton=Decimal('1000'),
            purchases=Decimal('10'),
            sales=Decimal('0'),
            total_cost=Decimal('10000')
        )
        db.session.add(item)
        db.session.commit()
        
        # Purchase 10 more tons at 2000/ton (amount=20000 for 10 tons)
        record_purchase(
            date.today(), 
            vendor_name='Vendor 1', 
            amount=Decimal('20000'), 
            gst_amount=Decimal('3600'),
            itc_eligible=True, 
            payment_type='cash', 
            description='Test Purchase 1',
            quantity=Decimal('10'), 
            stone_type='Test Stone', 
            size='30mm',
            supply_type='intra'
        )
        
        db.session.commit()
        db.session.expire_all()
        
        item = Inventory.query.filter_by(stone_type='Test Stone', size='30mm').first()
        assert item is not None
        
        # Expected: (10*1000 + 10*2000) / 20 = 1500
        assert item.rate_per_ton == Decimal('1500'), \
            f"Expected WAC to be 1500, got {item.rate_per_ton}"


def test_balance_sheet_net_book_value_excludes_accumulated_depreciation(app_context):
    """Test that balance sheet net book value excludes accumulated depreciation."""
    from decimal import Decimal
    from accounting_engine import run_monthly_depreciation, get_balance_sheet
    from models import FixedAsset
    from datetime import date
    
    with app_context.app_context():
        db.session.commit()
        db.session.expire_all()
        
        asset = FixedAsset(
            name='Test Asset',
            purchase_date=date.today(),
            cost=Decimal('100000'),
            salvage_value=Decimal('10000'),
            useful_life_years=10
        )
        db.session.add(asset)
        db.session.commit()
        
        result = run_monthly_depreciation()
        db.session.commit()
        db.session.expire_all()
        
        bs = get_balance_sheet(date.today())
        
        assert bs['total_assets'] < Decimal('100000'), \
            f"Total assets should be less than 100000 due to depreciation, got {bs['total_assets']}"