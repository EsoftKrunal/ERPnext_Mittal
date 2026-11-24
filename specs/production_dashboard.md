# Specification: Production Dashboard (`production-analytics`)

**Application:** `custom_dashbords`  
**Page Route:** `/app/production-analytics`  
**Page Name:** `production-analytics`  
**Module:** `Custom Dashbords`  

---

## 1. Overview & Scope
The Production Dashboard provides end-to-end manufacturing oversight across Production Plans, Work Orders, Job Cards, Workstation capacity/load, and finished goods throughput.

---

## 2. Page & API Architecture

### 2.1 Desk Page Definition
- **DocType:** `Page`
- **Standard:** `Yes`
- **Roles:** `System Manager`, `Manufacturing Manager`, `Manufacturing User`, `Stock Manager`
- **File Structure:**
  - `custom_dashbords/page/production_analytics/production_analytics.json`
  - `custom_dashbords/page/production_analytics/production_analytics.js`
  - `custom_dashbords/page/production_analytics/production_analytics.css`

### 2.2 Backend API Module
- **Module Path:** `custom_dashbords.api.production_analytics`
- **Primary Methods:**
  - `get_production_plan_kpis(company, from_date, to_date, status, production_plan)`
  - `get_item_wise_planned_vs_produced(...)`
  - `get_chart_plan_status_distribution(...)`
  - `get_chart_production_trend(...)`
  - `get_job_card_kpis(company, from_date, to_date, workstation, status, production_plan)`
  - `get_chart_workstation_load(...)`
  - `get_chart_jobcard_status_distribution(...)`
  - `get_chart_jobcard_throughput(...)`
  - `get_workstation_utilization(...)`
  - `get_delayed_job_cards(...)`
  - `get_plan_workorder_jobcard_drilldown(...)`

---

## 3. Filters
1. `Company` (Mandatory, default to current company).
2. `From Date` & `To Date` (Date range).
3. `Production Plan` (Link to Production Plan).
4. `Workstation` (Link to Workstation).
5. `Status` (Work Order / Plan / Job Card status).

---

## 4. Visual Components & KPI Definitions

### 4.1 Production Plan Analytics
- **KPIs:**
  1. `Active Plans`: Distinct count of submitted `Production Plan` (`docstatus = 1`).
  2. `Planned Quantity`: Sum of `planned_qty` in `tabProduction Plan Item`.
  3. `Produced Quantity`: Sum of `produced_qty` in `tabProduction Plan Item`.
  4. `Completion Percentage`: `(produced_qty / planned_qty) * 100`.
  5. `Delayed Plans`: Count of plans marked 'Delayed'.
  6. `Open Material Requests`: Count of pending 'Manufacture' Material Requests.
- **Charts:**
  1. `Plan Status Distribution`: Donut chart of Draft, Submitted, In Process, Completed.
  2. `Monthly Production Output Trend`: Historical monthly produced quantity.
  3. `Planned vs Produced by Item`: Grouped horizontal bar chart for top items.

### 4.2 Job Card & Workstation Analytics
- **KPIs:**
  1. `Open Job Cards`: Count where `status = 'Open'`.
  2. `Work In Progress (WIP)`: Count where `status = 'Work In Progress'`.
  3. `On Hold`: Count where `status = 'On Hold'`.
  4. `Completed This Week`: Completed since start of current week.
  5. `Overdue Job Cards`: Uncompleted job cards where `wo.planned_end_date < today()`.
  6. `Average Completion Time (Hours)`: Average `TIMESTAMPDIFF(MINUTE, actual_start_date, actual_end_date) / 60`.
- **Charts:**
  1. `Workstation Load`: Total planned operation minutes queued per workstation.
  2. `Workstation Utilization`: Actual operating time vs available capacity.
  3. `Job Card Throughput`: Daily completed job card counts.
- **Drilldown:**
  1. `3-Tier Manufacturing Drilldown`: Production Plan -> Linked Work Orders -> Linked Job Cards (with status, operator, and workstation).

---

## 5. Security & Bug Remediations
1. **Multi-Company Isolation:** Add `company` to `_parse_filters` and enforce `pp.company = %(company)s` and `wo.company = %(company)s`.
2. **Permission Guard:** Checks `frappe.has_permission("Work Order", "read")` and `frappe.has_permission("Job Card", "read")`.
3. **Clean ERPNext Standard Fallback:** In the absence of third-party custom doctypes (e.g. `Job Card Header`), standard ERPNext `Work Order` and `Job Card` structures are seamlessly and authoritatively utilized.
