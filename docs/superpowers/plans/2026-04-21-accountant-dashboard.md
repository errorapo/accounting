# Accountant Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create accountant dashboard with clean modern theme (light background, white cards), featuring sales trends, salary expenses, revenue vs expenses, top customers, and inventory alerts.

**Architecture:** Modify existing dashboard.py to add accountant-specific data queries. Create new accountant_dashboard.html template with light theme and Chart.js visualizations.

**Tech Stack:** Flask, Chart.js, SQLAlchemy

---

### Task 1: Update dashboard.py with accountant data queries

**Files:**
- Modify: `routes/dashboard.py:14-88`

- [ ] **Step 1: Read current dashboard.py file**

- [ ] **Step 2: Add accountant dashboard route**

```python
@bp.route('/accountant')
@login_required
def accountant_dashboard():
    if session.get('role') != 'accountant':
        return redirect(url_for('dashboard.admin_dashboard'))
    
    from models import Employee, Inventory, Sales, Payroll, Customer, Transaction
    from ext import db
    from sqlalchemy import func
    
    total_employees = Employee.query.filter_by(is_active=True).count()
    total_customers = Customer.query.count()
    total_inventory = Inventory.query.count()
    
    monthly_sales = db.session.query(func.sum(Sales.total_amount)).scalar() or 0
    total_salary = db.session.query(func.sum(Payroll.net_salary)).scalar() or 0
    
    recent_sales = Sales.query.order_by(Sales.created_at.desc()).limit(5).all()
    
    customers = Customer.query.all()
    customer_sales = []
    for c in customers:
        total = db.session.query(func.sum(Sales.total_amount)).filter(Sales.customer_id == c.id).scalar() or 0
        customer_sales.append({'name': c.name, 'total': total})
    customer_sales = sorted(customer_sales, key=lambda x: x['total'], reverse=True)[:5]
    
    inventory_low = Inventory.query.filter(Inventory.closing_stock < 20).all()
    
    sales_by_month = db.session.query(
        func.strftime('%Y-%m', Sales.invoice_date),
        func.sum(Sales.total_amount)
    ).group_by(func.strftime('%Y-%m', Sales.invoice_date)).all()
    
    salary_by_month = db.session.query(
        Payroll.month,
        func.sum(Payroll.net_salary)
    ).group_by(Payroll.month).all()
    
    total_expenses = db.session.query(func.sum(Transaction.debit)).filter(
        Transaction.entry_type == 'debit'
    ).scalar() or 0
    
    revenue_vs_expenses = [
        {'label': 'Revenue', 'value': monthly_sales},
        {'label': 'Expenses', 'value': total_expenses}
    ]
    
    return render_template('accountant_dashboard.html',
                         total_employees=total_employees,
                         total_customers=total_customers,
                         total_inventory=total_inventory,
                         monthly_sales=monthly_sales,
                         total_salary=total_salary,
                         recent_sales=recent_sales,
                         customer_sales=customer_sales,
                         inventory_low=inventory_low,
                         sales_by_month=sales_by_month,
                         salary_by_month=salary_by_month,
                         revenue_vs_expenses=revenue_vs_expenses)
```

- [ ] **Step 3: Modify index route to redirect accountant to accountant_dashboard**

Change `routes/dashboard.py:16-18` from:
```python
if session.get('role') == 'admin':
    return redirect(url_for('dashboard.admin_dashboard'))
```
To:
```python
if session.get('role') == 'admin':
    return redirect(url_for('dashboard.admin_dashboard'))
elif session.get('role') == 'accountant':
    return redirect(url_for('dashboard.accountant_dashboard'))
```

---

### Task 2: Create accountant_dashboard.html template

**Files:**
- Create: `templates/accountant_dashboard.html`

- [ ] **Step 1: Create accountant dashboard template with clean light theme**

