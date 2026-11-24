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
  - Desk Page (`custom_dashbords/page/sales_analytics/`): Implemented `sales_analytics.json`, `sales_analytics.js`, `sales_analytics.css`. Added `Company` filter to filter bar with dynamic default, updated `API` prefix to `custom_dashbords.api.sales_analytics.`.
  - Integration Test Suite (`custom_dashbords/tests/test_sales_analytics.py`): 5 integration tests covering all 26 endpoints, company isolation, SQL injection prevention, permission enforcement, and KPI calculations. Ran with `bench --site mittal.local run-tests --app custom_dashbords` -> 5 passed in 1.066s.
  - Browser/Desk verification: `curl -s -L -w "%{http_code}\n" -H "Host: mittal.local" http://127.0.0.1:8001/app/sales-analytics` returns HTTP 200 OK. Page record exists in `tabPage` with roles `System Manager`, `Sales Manager`, `Sales User`, `Accounts User`.
