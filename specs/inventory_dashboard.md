# Specification: Inventory Dashboard (`inventory-analytics`)

**Application:** `custom_dashbords`  
**Page Route:** `/app/inventory-analytics`  
**Page Name:** `inventory-analytics`  
**Module:** `Custom Dashbords`  

---

## 1. Overview & Scope
The Inventory Dashboard provides multi-tab visibility into stock balances, inventory valuation, stock movement velocity, batch shelf-life & expiry, and procurement reorder levels.

> [!NOTE]
> **Scope Confirmation:** In accordance with project instructions, the **ABC Analysis** tab is explicitly excluded from this dashboard.

---

## 2. Page & API Architecture

### 2.1 Desk Page Definition
- **DocType:** `Page`
- **Standard:** `Yes`
- **Roles:** `System Manager`, `Stock Manager`, `Stock User`, `Purchase Manager`, `Purchase User`
- **File Structure:**
  - `custom_dashbords/page/inventory_analytics/inventory_analytics.json`
  - `custom_dashbords/page/inventory_analytics/inventory_analytics.js`
  - `custom_dashbords/page/inventory_analytics/inventory_analytics.css`

### 2.2 Backend API Module
- **Module Path:** `custom_dashbords.api.inventory_analytics`
- **Primary Methods:**
  - `get_inventory_data(company, warehouse, item_group, from_date, to_date, tab)`
  - `get_item_analysis_data(company, warehouse, item_group, item_code, to_date)`
  - `get_material_fulfillment_data(company, warehouse, item_group, from_date, to_date)`
  - `get_daily_transactions(company, warehouse, item_code, from_date, to_date)`

---

## 3. Filters
1. `Company` (Mandatory, default to current company).
2. `Warehouse` (Group and leaf warehouse selection, resolved via `lft` and `rgt`).
3. `Item Group` (Group and leaf item group selection, resolved via `lft` and `rgt`).
4. `Item Code` (Dynamic link, active on Item Analysis / Reorder tab).
5. `Date Range` (`From Date` and `To Date`).

---

## 4. Tabs & Components

### Tab 1: Valuation & Balances (`valuation`)
- **KPIs:** Total Inventory Valuation, Total Stock Quantity, Stocked Items Count, Zero/Negative Stock Items Count.
- **Charts:** Top 10 Items by Valuation, Valuation by Warehouse (Donut).
- **Data Table:** Item Code, Item Name, Item Group, Warehouse, Balance Qty, Valuation Rate, Balance Value.

### Tab 2: Stock Velocity & Inactivity (`slow_moving`)
- **KPIs:** Active Inventory Value, Slow-Moving Value (>30 days inactive), Non-Moving Value (>90 days inactive).
- **Formulas:** `days_inactive = DATEDIFF(to_date, max(sle.posting_date))`.
- **Classification:**
  - `Active`: `days_inactive <= 30`
  - `Slow-Moving`: `days_inactive BETWEEN 31 AND 90`
  - `Non-Moving`: `days_inactive > 90`
- **Charts:** Velocity Split (Donut), Top 10 Inactive Items by Value.

### Tab 3: Shelf Life & Expiry Analytics (`expiry`)
- **Applies To:** Items with `has_expiry_date = 1` and `has_batch_no = 1`.
- **KPIs:** Expired Stock Value (`days_to_expiry < 0`), Near Expiry Value (`days_to_expiry <= 90`), Safe Stock Value.
- **v15/v16 Serial & Batch Bundle Compatibility:**
  Joins `Stock Ledger Entry` -> `Serial and Batch Bundle` -> `Serial and Batch Entry` -> `Batch`.
  *Crucial calculation:*
  `bal_qty = SUM(CASE WHEN sbl.is_outward = 1 THEN -sbl.qty ELSE sbl.qty END)`
- **Data Table:** Item Code, Item Name, Batch No, Warehouse, Expiry Date, Balance Qty, Balance Value, Status (`Expired`, `Expiring < 30 Days`, `Expiring < 90 Days`, `Safe`).

### Tab 4: Reorder Levels & Lead Time (`item_analysis`)
- **Data Sources:** `Item Reorder`, `Bin`, `Item`.
- **KPIs:** Total Reorder Deficit, Items Reaching Reorder Level, Average Lead Time.
- **Formulas:**
  - `deficit = max(0, warehouse_reorder_level - current_stock)`.
  - `status = "Reorder Required"` if `current_stock <= warehouse_reorder_level`.
- **Data Table:** Item Code, Warehouse, Current Qty, Reorder Level, Reorder Qty, Deficit, Urgency Ratio.

### Tab 5: Material Request Fulfillment (`fulfillment`)
- **Data Sources:** `Material Request`, `Material Request Item`, linked `Stock Entry`.
- **KPIs:** Open Material Requests, Overdue MRs, Fulfillment Percentage.
- **Charts:** MR Status Split (Pending / Partial / Transferred).

---

## 5. Security & Bug Remediations
1. **No Unsafe Test Endpoints:** Completely omit any test data generation or raw `frappe.db.delete` endpoints.
2. **Order of Variables:** Ensure `sle_ageing_conditions = []` is initialized before applying any filter checks.
3. **Correct Net Batch Qty:** Properly subtract outward transactions in `Serial and Batch Entry`.
4. **Table Aliasing:** Explicitly qualify columns with `sle.` to prevent ambiguous or invalid column queries.
