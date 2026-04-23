from flask import Blueprint, render_template, request, redirect, url_for, flash
from routes.dashboard import login_required
from routes.auth_utils import admin_required
from ext import db
from models import Employee, Payroll, Attendance
from datetime import datetime
from decimal import Decimal
from validators import parse_non_negative_float

bp = Blueprint('payroll', __name__)

@bp.route('/employees')
@login_required
def employees():
    employees = Employee.query.all()
    return render_template('employees.html', employees=employees)

@bp.route('/employees/add', methods=['GET', 'POST'])
@login_required
@admin_required
def add_employee():
    if request.method == 'POST':
        employee = Employee(
            name=request.form.get('name'),
            employee_type=request.form.get('employee_type'),
            base_salary=float(request.form.get('base_salary', 0)),
            hourly_rate=float(request.form.get('hourly_rate', 0)),
            pf_rate=float(request.form.get('pf_rate', 12)),
            transport_allowance=float(request.form.get('transport_allowance', 0)),
            food_allowance=float(request.form.get('food_allowance', 0)),
            housing_allowance=float(request.form.get('housing_allowance', 0))
        )
        db.session.add(employee)
        db.session.commit()
        flash('Employee added successfully', 'success')
        return redirect(url_for('payroll.employees'))
    return render_template('add_employee.html')

