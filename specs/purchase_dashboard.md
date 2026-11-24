# Specification: Purchase Dashboard (`purchase-analytics`)

**Application:** `custom_dashbords`  
**Page Route:** `/app/purchase-analytics`  
**Page Name:** `purchase-analytics`  
**Module:** `Custom Dashbords`  

---

## 1. Overview & Purpose
The Purchase Dashboard provides real-time visibility into open Purchase Orders, overdue supplier deliveries, pending billed quantities, and purchasing aging profile.

---

## 2. Page & API Architecture

### 2.1 Desk Page Definition
- **DocType:** `Page`
- **Standard:** `Yes`
- **Roles:** `System Manager`, `Purchase Manager`, `Purchase User`, `Stock Manager`, `Stock User`
- **File Structure:**
  - `custom_dashbords/page/purchase_analytics/purchase_analytics.json`
  - `custom_dashbords/page/purchase_analytics/purchase_analytics.js`
  - `custom_dashbords/page/purchase_analytics/purchase_analytics.css`

### 2.2 Backend API Module
- **Module Path:** `custom_dashbords.api.purchase_analytics` (aliased or directly callable as `custom_dashbords.api.purchase_analytics.get_po_data`)
- **Permission Guard:** `verify_read_permission("Purchase Order")`, `verify_read_permission("Purchase Invoice")`

---

## 3. Filters
1. `Company` (Link to Company, default to user default).
2. `Supplier` (Link to Supplier).
3. `Item Code` (Link to Item).
4. `Status Filter` (Select: All, Pending Only, Overdue Only).
5. `From Date` & `To Date` (Date range filter applied against PO Schedule Date `poi.schedule_date`).

---

## 4. Visual Components & KPI Definitions

### 4.1 KPI Cards
1. `Total Open POs`: Distinct count of submitted Purchase Orders where `qty > received_qty`.
2. `Total Outstanding Qty`: Sum of `(poi.qty - poi.received_qty)`.
3. `Total Outstanding Value`: Sum of `((poi.qty - poi.received_qty) * poi.rate)`.
4. `Total Pending Bill Value`: Sum of `max(0, poi.qty - billed_qty) * poi.rate`.
5. `Overdue Deliveries`: Count of PO line items where `schedule_date < today()` or PO age > 45 days.

### 4.2 Data Processing & Formulas
- **Ageing Days:** `DATEDIFF(today(), po.transaction_date)`
- **Is Overdue:** `1` if `schedule_date < today()` or `ageing_days > 45`, else `0`.
- **Billed Qty:** Correlated subquery on `tabPurchase Invoice Item` where `pii.po_detail = poi.name AND pi.docstatus = 1`.
- **Pending Bill Qty:** `max(0, poi.qty - billed_qty)`.
- **Pending Bill Value:** `pending_billed_qty * poi.rate`.

### 4.3 Interactive Data Table
Interactive table displaying:
- PO Number (Link to Purchase Order)
- PO Date & Schedule Date
- Supplier Name
- Item Code & Item Name
- Ordered Qty, Received Qty, Outstanding Qty
- Rate & Amount
- Billed Qty & Pending Bill Value
- Ageing Days & Status badge (Pending / Overdue)

---

## 5. Security & Bug Remediations
1. **Dynamic Currency:** Dynamically resolves base currency from `Company` or `Global Defaults`.
2. **Permission Guard:** Checks `frappe.has_permission("Purchase Order", "read")` before executing query.
3. **Company Restriction:** Filters `po.company = %(company)s` and respects User Permissions.
