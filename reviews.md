# Code & Security Review: `custom_dashbords`

**Document Purpose:** Track architectural review items, security remediations, and quality validations for the `custom_dashbords` application on Frappe/ERPNext v16.

---

## 1. Baseline Security & Code Quality Defect Checklist

Based on the audit of previous implementations (`frappe_dashboards` and `esoft_custom_bom`), the following defects are strictly prohibited and resolved in `custom_dashbords`:

| Defect ID | Severity | Description in Reference App | Required Remediation in `custom_dashbords` | Status |
|---|---|---|---|---|
| **SEC-01** | CRITICAL | SQL Injection in `get_chart_new_customer_trend` via unescaped string interpolation (`customer_group = '{f['customer_group']}'`). | Use parameterized queries: `cust_where.append("customer_group = %(customer_group)s")` and pass dict values. | **RESOLVED** |
| **SEC-02** | CRITICAL | Unsafe DB wipe/test endpoint: `create_shelf_life_test_data` running raw `frappe.db.delete("Stock Ledger Entry")`. | Completely omit test deletion endpoints from production app. | **RESOLVED** (Omitted by design) |
| **SEC-03** | HIGH | Multi-company data leakage: `_parse_filters` in `sales_analytics.py` and `production_analytics.py` ignored `company`. | Include `company` in `_parse_filters` and enforce `t.company = %(company)s` on all transactional queries. | **RESOLVED** |
| **SEC-04** | HIGH | Row-level permission bypass: Reference queries lacked `frappe.has_permission` checks on `Sales Order`, `Purchase Order`, `Stock Ledger Entry`, `Job Card`. | Add `verify_read_permission(doctype)` at entry of every whitelisted API method. | **RESOLVED** |
| **BUG-01** | HIGH | `UnboundLocalError`: `sle_ageing_conditions.append(match_cond_sle)` referenced before definition. | Ensure all filter and condition lists are initialized before any appends or checks. | **RESOLVED** |
| **BUG-02** | HIGH | Batch quantity inflation in v15/v16: `SUM(sbl.qty)` did not account for `sbl.is_outward = 1` in `Serial and Batch Entry`. | Use `SUM(CASE WHEN sbl.is_outward = 1 THEN -sbl.qty ELSE sbl.qty END)`. | **RESOLVED** |
| **BUG-03** | MEDIUM | Hardcoded currency: Hardcoded `₹` or `USD` in frontend JS and backend fallbacks. | Dynamically fetch `default_currency` from `Company` or `Global Defaults`. | **RESOLVED** |
| **BUG-04** | MEDIUM | Table alias SQL errors: `get_permission_condition(..., alias=None)` causing `None.field` syntax error. | Guard alias formatting in `permission_utils.py` so `None` alias does not prefix columns. | **RESOLVED** |

---

## 2. Review Log & Schema Adaptations

* **Phase 0 & 1 Review (2026-11-24):** Reference audit completed. All four reference dashboard source files inspected in `esoft_custom_bom`. Identified SQL injection in `sales_analytics.py`, missing company filters in Sales and Production, batch outward handling in Inventory, and `is_abstra()` fallback requirement.
* **Phase 2 — Sales Dashboard Review (2026-11-24):**
  - Backend API (`custom_dashbords/api/sales_analytics.py`): All 26 endpoints implement `verify_read_permission`, company filtering via `_parse_filters` defaulting to `get_default_company()` ("e"), parameterized SQL queries without string concatenation.
  - Desk Page (`custom_dashbords/page/sales_analytics/`): Implemented `sales_analytics.json`, `sales_analytics.js`, `sales_analytics.css`. Added `Company` filter to filter bar with dynamic default, updated `API` prefix to `custom_dashbords.api.sales_analytics.`. Added `is_chart_empty` guards to prevent empty chart rendering exceptions.
* **Phase 3 — Purchase Dashboard Review (2026-11-24):**
  - Backend API (`custom_dashbords/api/purchase_analytics.py`): Parameterized query on `tabPurchase Order` with status calculation, overdue tracking, bill status calculation, and strict company security.
  - Desk Page (`custom_dashbords/page/purchase_analytics/`): Clean UI with 7 KPI cards, Frappe Charts (Donut + Bar), Search and Supplier filters, dynamic Company filter, and paginated PO table with status pills.
