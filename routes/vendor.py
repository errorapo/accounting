from flask import Blueprint, render_template, request, redirect, url_for, flash
from routes.dashboard import login_required
from ext import db
from models import Vendor

bp = Blueprint('vendor', __name__)

@bp.route('/vendors')
@login_required
def vendors_list():
    vendors = Vendor.query.filter_by(is_active=True).all()
    return render_template('vendors.html', vendors=vendors)

@bp.route('/vendors/add', methods=['GET', 'POST'])
@login_required
def add_vendor():
    if request.method == 'POST':
        vendor = Vendor(
            name=request.form.get('name'),
            phone=request.form.get('phone'),
            address=request.form.get('address'),
            gstin=request.form.get('gstin'),
            state=request.form.get('state')
        )
        db.session.add(vendor)
        db.session.commit()
        flash('Vendor added successfully', 'success')
        return redirect(url_for('vendor.vendors_list'))
    return render_template('add_vendor.html')

@bp.route('/vendors/edit/<int:id>', methods=['GET', 'POST'])
@login_required
def edit_vendor(id):
    vendor = Vendor.query.get_or_404(id)
    if request.method == 'POST':
        vendor.name = request.form.get('name')
        vendor.phone = request.form.get('phone')
        vendor.address = request.form.get('address')
        vendor.gstin = request.form.get('gstin')
        vendor.state = request.form.get('state')
        db.session.commit()
        flash('Vendor updated successfully', 'success')
        return redirect(url_for('vendor.vendors_list'))
    return render_template('edit_vendor.html', vendor=vendor)

@bp.route('/vendors/delete/<int:id>')
@login_required
def delete_vendor(id):
    vendor = Vendor.query.get_or_404(id)
    vendor.is_active = False
    db.session.commit()
    flash('Vendor deleted successfully', 'success')
    return redirect(url_for('vendor.vendors_list'))