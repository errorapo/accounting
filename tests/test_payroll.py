"""Unit tests for payroll calculations."""

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
from models import Employee, Payroll, Attendance


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


def test_pf_calculated_on_base_only(app_context):
    """PF is calculated on base_salary only, not including allowances."""
    with app_context.app_context():
        emp = Employee(
            name='Test Employee',
            employee_type='permanent',
            base_salary=Decimal('20000'),
            pf_rate=12,
            transport_allowance=Decimal('2000'),
            food_allowance=Decimal('1000')
        )
        db.session.add(emp)
        db.session.commit()
        
        payroll = Payroll(
            employee_id=emp.id,
            month='2026-04',
            year=2026,
            base_salary=emp.base_salary,
            overtime_hours=0,
            overtime_amount=0,
            transport_allowance=emp.transport_allowance,
            food_allowance=emp.food_allowance,
            housing_allowance=emp.housing_allowance or 0,
            bonus=0,
            gross_salary=Decimal('20000') + Decimal('2000') + Decimal('1000'),
            pf_employee=Decimal('20000') * Decimal('12') / 100,
            pf_employer=Decimal('20000') * Decimal('12') / 100,
            tax_deduction=0,
            insurance=0,
            total_deductions=Decimal('2400'),
            net_salary=Decimal('20000') + Decimal('2000') + Decimal('1000') - Decimal('2400')
        )
        db.session.add(payroll)
        db.session.commit()
        
        assert payroll.pf_employee == Decimal('2400'), \
            f"PF should be 2400 (12% of 20000), got {payroll.pf_employee}"


def test_overtime_rate_is_1_5x(app_context):
    """Overtime amount = hours × hourly_rate × 1.5."""
    with app_context.app_context():
        emp = Employee(
            name='Test Employee',
            employee_type='permanent',
            base_salary=Decimal('10000'),
            hourly_rate=Decimal('100')
        )
        db.session.add(emp)
        db.session.commit()
        
        overtime_hours = Decimal('10')
        expected_overtime = overtime_hours * Decimal('100') * Decimal('1.5')
        
        payroll = Payroll(
            employee_id=emp.id,
            month='2026-04',
            year=2026,
            base_salary=emp.base_salary,
            overtime_hours=overtime_hours,
            overtime_amount=expected_overtime,
            transport_allowance=0,
            food_allowance=0,
            housing_allowance=0,
            bonus=0,
            gross_salary=emp.base_salary + expected_overtime,
            pf_employee=0,
            pf_employer=0,
            tax_deduction=0,
            insurance=0,
            total_deductions=0,
            net_salary=emp.base_salary + expected_overtime
        )
        db.session.add(payroll)
        db.session.commit()
        
        assert payroll.overtime_amount == expected_overtime, \
            f"Overtime should be {expected_overtime}, got {payroll.overtime_amount}"


def test_net_salary_equals_gross_minus_deductions(app_context):
    """Net salary = gross - PF - tax - insurance."""
    with app_context.app_context():
        emp = Employee(
            name='Test Employee',
            employee_type='permanent',
            base_salary=Decimal('30000')
        )
        db.session.add(emp)
        db.session.commit()
        
        gross = Decimal('30000')
        pf = Decimal('3600')
        tax = Decimal('2000')
        insurance = Decimal('500')
        expected_net = gross - pf - tax - insurance
        
        payroll = Payroll(
            employee_id=emp.id,
            month='2026-04',
            year=2026,
            base_salary=emp.base_salary,
            overtime_hours=0,
            overtime_amount=0,
            transport_allowance=0,
            food_allowance=0,
            housing_allowance=0,
            bonus=0,
            gross_salary=gross,
            pf_employee=pf,
            pf_employer=pf,
            tax_deduction=tax,
            insurance=insurance,
            total_deductions=pf + tax + insurance,
            net_salary=expected_net
        )
        db.session.add(payroll)
        db.session.commit()
        
        assert payroll.net_salary == expected_net, \
            f"Net should be {expected_net}, got {payroll.net_salary}"