@bp.route('/employees/edit/<int:id>', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_employee(id):
    employee = Employee.query.get_or_404(id)
    if request.method == 'POST':
        employee.name = request.form.get('name')
        employee.employee_type = request.form.get('employee_type')
        employee.base_salary = float(request.form.get('base_salary', 0))
        employee.hourly_rate = float(request.form.get('hourly_rate', 0))
        employee.pf_rate = float(request.form.get('pf_rate', 12))
        employee.transport_allowance = float(request.form.get('transport_allowance', 0))
        employee.food_allowance = float(request.form.get('food_allowance', 0))
        employee.housing_allowance = float(request.form.get('housing_allowance', 0))
        db.session.commit()
        flash('Employee updated successfully', 'success')
        return redirect(url_for('payroll.employees'))
    return render_template('edit_employee.html', employee=employee)

@bp.route('/employees/delete/<int:id>')
@login_required
@admin_required
def delete_employee(id):
    employee = Employee.query.get_or_404(id)
    employee.is_active = False
    db.session.commit()
    flash('Employee deleted successfully', 'success')
    return redirect(url_for('payroll.employees'))

@bp.route('/payroll/create', methods=['GET', 'POST'])
@login_required
def create_payroll():
    employees = Employee.query.filter_by(is_active=True).all()
    
    if request.method == 'POST':
        from datetime import date
        employee_id = int(request.form.get('employee_id'))
        employee = Employee.query.get(employee_id)
        
        try:
            overtime_hours = parse_non_negative_float(request.form.get('overtime_hours', 0), 'Overtime hours')
            bonus          = parse_non_negative_float(request.form.get('bonus', 0), 'Bonus')
            insurance      = parse_non_negative_float(request.form.get('insurance', 0), 'Insurance')
            tax_deduction  = parse_non_negative_float(request.form.get('tax_deduction', 0), 'Tax deduction')
        except ValueError as e:
            flash(str(e), 'error')
            return render_template('create_payroll.html', employees=employees)

        # Convert all to Decimal for safe arithmetic with Numeric columns
        base = employee.base_salary
        hourly = employee.hourly_rate
        transport = employee.transport_allowance
        food = employee.food_allowance
        housing = employee.housing_allowance
        pf_rate = employee.pf_rate

        overtime_amount = Decimal(str(overtime_hours)) * Decimal(str(hourly)) * Decimal('1.5')
        gross_salary = base + overtime_amount + transport + food + housing + Decimal(str(bonus))

        pf_employee = base * Decimal(str(pf_rate)) / Decimal('100')
        pf_employer = pf_employee
        bonus_dec = Decimal(str(bonus))
        tax_dec = Decimal(str(tax_deduction))
        insurance_dec = Decimal(str(insurance))
        total_deductions = pf_employee + tax_dec + insurance_dec
        net_salary = gross_salary - total_deductions
        
        month = request.form.get('month')
        year = int(request.form.get('year'))
        
        payroll = Payroll(
            employee_id=employee_id,
            month=month,
            year=year,
            base_salary=employee.base_salary,
            overtime_hours=overtime_hours,
            overtime_amount=overtime_amount,
            transport_allowance=employee.transport_allowance,
            food_allowance=employee.food_allowance,
            housing_allowance=employee.housing_allowance,
            bonus=bonus,
            gross_salary=gross_salary,
            pf_employee=pf_employee,
            pf_employer=pf_employer,
            tax_deduction=tax_deduction,
            insurance=insurance,
            total_deductions=total_deductions,
            net_salary=net_salary
        )
        db.session.add(payroll)
        db.session.flush()

        from accounting_engine import record_salary_payment
        record_salary_payment(date.today(), employee.name, gross_salary, pf_employee, pf_employer, tax_deduction, f"Salary {month}")

        db.session.commit()
        flash('Payroll created successfully', 'success')
        return redirect(url_for('payroll.payroll_list'))
    
    return render_template('create_payroll.html', employees=employees)

@bp.route('/payroll/list')
@login_required
def payroll_list():
    payrolls = Payroll.query.order_by(Payroll.created_at.desc()).all()
    return render_template('payroll_list.html', payrolls=payrolls)

@bp.route('/attendance')
@login_required
def attendance():
    from datetime import date
    employees = Employee.query.filter_by(is_active=True).all()
    today = date.today()
    attendance_records = Attendance.query.filter_by(date=today).all()
    present_ids = [a.employee_id for a in attendance_records]
    return render_template('attendance.html', employees=employees, attendance_records=attendance_records, present_ids=present_ids, today=today)

@bp.route('/attendance/mark/<int:id>/<status>')
@login_required
def mark_attendance(id, status):
    from datetime import date
    today = date.today()
    att = Attendance.query.filter_by(employee_id=id, date=today).first()
    
    if status == 'present':
        if att:
            att.status = 'present'
            att.half_day = False
        else:
            att = Attendance(employee_id=id, date=today, status='present', half_day=False)
        db.session.add(att)
    elif status == 'half':
        if att:
            att.status = 'present'
            att.half_day = True
        else:
            att = Attendance(employee_id=id, date=today, status='present', half_day=True)
        db.session.add(att)
    elif status == 'absent':
        if att:
            att.status = 'absent'
            att.half_day = False
        else:
            att = Attendance(employee_id=id, date=today, status='absent', half_day=False)
        db.session.add(att)
    elif status == 'overtime':
        hours = float(request.args.get('hours', 0))
        if hours < 0:
            flash('Overtime hours cannot be negative', 'error')
            return redirect(url_for('payroll.attendance'))
        if att:
            att.overtime_hours = hours
        else:
            att = Attendance(employee_id=id, date=today, status='present', overtime_hours=hours)
        db.session.add(att)
    
    db.session.commit()
    flash('Attendance marked', 'success')
    return redirect(url_for('payroll.attendance'))

@bp.route('/attendance/overtime/<int:id>', methods=['GET', 'POST'])
@login_required
def add_overtime(id):
    from datetime import date
    today = date.today()
    att = Attendance.query.filter_by(employee_id=id, date=today).first()
    
    if request.method == 'POST':
        hours = float(request.form.get('hours', 0))
        if hours < 0:
            flash('Overtime hours cannot be negative', 'error')
            return redirect(url_for('payroll.attendance'))
        if att:
            att.overtime_hours = hours
        else:
            att = Attendance(employee_id=id, date=today, status='present', overtime_hours=hours)
        db.session.add(att)
        db.session.commit()
        flash('Overtime added', 'success')
        return redirect(url_for('payroll.attendance'))
    
    current_hours = att.overtime_hours if att else 0
    return render_template('add_overtime.html', employee_id=id, hours=current_hours)

@bp.route('/payroll/generate')
@login_required
@admin_required
def generate_payroll():
    from datetime import date

    today = date.today()
    month = f"{today.year}-{today.month:02d}"
    month_start = date(today.year, today.month, 1)
    
    if today.month == 12:
        month_end = date(today.year + 1, 1, 1)
    else:
        month_end = date(today.year, today.month + 1, 1)
    
    employees = Employee.query.filter_by(is_active=True).all()
    created_count = 0
    skipped_count = 0
    
    for emp in employees:
        existing_payroll = Payroll.query.filter_by(
            employee_id=emp.id,
            month=month,
            year=today.year
        ).first()
        
        if existing_payroll:
            skipped_count += 1
            continue
        
        attendance_records = Attendance.query.filter(
            Attendance.employee_id == emp.id,
            Attendance.date >= month_start,
            Attendance.date < month_end,
            Attendance.status == 'present'
        ).all()
        
        if not attendance_records:
            continue
        
        days_present = 0
        total_overtime = 0.0

        for att in attendance_records:
            if att.half_day:
                days_present += 0.5  # Half day = 0.5
            else:
                days_present += 1
            total_overtime += att.overtime_hours or 0

        daily_rate = emp.base_salary / 26  # Indian payroll uses 26 working days (excluding Sunday) as standard
        base = days_present * daily_rate
        
        overtime_amount = total_overtime * emp.hourly_rate * 1.5
        
        gross = base + overtime_amount + emp.transport_allowance + emp.food_allowance + emp.housing_allowance
        
        pf_employee = (base * emp.pf_rate) / 100
        pf_employer = pf_employee
        total_deductions = pf_employee
        net = gross - total_deductions
        
        payroll = Payroll(
            employee_id=emp.id,
            month=month,
            year=today.year,
            base_salary=base,
            overtime_hours=total_overtime,
            overtime_amount=overtime_amount,
            transport_allowance=emp.transport_allowance,
            food_allowance=emp.food_allowance,
            housing_allowance=emp.housing_allowance,
            bonus=0,
            gross_salary=gross,
            pf_employee=pf_employee,
            pf_employer=pf_employer,
            tax_deduction=0,
            insurance=0,
            total_deductions=total_deductions,
            net_salary=net
        )
        db.session.add(payroll)
        db.session.flush()

        from accounting_engine import record_salary_payment
        record_salary_payment(today, emp.name, gross, pf_employee, pf_employer, 0, f"Monthly {month}")

        created_count += 1

    db.session.commit()
    msg = f'Payroll generated for {created_count} employees ({month})'
    if skipped_count > 0:
        msg += f', {skipped_count} skipped (already exists)'
    flash(msg, 'success')
    return redirect(url_for('payroll.payroll_list'))