* **Phase 4 — Inventory Dashboard Review (2026-11-24):**
  - Backend API (`custom_dashbords/api/inventory_analytics.py`): 4 whitelisted methods (`get_inventory_data`, `get_item_analysis_data`, `get_daily_transactions`, `get_material_fulfillment_data`). BUG-01 (variable ordering) and BUG-02 (net outward subtraction) resolved. Dangerous test endpoint (`create_shelf_life_test_data`) completely omitted. ABC Analysis completely excluded.
  - Desk Page (`custom_dashbords/page/inventory_analytics/`): 4 tabs (Overview, Stock Movements, Item Analysis, Material Fulfillment). Safe chart destruction and rendering.
* **Phase 5 — Production Dashboard Review (2026-11-24):**
  - Backend API (`custom_dashbords/api/production_analytics.py`): Native ERPNext v16 manufacturing methods using `Production Plan`, `Work Order`, and `Job Card`. No dependency on `Job Card Header` or `is_abstra()`. Company filtering applied.
  - Schema Compatibility Adaptations:
    - `tabProduction Plan`: Standard ERPNext v16 uses `to_delivery_date` / `to_date` instead of site-specific `expected_delivery_date`. Handled dynamically via `_plan_end_date_col()`.
    - `tabMaterial Request`: Joined through child table `tabMaterial Request Item` (`mri.production_plan = pp.name`) where standard ERPNext links the Production Plan.
    - `tabMaterial Request Plan Item`: Standard ERPNext field is `quantity` (instead of site-specific `required_qty`), resolved dynamically via `_mr_plan_item_qty_col()`.
  - Desk Page (`custom_dashbords/page/production_analytics/`): 4 tabs (Overview, Workstation Load, Lead Time & Delays, Production Plans & Orders).
  - Enhanced Feature — Production Plan Summary Report: Added dedicated `Plan Summary Report` tab in `production-analytics` with interactive plan switcher, real-time search, status filter pills, sub-assembly tree expansion/collapse, CSV export, and 6 summary KPI cards. Backed by whitelisted `get_production_plan_summary_report` with strict company isolation and multi-plan support.

---

## 3. Four Dashboards Verification & Audit Summary

### 1. Company Security Audit — ALL PASS
- **Multi-Company Isolation:** Verified across all 4 dashboards. If a user has User Permission restricted to Company A (e.g. `"e"`), requesting Company B (e.g. `"_Test_Inv_Co_2"`) raises `frappe.PermissionError` via `verify_company_permission(company)`.
- **Query Filter Enforcement:** Every transactional query joins or filters on company combined with Frappe's native `get_permission_condition("Company")`.

### 2. Browser & Desk Page Verification — READY FOR MANUAL REVIEW
- **Routes Registered:**
  - Sales: `/app/sales-analytics` (Desk Page name: `sales-analytics`)
  - Purchase: `/app/purchase-analytics` (Desk Page name: `purchase-analytics`)
  - Inventory: `/app/inventory-analytics` (Desk Page name: `inventory-analytics`)
  - Production: `/app/production-analytics` (Desk Page name: `production-analytics`)
- **Assets Built:** `bench build --app custom_dashbords` succeeded.
- **Chart Empty Guards:** All charts across all 4 dashboards handle empty data safely with `is_chart_empty()` to avoid SVG `NaN` exceptions.
- **Status:** Automated desk routes respond correctly with authentication redirect for guests. Ready for manual browser testing by user.

### 3. Test Data Cleanup Audit — ALL PASS
- **Cleanup Guarantee:** Tests in all test suites record all generated documents (`Company`, `Customer`, `Supplier`, `Item`, `Sales Order`, `Sales Invoice`, `Purchase Order`, `User`, `User Permission`) in `self.cleanup_records` and delete them during `tearDown()`.
- **Database State Verified on `mittal.local`:**
  - `tabSales Order`: 0 records
  - `tabSales Invoice`: 0 records
  - `tabPurchase Order`: 0 records
  - `tabStock Entry`: 0 records
  - `tabStock Ledger Entry`: 0 records
  - `tabProduction Plan`: 0 records
  - `tabWork Order`: 0 records
  - `tabJob Card`: 0 records
  - `tabCustomer`: 0 test records
  - `tabSupplier`: 0 test records
  - `tabItem`: 0 test records
  - `tabCompany`: 1 record (`"e"`, target site original)
  - `tabUser`: 0 test users
  - `tabUser Permission`: 0 test permissions

### 4. Integration Test Results — 21/21 PASS (100%)
- `TestPurchaseAnalytics`: 5/5 passed
- `TestSalesDashboardVerification`: 3/3 passed
- `TestInventoryAnalytics`: 4/4 passed
- `TestProductionAnalytics`: 4/4 passed
- `TestSalesAnalytics`: 5/5 passed
- **Total:** 21 passed in 27.8s. Zero errors, zero failures.
