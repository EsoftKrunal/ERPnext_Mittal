# Specification: Sales Dashboard (`sales-analytics`)

**Application:** `custom_dashbords`  
**Page Route:** `/app/sales-analytics`  
**Page Name:** `sales-analytics`  
**Module:** `Custom Dashbords`  

---

## 1. Overview & Purpose
The Sales Dashboard replicates the layout, KPI metrics, chart trends, and tables from Nidhi's `sales-analytics` dashboard while introducing robust multi-company isolation, row-level Frappe permission enforcement, and parameterized SQL queries.

---

## 2. Page & API Architecture

### 2.1 Desk Page Definition
- **DocType:** `Page`
- **Standard:** `Yes`
- **Roles:** `System Manager`, `Sales Manager`, `Sales User`, `Accounts User`
- **File Structure:**
  - `custom_dashbords/page/sales_analytics/sales_analytics.json`
  - `custom_dashbords/page/sales_analytics/sales_analytics.js`
  - `custom_dashbords/page/sales_analytics/sales_analytics.css`

### 2.2 Backend API Module
- **Module Path:** `custom_dashbords.api.sales_analytics`
- **Permission Guard:** `verify_read_permission("Sales Order")`, `verify_read_permission("Sales Invoice")`

---

## 3. Filters
The dashboard supports the following page-level filters:
1. `Company` (Mandatory/Default from User Defaults): Guarantees company data isolation.
2. `From Date` & `To Date` (Date range picker, defaults to Last 30 Days / Current Financial Year).
3. `Customer` (Link to Customer, filtered by Company if applicable).
4. `Customer Group` (Link to Customer Group).
5. `Territory` (Link to Territory).
6. `Item Group` (Link to Item Group).
7. `Sales Person` (Link to Sales Person).

---

## 4. Tabs & Visual Components

### Tab 1: Overview
- **KPI Cards:**
  1. `Total Revenue`: Sum of `base_grand_total` from submitted `Sales Invoice` (`docstatus = 1`).
  2. `Total Bookings`: Sum of `base_grand_total` from submitted `Sales Order` (`docstatus = 1`).
  3. `Total Orders`: Count of submitted `Sales Order`.
  4. `Average Order Value (AOV)`: `Total Bookings / Total Orders`.
  5. `MoM Revenue Growth`: Percentage change compared to the previous month.
- **Charts:**
  1. `Monthly Sales Trend`: Dual-line/bar chart comparing monthly Booked Sales (`Sales Order`) vs Invoiced Sales (`Sales Invoice`).
  2. `Revenue by Territory`: Bar chart of top territories by invoice total.
  3. `Revenue by Item Group`: Donut chart of revenue split across item groups.
- **Tables:**
  1. `Top 5 Customers by Revenue`: Customer name, Total revenue.
  2. `Top 5 Items by Revenue`: Item code, Item name, Total amount.
  3. `Recent Sales Orders Table`: Paginated list of recent orders with status and value.

### Tab 2: Fulfillment & Delivery Performance
- **KPI Cards:**
  1. `Pending Delivery`: Count of SOs where `per_delivered < 100%`.
  2. `Overdue Delivery`: Count of SOs where `delivery_date < CURDATE()` and `per_delivered < 100%`.
  3. `Value Stuck in Pipeline`: Value of un-delivered order quantities.
- **Charts:**
  1. `Delivery Performance Trend`: Monthly percentage of on-time deliveries.
  2. `Fulfillment Status Split`: Donut chart of Pending vs Partial vs Completed orders.
  3. `Ordered vs Delivered vs Invoiced`: Grouped bar chart by top items.
- **Table / Drilldown:**
  1. `Order-to-Delivery Drilldown`: SO -> Linked Delivery Notes -> Linked Sales Invoices.

### Tab 3: Receivables & Collection
- **KPI Cards:**
  1. `Total Outstanding`: Sum of `outstanding_amount` from submitted `Sales Invoice`.
  2. `Total Overdue`: Outstanding amount where `due_date < CURDATE()`.
  3. `Overdue Invoices Count`: Count of invoices with overdue balance.
- **Charts:**
  1. `Aging Buckets`: Bar chart split into `Current`, `0-30 Days`, `31-60 Days`, `61-90 Days`, `90+ Days`.
  2. `Collections Trend`: Monthly invoiced vs collected revenue.
- **Table:**
  1. `Receivables Ledger`: Top overdue invoices with aging bucket and paid amount.

### Tab 4: Customer Activity
- **KPI Cards:**
  1. `Active Customers` (Ordered in last 30 days).
  2. `At-Risk Customers` (Last order 31-90 days ago).
  3. `Dormant Customers` (Last order >90 days ago).
  4. `New Customers` (Created in filtered period).
- **Charts:**
  1. `Customer Activity Split`: Active vs At-Risk vs Dormant.
  2. `New Customer Trend`: Monthly new customer acquisition count.
- **Table:**
  1. `Customer Inactivity Table`: Days since last order, historical spend, and status.

---

## 5. Security & Bug Remediations
1. **Parameterized Queries:** All SQL string interpolations (e.g. `customer_group` in `get_chart_new_customer_trend`) are strictly replaced with parameterized `%(param)s`.
2. **Company Filter Enforcement:** In `_parse_filters`, `company` is parsed and applied as `t.company = %(company)s`.
3. **Permissions:** Evaluates user company permissions and row-level restrictions.
