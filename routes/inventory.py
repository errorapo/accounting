from flask import Blueprint, render_template, request, redirect, url_for, flash
from routes.dashboard import login_required
from ext import db
from models import Inventory
from datetime import datetime

bp = Blueprint('inventory', __name__)

@bp.route('/inventory')
@login_required
def index():
    items = Inventory.query.all()
    return render_template('inventory.html', items=items)

@bp.route('/inventory/add', methods=['GET', 'POST'])
@login_required
def add_item():
    if request.method == 'POST':
        item = Inventory(
            stone_type=request.form.get('stone_type'),
            size=request.form.get('size'),
            opening_stock=float(request.form.get('opening_stock', 0)),
            purchases=float(request.form.get('purchases', 0)),
            sales=float(request.form.get('sales', 0)),
            rate_per_ton=float(request.form.get('rate_per_ton', 0))
        )
        item.closing_stock = item.opening_stock + item.purchases - item.sales
        db.session.add(item)
        db.session.commit()
        flash('Inventory item added successfully', 'success')
        return redirect(url_for('inventory.index'))
    return render_template('add_inventory.html')

@bp.route('/inventory/edit/<int:id>', methods=['GET', 'POST'])
@login_required
def edit_item(id):
    item = Inventory.query.get_or_404(id)
    if request.method == 'POST':
        item.stone_type = request.form.get('stone_type')
        item.size = request.form.get('size')
        item.opening_stock = float(request.form.get('opening_stock', 0))
        item.purchases = float(request.form.get('purchases', 0))
        item.sales = float(request.form.get('sales', 0))
        item.rate_per_ton = float(request.form.get('rate_per_ton', 0))
        item.closing_stock = item.opening_stock + item.purchases - item.sales
        db.session.commit()
        flash('Inventory updated successfully', 'success')
        return redirect(url_for('inventory.index'))
    return render_template('edit_inventory.html', item=item)

@bp.route('/inventory/purchase/<int:id>', methods=['GET', 'POST'])
@login_required
def purchase_item(id):
    """Direct inventory purchase recording — use /purchases/create for proper accounting."""
    flash('Use Purchases > Create Purchase for proper double-entry accounting', 'error')
    return redirect(url_for('inventory.index'))

@bp.route('/inventory/sale/<int:id>', methods=['GET', 'POST'])
@login_required
def sale_item(id):
    """Direct inventory sale recording — use /sales/create for proper double-entry accounting."""
    flash('Use Sales > Create Sale for proper double-entry accounting', 'error')
    return redirect(url_for('inventory.index'))