import os
import uuid
import time
import logging
import base64
from logging.handlers import RotatingFileHandler
from dotenv import load_dotenv
load_dotenv()

from flask import Flask, request, g
from werkzeug.security import generate_password_hash, check_password_hash
from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from ext import db
from config import config

def format_inr(value):
    """Format number as Indian INR (Lakh/Crore): 1845000 → ₹18.45L"""
    if value is None:
        return '₹0'
    value = float(value)
    if value >= 10000000:
        return f'₹{value/10000000:.2f}Cr'
    elif value >= 100000:
        return f'₹{value/100000:.2f}L'
    elif value >= 1000:
        return f'₹{value/1000:.1f}K'
    else:
        return f'₹{value:.0f}'

def create_app(config_name=None):
    if config_name is None:
        config_name = os.environ.get('FLASK_ENV', 'development')
    
    skip_init = os.environ.get('SKIP_INIT_DEFAULT_DATA', 'false').lower() == 'true'
    
    app = Flask(__name__)
    cfg = config.get(config_name, config['development'])
    app.config.from_object(cfg)
    if hasattr(cfg, 'init_app'):
        cfg.init_app(app)
    
    app.jinja_env.filters['format_inr'] = format_inr
    
    csrf = CSRFProtect(app)
    db.init_app(app)
    
    limiter = Limiter(
        get_remote_address,
        app=app,
        default_limits=["200 per day", "50 per hour"],
        storage_uri=os.environ.get('REDIS_URL', 'memory://')
    )

    @app.before_request
    def before_request():
        g.start_time = time.time()
        g.request_id = str(uuid.uuid4())[:8]
        g.csp_nonce = base64.b64encode(os.urandom(16)).decode()

    @app.after_request
    def after_request(response):
        if hasattr(g, 'start_time') and hasattr(g, 'request_id'):
            duration_ms = int((time.time() - g.start_time) * 1000)
            app.logger.info(
                '%s %s %s %s %sms',
                g.request_id, request.method, request.path,
                response.status_code, duration_ms
            )
            response.headers['X-Request-ID'] = g.request_id
        return response

    @app.after_request
    def add_security_headers(response):
        nonce = getattr(g, 'csp_nonce', '')
        csp_header = f"default-src 'self'; script-src 'self' https://cdn.jsdelivr.net 'nonce-{nonce}'; style-src 'self' 'unsafe-inline';"
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['X-XSS-Protection'] = '1; mode=block'
        response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
        response.headers['Content-Security-Policy'] = csp_header
        return response
    
    from routes import auth, dashboard, payroll, inventory, sales, purchases, accounts, reports, vendor
    app.register_blueprint(auth.bp)
    app.register_blueprint(dashboard.bp)
    app.register_blueprint(payroll.bp)
    app.register_blueprint(inventory.bp)
    app.register_blueprint(sales.bp)
    app.register_blueprint(purchases.bp)
    app.register_blueprint(accounts.bp)
    app.register_blueprint(reports.bp)
    app.register_blueprint(vendor.bp)

    # Health check endpoints (no auth required, exempt from rate limiting)
    @app.route('/health')
    def health():
        """Liveness probe — app is running."""
        return {'status': 'ok'}, 200

    @app.route('/ready')
    def ready():
        """Readiness probe — DB is reachable."""
        try:
            db.session.execute(db.text('SELECT 1'))
        except Exception as e:
            return {'status': 'error', 'reason': str(e)}, 503
        return {'status': 'ready'}, 200

    limiter.exempt(health)
    limiter.exempt(ready)
    
    app.limiter = limiter

    # Production file logging (not in debug/testing)
    if not app.debug and not app.testing:
        os.makedirs('logs', exist_ok=True)
        file_handler = RotatingFileHandler(
            'logs/app.log', maxBytes=10*1024*1024, backupCount=5
        )
        file_handler.setFormatter(logging.Formatter(
            '%(asctime)s %(levelname)s %(name)s — %(message)s'
        ))
        file_handler.setLevel(logging.INFO)
        app.logger.addHandler(file_handler)
        app.logger.setLevel(logging.INFO)
        app.logger.propagate = False

    with app.app_context():
        db.create_all()
        if not skip_init:
            init_default_data()
    
    return app

