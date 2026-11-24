# Code & Security Review: `custom_dashbords`

**Document Purpose:** Track architectural review items, security remediations, and quality validations for the `custom_dashbords` application on Frappe/ERPNext v16.

---

## 1. Baseline Security & Code Quality Defect Checklist

Based on the audit of previous implementations (`frappe_dashboards` and `esoft_custom_bom`), the following defects are strictly prohibited in `custom_dashbords`:

| Defect ID | Severity | Description in Reference App | Required Remediation in `custom_dashbords` | Status |
|---|---|---|---|---|
| **SEC-01** | CRITICAL | SQL Injection in `get_chart_new_customer_trend` via unescaped string interpolation (`customer_group = '{f['customer_group']}'`). | Use parameterized queries: `cust_where.append("customer_group = %(customer_group)s")` and pass dict values. | Pending Implementation |
| **SEC-02** | CRITICAL | Unsafe DB wipe/test endpoint: `create_shelf_life_test_data` running raw `frappe.db.delete("Stock Ledger Entry")`. | Completely omit test deletion endpoints from production app. | Resolved (Omitted by design) |
| **SEC-03** | HIGH | Multi-company data leakage: `_parse_filters` in `sales_analytics.py` and `production_analytics.py` ignored `company`. | Include `company` in `_parse_filters` and enforce `t.company = %(company)s` on all transactional queries. | Pending Implementation |
| **SEC-04** | HIGH | Row-level permission bypass: Reference queries lacked `frappe.has_permission` checks on `Sales Order`, `Purchase Order`, `Stock Ledger Entry`, `Job Card`. | Add `verify_read_permission(doctype)` at entry of every whitelisted API method. | Pending Implementation |
| **BUG-01** | HIGH | `UnboundLocalError`: `sle_ageing_conditions.append(match_cond_sle)` referenced before definition. | Ensure all filter and condition lists are initialized before any appends or checks. | Pending Implementation |
| **BUG-02** | HIGH | Batch quantity inflation in v15/v16: `SUM(sbl.qty)` did not account for `sbl.is_outward = 1` in `Serial and Batch Entry`. | Use `SUM(CASE WHEN sbl.is_outward = 1 THEN -sbl.qty ELSE sbl.qty END)`. | Pending Implementation |
| **BUG-03** | MEDIUM | Hardcoded currency: Hardcoded `₹` or `USD` in frontend JS and backend fallbacks. | Dynamically fetch `default_currency` from `Company` or `Global Defaults`. | Pending Implementation |
| **BUG-04** | MEDIUM | Table alias SQL errors: `get_permission_condition(..., alias=None)` causing `None.field` syntax error. | Guard alias formatting in `permission_utils.py` so `None` alias does not prefix columns. | Pending Implementation |

---

## 2. Review Log

* **Phase 0 & 1 Review (2026-11-24):** Reference audit completed. All four reference dashboard source files inspected in `esoft_custom_bom`. Identified SQL injection in `sales_analytics.py`, missing company filters in Sales and Production, batch outward handling in Inventory, and `is_abstra()` fallback requirement.
