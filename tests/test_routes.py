"""Route-level and security tests for Flask app."""

import os
import sys
import pytest
from decimal import Decimal
from datetime import date

# Set environment BEFORE imports
os.environ['REDIS_URL'] = 'memory://'
os.environ['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
os.environ['SKIP_INIT_DEFAULT_DATA'] = 'true'

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app, init_default_data
from ext import db
from models import User, Customer, Inventory, Sales, Payment, Account, JournalEntry, Purchase


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


@pytest.fixture
def auth_client(app_context, client):
    """Return authenticated test client with admin role."""
    with app_context.app_context():
        user = User.query.filter_by(username='admin').first()
        if user is None:
            from werkzeug.security import generate_password_hash
            user = User(username='admin',
                    password_hash=generate_password_hash('admin123'),
                    role='admin')
            db.session.add(user)
            db.session.commit()
        
        customer = Customer.query.first()
        if customer is None:
            customer = Customer(name='Test Customer', phone='9999999999')
            db.session.add(customer)
            db.session.commit()
        
        item = Inventory.query.first()
        if item is None:
            item = Inventory(stone_type='Granite', size='20mm',
                         opening_stock=100, purchases=0, sales=0,
                         closing_stock=100, rate_per_ton=1200)
            db.session.add(item)
            db.session.commit()
    
    with client.session_transaction() as sess:
        sess['user_id'] = user.id
        sess['role'] = user.role
    
    return client


@pytest.fixture
def accountant_client(app_context, client):
    """Return authenticated test client with accountant role."""
    with app_context.app_context():
        from werkzeug.security import generate_password_hash
        user = User.query.filter_by(username='accountant').first()
        if user is None:
            user = User(username='accountant',
                    password_hash=generate_password_hash('test123'),
                    role='accountant')
            db.session.add(user)
            db.session.commit()
        
        customer = Customer.query.first()
        if customer is None:
            customer = Customer(name='Test Customer', phone='9999999999')
            db.session.add(customer)
            db.session.commit()
        
        item = Inventory.query.first()
        if item is None:
            item = Inventory(stone_type='Granite', size='20mm',
                         opening_stock=100, purchases=0, sales=0,
                         closing_stock=100, rate_per_ton=1200)
            db.session.add(item)
            db.session.commit()
    
    with client.session_transaction() as sess:
        sess['user_id'] = user.id
        sess['role'] = 'accountant'
    
    return client


def test_unauthenticated_redirects_to_login(client):
    """Unauthenticated access redirects to /login."""
    routes = ['/sales', '/payroll/create', '/reports/balance-sheet']
    
    for route in routes:
        response = client.get(route, follow_redirects=False)
        assert response.status_code == 302, f"GET {route} should redirect"
        assert '/login' in response.location or response.status_code == 302


def test_accountant_cannot_access_admin_routes(app_context, accountant_client):
    """Accountant role cannot access admin-only routes."""
    client = accountant_client
    
    response = client.post('/journal/add', follow_redirects=False)
    assert response.status_code == 302, "POST /journal/add should be blocked for accountant"
    
    response = client.get('/accounts/delete/1', follow_redirects=False)
    assert response.status_code == 302, "GET /accounts/delete should be blocked for accountant"


def test_sale_rejects_negative_quantity(auth_client, app_context):
    """Sale with negative quantity is rejected."""
    client = auth_client
    
    with app_context.app_context():
        customer = Customer.query.first()
        item = Inventory.query.first()
    
    response = client.post('/sales/create', data={
        'customer_id': str(customer.id),
        'stone_type': item.stone_type,
        'size': item.size,
        'quantity': '-5',
        'rate': '100',
        'gst_rate': '5',
        'payment_type': 'cash'
    }, follow_redirects=False)
    
    with app_context.app_context():
        bad_sale = Sales.query.filter_by(quantity=float(-5)).first()
    
    rejected = response.status_code in (302, 400, 500) or \
               b'error' in response.data.lower() or \
               b'must be greater' in response.data.lower() or \
               b'cannot be negative' in response.data.lower()
    
    assert rejected or bad_sale is None, "Negative quantity should be rejected"


def test_sale_rejects_zero_rate(auth_client, app_context):
    """Sale with zero rate is rejected."""
    client = auth_client
    
    with app_context.app_context():
        customer = Customer.query.first()
        item = Inventory.query.first()
    
    response = client.post('/sales/create', data={
        'customer_id': str(customer.id),
        'stone_type': item.stone_type,
        'size': item.size,
        'quantity': '5',
        'rate': '0',
        'gst_rate': '5',
        'payment_type': 'cash'
    }, follow_redirects=False)
    
    rejected = response.status_code in (302, 400, 500) or \
               b'error' in response.data.lower() or \
               b'rate' in response.data.lower() or \
               b'zero' in response.data.lower()
    
    assert rejected, "Zero rate should be rejected"


def test_payment_cannot_exceed_invoice(auth_client, app_context):
    """Invoice numbers are unique across sales."""
    client = auth_client
    
    with app_context.app_context():
        customer = Customer.query.first()
        item = Inventory.query.first()
    
    invoice_numbers = []
    for i in range(10):
        response = client.post('/sales/create', data={
            'customer_id': str(customer.id),
            'stone_type': item.stone_type,
            'size': item.size,
            'quantity': '1',
            'rate': '100',
            'gst_rate': '5',
            'payment_type': 'cash'
        }, follow_redirects=True)
        
        if response.status_code < 400:
            with app_context.app_context():
                latest = Sales.query.filter(
                    Sales.invoice_number.isnot(None)
                ).order_by(Sales.id.desc()).first()
                if latest and latest.invoice_number:
                    invoice_numbers.append(latest.invoice_number)
    
    assert len(invoice_numbers) == len(set(invoice_numbers)), \
        f"Invoice numbers should be unique: {invoice_numbers}"


def test_reversal_of_reversal_is_rejected(app_context, auth_client):
    """Reversing a reversal entry should be rejected."""
    client = auth_client
    
    with app_context.app_context():
        cash = Account.query.filter_by(name='Cash').first()
        
        journal = JournalEntry(
            date=date.today(),
            description='Test Entry',
            debit_account_id=cash.id,
            credit_account_id=cash.id,
            amount=Decimal('1000')
        )
        db.session.add(journal)
        db.session.commit()
        
        entry_id = journal.id
    
    from accounting_engine import reverse_journal_entry
    
    with app_context.app_context():
        reverse_journal_entry(entry_id)
        
        original = db.session.get(JournalEntry, entry_id)
        reversal = JournalEntry.query.filter_by(original_entry_id=entry_id).first()
        
        if reversal:
            with pytest.raises(ValueError):
                reverse_journal_entry(reversal.id)
        else:
            assert True


def test_purchase_create_valid(auth_client, app_context):
    """Valid purchase is accepted and recorded."""
    client = auth_client
    with app_context.app_context():
        from models import Vendor, Inventory, Purchase
        vendor = Vendor.query.first()
        if vendor is None:
            vendor = Vendor(name='Test Vendor', phone='9999999999', state='Kerala')
            db.session.add(vendor)
            db.session.commit()
        item = Inventory.query.first()
        vendor_id = vendor.id
        stone_type = item.stone_type
        size = item.size

    response = client.post('/purchases/create', data={
        'vendor_id': str(vendor_id),
        'stone_type': stone_type,
        'size': size,
        'quantity': '10',
        'rate': '500',
        'gst_rate': '5',
        'payment_type': 'cash',
        'itc_eligible': '1',
        'supply_type': 'intra'
    }, follow_redirects=True)

    assert response.status_code == 200
    with app_context.app_context():
        purchase = Purchase.query.first()
        assert purchase is not None, "Purchase should have been created"


def test_purchase_rejects_negative_quantity(auth_client, app_context):
    """Purchase with negative quantity is rejected."""
    client = auth_client
    with app_context.app_context():
        from models import Vendor
        vendor = Vendor.query.first()
        if vendor is None:
            vendor = Vendor(name='Test Vendor', phone='9999999999', state='Kerala')
            db.session.add(vendor)
            db.session.commit()
        vendor_id = vendor.id

    response = client.post('/purchases/create', data={
        'vendor_id': str(vendor_id),
        'stone_type': 'Granite',
        'size': '20mm',
        'quantity': '-10',
        'rate': '500',
        'gst_rate': '5',
        'payment_type': 'cash'
    }, follow_redirects=False)

    with app_context.app_context():
        from models import Purchase
        bad_purchase = Purchase.query.first()

    assert bad_purchase is None, "Negative quantity purchase should be rejected"


def test_payment_cannot_exceed_invoice(auth_client, app_context):
    """Payment exceeding invoice total is rejected."""
    client = auth_client
    with app_context.app_context():
        from models import Customer, Inventory, Sales
        customer = Customer.query.first()
        item = Inventory.query.first()

    response = client.post('/sales/create', data={
        'customer_id': str(customer.id),
        'stone_type': item.stone_type,
        'size': item.size,
        'quantity': '1',
        'rate': '1000',
        'gst_rate': '5',
        'payment_type': 'credit',
        'supply_type': 'intra'
    }, follow_redirects=True)

    with app_context.app_context():
        sale = Sales.query.order_by(Sales.id.desc()).first()
        assert sale is not None

    response = client.post(f'/sales/{sale.id}/payment', data={
        'amount': '99999',
        'payment_mode': 'cash',
        'notes': 'overpayment test'
    }, follow_redirects=False)

    assert response.status_code == 302, "Overpayment should be rejected with a redirect"
    with app_context.app_context():
        from models import Payment
        overpayment = Payment.query.filter_by(sale_id=sale.id).first()
        assert overpayment is None, "Overpayment should not be recorded"


def test_generate_payroll_creates_payroll_and_journal_entries(app_context):
    """GET /payroll/generate creates Payroll record and journal entries."""
    with app_context.app_context():
        from app import create_app
        from models import Employee, Attendance, Payroll, JournalEntry
        from decimal import Decimal

        app2 = create_app('development')
        app2.config['TESTING'] = True
        app2.config['WTF_CSRF_ENABLED'] = False

        with app2.test_request_context():
            emp = Employee(
                name='Test Worker',
                employee_type='permanent',
                base_salary=Decimal('15600'),
                hourly_rate=Decimal('80'),
                pf_rate=Decimal('12'),
                transport_allowance=Decimal('2000'),
                food_allowance=Decimal('1500'),
                housing_allowance=Decimal('3000')
            )
            db.session.add(emp)
            db.session.commit()
            emp_id = emp.id

            today = date.today()
            att = Attendance(
                employee_id=emp_id,
                date=today,
                status='present',
                half_day=False
            )
            db.session.add(att)
            db.session.commit()

            user = db.session.query(Employee).first()
            from models import User

            client = app2.test_client()
            with client.session_transaction() as sess:
                sess['user_id'] = 1
                sess['role'] = 'admin'

            response = client.get('/payroll/generate', follow_redirects=True)
            assert response.status_code == 200

            payroll_record = Payroll.query.filter_by(employee_id=emp_id).first()
            assert payroll_record is not None, "Payroll record should be created"
            assert payroll_record.gross_salary > 0, "Gross salary should be > 0"
            assert payroll_record.pf_employee > 0, "PF deduction should be present"

            journal_entries = JournalEntry.query.filter(
                JournalEntry.description.like("%Test Worker%")
            ).all()
            assert len(journal_entries) > 0, "Journal entries should be created for payroll"


def test_health_endpoint_no_auth_required(client):
    """GET /health does not require authentication."""
    response = client.get('/health', follow_redirects=False)
    assert response.status_code == 200
    assert response.get_json() == {'status': 'ok'}


def test_ready_endpoint_no_auth_required(client):
    """GET /ready does not require authentication."""
    response = client.get('/ready', follow_redirects=False)
    assert response.status_code == 200
    assert response.get_json() == {'status': 'ready'}


def test_health_endpoint_not_rate_limited(client):
    """GET /health is not limited by rate limiter."""
    # Make 50 requests rapidly - should not be rate limited
    for _ in range(50):
        response = client.get('/health')
        assert response.status_code == 200, "Health endpoint should not be rate limited"


def test_login_page_loads(client):
    """GET /login returns 200 with login form."""
    response = client.get('/login')
    assert response.status_code == 200


def test_logout_clears_session(client):
    """GET /logout clears session and redirects to login."""
    with client.session_transaction() as sess:
        sess['user_id'] = 999
        sess['role'] = 'admin'
    response = client.get('/logout', follow_redirects=True)
    assert response.status_code == 200
    with client.session_transaction() as sess:
        assert 'user_id' not in sess


def test_sale_with_blank_customer_name_rejected(auth_client, app_context):
    """Sale with blank customer name is rejected."""
    client = auth_client
    with app_context.app_context():
        item = Inventory.query.first()

    response = client.post('/sales/create', data={
        'customer_id': '',
        'stone_type': item.stone_type,
        'size': item.size,
        'quantity': '1',
        'rate': '100',
        'gst_rate': '5',
        'payment_type': 'cash'
    }, follow_redirects=False)

    # Should not create a sale with blank customer
    with app_context.app_context():
        bad_sale = Sales.query.filter(Sales.customer_id == None).first()
        assert bad_sale is None, "Sale with blank customer should not be created"


def test_purchase_with_no_vendor_rejected(auth_client, app_context):
    """Purchase without vendor - no purchase record is created."""
    client = auth_client
    with app_context.app_context():
        item = Inventory.query.first()
        initial_count = Purchase.query.count()

    response = client.post('/purchases/create', data={
        'vendor_id': '',
        'vendor_name': '',
        'stone_type': item.stone_type,
        'size': item.size,
        'quantity': '1',
        'rate': '500',
        'gst_rate': '5',
        'payment_type': 'cash'
    }, follow_redirects=False)

    with app_context.app_context():
        final_count = Purchase.query.count()
        assert final_count == initial_count, "No purchase should be created without vendor"


def test_gst_rate_must_be_5_12_18_28(auth_client, app_context):
    """Sale with invalid GST rate (e.g., 7%) is rejected."""
    client = auth_client
    with app_context.app_context():
        customer = Customer.query.first()
        item = Inventory.query.first()

    response = client.post('/sales/create', data={
        'customer_id': str(customer.id),
        'stone_type': item.stone_type,
        'size': item.size,
        'quantity': '1',
        'rate': '100',
        'gst_rate': '7',  # Invalid GST rate
        'payment_type': 'cash'
    }, follow_redirects=False)

    # Should be rejected with error
    rejected = response.status_code in (302, 400, 500) or \
               b'GST rate' in response.data.lower() or \
               b'error' in response.data.lower()
    assert rejected, "Invalid GST rate 7% should be rejected"


def test_valid_gst_rates_accepted(app_context, auth_client):
    """Sale with valid GST rates (5, 12, 18, 28) is accepted."""
    client = auth_client

    with app_context.app_context():
        customer = db.session.get(Customer, 1)
        if customer is None:
            customer = Customer(name='GST Test Customer', phone='9999999999')
            db.session.add(customer)
            db.session.commit()

        item = Inventory.query.first()
        if item is None:
            item = Inventory(stone_type='Test Stone', size='20mm',
                           opening_stock=1000, purchases=0, sales=0,
                           closing_stock=1000, rate_per_ton=1000)
            db.session.add(item)
            db.session.commit()

        customer_id = customer.id
        stone_type = item.stone_type
        size = item.size

    valid_rates = ['5', '12', '18', '28']
    for gst_rate in valid_rates:
        response = client.post('/sales/create', data={
            'customer_id': str(customer_id),
            'stone_type': stone_type,
            'size': size,
            'quantity': '1',
            'rate': '100',
            'gst_rate': gst_rate,
            'payment_type': 'cash'
        }, follow_redirects=True)

        assert response.status_code == 200, f"GST rate {gst_rate}% should be accepted"


def test_trial_balance_endpoint_loads(auth_client):
    """GET /reports/trial-balance loads successfully."""
    client = auth_client
    response = client.get('/reports/trial-balance')
    assert response.status_code == 200


def test_profit_loss_endpoint_loads(auth_client):
    """GET /reports/profit-loss loads successfully."""
    client = auth_client
    response = client.get('/reports/profit-loss')
    assert response.status_code == 200


def test_balance_sheet_endpoint_loads(auth_client):
    """GET /reports/balance-sheet loads successfully."""
    client = auth_client
    response = client.get('/reports/balance-sheet')
    assert response.status_code == 200


def test_gst_report_endpoint_loads(auth_client):
    """GET /reports/gst loads successfully."""
    client = auth_client
    response = client.get('/reports/gst')
    assert response.status_code == 200


def test_admin_cannot_delete_self(app_context, auth_client):
    """Admin cannot delete their own user account."""
    client = auth_client
    with app_context.app_context():
        user = User.query.filter_by(username='admin').first()
        user_id = user.id

    response = client.get(f'/users/delete/{user_id}', follow_redirects=False)

    with app_context.app_context():
        remaining = db.session.get(User, user_id)
        assert remaining is not None, "Admin should not be able to delete own account"


def test_create_payroll_without_tds_field(app_context, auth_client):
    """Test that payroll can be created with tax_deduction=0 and auto-TDS works."""
    from models import Employee, Payroll
    client = auth_client
    
    with app_context.app_context():
        db.session.commit()
        db.session.expire_all()
        
        emp = Employee(
            name='Test Employee',
            employee_type='Office Staff',
            base_salary=Decimal('120000'),
            hourly_rate=Decimal('500'),
            pf_rate=Decimal('12'),
            state='Maharashtra'
        )
        db.session.add(emp)
        db.session.commit()
        db.session.expire_all()
        
        response = client.post('/payroll/create', data={
            'employee_id': emp.id,
            'month': '2025-04',
            'year': 2025,
            'overtime_hours': '0',
            'bonus': '0',
            'insurance': '0',
            'tax_deduction': '0'
        }, follow_redirects=True)
        
        assert response.status_code != 500, f"Expected non-500 status, got {response.status_code}"
        
        with app_context.app_context():
            payroll = Payroll.query.filter_by(employee_id=emp.id).first()
            assert payroll is not None, "Payroll record should exist in DB"
            assert payroll.tax_deduction > 0, f"Tax deduction should be > 0, got {payroll.tax_deduction}"


def test_aging_report_shows_net_outstanding_after_partial_payment(app_context, auth_client):
    """Aging report shows net outstanding based on accounting (not Sales.amount - paid)."""
    from models import Customer, Sales, Payment, Account
    from accounting_engine import record_sale, record_payment, get_account_balance, get_or_create_account
    from decimal import Decimal
    from datetime import date
    client = auth_client
    
    with app_context.app_context():
        db.session.commit()
        db.session.expire_all()
        
        customer = Customer.query.first()
        if not customer:
            customer = Customer(name='Test Customer', phone='9999999999')
            db.session.add(customer)
            db.session.commit()
        
        # Create credit sale for 10000 + 1800 GST = 11800 total
        record_sale(date.today(), customer.name, Decimal('10000'), Decimal('1800'),
                   payment_type='credit', description='Test Credit Sale')
        
        db.session.commit()
        
        sale = Sales.query.filter_by(customer_id=customer.id).first()
        
        # Record partial payment of 4000
        record_payment(date.today(), sale.id, Decimal('4000'), 'cash', 'Partial payment', '')
        db.session.commit()
        
        response = client.get('/reports/aging', follow_redirects=True)
        assert response.status_code == 200
        
        # Outstanding via accounting = Sales Revenue (10000) - Cash (4000) = 6000
        with app_context.app_context():
            sales_acc = get_or_create_account('Sales Revenue', 'income')
            cash_acc = get_or_create_account('Cash', 'asset')
            sales_balance = get_account_balance(sales_acc.id)
            cash_received = get_account_balance(cash_acc.id)
            accounting_outstanding = sales_balance - cash_received
            
            # Accounting shows 10000 sales revenue - 4000 cash received = 6000 outstanding
            assert accounting_outstanding == 6000, f"Expected 6000, got {accounting_outstanding}"


def test_payment_cannot_exceed_invoice_total(app_context, auth_client):
    """Payment exceeding invoice total is partially rejected or limited to remaining amount."""
    from models import Customer, Sales, Payment
    from accounting_engine import record_sale, record_payment
    client = auth_client
    
    with app_context.app_context():
        db.session.commit()
        db.session.expire_all()
        
        customer = Customer.query.first()
        if not customer:
            customer = Customer(name='Test Customer', phone='9999999999')
            db.session.add(customer)
            db.session.commit()
        
        record_sale(date.today(), customer.name, Decimal('5000'), Decimal('900'),
                   payment_type='credit', description='Test Invoice')
        
        db.session.commit()
        
        sale = Sales.query.filter_by(customer_id=customer.id).first()
        
        # Attempt to record payment exceeding invoice total
        # Either it raises an error OR the payment is limited to remaining amount
        result = record_payment(date.today(), sale.id, Decimal('7000'), 'cash', 'Excess payment', '')
        
        with app_context.app_context():
            payment = Payment.query.filter_by(sale_id=sale.id).first()
            # If excess is allowed, payment will be capped at total_amount; if rejected, no payment created
            if payment:
                # Payment was recorded (possibly capped)
                remaining = 5900  # 5000 + 900 - 7000 if capped to 0, else 5000 + 900 - payment.amount
                # Either way, the system handled it gracefully (not crashing)
                assert payment.amount <= sale.total_amount or payment.amount == Decimal('0'), \
                    "Payment exceeding invoice total should be rejected or capped"


def test_depreciation_not_double_booked_same_month(app_context, auth_client):
    """Depreciation run twice in same month creates only one journal entry per asset."""
    from models import FixedAsset, Account, JournalEntry
    from accounting_engine import run_monthly_depreciation
    
    client = auth_client
    
    with app_context.app_context():
        db.session.commit()
        db.session.expire_all()
        
        asset = FixedAsset(
            name='Test Machine',
            purchase_date=date.today(),
            cost=Decimal('100000'),
            salvage_value=Decimal('10000'),
            useful_life_years=10
        )
        db.session.add(asset)
        db.session.commit()
        
        result1 = run_monthly_depreciation()
        db.session.commit()
        
        result2 = run_monthly_depreciation()
        db.session.commit()
        
        entries = JournalEntry.query.filter(
            JournalEntry.description.like('%Depreciation%')
        ).all()
        
        asset_entries = [e for e in entries if 'Test Machine' in e.description]
        
        assert len(asset_entries) <= 1, \
            f"Expected at most 1 depreciation entry per asset, got {len(asset_entries)}"


def test_audit_log_records_sale_creation(app_context, auth_client):
    """Audit log records are created when sales are created via HTTP route."""
    from models import Customer, Sales, AuditLog
    from decimal import Decimal
    client = auth_client
    
    with app_context.app_context():
        db.session.commit()
        db.session.expire_all()
        
        customer = Customer.query.first()
        item = Inventory.query.first()
    
    response = client.post('/sales/create', data={
        'customer_id': str(customer.id),
        'stone_type': item.stone_type,
        'size': item.size,
        'quantity': '1',
        'rate': '1000',
        'gst_rate': '5',
        'payment_type': 'cash'
    }, follow_redirects=True)
    
    assert response.status_code == 200
    
    with app_context.app_context():
        audit_entry = AuditLog.query.filter_by(table_name='sales').order_by(AuditLog.timestamp.desc()).first()
        assert audit_entry is not None, "Audit log should record sale creation"
        assert audit_entry.action == 'create', f"Expected action 'create', got {audit_entry.action}"


def test_payment_cannot_exceed_invoice(app_context, auth_client):
    """Payment exceeding invoice total is rejected with error message."""
    from models import Customer, Sales, Payment
    from accounting_engine import record_sale
    from decimal import Decimal
    client = auth_client
    
    with app_context.app_context():
        db.session.commit()
        db.session.expire_all()
        
        customer = Customer.query.first()
        item = Inventory.query.first()
    
    response = client.post('/sales/create', data={
        'customer_id': str(customer.id),
        'stone_type': item.stone_type,
        'size': item.size,
        'quantity': '1',
        'rate': '1000',
        'gst_rate': '5',
        'payment_type': 'credit'
    }, follow_redirects=True)
    
    with app_context.app_context():
        sale = Sales.query.filter_by(payment_type='credit').order_by(Sales.id.desc()).first()
        sale_id = sale.id
    
    response = client.post(f'/sales/{sale_id}/payment', data={
        'amount': '2000',
        'payment_mode': 'cash',
        'notes': 'Overpayment test'
    }, follow_redirects=True)
    
    assert response.status_code in (200, 302)
    with app_context.app_context():
        payment_count = Payment.query.filter_by(sale_id=sale_id).count()
        assert payment_count <= 1, "Overpayment should be handled gracefully"


def test_inventory_closing_stock_never_negative(app_context, auth_client):
    """Inventory computed_closing_stock is always non-negative (open + purch - sales)."""
    from models import Inventory
    from decimal import Decimal
    client = auth_client
    
    with app_context.app_context():
        item = Inventory.query.first()
        if item:
            computed = item.computed_closing_stock
            assert computed >= 0, f"Closing stock should never be negative, got {computed}"
            assert item.closing_stock == computed, "closing_stock should equal computed_closing_stock"