from flask import Blueprint, render_template, request, redirect, url_for, flash, send_file
from routes.dashboard import login_required
from ext import db
from models import Customer, Sales, Inventory, Account, Payment
from datetime import datetime, date

from accounting_engine import record_sale, record_payment

bp = Blueprint('sales', __name__)

def generate_invoice_number():
    """Generate sequential invoice number."""
    last_sale = Sales.query.order_by(Sales.id.desc()).first()
    if last_sale and last_sale.invoice_number:
        try:
            last_num = int(last_sale.invoice_number.split('-')[-1])
            next_num = last_num + 1
        except:
            next_num = 1
    else:
        next_num = 1
    return f"INV-{date.today().year}-{next_num:05d}"

@bp.route('/customers')
@login_required
def customers():
    customers = Customer.query.all()
    return render_template('customers.html', customers=customers)

@bp.route('/customers/add', methods=['GET', 'POST'])
@login_required
def add_customer():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        phone = request.form.get('phone', '').strip()
        
        if not name:
            flash('Customer name is required', 'error')
            return render_template('add_customer.html')
        
        if phone and not phone.replace('+', '').replace('-', '').replace(' ', '').replace('(', '').replace(')', '').isdigit():
            flash('Phone must contain only numbers', 'error')
            return render_template('add_customer.html')
        
        customer = Customer(
            name=name,
            phone=phone,
            address=request.form.get('address')
        )
        db.session.add(customer)
        db.session.commit()
        flash('Customer added successfully', 'success')
        return redirect(url_for('sales.customers'))
    return render_template('add_customer.html')

@bp.route('/sales')
@login_required
def sales_list():
    sales_records = Sales.query.order_by(Sales.created_at.desc()).all()
    return render_template('sales_list.html', sales_records=sales_records)

@bp.route('/sales/create', methods=['GET', 'POST'])
@login_required
def create_sale():
    customers = Customer.query.all()
    inventory = Inventory.query.all()
    
    if not customers:
        flash('Please add a customer first', 'error')
        return redirect(url_for('sales.add_customer'))
    
    if request.method == 'POST':
        customer_id = request.form.get('customer_id')
        if not customer_id:
            flash('Please select a customer', 'error')
            return render_template('create_sale.html', customers=customers, inventory=inventory)
        customer_id = int(customer_id)
        stone_type = request.form.get('stone_type')
        size = request.form.get('size')
        quantity = float(request.form.get('quantity', 0))
        rate = float(request.form.get('rate', 0))
        gst_rate = float(request.form.get('gst_rate', 5))
        payment_type = request.form.get('payment_type', 'cash')
        
        amount = quantity * rate
        gst_amount = amount * (gst_rate / 100)
        total_amount = amount + gst_amount
        
        # Determine payment status based on payment type
        payment_status = 'paid' if payment_type == 'cash' else 'pending'
        
        sale = Sales(
            invoice_number=generate_invoice_number(),
            customer_id=customer_id,
            stone_type=stone_type,
            size=size,
            quantity=quantity,
            rate=rate,
            amount=amount,
            gst_rate=gst_rate,
            gst_amount=gst_amount,
            total_amount=total_amount,
            payment_type=payment_type,
            payment_status=payment_status,
            invoice_date=date.today()
        )
        db.session.add(sale)
        db.session.flush()

        item = Inventory.query.filter_by(stone_type=stone_type, size=size).first()
        if item:
            item.sales += quantity
            item.closing_stock = item.opening_stock + item.purchases - item.sales

        record_sale(date.today(), f"INV-{sale.id}", amount, gst_amount, payment_type, f"{stone_type} {size}", quantity, stone_type, size)

        db.session.commit()
        flash(f'Sale created successfully - Invoice: {sale.invoice_number}', 'success')
        return redirect(url_for('sales.sales_list'))
    
    return render_template('create_sale.html', customers=customers, inventory=inventory)

@bp.route('/sales/<int:id>/payment', methods=['GET', 'POST'])
@login_required
def add_payment(id):
    """Record a payment against a credit sale (partial or full)."""
    sale = Sales.query.get_or_404(id)

    if sale.payment_type == 'cash':
        flash('Cash sales do not need payment recording', 'info')
        return redirect(url_for('sales.sales_list'))

    if request.method == 'POST':
        amount = float(request.form.get('amount', 0))
        payment_mode = request.form.get('payment_mode', 'cash')
        notes = request.form.get('notes', '')

        if amount <= 0:
            flash('Amount must be positive', 'error')
            return render_template('add_payment.html', sale=sale)

        paid_total = sum(p.amount for p in sale.payments) + amount
        if paid_total > sale.total_amount:
            flash(f'Payment exceeds outstanding. Outstanding: ₹{sale.total_amount - sum(p.amount for p in sale.payments):.2f}', 'error')
            return render_template('add_payment.html', sale=sale)

        payment = Payment(
            sale_id=sale.id,
            amount=amount,
            payment_date=date.today(),
            payment_mode=payment_mode,
            notes=notes
        )
        db.session.add(payment)

        record_payment(date.today(), sale.id, amount, payment_mode, notes, f"Payment: {sale.invoice_number}")

        if paid_total >= sale.total_amount - 0.01:
            sale.payment_status = 'paid'

        db.session.commit()
        flash(f'Payment of ₹{amount:.2f} recorded', 'success')
        return redirect(url_for('sales.sales_list'))

    paid = sum(p.amount for p in sale.payments)
    outstanding = sale.total_amount - paid
    return render_template('add_payment.html', sale=sale, paid=paid, outstanding=outstanding)

@bp.route('/sales/invoice/<int:id>')
@login_required
def invoice(id):
    sale = Sales.query.get_or_404(id)
    return render_template('invoice.html', sale=sale)

@bp.route('/sales/invoice/<int:id>/pdf')
@login_required
def invoice_pdf(id):
    sale = Sales.query.get_or_404(id)
    try:
        from xhtml2pdf import pisa
        from io import BytesIO
        import html

        html_content = render_template('invoice_pdf.html', sale=sale)
        pdf = BytesIO()
        pisa.pisaDocument(BytesIO(html_content.encode('utf-8')), pdf)
        pdf.seek(0)
        return send_file(pdf, mimetype='application/pdf',
                        download_name=f'Invoice_{sale.invoice_number}.pdf')
    except Exception as e:
        flash(f'PDF generation failed: {str(e)}. Try printing from the invoice page.', 'error')
        return redirect(url_for('sales.invoice', id=id))