```html
{% extends "base.html" %}
{% block title %}Accountant Dashboard{% endblock %}
{% block content %}
<style>
    .dashboard-container { max-width: 1400px; margin: 0 auto; padding: 20px; }
    .header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 30px; }
    .header h1 { color: #1e293b; margin: 0; font-size: 28px; }
    .user-info { color: #64748b; }
    .stats-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 20px; margin-bottom: 30px; }
    .stat-card { background: white; border-radius: 12px; padding: 24px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }
    .stat-card .label { color: #64748b; font-size: 14px; margin-bottom: 8px; }
    .stat-card .number { font-size: 32px; font-weight: 700; color: #1e293b; }
    .chart-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-bottom: 30px; }
    .chart-card { background: white; border-radius: 12px; padding: 24px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }
    .chart-card h3 { color: #1e293b; margin: 0 0 20px 0; font-size: 18px; }
    .alert-card { background: #fef2f2; border: 1px solid #fecaca; border-radius: 12px; padding: 20px; margin-bottom: 20px; }
    .alert-card h3 { color: #dc2626; margin: 0 0 10px 0; }
    .alert-card ul { margin: 0; padding-left: 20px; }
    .alert-card li { color: #991b1b; margin-bottom: 5px; }
    .recent-table { width: 100%; font-size: 14px; }
    .recent-table th { text-align: left; color: #64748b; padding: 10px 0; border-bottom: 1px solid #e2e8f0; }
    .recent-table td { padding: 12px 0; border-bottom: 1px solid #e2e8f0; }
    .btn { display: inline-block; padding: 10px 20px; background: #2563eb; color: white; text-decoration: none; border-radius: 8px; margin-right: 10px; }
    .btn:hover { background: #1d4ed8; }
    @media (max-width: 1024px) { .stats-grid { grid-template-columns: 1fr 1fr; } .chart-grid { grid-template-columns: 1fr; } }
    @media (max-width: 640px) { .stats-grid { grid-template-columns: 1fr; } }
</style>

<div class="dashboard-container">
    <div class="header">
        <h1>Accountant Dashboard</h1>
        <div class="user-info">Welcome, {{ session.username }}</div>
    </div>

    <div class="stats-grid">
        <div class="stat-card">
            <div class="label">Total Sales</div>
            <div class="number">₹{{ "%.0f"|format(monthly_sales) }}</div>
        </div>
        <div class="stat-card">
            <div class="label">Total Salary Paid</div>
            <div class="number">₹{{ "%.0f"|format(total_salary) }}</div>
        </div>
        <div class="stat-card">
            <div class="label">Employees</div>
            <div class="number">{{ total_employees }}</div>
        </div>
        <div class="stat-card">
            <div class="label">Customers</div>
            <div class="number">{{ total_customers }}</div>
        </div>
    </div>

    {% if inventory_low %}
    <div class="alert-card">
        <h3>Low Stock Alert!</h3>
        <ul>
        {% for item in inventory_low %}
            <li>{{ item.stone_type }} - {{ item.size }}: {{ item.closing_stock }} tons</li>
        {% endfor %}
        </ul>
    </div>
    {% endif %}

    <div class="chart-grid">
        <div class="chart-card">
            <h3>Sales Trends</h3>
            <canvas id="salesChart" height="200"></canvas>
        </div>
        <div class="chart-card">
            <h3>Salary Expenses by Month</h3>
            <canvas id="salaryChart" height="200"></canvas>
        </div>
    </div>

    <div class="chart-grid">
        <div class="chart-card">
            <h3>Revenue vs Expenses</h3>
            <canvas id="revenueChart" height="200"></canvas>
        </div>
        <div class="chart-card">
            <h3>Top Customers</h3>
            <canvas id="customerChart" height="200"></canvas>
        </div>
    </div>

    <div class="chart-card" style="margin-top: 20px;">
        <h3>Recent Sales</h3>
        <table class="recent-table">
            <tr><th>Date</th><th>Customer</th><th>Stone</th><th>Size</th><th>Amount</th></tr>
            {% for s in recent_sales %}
            <tr>
                <td>{{ s.invoice_date }}</td>
                <td>{{ s.customer_id }}</td>
                <td>{{ s.stone_type }}</td>
                <td>{{ s.size }}</td>
                <td>₹{{ "%.0f"|format(s.total_amount) }}</td>
            </tr>
            {% endfor %}
        </table>
    </div>

    <div style="margin-top: 30px;">
        <a href="{{ url_for('attendance.index') }}" class="btn">Attendance</a>
        <a href="{{ url_for('payroll.employees') }}" class="btn">Payroll</a>
        <a href="{{ url_for('sales.sales_list') }}" class="btn">Sales</a>
        <a href="{{ url_for('inventory.index') }}" class="btn">Inventory</a>
        <a href="{{ url_for('accounts.index') }}" class="btn">Accounts</a>
        <a href="{{ url_for('reports.index') }}" class="btn">Reports</a>
    </div>
</div>

<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<script>
const salesData = {{ sales_by_month|tojson }};
const salaryData = {{ salary_by_month|tojson }};
const customerData = {{ customer_sales|tojson }};
const revenueData = {{ revenue_vs_expenses|tojson }};

new Chart(document.getElementById('salesChart'), {
    type: 'line',
    data: {
        labels: salesData.map(x => x[0] || 'N/A'),
        datasets: [{
            label: 'Sales (₹)',
            data: salesData.map(x => x[1] || 0),
            borderColor: '#2563eb',
            backgroundColor: 'rgba(37, 99, 235, 0.1)',
            fill: true
        }]
    },
    options: { responsive: true, plugins: { legend: { display: false } }
});

new Chart(document.getElementById('salaryChart'), {
    type: 'bar',
    data: {
        labels: salaryData.map(x => x[0] || 'N/A'),
        datasets: [{
            label: 'Salary (₹)',
            data: salaryData.map(x => x[1] || 0),
            backgroundColor: '#10b981'
        }]
    },
    options: { responsive: true, plugins: { legend: { display: false } }
});

new Chart(document.getElementById('revenueChart'), {
    type: 'bar',
    data: {
        labels: revenueData.map(x => x.label),
        datasets: [{
            label: 'Amount (₹)',
            data: revenueData.map(x => x.value),
            backgroundColor: ['#10b981', '#ef4444']
        }]
    },
    options: { responsive: true, plugins: { legend: { display: false } }
});

new Chart(document.getElementById('customerChart'), {
    type: 'doughnut',
    data: {
        labels: customerData.map(x => x.name),
        datasets: [{
            data: customerData.map(x => x.total),
            backgroundColor: ['#2563eb', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6']
        }]
    },
    options: { responsive: true }
});
</script>
{% endblock %}
```

---

### Task 3: Test the implementation

**Files:**
- Test: Navigate to accountant dashboard

- [ ] **Step 1: Run the Flask app**

Run: `python app.py`

- [ ] **Step 2: Login as accountant and verify dashboard loads**

Navigate to: `http://localhost:5000/`

Login with accountant credentials.

- [ ] **Step 3: Verify charts render correctly**

Check that all 4 charts display: Sales Trends, Salary Expenses, Revenue vs Expenses, Top Customers

- [ ] **Step 4: Verify navigation buttons work**

Click each button (Attendance, Payroll, Sales, Inventory, Accounts, Reports)

---

### Summary

**Files Modified:**
- `routes/dashboard.py` - Added accountant_dashboard route, modified index redirect

**Files Created:**
- `templates/accountant_dashboard.html` - New clean light theme dashboard

**Features:**
- Sales trends chart (line)
- Salary expenses by month (bar)
- Revenue vs Expenses comparison (bar)
- Top customers (doughnut)
- Low stock alerts
- Quick stats cards
- Navigation buttons