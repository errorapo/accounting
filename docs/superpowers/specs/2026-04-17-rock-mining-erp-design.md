# Rock Mining Business Accounting Tool - Design Spec

## Project Overview

**Project Name:** Rock Mining ERP
**Type:** Web-based ERP for quarry/construction stone business
**Users:** 2-5 users with passkey login

## Technology Stack

- **Backend:** Flask (Python)
- **Database:** SQLite (designed for future PostgreSQL migration)
- **ORM:** SQLAlchemy
- **Frontend:** HTML/CSS/JavaScript (vanilla)

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                 WEB INTERFACE                        │
│   Dashboard + Forms + Reports                       │
├─────────────────────────────────────────────────────┤
│                  FLASK API                         │
│   Routes + Business Logic                          │
├─────────────────────────────────────────────────────┤
│                SQLALCHEMY ORM                     │
├─────────────────────────────────────────────────────┤
│               SQLite Database                      │
└─────────────────────────────────────────────────────┘
```

## Module 1: Authentication

- Passkey login (simple shared password)
- Session-based authentication
- No role-based access (all users have full access)

## Module 2: Payroll

**Employee Types:** Drivers, Machine Operators, Manual Laborers, Supervisors, Office Staff, Security

**Salary Components:**
- Base Salary (fixed)
- Overtime Pay (hours × hourly rate × 1.5)
- Transport Allowance (fixed or per km)
- Food Allowance (fixed)
- Housing Allowance (fixed)
- Bonus/Incentive (performance-based)
- PF (provident fund: employee + employer contribution)
- Tax/TDS (monthly based on annual slabs)
- Insurance (fixed or %)

**Formulas:**
```
Gross = Base + Overtime + Allowances + Bonus
Deductions = PF + Tax + Insurance
Net = Gross - Deductions
```

## Module 3: Inventory

**Stone Types:** Granite, Limestone, Marble, Sandstone, Slate

**Sizes:** 5mm, 10mm, 20mm, 40mm, 65mm

**Tracking:**
```
Closing Stock = Opening + Purchases - Sales
Unit: Per ton
```

## Module 4: Sales

- Customer management
- Orders/Invoices
- Track by stone type and size
- Link to inventory and accounts

## Module 5: Accounts (Double-Entry)

**Account Types:**
- Assets: Cash, Bank, Equipment, Stock
- Liabilities: Loans, Creditors, GST Payable
- Capital: Owner Investment, Retained Earnings
- Income: Sales Revenue, Other Income
- Expenses: Salary, Transport, Material, Rent

**Core Equation:** Debit = Credit (every transaction must balance)

**Formula:** Assets = Liabilities + Capital

## Module 6: Reports

- Trial Balance
- Profit & Loss Statement
- Balance Sheet
- GST Summary

## Module 7: Tax

- GST: Input (purchases) - Output (sales) = Payable/Receivable
- TDS: Monthly = Annual Tax / 12

## Data Model

### Employees Table
- id, name, type, base_salary, hourly_rate, pf_rate, created_at

### Inventory Table
- id, stone_type, size, opening_stock, purchases, sales, closing_stock, updated_at

### Transactions Table
- id, date, description, account_id, debit, credit, entry_type

### Accounts Table
- id, name, type (asset/liability/capital/income/expense)

### Sales Table
- id, date, customer, stone_type, size, quantity, rate, amount

## Acceptance Criteria

1. Users can log in with passkey
2. Add/Edit/Delete employees with salary components
3. Calculate monthly payroll with all deductions
4. Track inventory by stone type and size
5. Record sales and link to inventory/accounts
6. Double-entry ledger records every transaction
7. Generate Trial Balance, P&L, Balance Sheet
8. Calculate GST and TDS
9. All reports can be viewed and printed

## Future Considerations

- Cloud database migration (PostgreSQL)
- Multi-user with roles
- Customer portal
- API for mobile app