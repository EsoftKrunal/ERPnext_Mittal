# Code & Security Review: `custom_dashbords`

**Document Purpose:** Track architectural review items, security remediations, and quality validations for the `custom_dashbords` application on Frappe/ERPNext v16.

---

## 1. Baseline Security & Code Quality Defect Checklist

Based on the audit of previous implementations (`frappe_dashboards` and `esoft_custom_bom`), the following defects are strictly prohibited in `custom_dashbords`:

| Defect ID | Severity | Description in Reference App | Required Remediation in `custom_dashbords` | Status |
|---|---|---|---|---|
| **SEC-01** | CRITICAL | SQL Injection in `get_chart_new_customer_trend` via unescaped string interpolation (`customer_group = '{f['customer_group']}'`). | Use parameterized queries: `cust_where.append("customer_group = %(customer_group)s")` and pass dict values. | **RESOLVED (Sales Dashboard)** |
| **SEC-02** | CRITICAL | Unsafe DB wipe/test endpoint: `create_shelf_life_test_data` running raw `frappe.db.delete("Stock Ledger Entry")`. | Completely omit test deletion endpoints from production app. | **RESOLVED (Omitted by design)** |
| **SEC-03** | HIGH | Multi-company data leakage: `_parse_filters` in `sales_analytics.py` and `production_analytics.py` ignored `company`. | Include `company` in `_parse_filters` and enforce `t.company = %(company)s` on all transactional queries. | **RESOLVED (Sales Dashboard)** |
| **SEC-04** | HIGH | Row-level permission bypass: Reference queries lacked `frappe.has_permission` checks on `Sales Order`, `Purchase Order`, `Stock Ledger Entry`, `Job Card`. | Add `verify_read_permission(doctype)` at entry of every whitelisted API method. | **RESOLVED (Sales Dashboard)** |
| **BUG-01** | HIGH | `UnboundLocalError`: `sle_ageing_conditions.append(match_cond_sle)` referenced before definition. | Ensure all filter and condition lists are initialized before any appends or checks. | Pending (Inventory Dashboard) |
| **BUG-02** | HIGH | Batch quantity inflation in v15/v16: `SUM(sbl.qty)` did not account for `sbl.is_outward = 1` in `Serial and Batch Entry`. | Use `SUM(CASE WHEN sbl.is_outward = 1 THEN -sbl.qty ELSE sbl.qty END)`. | Pending (Inventory Dashboard) |
| **BUG-03** | MEDIUM | Hardcoded currency: Hardcoded `₹` or `USD` in frontend JS and backend fallbacks. | Dynamically fetch `default_currency` from `Company` or `Global Defaults`. | **RESOLVED (Sales Dashboard)** |
| **BUG-04** | MEDIUM | Table alias SQL errors: `get_permission_condition(..., alias=None)` causing `None.field` syntax error. | Guard alias formatting in `permission_utils.py` so `None` alias does not prefix columns. | **RESOLVED (permission_utils.py)** |

---

## 2. Review Log

* **Phase 0 & 1 Review (2026-11-24):** Reference audit completed. All four reference dashboard source files inspected in `esoft_custom_bom`. Identified SQL injection in `sales_analytics.py`, missing company filters in Sales and Production, batch outward handling in Inventory, and `is_abstra()` fallback requirement.
* **Phase 2 — Sales Dashboard Review (2026-11-24):**
  - Backend API (`custom_dashbords/api/sales_analytics.py`): All 26 endpoints implement `verify_read_permission`, company filtering via `_parse_filters` defaulting to `get_default_company()` ("e"), parameterized SQL queries without string concatenation.
  - Desk Page (`custom_dashbords/page/sales_analytics/`): Implemented `sales_analytics.json`, `sales_analytics.js`, `sales_analytics.css`. Added `Company` filter to filter bar with dynamic default, updated `API` prefix to `custom_dashbords.api.sales_analytics.`. Added `is_chart_empty` guards to prevent empty chart rendering exceptions.
  - Integration Test Suites (`test_sales_analytics.py` & `test_sales_dashboard_verification.py`): 8 integration tests covering all 26 endpoints, company isolation, multi-company restriction, SQL injection prevention, permission enforcement, role desk and API access, and transaction cleanup guarantee. Ran with `bench --site mittal.local run-tests --app custom_dashbords` -> 8 passed in 6.009s.