def init_default_data():
    import os
    from models import User, Employee, Customer, Inventory, Sales, Payroll
    from datetime import date
    from accounting_engine import initialize_default_accounts

    # Get credentials from environment (fall back to .env values)
    admin_user = os.environ.get('ADMIN_USERNAME', 'admin')
    admin_pass = os.environ.get('ADMIN_PASSWORD', 'admin123')
    accountant_user = os.environ.get('ACCOUNTANT_USERNAME', 'accountant')
    accountant_pass = os.environ.get('ACCOUNTANT_PASSWORD', 'accountant123')

    if User.query.count() == 0:
        default_user = User(username=admin_user, password_hash=generate_password_hash(admin_pass), role='admin')
        db.session.add(default_user)

        accountant_user = User(username=accountant_user, password_hash=generate_password_hash(accountant_pass), role='accountant')
        db.session.add(accountant_user)
        db.session.commit()
    
    initialize_default_accounts()
    
    if Employee.query.count() == 0:
        employees = [
            Employee(name='Rajesh Kumar', employee_type='Driver', base_salary=15000, hourly_rate=80, pf_rate=12, transport_allowance=2000, food_allowance=1500, housing_allowance=3000),
            Employee(name='Mahesh Patel', employee_type='Machine Operator', base_salary=18000, hourly_rate=100, pf_rate=12, transport_allowance=2500, food_allowance=1500, housing_allowance=3500),
            Employee(name='Suresh Singh', employee_type='Manual Labour', base_salary=12000, hourly_rate=60, pf_rate=12, transport_allowance=1500, food_allowance=1500, housing_allowance=2000),
            Employee(name='Priya Sharma', employee_type='Office Staff', base_salary=20000, hourly_rate=120, pf_rate=12, transport_allowance=2000, food_allowance=1500, housing_allowance=4000),
            Employee(name='Amit Gupta', employee_type='Supervisor', base_salary=25000, hourly_rate=150, pf_rate=12, transport_allowance=3000, food_allowance=1500, housing_allowance=5000),
            Employee(name='Vikram Security', employee_type='Security', base_salary=14000, hourly_rate=70, pf_rate=12, transport_allowance=1000, food_allowance=1500, housing_allowance=2500),
        ]
        for emp in employees:
            db.session.add(emp)
        db.session.commit()
    
    if Customer.query.count() == 0:
        customers = [
            Customer(name='ABC Construction Ltd', phone='9876543210', address='Mumbai, Maharashtra'),
            Customer(name='XYZ Builders', phone='9876543211', address='Pune, Maharashtra'),
            Customer(name='Smith Infra', phone='9876543212', address='Delhi'),
            Customer(name='Raj Properties', phone='9876543213', address='Ahmedabad, Gujarat'),
        ]
        for cust in customers:
            db.session.add(cust)
        db.session.commit()
    
    if Inventory.query.count() == 0:
        inventory_items = [
            Inventory(stone_type='Granite', size='20mm', opening_stock=100, purchases=50, sales=30, rate_per_ton=1200),
            Inventory(stone_type='Granite', size='40mm', opening_stock=80, purchases=40, sales=25, rate_per_ton=1000),
            Inventory(stone_type='Limestone', size='10mm', opening_stock=60, purchases=30, sales=20, rate_per_ton=800),
            Inventory(stone_type='Limestone', size='20mm', opening_stock=50, purchases=25, sales=15, rate_per_ton=750),
            Inventory(stone_type='Marble', size='5mm', opening_stock=30, purchases=20, sales=10, rate_per_ton=2000),
            Inventory(stone_type='Sandstone', size='40mm', opening_stock=70, purchases=35, sales=20, rate_per_ton=900),
        ]
        for item in inventory_items:
            item.closing_stock = item.opening_stock + item.purchases - item.sales
            db.session.add(item)
        db.session.commit()
    
    if Sales.query.count() == 0:
        sale = Sales(
            customer_id=1,
            stone_type='Granite',
            size='20mm',
            quantity=20,
            rate=1200,
            amount=24000,
            gst_rate=5,
            gst_amount=1200,
            total_amount=25200,
            invoice_date=date.today()
        )
        db.session.add(sale)
        db.session.commit()

if __name__ == '__main__':
    app = create_app()
    cfg_name = os.environ.get('FLASK_ENV', 'development')
    app.run(debug=(cfg_name == 'development'), host='0.0.0.0', port=5000)