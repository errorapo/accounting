from flask import Blueprint, render_template, request, redirect, url_for, flash, send_file
from routes.dashboard import login_required
from ext import db
from models import Purchase, Inventory, Account, PurchasePayment
from datetime import datetime, date
from accounting_engine import record_purchase, create_journal_entry, get_or_create_account

bp = Blueprint('purchases', __name__)

def generate_purchase_invoice_number():
    last = Purchase.query.order_by(Purchase.id.desc()).first()
    if last and last.invoice_number:
        try:
            last_num = int(last.invoice_number.split('-')[-1])
            next_num = last_num + 1
        except:
            next_num = 1
    else:
        next_num = 1
    return f"PUR-{date.today().year}-{next_num:05d}"

@bp.route('/purchases')
@login_required
def purchases_list():
    purchases = Purchase.query.order_by(Purchase.created_at.desc()).all()
    return render_template('purchases_list.html', purchases=purchases)

@bp.route('/purchases/create', methods=['GET', 'POST'])
@login_required
def create_purchase():
    inventory = Inventory.query.all()

    if request.method == 'POST':
        vendor_name = request.form.get('vendor_name', '').strip()
        payment_type = request.form.get('payment_type', 'cash')
        stone_type = request.form.get('stone_type')
        size = request.form.get('size')
        quantity = float(request.form.get('quantity', 0))
        rate = float(request.form.get('rate', 0))
        gst_rate = float(request.form.get('gst_rate', 5))
        itc_eligible = request.form.get('itc_eligible') == '1'

        if not vendor_name:
            flash('Vendor name is required', 'error')
            return render_template('create_purchase.html', inventory=inventory)

        amount = quantity * rate
        gst_amount = amount * (gst_rate / 100)
        total_amount = amount + gst_amount
        payment_status = 'paid' if payment_type == 'cash' else 'pending'

        purchase = Purchase(
            invoice_number=generate_purchase_invoice_number(),
            vendor_name=vendor_name,
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
            itc_eligible=itc_eligible,
            invoice_date=date.today()
        )
        db.session.add(purchase)
        db.session.flush()

        item = Inventory.query.filter_by(stone_type=stone_type, size=size).first()
        if item:
            item.purchases += quantity
            item.closing_stock = item.opening_stock + item.purchases - item.sales

        record_purchase(date.today(), vendor_name, amount, gst_amount, payment_type, f"{stone_type} {size}", quantity, stone_type, size)

        db.session.commit()
        flash(f'Purchase created successfully - {purchase.invoice_number}', 'success')
        return redirect(url_for('purchases.purchases_list'))

    return render_template('create_purchase.html', inventory=inventory)

@bp.route('/purchases/<int:id>/mark-paid')
@login_required
def mark_paid(id):
    purchase = Purchase.query.get_or_404(id)

    if purchase.payment_type == 'cash':
        flash('Cash purchase already marked as paid', 'info')
        return redirect(url_for('purchases.purchases_list'))

    if purchase.payment_status == 'paid':
        flash('Purchase already marked as paid', 'info')
        return redirect(url_for('purchases.purchases_list'))

    purchase.payment_status = 'paid'

    payable_acc = get_or_create_account('Accounts Payable', 'liability')
    cash_acc = get_or_create_account('Cash', 'asset')
    if payable_acc and cash_acc:
        create_journal_entry(date.today(), f"Purchase Payment: {purchase.invoice_number}",
                            payable_acc.id, cash_acc.id, purchase.total_amount)

    db.session.commit()
    flash('Purchase payment recorded', 'success')
    return redirect(url_for('purchases.purchases_list'))

@bp.route('/purchases/<int:id>/payment', methods=['GET', 'POST'])
@login_required
def add_payment(id):
    """Record a payment against a credit purchase (partial or full)."""
    purchase = Purchase.query.get_or_404(id)

    if purchase.payment_type == 'cash':
        flash('Cash purchases do not need payment recording', 'info')
        return redirect(url_for('purchases.purchases_list'))

    if request.method == 'POST':
        amount = float(request.form.get('amount', 0))
        payment_mode = request.form.get('payment_mode', 'cash')
        notes = request.form.get('notes', '')

        if amount <= 0:
            flash('Amount must be positive', 'error')
            return render_template('add_payment.html', purchase=purchase)

        paid_total = sum(p.amount for p in purchase.payments) + amount
        if paid_total > purchase.total_amount:
            flash(f'Payment exceeds outstanding. Outstanding: ₹{purchase.total_amount - sum(p.amount for p in purchase.payments):.2f}', 'error')
            return render_template('add_payment.html', purchase=purchase)

        payment = PurchasePayment(
            purchase_id=purchase.id,
            amount=amount,
            payment_date=date.today(),
            payment_mode=payment_mode,
            notes=notes
        )
        db.session.add(payment)

        payable_acc = get_or_create_account('Accounts Payable', 'liability')
        cash_acc = get_or_create_account('Cash', 'asset')
        create_journal_entry(date.today(), f"Purchase Payment: {purchase.invoice_number}",
                            payable_acc.id, cash_acc.id, amount)

        if paid_total >= purchase.total_amount - 0.01:
            purchase.payment_status = 'paid'

        db.session.commit()
        flash(f'Payment of ₹{amount:.2f} recorded', 'success')
        return redirect(url_for('purchases.purchases_list'))

    paid = sum(p.amount for p in purchase.payments)
    outstanding = purchase.total_amount - paid
    return render_template('add_payment.html', purchase=purchase, paid=paid, outstanding=outstanding)

@bp.route('/purchases/<int:id>/delete', methods=['POST'])
@login_required
def delete_purchase(id):
    purchase = Purchase.query.get_or_404(id)
    db.session.delete(purchase)
    db.session.commit()
    flash('Purchase deleted', 'success')
    return redirect(url_for('purchases.purchases_list'))

@bp.route('/purchases/<int:id>/invoice')
@login_required
def invoice(id):
    purchase = Purchase.query.get_or_404(id)
    return render_template('purchase_invoice_pdf.html', purchase=purchase)

@bp.route('/purchases/<int:id>/invoice/pdf')
@login_required
def invoice_pdf(id):
    purchase = Purchase.query.get_or_404(id)
    try:
        from xhtml2pdf import pisa
        from io import BytesIO

        html_content = render_template('purchase_invoice_pdf.html', purchase=purchase)
        pdf = BytesIO()
        pisa.pisaDocument(BytesIO(html_content.encode('utf-8')), pdf)
        pdf.seek(0)
        return send_file(pdf, mimetype='application/pdf',
                        download_name=f'Purchase_{purchase.invoice_number}.pdf')
    except Exception as e:
        flash(f'PDF generation failed: {str(e)}. Try printing from the invoice page.', 'error')
        return redirect(url_for('purchases.invoice', id=id))