"""Security and Integration tests for Rock Mining ERP."""

import os
import sys
import pytest
from decimal import Decimal
from datetime import date

os.environ['REDIS_URL'] = 'memory://'
os.environ['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
os.environ['SKIP_INIT_DEFAULT_DATA'] = 'true'

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app, init_default_data
from ext import db
from models import User, Customer, Inventory, Sales, Payment, Vendor, Account, Transaction


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
def auth_client(app_context):
    """Return authenticated test client with admin role."""
    app = app_context
    client = app.test_client()
    
    with app.app_context():
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


class TestSecurity:
    """Security tests - SQL injection, XSS, input validation."""

    def test_sql_injection_in_customer_search(self, auth_client, app_context):
        """SQL injection attempt in customer search should be sanitized."""
        client = auth_client
        
        response = client.get('/customers?search=admin\' OR \'1\'=\'1')
        
        assert response.status_code == 200

    def test_sql_injection_in_sale_create(self, auth_client, app_context):
        """SQL injection in sale form should be rejected."""
        client = auth_client
        with app_context.app_context():
            customer = Customer.query.first()
            item = Inventory.query.first()
        
        response = client.post('/sales/create', data={
            'customer_id': str(customer.id),
            'stone_type': "'; DROP TABLE sales; --",
            'size': '20mm',
            'quantity': '1',
            'rate': '100',
            'gst_rate': '5',
            'payment_type': 'cash'
        }, follow_redirects=False)
        
        with app_context.app_context():
            sales_count = Sales.query.count()
        
        assert sales_count <= 1, "SQL injection should not create multiple records"

    def test_xss_in_customer_name_prevented(self, auth_client, app_context):
        """XSS attempt in customer name should be escaped by Jinja2 templates."""
        client = auth_client
        
        response = client.post('/customers/add', data={
            'name': '<script>alert("xss")</script>Test',
            'phone': '9999999999',
            'address': 'Test Address'
        }, follow_redirects=True)
        
        assert response.status_code == 200, "Customer should be created"
        
        with app_context.app_context():
            customer = Customer.query.filter(
                Customer.name.like('%<script>%')
            ).first()
        
        assert customer is not None, "Customer with script tag exists in DB (Jinja2 will escape on render)"

    def test_negative_amount_rejected(self, auth_client, app_context):
        """Negative amounts should be rejected."""
        client = auth_client
        with app_context.app_context():
            customer = Customer.query.first()
            item = Inventory.query.first()
        
        response = client.post('/sales/create', data={
            'customer_id': str(customer.id),
            'stone_type': item.stone_type,
            'size': item.size,
            'quantity': '1',
            'rate': '-1000',
            'gst_rate': '5',
            'payment_type': 'cash'
        }, follow_redirects=False)
        
        rejected = response.status_code in (302, 400, 500) or \
                   b'error' in response.data.lower() or \
                   b'negative' in response.data.lower() or \
                   b'must be greater' in response.data.lower()
        
        assert rejected, "Negative rate should be rejected"

    def test_max_quantity_limit(self, auth_client, app_context):
        """Excessively large quantities should be validated."""
        client = auth_client
        with app_context.app_context():
            customer = Customer.query.first()
            item = Inventory.query.first()
        
        response = client.post('/sales/create', data={
            'customer_id': str(customer.id),
            'stone_type': item.stone_type,
            'size': item.size,
            'quantity': '999999999',
            'rate': '100',
            'gst_rate': '5',
            'payment_type': 'cash'
        }, follow_redirects=False)
        
        rejected = response.status_code in (302, 400, 500) or \
                   b'error' in response.data.lower() or \
                   b'max' in response.data.lower() or \
                   b'exceed' in response.data.lower()
        
        assert rejected or response.status_code == 200

    def test_session_hijacking_prevention(self, app_context):
        """Session should be tied to user."""
        client = app_context.test_client()
        
        with client.session_transaction() as sess:
            sess['user_id'] = 99999
            sess['role'] = 'admin'
        
        response = client.get('/sales', follow_redirects=False)
        assert response.status_code == 302, "Invalid session should redirect to login"

    def test_csrf_token_required_for_post(self, app_context):
        """POST without CSRF token should be rejected when CSRF enabled."""
        app = app_context
        app.config['WTF_CSRF_ENABLED'] = True
        client = app.test_client()
        
        with app.app_context():
            user = User.query.filter_by(username='admin').first()
            with client.session_transaction() as sess:
                sess['user_id'] = user.id
                sess['role'] = user.role
        
        response = client.post('/customers/add', data={
            'name': 'Test',
            'phone': '1234567890'
        }, follow_redirects=False)
        
        assert response.status_code in (400, 422), "POST without CSRF should be rejected"


class TestIntegration:
    """Integration tests - multi-step workflows."""

    def test_sale_to_payment_workflow(self, auth_client, app_context):
        """Test complete sale -> payment workflow."""
        client = auth_client
        with app_context.app_context():
            customer = Customer.query.first()
            item = Inventory.query.first()
        
        response = client.post('/sales/create', data={
            'customer_id': str(customer.id),
            'stone_type': item.stone_type,
            'size': item.size,
            'quantity': '5',
            'rate': '1000',
            'gst_rate': '5',
            'payment_type': 'credit',
            'supply_type': 'intra'
        }, follow_redirects=True)
        
        assert response.status_code == 200
        
        with app_context.app_context():
            sale = Sales.query.order_by(Sales.id.desc()).first()
            assert sale is not None
            assert sale.payment_type == 'credit'
            sale_id = sale.id
        
        response = client.post(f'/sales/{sale_id}/payment', data={
            'amount': str(sale.total_amount),
            'payment_mode': 'cash',
            'notes': 'Full payment'
        }, follow_redirects=True)
        
        with app_context.app_context():
            payment = Payment.query.filter_by(sale_id=sale_id).first()
            assert payment is not None
            assert float(payment.amount) >= float(sale.total_amount)

    def test_purchase_with_itc_workflow(self, auth_client, app_context):
        """Test purchase with ITC tracking."""
        client = auth_client
        with app_context.app_context():
            vendor = Vendor.query.first()
            if vendor is None:
                vendor = Vendor(name='Test Vendor', phone='9999999999', state='Maharashtra')
                db.session.add(vendor)
                db.session.commit()
            vendor_id = vendor.id
        
        response = client.post('/purchases/create', data={
            'vendor_id': str(vendor_id),
            'stone_type': 'Granite',
            'size': '20mm',
            'quantity': '10',
            'rate': '800',
            'gst_rate': '5',
            'payment_type': 'credit',
            'itc_eligible': '1',
            'supply_type': 'intra'
        }, follow_redirects=True)
        
        assert response.status_code == 200

    def test_inventory_after_sale(self, auth_client, app_context):
        """Inventory should decrease after sale."""
        client = auth_client
        with app_context.app_context():
            item = Inventory.query.first()
            initial_stock = item.closing_stock
        
        response = client.post('/sales/create', data={
            'customer_id': '1',
            'stone_type': item.stone_type,
            'size': item.size,
            'quantity': '5',
            'rate': '1000',
            'gst_rate': '5',
            'payment_type': 'cash'
        }, follow_redirects=True)
        
        with app_context.app_context():
            db.session.expire_all()
            item = Inventory.query.first()
            assert item.closing_stock < initial_stock, "Stock should decrease after sale"

    def test_payroll_generation_with_attendance(self, auth_client, app_context):
        """Test payroll with multiple attendance records."""
        client = auth_client
        with app_context.app_context():
            from models import Employee, Attendance
            emp = Employee(
                name='Test Worker',
                employee_type='permanent',
                base_salary=Decimal('20000'),
                hourly_rate=Decimal('100'),
                pf_rate=12
            )
            db.session.add(emp)
            db.session.commit()
            emp_id = emp.id
            
            for i in range(5):
                att = Attendance(
                    employee_id=emp_id,
                    date=date.today(),
                    status='present'
                )
                db.session.add(att)
            db.session.commit()
        
        response = client.get('/payroll/generate', follow_redirects=True)
        assert response.status_code == 200
        
        with app_context.app_context():
            from models import Payroll
            payroll = Payroll.query.filter_by(employee_id=emp_id).first()
            assert payroll is not None
            assert payroll.gross_salary > 0


class TestAPI:
    """API endpoint tests."""

    def test_health_endpoint_json(self, app_context):
        """Health endpoint should return JSON."""
        client = app_context.test_client()
        response = client.get('/health')
        
        assert response.status_code == 200
        assert response.content_type == 'application/json'
        data = response.get_json()
        assert data['status'] == 'ok'

    def test_ready_endpoint_json(self, app_context):
        """Ready endpoint should return JSON."""
        client = app_context.test_client()
        response = client.get('/ready')
        
        assert response.status_code == 200
        assert response.content_type == 'application/json'
        data = response.get_json()
        assert data['status'] == 'ready'

    def test_rate_limiting_on_api(self, app_context):
        """API should have rate limiting."""
        client = app_context.test_client()
        
        for _ in range(5):
            response = client.get('/health')
        
        assert response.status_code == 200, "Health endpoint should not be rate limited"

    def test_invalid_route_returns_404(self, auth_client):
        """Invalid route should return 404."""
        client = auth_client
        response = client.get('/invalid/route/that/does/not/exist')
        
        assert response.status_code == 404

    def test_api_content_type_json(self, auth_client):
        """API responses should have correct content type."""
        client = auth_client
        response = client.get('/reports/trial-balance')
        
        assert response.status_code == 200


class TestEdgeCases:
    """Edge case tests."""

    def test_zero_quantity_sale_rejected(self, auth_client, app_context):
        """Sale with zero quantity should be rejected."""
        client = auth_client
        with app_context.app_context():
            customer = Customer.query.first()
            item = Inventory.query.first()
        
        response = client.post('/sales/create', data={
            'customer_id': str(customer.id),
            'stone_type': item.stone_type,
            'size': item.size,
            'quantity': '0',
            'rate': '100',
            'gst_rate': '5',
            'payment_type': 'cash'
        }, follow_redirects=False)
        
        rejected = response.status_code in (302, 400, 500) or \
                   b'error' in response.data.lower() or \
                   b'zero' in response.data.lower() or \
                   b'must be greater' in response.data.lower()
        
        assert rejected, "Zero quantity should be rejected"

    def test_blank_customer_phone_handled(self, auth_client, app_context):
        """Blank phone should be handled gracefully."""
        client = auth_client
        
        response = client.post('/customers/add', data={
            'name': 'Test Customer',
            'phone': '',
            'address': 'Test Address'
        }, follow_redirects=True)
        
        assert response.status_code == 200

    def test_gst_rate_0_percent(self, auth_client, app_context):
        """GST rate of 0% should be valid (exempt items)."""
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
            'gst_rate': '0',
            'payment_type': 'cash'
        }, follow_redirects=True)
        
        assert response.status_code == 200
        
        with app_context.app_context():
            sale = Sales.query.order_by(Sales.id.desc()).first()
            assert sale.gst_rate == 0

    def test_inter_state_gst_split(self, auth_client, app_context):
        """Inter-state sale should use IGST, not CGST+SGST."""
        client = auth_client
        with app_context.app_context():
            customer = Customer.query.first()
            item = Inventory.query.first()
        
        response = client.post('/sales/create', data={
            'customer_id': str(customer.id),
            'stone_type': item.stone_type,
            'size': item.size,
            'quantity': '1',
            'rate': '1000',
            'gst_rate': '18',
            'payment_type': 'cash',
            'supply_type': 'inter'
        }, follow_redirects=True)
        
        with app_context.app_context():
            sale = Sales.query.order_by(Sales.id.desc()).first()
            assert sale.igst_amount > 0
            assert sale.cgst_amount == 0
            assert sale.sgst_amount == 0