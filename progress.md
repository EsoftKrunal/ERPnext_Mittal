# Project Progress: `custom_dashbords` for Mittal ERPNext

**Project:** Custom Dashboards App (`custom_dashbords`)  
**Target Site:** `mittal.local` (Frappe v16.18.3, ERPNext v16.19.1, Python 3.14.5)  
**Reference Site:** `nidhicookware.local` (App: `esoft_custom_bom`)  
**Bench:** `/home/varun/frappe/frappe-bench-v16`  

---

## 1. Phase Tracker

| Phase | Description | Status | Evidence / Notes |
|---|---|---|---|
| **Phase 0: Environment Setup** | Fix Node.js >=24 requirement, verify services, verify `mittal.local` Desk | **COMPLETED** | Node v24.15.0 set as NVM default; HTTP 200 on `mittal.local:8001`; all 5 bench services running. |
| **Phase 1: App Creation & Install** | Create `custom_dashbords`, declare `required_apps`, install on site | **COMPLETED** | `bench new-app` succeeded; installed on `mittal.local`; listed in `bench --site mittal.local list-apps`. |
| **Phase 2: Reference Investigation** | Audit `esoft_custom_bom` 4 dashboards, formulas, queries, and permissions | **COMPLETED** | Re-audited `sales_analytics`, `purchase_analytics`, `inventory_analytics`, `production_analytics`. |
| **Phase 3: Specifications & Planning** | Author formal specs in `specs/` for all 4 dashboards | **COMPLETED** | Authored `specs/sales_dashboard.md`, `specs/purchase_dashboard.md`, `specs/inventory_dashboard.md`, `specs/production_dashboard.md`. |
| **Phase 4: Dashboard Implementation** | Implement clean, parameterized pages & APIs | **IN PROGRESS** | **Sales Dashboard (`sales-analytics`) COMPLETED.** Implemented `api/permission_utils.py`, `api/sales_analytics.py` (26 endpoints), Desk Page `sales-analytics` (JSON, JS, CSS). Built assets and synced page. |
| **Phase 5: Automated Testing** | Unit, KPI, company isolation, permission & security tests | **IN PROGRESS** | 8 integration tests passing (5 in `test_sales_analytics.py`, 3 in `test_sales_dashboard_verification.py`). Total runtime 6.009s. |
| **Phase 6: Independent Review** | Code quality, security, and final readiness review | **IN PROGRESS** | Sales Dashboard verified against SEC-01, SEC-03, SEC-04, BUG-03, BUG-04. Browser UI verification ready for manual inspection. |

---

## 2. Dashboard Implementation Status

| Dashboard | Route | Backend API | Desk Page | Tests | Status |
|---|---|---|---|---|---|
| **Sales Dashboard** | `/app/sales-analytics` | `custom_dashbords.api.sales_analytics` (26 endpoints) | `sales_analytics.json`, `sales_analytics.js`, `sales_analytics.css` | 8 integration tests passing (100%) | **READY FOR USER MANUAL VERIFICATION** |
| **Purchase Dashboard** | `/app/purchase-analytics` | Pending | Pending | Pending | PENDING APPROVAL |
| **Inventory Dashboard** | `/app/inventory-analytics` | Pending | Pending | Pending | PENDING |
| **Production Dashboard** | `/app/production-analytics` | Pending | Pending | Pending | PENDING |

---

## 3. Database State Verification (`mittal.local`)

- **Sales Order:** 0 records
- **Sales Invoice:** 0 records
- **Test Items / Customers:** 0 records
- **Company:** 1 original record (`"e"`)
- **Residual Test Users / Permissions:** 0 records
