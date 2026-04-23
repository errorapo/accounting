"""Smoke tests for Rock Mining ERP."""

import os
import sys

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Force memory:// for rate limiter before any app imports
os.environ['REDIS_URL'] = 'memory://'

from app import create_app, init_default_data
from ext import db
from models import User, Inventory, Sales, InvoiceSequence


def run_tests():
    app = create_app('development')
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'

    results = []

    # ── Test 1: App starts without errors ──────────────────────────────────────
    try:
        with app.app_context():
            db.create_all()
            init_default_data()
        results.append(("App starts without errors", True))
    except Exception as e:
        results.append(("App starts without errors", False, str(e)))

    # ── Test 2: Login route returns 200 ───────────────────────────────────────
    try:
        client = app.test_client()
        with app.app_context():
            # Login first
            user = User.query.filter_by(username='admin').first()
            if user is None:
                user = User(username='admin',
                            password_hash=generate_password_hash('admin123'),
                            role='admin')
                db.session.add(user)
                db.session.commit()

        with client.session_transaction() as sess:
            sess['user_id'] = user.id
            sess['role'] = user.role

        response = client.get('/sales', follow_redirects=True)
        status = response.status_code
        results.append(("Login route returns 200", 200 <= status < 400,
                        f"Got {status}"))
    except Exception as e:
        results.append(("Login route returns 200", False, str(e)))

    # ── Test 3: Sale cannot be created with negative quantity ─────────────────
    try:
        client = app.test_client()
        with app.app_context():
            db.create_all()
            init_default_data()

            # Get a valid item from inventory
            item = Inventory.query.first()
            if item is None:
                item = Inventory(stone_type='Granite', size='20mm',
                                 opening_stock=100, purchases=0, sales=0,
                                 closing_stock=100, rate_per_ton=1200)
                db.session.add(item)
                db.session.commit()

            user = User.query.filter_by(username='admin').first()
            customer = db.session.query(Customer).first()
            if customer is None:
                customer = Customer(name='Test Customer', phone='9999999999')
                db.session.add(customer)
                db.session.commit()

        with client.session_transaction() as sess:
            sess['user_id'] = user.id
            sess['role'] = user.role

        response = client.post('/sales/create', data={
            'customer_id': str(customer.id),
            'stone_type': item.stone_type,
            'size': item.size,
            'quantity': '-5',
            'rate': '100',
            'gst_rate': '5',
            'payment_type': 'cash'
        }, follow_redirects=False)

        with app.app_context():
            bad_sale = Sales.query.filter_by(quantity=float(-5)).first()

        # Check that either the HTTP response rejected it, OR the DB has no bad sale
        rejected = response.status_code in (302, 400, 500) or \
                b'error' in response.data.lower() or \
                b'must be greater' in response.data.lower() or \
                b'cannot be negative' in response.data.lower()
        passed = rejected and bad_sale is None

        results.append(("Sale cannot be created with negative quantity", passed,
                        f"Sale with qty=-5 was created (id={bad_sale.id})" if bad_sale else ""))
    except Exception as e:
        results.append(("Sale cannot be created with negative quantity",
                        False, str(e)))

    # ── Test 4: Sale cannot be created with quantity exceeding stock ──────────
    try:
        client = app.test_client()
        with app.app_context():
            db.create_all()

            # Create item with known closing stock
            item = Inventory(stone_type='Limestone', size='10mm',
                             opening_stock=10, purchases=0, sales=0,
                             closing_stock=10, rate_per_ton=800)
            db.session.add(item)
            db.session.commit()

            user = User.query.filter_by(username='admin').first()
            customer = db.session.query(Customer).first()
            if customer is None:
                customer = Customer(name='Test Customer', phone='9999999999')
                db.session.add(customer)
                db.session.commit()

        with client.session_transaction() as sess:
            sess['user_id'] = user.id
            sess['role'] = user.role

        response = client.post('/sales/create', data={
            'customer_id': str(customer.id),
            'stone_type': 'Limestone',
            'size': '10mm',
            'quantity': '9999',
            'rate': '800',
            'gst_rate': '5',
            'payment_type': 'cash'
        }, follow_redirects=False)

        with app.app_context():
            # Verify the large sale was NOT committed
            large_sale = Sales.query.filter_by(quantity=float(9999)).first()

        rejected = response.status_code in (302, 400, 500) or \
                b'error' in response.data.lower() or \
                b'insufficient' in response.data.lower() or \
                b'stock' in response.data.lower()
        passed = rejected and large_sale is None

        results.append(("Sale cannot be created with quantity exceeding stock",
                        passed,
                        f"Sale with qty=9999 was created (id={large_sale.id})" if large_sale else ""))
    except Exception as e:
        results.append(("Sale cannot be created with quantity exceeding stock",
                        False, str(e)))

    # ── Test 5: Invoice number generation works without duplicates ─────────────
    try:
        client = app.test_client()
        with app.app_context():
            db.drop_all()
            db.create_all()
            init_default_data()

            user = User.query.filter_by(username='admin').first()
            customer = db.session.query(Customer).first()
            if customer is None:
                customer = Customer(name='Test Customer', phone='9999999999')
                db.session.add(customer)
                db.session.commit()

            item = Inventory.query.first()
            if item is None:
                item = Inventory(stone_type='Granite', size='20mm',
                                 opening_stock=1000, purchases=0, sales=0,
                                 closing_stock=1000, rate_per_ton=1200)
                db.session.add(item)
                db.session.commit()

        with client.session_transaction() as sess:
            sess['user_id'] = user.id
            sess['role'] = user.role

        invoice_numbers = []
        for i in range(5):
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
                with app.app_context():
                    latest = Sales.query.filter(
                        Sales.invoice_number.isnot(None)
                    ).order_by(Sales.id.desc()).first()
                    if latest and latest.invoice_number:
                        invoice_numbers.append(latest.invoice_number)

        passed = len(invoice_numbers) >= 3 and len(invoice_numbers) == len(set(invoice_numbers))

        results.append(("Invoice number generation works without duplicates",
                        passed,
                        f"Numbers: {invoice_numbers}" if not passed else ""))
    except Exception as e:
        import traceback
        traceback.print_exc()
        results.append(("Invoice number generation works without duplicates",
                        False, str(e)))

    # ── Print results ─────────────────────────────────────────────────────────
    print("\n=== Smoke Test Results ===")
    for name, passed, *extra in results:
        status = "PASS" if passed else "FAIL"
        detail = f" ({extra[0]})" if extra else ""
        print(f"  [{status}] {name}{detail}")

    all_passed = all(r[1] for r in results)
    print(f"\nOverall: {'ALL PASSED' if all_passed else 'SOME FAILED'}")
    return all_passed


if __name__ == '__main__':
    from werkzeug.security import generate_password_hash
    from models import Customer

    ok = run_tests()
    sys.exit(0 if ok else 1)