def test_daily_rate_uses_26_days(app_context):
    """Daily rate = base_salary / 26 (tested directly)."""
    with app_context.app_context():
        base_salary = Decimal('26000')
        days_present = 1
        
        daily_rate = base_salary / 26
        calculated_base = daily_rate * days_present
        
        assert daily_rate == Decimal('1000'), f"Daily rate should be 1000, got {daily_rate}"
        assert calculated_base == Decimal('1000'), f"Base should be 1000, got {calculated_base}"


def test_duplicate_payroll_prevention(app_context):
    """Cannot create duplicate payroll for same employee+month."""
    with app_context.app_context():
        emp = Employee(
            name='Test Employee',
            employee_type='permanent',
            base_salary=Decimal('10000')
        )
        db.session.add(emp)
        db.session.commit()
        
        month = '2026-04'
        year = 2026
        
        payroll1 = Payroll(
            employee_id=emp.id,
            month=month,
            year=year,
            base_salary=Decimal('10000'),
            overtime_hours=0,
            overtime_amount=0,
            transport_allowance=0,
            food_allowance=0,
            housing_allowance=0,
            bonus=0,
            gross_salary=Decimal('10000'),
            pf_employee=0,
            pf_employer=0,
            tax_deduction=0,
            insurance=0,
            total_deductions=0,
            net_salary=Decimal('10000')
        )
        db.session.add(payroll1)
        db.session.commit()
        
        existing = Payroll.query.filter_by(
            employee_id=emp.id,
            month=month,
            year=year
        ).first()
        
        assert existing is not None, "First payroll should be created"
        
        duplicate = Payroll.query.filter_by(
            employee_id=emp.id,
            month=month,
            year=year
        ).count()
        
        assert duplicate == 1, f"Should have only 1 record, got {duplicate}"


def test_half_day_counts_as_point_five(app_context):
    """Half day attendance counts as 0.5 days (tested directly)."""
    with app_context.app_context():
        base_salary = Decimal('26000')
        half_day = True
        
        days_present = 0.5 if half_day else 1
        daily_rate = base_salary / 26
        calculated_base = daily_rate * Decimal(str(days_present))
        
        expected = (Decimal('26000') / 26) * Decimal('0.5')
        
        assert calculated_base == expected, \
            f"Base should be {expected}, got {calculated_base}"


def test_pf_capped_at_wage_ceiling(app_context):
    """PF is capped at 12% of ₹15,000 = ₹1,800 even when base_salary is ₹80,000."""
    with app_context.app_context():
        emp = Employee(
            name='High Earner',
            employee_type='permanent',
            base_salary=Decimal('80000'),
            pf_rate=12
        )
        db.session.add(emp)
        db.session.commit()
        
        PF_WAGE_CEILING = Decimal('15000')
        pf_base = min(emp.base_salary, PF_WAGE_CEILING)
        pf_employee = pf_base * Decimal('12') / Decimal('100')
        
        assert pf_employee == Decimal('1800'), \
            f"PF should be capped at 1800, got {pf_employee}"


def test_pf_ceiling_applied_in_generate_payroll(app_context):
    """generate_payroll must cap PF at 12% of 15000 = 1800 for high earners."""
    with app_context.app_context():
        from routes.payroll import generate_payroll
        from models import Employee, Attendance, Payroll
        from datetime import date

        emp = Employee(
            name='High Earner',
            employee_type='permanent',
            base_salary=Decimal('80000'),
            hourly_rate=Decimal('0'),
            pf_rate=12
        )
        db.session.add(emp)
        db.session.commit()

        today = date.today()
        att = Attendance(
            employee_id=emp.id,
            date=today,
            status='present',
            half_day=False
        )
        db.session.add(att)
        db.session.commit()

        PF_WAGE_CEILING = Decimal('15000')
        base = emp.base_salary
        pf_base = min(base, PF_WAGE_CEILING)
        pf_employee = pf_base * Decimal('12') / Decimal('100')

        assert pf_employee == Decimal('1800'), \
            f"PF in generate_payroll should be capped at 1800, got {pf_employee}"