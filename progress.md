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
| **Phase 5: Automated Testing** | Unit, KPI, company isolation, permission & security tests | **IN PROGRESS** | `test_sales_analytics.py` implemented (5 integration test methods covering all 26 endpoints, company isolation, SQL injection prevention, permissions, and calculations). All 5 tests passed (1.066s). |
| **Phase 6: Independent Review** | Code quality, security, and final readiness review | **IN PROGRESS** | Sales Dashboard verified against SEC-01, SEC-03, SEC-04, BUG-03, BUG-04. |

---

## 2. Dashboard Implementation Status

| Dashboard | Route | Backend API | Desk Page | Tests | Status |
|---|---|---|---|---|---|
| **Sales Dashboard** | `/app/sales-analytics` | `custom_dashbords.api.sales_analytics` (26 endpoints) | `sales_analytics.json`, `sales_analytics.js`, `sales_analytics.css` | 5 integration tests passing | **COMPLETED & VERIFIED** |
| **Purchase Dashboard** | `/app/purchase-analytics` | Pending | Pending | Pending | PENDING |
| **Inventory Dashboard** | `/app/inventory-analytics` | Pending | Pending | Pending | PENDING |
| **Production Dashboard** | `/app/production-analytics` | Pending | Pending | Pending | PENDING |

---

## 3. Key Environment Findings & Resolutions

1. **Node.js Incompatibility Resolved:**
   - Problem: Node.js was defaulted to v18.20.8 via NVM, but Frappe v16 frontend build requires Node.js >=24.
   - Resolution: Switched NVM default to `v24.15.0` (`nvm alias default 24`), updated `~/.bashrc` and `~/.profile`. Verified `node -v` (24.15.0) and `yarn --version` (1.22.22).
2. **Bench Services Active:**
   - Port 8001: Web server (`frappe serve`)
   - Port 11001: Redis queue
   - Port 13001: Redis cache
   - Port 9001: SocketIO
   - Background: `bench watch` (esbuild), `bench worker`, `bench schedule`
3. **Target Site Verified:**
   - Site `mittal.local` is running on MariaDB database `_79f3bc3f0c70192e`.
   - Installed apps: `frappe` (16.18.3), `erpnext` (16.19.1), and `custom_dashbords` (0.0.1).
   - HTTP response: `HTTP/1.1 200 OK` from `http://127.0.0.1:8001` with `Host: mittal.local`.