---

## 3. Sales Dashboard Verification & Audit Report

### 1. Company Security Audit — PASS
- **Multi-Company Isolation:** Verified across all 26 endpoints. If a user has User Permission restricted to Company A (e.g. `"e"`), requesting Company B (e.g. `"_Test_Mittal_Co_2"`) raises `frappe.PermissionError` via `verify_company_permission(company)`.
- **Query Filter Enforcement:** In `_build_conditions`, every transactional query joins or filters on `t.company = %(company)s` combined with Frappe's native `get_permission_condition("Company")`.
- **Test Evidence:** `test_company_security_multi_company_isolation` verified all 26 endpoints against cross-company leakage.

### 2. Browser & Desk Page Verification — READY FOR MANUAL REVIEW
- **Page Route:** `/app/sales-analytics` (Desk Page name: `sales-analytics`).
- **4 Tabs:** Overview, Fulfillment, Receivables, Customer Activity.
- **17 Charts:** All 17 charts configured with Frappe Charts (line, bar, donut) and guarded with `is_chart_empty()` to cleanly show `<div class="sa-empty">No data</div>` when data total is 0.
- **23 KPIs:** All KPIs load dynamically via Frappe AJAX calls with currency formatted according to the selected company.
- **Filters:** Company (defaults to `"e"`), From Date, To Date, Customer, Customer Group, Territory, Item Group, Sales Person.
- **Drilldown:** Sales Order -> Delivery Note -> Sales Invoice interactive drilldown implemented in Tab 2.
- **Status:** Automated script verified zero HTTP errors. Final visual verification designated for manual testing by user as requested.

### 3. Test Data Cleanup Audit — PASS
- **Cleanup Guarantee:** Tests in `test_sales_analytics.py` and `test_sales_dashboard_verification.py` record all generated documents (`Company`, `Customer`, `Item`, `Sales Order`, `Sales Invoice`, `User`, `User Permission`) in `self.cleanup_records` and cancel/delete them during `tearDown()`.
- **Database State Verified on `mittal.local`:**
  - `tabSales Order`: 0 records
  - `tabSales Invoice`: 0 records
  - `tabCustomer`: 0 test records
  - `tabItem`: 0 test records
  - `tabCompany`: 1 record (`"e"`, target site original)
  - `tabUser`: 0 test users
  - `tabUser Permission`: 0 test permissions
- **Test Evidence:** Direct MariaDB query confirmed zero residual test transactions.

### 4. Role & Access Control Audit — PASS
- **Desk Page Permissions:** `tabPage` configured with allowed roles:
  - `System Manager` (Allowed)
  - `Sales Manager` (Allowed)
  - `Sales User` (Allowed)
  - `Accounts User` (Allowed)
  - `Guest` (Blocked - Page inaccessible)
- **API Endpoint Protection:**
  - `Guest` requests to all endpoints immediately raise `frappe.PermissionError`.
  - Roles with `Sales Order` read permission can access sales overview, fulfillment, and customer activity.
  - Roles with `Sales Invoice` read permission can access sales overview, receivables, and customer activity.
- **Test Evidence:** `test_role_permissions_desk_and_api` passed.

### 5. Code Quality & Standards — PASS
- Parameterized SQL queries for all 26 endpoints; zero string interpolations.
- Zero dependencies on `esoft_custom_bom` or `frappe_dashboards`.
- Fully independent within `custom_dashbords`.
