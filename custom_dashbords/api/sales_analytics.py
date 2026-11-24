# Copyright (c) 2026, Administrator and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import flt, cint, today, add_months, getdate, date_diff
from custom_dashbords.api.permission_utils import (
	verify_read_permission,
	verify_company_permission,
	get_permission_condition,
	get_default_company,
	get_company_currency,
)


# ---------------------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------------------

def _parse_filters(kwargs):
	company = kwargs.get("company")
	if not company:
		company = get_default_company()

	verify_company_permission(company)

	return {
		"company": company,
		"from_date": kwargs.get("from_date"),
		"to_date": kwargs.get("to_date"),
		"customer": kwargs.get("customer"),
		"customer_group": kwargs.get("customer_group"),
		"territory": kwargs.get("territory"),
		"item_group": kwargs.get("item_group"),
		"sales_person": kwargs.get("sales_person"),
	}


def _build_conditions(filters, doctype, date_field="transaction_date"):
	conds = ["t.docstatus = 1"]
	vals = {}

	if filters.get("company"):
		conds.append("t.company = %(company)s")
		vals["company"] = filters["company"]
	if filters.get("from_date"):
		conds.append(f"t.{date_field} >= %(from_date)s")
		vals["from_date"] = filters["from_date"]
	if filters.get("to_date"):
		conds.append(f"t.{date_field} <= %(to_date)s")
		vals["to_date"] = filters["to_date"]
	if filters.get("customer"):
		conds.append("t.customer = %(customer)s")
		vals["customer"] = filters["customer"]
	if filters.get("customer_group"):
		conds.append("t.customer IN (SELECT name FROM `tabCustomer` WHERE customer_group = %(customer_group)s)")
		vals["customer_group"] = filters["customer_group"]
	if filters.get("territory"):
		conds.append("t.territory = %(territory)s")
		vals["territory"] = filters["territory"]
	if filters.get("sales_person"):
		conds.append(
			f"EXISTS (SELECT 1 FROM `tabSales Team` st WHERE st.parent = t.name AND st.parenttype = '{doctype}' AND st.sales_person = %(sales_person)s)"
		)
		vals["sales_person"] = filters["sales_person"]
	if filters.get("item_group"):
		child_table = f"{doctype} Item"
		conds.append(
			f"EXISTS (SELECT 1 FROM `tab{child_table}` child WHERE child.parent = t.name AND child.item_group = %(item_group)s)"
		)
		vals["item_group"] = filters["item_group"]

	perm_cond = get_permission_condition(doctype, alias="t")
	if perm_cond:
		conds.append(f"({perm_cond})")

	return " AND ".join(conds), vals


# ---------------------------------------------------------------------------
# TAB 1 - Overview
# ---------------------------------------------------------------------------

def _can_read(doctype: str) -> bool:
	if frappe.session.user == "Administrator" or "System Manager" in frappe.get_roles():
		return True
	return frappe.has_permission(doctype, ptype="read")


@frappe.whitelist()
def get_overview_kpis(**kwargs):
	has_so = _can_read("Sales Order")
	has_si = _can_read("Sales Invoice")

	if not (has_so or has_si):
		frappe.throw(
			_("You do not have permission to access sales records."),
			frappe.PermissionError,
		)

	f = _parse_filters(kwargs)

	# Revenue & Invoices
	total_revenue = 0.0
	invoice_count = 0
	total_qty_sold = 0.0
	mom_growth = 0.0

	if has_si:
		si_where, si_vals = _build_conditions(f, "Sales Invoice", "posting_date")
		si_data = frappe.db.sql(f"""
			SELECT 
				SUM(t.base_grand_total) as total_revenue,
				COUNT(t.name) as invoice_count,
				SUM(t.total_qty) as total_qty_sold
			FROM `tabSales Invoice` t
			WHERE {si_where}
		""", si_vals, as_dict=True)

		lm_f = f.copy()
		lm_f["from_date"] = add_months(f.get("from_date") or today(), -1)
		lm_f["to_date"] = add_months(f.get("to_date") or today(), -1)
		lm_where, lm_vals = _build_conditions(lm_f, "Sales Invoice", "posting_date")
		lm_data = frappe.db.sql(f"""
			SELECT SUM(t.base_grand_total) as lm_revenue
			FROM `tabSales Invoice` t
			WHERE {lm_where}
		""", lm_vals, as_dict=True)

		total_revenue = flt(si_data[0].get("total_revenue")) if si_data else 0.0
		invoice_count = cint(si_data[0].get("invoice_count")) if si_data else 0
		total_qty_sold = flt(si_data[0].get("total_qty_sold")) if si_data else 0.0
		lm_revenue = flt(lm_data[0].get("lm_revenue")) if lm_data else 0.0
		mom_growth = ((total_revenue - lm_revenue) / lm_revenue * 100.0) if lm_revenue else 0.0

	# Bookings & Orders
	total_so_value = 0.0
	order_count = 0
	aov = 0.0

	if has_so:
		so_where, so_vals = _build_conditions(f, "Sales Order", "transaction_date")
		so_data = frappe.db.sql(f"""
			SELECT 
				SUM(t.base_grand_total) as total_so_value,
				COUNT(t.name) as order_count
			FROM `tabSales Order` t
			WHERE {so_where}
		""", so_vals, as_dict=True)

		order_count = cint(so_data[0].get("order_count")) if so_data else 0
		total_so_value = flt(so_data[0].get("total_so_value")) if so_data else 0.0
		aov = (total_so_value / order_count) if order_count else 0.0

	return {
		"total_revenue": total_revenue,
		"total_so_value": total_so_value,
		"total_qty_sold": total_qty_sold,
		"order_count": order_count,
		"invoice_count": invoice_count,
		"aov": aov,
		"mom_growth": mom_growth,
		"currency": get_company_currency(f.get("company")),
	}


@frappe.whitelist()
def get_chart_monthly_sales_trend(**kwargs):
	has_so = _can_read("Sales Order")
	has_si = _can_read("Sales Invoice")

	if not (has_so or has_si):
		frappe.throw(
			_("You do not have permission to access sales records."),
			frappe.PermissionError,
		)

	f = _parse_filters(kwargs)

	so_trend = []
	if has_so:
		so_where, so_vals = _build_conditions(f, "Sales Order", "transaction_date")
		so_trend = frappe.db.sql(f"""
			SELECT DATE_FORMAT(t.transaction_date, '%%Y-%%m') as month, SUM(t.base_grand_total) as value
			FROM `tabSales Order` t WHERE {so_where} GROUP BY month
		""", so_vals, as_dict=True)

	si_trend = []
	if has_si:
		si_where, si_vals = _build_conditions(f, "Sales Invoice", "posting_date")
		si_trend = frappe.db.sql(f"""
			SELECT DATE_FORMAT(t.posting_date, '%%Y-%%m') as month, SUM(t.base_grand_total) as value
			FROM `tabSales Invoice` t WHERE {si_where} GROUP BY month
		""", si_vals, as_dict=True)

	return {"booked": so_trend, "invoiced": si_trend}


@frappe.whitelist()
def get_top_items_by_revenue(**kwargs):
	has_si = _can_read("Sales Invoice")
	has_so = _can_read("Sales Order")

	if not (has_si or has_so):
		frappe.throw(
			_("You do not have permission to access sales records."),
			frappe.PermissionError,
		)

	f = _parse_filters(kwargs)
	if has_si:
		si_where, si_vals = _build_conditions(f, "Sales Invoice", "posting_date")
		return frappe.db.sql(f"""
			SELECT i.item_code, i.item_name, SUM(i.base_amount) as revenue
			FROM `tabSales Invoice Item` i
			JOIN `tabSales Invoice` t ON t.name = i.parent
			WHERE {si_where}
			GROUP BY i.item_code
			ORDER BY revenue DESC LIMIT 5
		""", si_vals, as_dict=True)
	else:
		so_where, so_vals = _build_conditions(f, "Sales Order", "transaction_date")
		return frappe.db.sql(f"""
			SELECT i.item_code, i.item_name, SUM(i.base_amount) as revenue
			FROM `tabSales Order Item` i
			JOIN `tabSales Order` t ON t.name = i.parent
			WHERE {so_where}
			GROUP BY i.item_code
			ORDER BY revenue DESC LIMIT 5
		""", so_vals, as_dict=True)


@frappe.whitelist()
def get_top_customers_by_revenue(**kwargs):
	has_si = _can_read("Sales Invoice")
	has_so = _can_read("Sales Order")

	if not (has_si or has_so):
		frappe.throw(
			_("You do not have permission to access sales records."),
			frappe.PermissionError,
		)

	f = _parse_filters(kwargs)
	if has_si:
		si_where, si_vals = _build_conditions(f, "Sales Invoice", "posting_date")
		return frappe.db.sql(f"""
			SELECT t.customer, t.customer_name, SUM(t.base_grand_total) as revenue
			FROM `tabSales Invoice` t
			WHERE {si_where}
			GROUP BY t.customer
			ORDER BY revenue DESC LIMIT 5
		""", si_vals, as_dict=True)
	else:
		so_where, so_vals = _build_conditions(f, "Sales Order", "transaction_date")
		return frappe.db.sql(f"""
			SELECT t.customer, t.customer_name, SUM(t.base_grand_total) as revenue
			FROM `tabSales Order` t
			WHERE {so_where}
			GROUP BY t.customer
			ORDER BY revenue DESC LIMIT 5
		""", so_vals, as_dict=True)


@frappe.whitelist()
def get_chart_revenue_by_territory(**kwargs):
	has_si = _can_read("Sales Invoice")
	has_so = _can_read("Sales Order")

	if not (has_si or has_so):
		frappe.throw(
			_("You do not have permission to access sales records."),
			frappe.PermissionError,
		)

	f = _parse_filters(kwargs)
	if has_si:
		si_where, si_vals = _build_conditions(f, "Sales Invoice", "posting_date")
		return frappe.db.sql(f"""
			SELECT t.territory, SUM(t.base_grand_total) as value
			FROM `tabSales Invoice` t
			WHERE {si_where}
			GROUP BY t.territory
			ORDER BY value DESC
		""", si_vals, as_dict=True)
	else:
		so_where, so_vals = _build_conditions(f, "Sales Order", "transaction_date")
		return frappe.db.sql(f"""
			SELECT t.territory, SUM(t.base_grand_total) as value
			FROM `tabSales Order` t
			WHERE {so_where}
			GROUP BY t.territory
			ORDER BY value DESC
		""", so_vals, as_dict=True)


@frappe.whitelist()
def get_chart_revenue_by_item_group(**kwargs):
	has_si = _can_read("Sales Invoice")
	has_so = _can_read("Sales Order")

	if not (has_si or has_so):
		frappe.throw(
			_("You do not have permission to access sales records."),
			frappe.PermissionError,
		)

	f = _parse_filters(kwargs)
	if has_si:
		si_where, si_vals = _build_conditions(f, "Sales Invoice", "posting_date")
		return frappe.db.sql(f"""
			SELECT i.item_group, SUM(i.base_amount) as value
			FROM `tabSales Invoice Item` i
			JOIN `tabSales Invoice` t ON t.name = i.parent
			WHERE {si_where}
			GROUP BY i.item_group
			ORDER BY value DESC
		""", si_vals, as_dict=True)
	else:
		so_where, so_vals = _build_conditions(f, "Sales Order", "transaction_date")
		return frappe.db.sql(f"""
			SELECT i.item_group, SUM(i.base_amount) as value
			FROM `tabSales Order Item` i
			JOIN `tabSales Order` t ON t.name = i.parent
			WHERE {so_where}
			GROUP BY i.item_group
			ORDER BY value DESC
		""", so_vals, as_dict=True)


@frappe.whitelist()
def get_overview_table(**kwargs):
	verify_read_permission("Sales Order")

	f = _parse_filters(kwargs)
	so_where, so_vals = _build_conditions(f, "Sales Order", "transaction_date")

	return frappe.db.sql(f"""
		SELECT 
			t.name as docname, t.transaction_date as date, t.customer, 
			t.territory, t.status, t.base_grand_total as amount, t.total_qty as qty,
			'Sales Order' as doctype
		FROM `tabSales Order` t
		WHERE {so_where}
		ORDER BY t.transaction_date DESC LIMIT 100
	""", so_vals, as_dict=True)


# ---------------------------------------------------------------------------
# TAB 2 - Fulfillment
# ---------------------------------------------------------------------------

@frappe.whitelist()
def get_fulfillment_kpis(**kwargs):
	verify_read_permission("Sales Order")

	f = _parse_filters(kwargs)
	so_where, so_vals = _build_conditions(f, "Sales Order", "transaction_date")

	data = frappe.db.sql(f"""
		SELECT 
			COALESCE(SUM(CASE WHEN t.per_delivered < 100 THEN 1 ELSE 0 END), 0) as pending_delivery,
			COALESCE(SUM(CASE WHEN t.per_delivered > 0 AND t.per_delivered < 100 THEN 1 ELSE 0 END), 0) as partial_delivery,
			COALESCE(SUM(CASE WHEN t.per_delivered = 100 THEN 1 ELSE 0 END), 0) as completed_delivery,
			COALESCE(SUM(CASE WHEN t.delivery_date < CURDATE() AND t.per_delivered < 100 THEN 1 ELSE 0 END), 0) as overdue_delivery,
			COALESCE(SUM(CASE WHEN t.per_billed < 100 THEN 1 ELSE 0 END), 0) as pending_invoicing,
			COALESCE(SUM((100 - t.per_delivered)/100.0 * t.base_grand_total), 0.0) as value_stuck
		FROM `tabSales Order` t
		WHERE {so_where} AND t.status NOT IN ('Cancelled', 'Closed')
	""", so_vals, as_dict=True)

	return data[0] if data else {
		"pending_delivery": 0,
		"partial_delivery": 0,
		"completed_delivery": 0,
		"overdue_delivery": 0,
		"pending_invoicing": 0,
		"value_stuck": 0.0,
	}


@frappe.whitelist()
def get_chart_fulfillment_status_split(**kwargs):
	verify_read_permission("Sales Order")

	f = _parse_filters(kwargs)
	so_where, so_vals = _build_conditions(f, "Sales Order", "transaction_date")

	return frappe.db.sql(f"""
		SELECT 
			CASE 
				WHEN t.per_delivered = 100 THEN 'Completed'
				WHEN t.per_delivered > 0 THEN 'Partial'
				ELSE 'Pending'
			END as status,
			COUNT(*) as value
		FROM `tabSales Order` t
		WHERE {so_where} AND t.status NOT IN ('Cancelled', 'Closed')
		GROUP BY status
	""", so_vals, as_dict=True)


@frappe.whitelist()
def get_chart_overdue_value_by_customer(**kwargs):
	verify_read_permission("Sales Order")

	f = _parse_filters(kwargs)
	so_where, so_vals = _build_conditions(f, "Sales Order", "transaction_date")

	return frappe.db.sql(f"""
		SELECT t.customer, SUM((100 - t.per_delivered)/100.0 * t.base_grand_total) as value
		FROM `tabSales Order` t
		WHERE {so_where} AND t.delivery_date < CURDATE() AND t.per_delivered < 100 AND t.status NOT IN ('Cancelled', 'Closed')
		GROUP BY t.customer
		ORDER BY value DESC LIMIT 10
	""", so_vals, as_dict=True)


@frappe.whitelist()
def get_chart_ordered_vs_delivered_vs_invoiced(**kwargs):
	verify_read_permission("Sales Order")

	f = _parse_filters(kwargs)
	so_where, so_vals = _build_conditions(f, "Sales Order", "transaction_date")

	return frappe.db.sql(f"""
		SELECT 
			i.item_code, 
			SUM(i.qty) as ordered, 
			SUM(i.delivered_qty) as delivered, 
			SUM(CASE WHEN i.rate > 0 THEN i.billed_amt / i.rate ELSE 0 END) as invoiced_approx
		FROM `tabSales Order Item` i
		JOIN `tabSales Order` t ON t.name = i.parent
		WHERE {so_where} AND t.status NOT IN ('Cancelled', 'Closed')
		GROUP BY i.item_code
		ORDER BY ordered DESC LIMIT 5
	""", so_vals, as_dict=True)


@frappe.whitelist()
def get_chart_delivery_performance_trend(**kwargs):
	verify_read_permission("Delivery Note")
	verify_read_permission("Sales Order")

	f = _parse_filters(kwargs)
	dn_where, dn_vals = _build_conditions(f, "Delivery Note", "posting_date")

	return frappe.db.sql(f"""
		SELECT 
			DATE_FORMAT(t.posting_date, '%%Y-%%m') as month,
			SUM(CASE WHEN t.posting_date <= so.delivery_date THEN 1 ELSE 0 END) * 100.0 / NULLIF(COUNT(*), 0) as on_time_pct
		FROM `tabDelivery Note Item` i
		JOIN `tabDelivery Note` t ON t.name = i.parent
		JOIN `tabSales Order` so ON so.name = i.against_sales_order
		WHERE {dn_where} AND i.against_sales_order IS NOT NULL
		GROUP BY month
		ORDER BY month
	""", dn_vals, as_dict=True)


@frappe.whitelist()
def get_fulfillment_table(**kwargs):
	verify_read_permission("Sales Order")

	f = _parse_filters(kwargs)
	so_where, so_vals = _build_conditions(f, "Sales Order", "transaction_date")

	return frappe.db.sql(f"""
		SELECT 
			t.name as so_no, i.item_code, i.qty as ordered_qty, 
			i.delivered_qty, 
			(CASE WHEN i.rate > 0 THEN i.billed_amt / i.rate ELSE 0 END) as invoiced_qty,
			t.delivery_date as expected_delivery_date, 
			DATEDIFF(CURDATE(), t.delivery_date) as days_overdue,
			t.status
		FROM `tabSales Order Item` i
		JOIN `tabSales Order` t ON t.name = i.parent
		WHERE {so_where} AND t.status NOT IN ('Cancelled', 'Closed')
		ORDER BY t.transaction_date DESC LIMIT 100
	""", so_vals, as_dict=True)


@frappe.whitelist()
def get_fulfillment_drilldown(**kwargs):
	verify_read_permission("Sales Order")
	verify_read_permission("Delivery Note")
	verify_read_permission("Sales Invoice")

	f = _parse_filters(kwargs)
	so_where, so_vals = _build_conditions(f, "Sales Order", "transaction_date")

	sos = frappe.db.sql(f"""
		SELECT t.name as so_no, t.customer, t.per_delivered, t.per_billed, t.status
		FROM `tabSales Order` t
		WHERE {so_where} AND t.status NOT IN ('Cancelled', 'Closed')
		ORDER BY t.transaction_date DESC LIMIT 50
	""", so_vals, as_dict=True)

	if not sos:
		return []

	so_names = [so["so_no"] for so in sos]

	dns = frappe.db.sql("""
		SELECT DISTINCT t.name as dn_no, i.against_sales_order as so_no, t.posting_date, t.status
		FROM `tabDelivery Note` t
		JOIN `tabDelivery Note Item` i ON i.parent = t.name
		WHERE i.against_sales_order IN %(so_names)s AND t.docstatus = 1
	""", {"so_names": so_names}, as_dict=True)

	sis = frappe.db.sql("""
		SELECT DISTINCT t.name as si_no, i.sales_order as so_no, t.posting_date, t.status, t.outstanding_amount
		FROM `tabSales Invoice` t
		JOIN `tabSales Invoice Item` i ON i.parent = t.name
		WHERE i.sales_order IN %(so_names)s AND t.docstatus = 1
	""", {"so_names": so_names}, as_dict=True)

	for so in sos:
		so["delivery_notes"] = [dn for dn in dns if dn["so_no"] == so["so_no"]]
		so["sales_invoices"] = [si for si in sis if si["so_no"] == so["so_no"]]

	return sos


# ---------------------------------------------------------------------------
# TAB 3 - Receivables
# ---------------------------------------------------------------------------

@frappe.whitelist()
def get_receivables_kpis(**kwargs):
	verify_read_permission("Sales Invoice")

	f = _parse_filters(kwargs)
	si_where, si_vals = _build_conditions(f, "Sales Invoice", "posting_date")

	data = frappe.db.sql(f"""
		SELECT 
			COALESCE(SUM(t.outstanding_amount), 0.0) as total_outstanding,
			COALESCE(SUM(CASE WHEN t.due_date < CURDATE() THEN t.outstanding_amount ELSE 0 END), 0.0) as total_overdue,
			COALESCE(SUM(CASE WHEN t.due_date >= CURDATE() THEN t.outstanding_amount ELSE 0 END), 0.0) as current_amount,
			COALESCE(SUM(CASE WHEN t.due_date < CURDATE() AND t.outstanding_amount > 0 THEN 1 ELSE 0 END), 0) as overdue_invoice_count,
			COALESCE(MAX(DATEDIFF(CURDATE(), t.due_date)), 0) as oldest_outstanding_days
		FROM `tabSales Invoice` t
		WHERE {si_where} AND t.outstanding_amount > 0
	""", si_vals, as_dict=True)

	return data[0] if data else {
		"total_outstanding": 0.0,
		"total_overdue": 0.0,
		"current_amount": 0.0,
		"overdue_invoice_count": 0,
		"oldest_outstanding_days": 0,
	}


@frappe.whitelist()
def get_chart_ageing_buckets(**kwargs):
	verify_read_permission("Sales Invoice")

	f = _parse_filters(kwargs)
	si_where, si_vals = _build_conditions(f, "Sales Invoice", "posting_date")

	return frappe.db.sql(f"""
		SELECT 
			CASE 
				WHEN t.due_date >= CURDATE() THEN 'Current'
				WHEN DATEDIFF(CURDATE(), t.due_date) BETWEEN 1 AND 30 THEN '0-30 Days'
				WHEN DATEDIFF(CURDATE(), t.due_date) BETWEEN 31 AND 60 THEN '31-60 Days'
				WHEN DATEDIFF(CURDATE(), t.due_date) BETWEEN 61 AND 90 THEN '61-90 Days'
				ELSE '90+ Days'
			END as bucket,
			SUM(t.outstanding_amount) as value
		FROM `tabSales Invoice` t
		WHERE {si_where} AND t.outstanding_amount > 0
		GROUP BY bucket
	""", si_vals, as_dict=True)


@frappe.whitelist()
def get_chart_outstanding_by_territory_or_group(**kwargs):
	verify_read_permission("Sales Invoice")

	f = _parse_filters(kwargs)
	si_where, si_vals = _build_conditions(f, "Sales Invoice", "posting_date")

	return frappe.db.sql(f"""
		SELECT t.territory as label, SUM(t.outstanding_amount) as value
		FROM `tabSales Invoice` t
		WHERE {si_where} AND t.outstanding_amount > 0
		GROUP BY t.territory
		ORDER BY value DESC
	""", si_vals, as_dict=True)


@frappe.whitelist()
def get_top_customers_by_outstanding(**kwargs):
	verify_read_permission("Sales Invoice")

	f = _parse_filters(kwargs)
	si_where, si_vals = _build_conditions(f, "Sales Invoice", "posting_date")

	return frappe.db.sql(f"""
		SELECT t.customer, SUM(t.outstanding_amount) as outstanding
		FROM `tabSales Invoice` t
		WHERE {si_where} AND t.outstanding_amount > 0
		GROUP BY t.customer
		ORDER BY outstanding DESC LIMIT 5
	""", si_vals, as_dict=True)


@frappe.whitelist()
def get_chart_collections_trend(**kwargs):
	verify_read_permission("Sales Invoice")

	f = _parse_filters(kwargs)
	si_where, si_vals = _build_conditions(f, "Sales Invoice", "posting_date")

	return frappe.db.sql(f"""
		SELECT 
			DATE_FORMAT(t.posting_date, '%%Y-%%m') as month,
			SUM(t.base_grand_total) as invoiced,
			SUM(t.base_grand_total - t.outstanding_amount) as collected
		FROM `tabSales Invoice` t
		WHERE {si_where}
		GROUP BY month
		ORDER BY month
	""", si_vals, as_dict=True)


@frappe.whitelist()
def get_receivables_table(**kwargs):
	verify_read_permission("Sales Invoice")

	f = _parse_filters(kwargs)
	si_where, si_vals = _build_conditions(f, "Sales Invoice", "posting_date")

	return frappe.db.sql(f"""
		SELECT 
			t.name as invoice_no, t.customer, t.posting_date as invoice_date, 
			t.due_date, t.base_grand_total as invoice_amount, 
			(t.base_grand_total - t.outstanding_amount) as paid_amount, 
			t.outstanding_amount as outstanding, 
			GREATEST(DATEDIFF(CURDATE(), t.due_date), 0) as days_overdue,
			CASE 
				WHEN t.due_date >= CURDATE() THEN 'Current'
				WHEN DATEDIFF(CURDATE(), t.due_date) BETWEEN 1 AND 30 THEN '0-30'
				WHEN DATEDIFF(CURDATE(), t.due_date) BETWEEN 31 AND 60 THEN '31-60'
				WHEN DATEDIFF(CURDATE(), t.due_date) BETWEEN 61 AND 90 THEN '61-90'
				ELSE '90+'
			END as ageing_bucket
		FROM `tabSales Invoice` t
		WHERE {si_where} AND t.outstanding_amount > 0
		ORDER BY days_overdue DESC LIMIT 100
	""", si_vals, as_dict=True)


# ---------------------------------------------------------------------------
# TAB 4 - Customer Activity
# ---------------------------------------------------------------------------

@frappe.whitelist()
def get_customer_activity_kpis(**kwargs):
	verify_read_permission("Sales Order")
	verify_read_permission("Customer")

	f = _parse_filters(kwargs)
	so_where, so_vals = _build_conditions(f, "Sales Order", "transaction_date")

	customer_activity = frappe.db.sql(f"""
		SELECT 
			t.customer, 
			MAX(t.transaction_date) as last_order_date,
			SUM(t.base_grand_total) as total_revenue
		FROM `tabSales Order` t
		WHERE {so_where}
		GROUP BY t.customer
	""", so_vals, as_dict=True)

	active_count = 0
	at_risk_count = 0
	dormant_count = 0
	active_rev = 0.0

	today_date = getdate(today())

	for row in customer_activity:
		days_since = date_diff(today_date, row["last_order_date"])
		if days_since <= 30:
			active_count += 1
			active_rev += flt(row["total_revenue"])
		elif days_since <= 90:
			at_risk_count += 1
		else:
			dormant_count += 1

	# Parameterized Customer query for new customer count
	cust_conds = ["1=1"]
	cust_vals = {}
	if f.get("customer_group"):
		cust_conds.append("customer_group = %(customer_group)s")
		cust_vals["customer_group"] = f["customer_group"]
	if f.get("territory"):
		cust_conds.append("territory = %(territory)s")
		cust_vals["territory"] = f["territory"]

	date_filter = f.get("from_date") or add_months(today(), -1)
	cust_conds.append("creation >= %(date_filter)s")
	cust_vals["date_filter"] = date_filter

	new_cust_query = frappe.db.sql(f"""
		SELECT COUNT(*) as cnt
		FROM `tabCustomer`
		WHERE {" AND ".join(cust_conds)}
	""", cust_vals, as_dict=True)

	return {
		"active_count": active_count,
		"at_risk_count": at_risk_count,
		"dormant_count": dormant_count,
		"active_revenue": active_rev,
		"new_customers": new_cust_query[0]["cnt"] if new_cust_query else 0,
	}


@frappe.whitelist()
def get_chart_customer_activity_split(**kwargs):
	kpis = get_customer_activity_kpis(**kwargs)
	return [
		{"status": "Active", "value": kpis["active_count"]},
		{"status": "At-Risk", "value": kpis["at_risk_count"]},
		{"status": "Dormant", "value": kpis["dormant_count"]},
	]


@frappe.whitelist()
def get_top_dormant_customers_by_value(**kwargs):
	verify_read_permission("Sales Order")

	f = _parse_filters(kwargs)
	so_where, so_vals = _build_conditions(f, "Sales Order", "transaction_date")

	return frappe.db.sql(f"""
		SELECT 
			t.customer, 
			MAX(t.transaction_date) as last_order_date,
			SUM(t.base_grand_total) as value
		FROM `tabSales Order` t
		WHERE {so_where}
		GROUP BY t.customer
		HAVING DATEDIFF(CURDATE(), last_order_date) > 90
		ORDER BY value DESC LIMIT 5
	""", so_vals, as_dict=True)


@frappe.whitelist()
def get_chart_dormant_value_by_customer_group(**kwargs):
	verify_read_permission("Sales Order")
	verify_read_permission("Customer")

	f = _parse_filters(kwargs)
	so_where, so_vals = _build_conditions(f, "Sales Order", "transaction_date")

	data = frappe.db.sql(f"""
		SELECT 
			c.customer_group as label, 
			SUM(t.base_grand_total) as value
		FROM `tabSales Order` t
		JOIN `tabCustomer` c ON c.name = t.customer
		WHERE {so_where}
		GROUP BY t.customer
		HAVING DATEDIFF(CURDATE(), MAX(t.transaction_date)) > 90
	""", so_vals, as_dict=True)

	aggr = {}
	for row in data:
		aggr[row["label"]] = aggr.get(row["label"], 0.0) + flt(row["value"])

	return [{"label": k, "value": v} for k, v in aggr.items()]


@frappe.whitelist()
def get_chart_new_customer_trend(**kwargs):
	verify_read_permission("Customer")

	f = _parse_filters(kwargs)
	cust_conds = ["1=1"]
	cust_vals = {}
	if f.get("customer_group"):
		cust_conds.append("customer_group = %(customer_group)s")
		cust_vals["customer_group"] = f["customer_group"]
	if f.get("territory"):
		cust_conds.append("territory = %(territory)s")
		cust_vals["territory"] = f["territory"]

	return frappe.db.sql(f"""
		SELECT DATE_FORMAT(creation, '%%Y-%%m') as month, COUNT(name) as value
		FROM `tabCustomer`
		WHERE {" AND ".join(cust_conds)}
		GROUP BY month
		ORDER BY month
	""", cust_vals, as_dict=True)


@frappe.whitelist()
def get_customer_activity_table(**kwargs):
	verify_read_permission("Sales Order")
	verify_read_permission("Customer")

	f = _parse_filters(kwargs)
	so_where, so_vals = _build_conditions(f, "Sales Order", "transaction_date")

	return frappe.db.sql(f"""
		SELECT 
			t.customer, 
			c.territory, 
			c.customer_group,
			MAX(t.transaction_date) as last_order_date,
			DATEDIFF(CURDATE(), MAX(t.transaction_date)) as days_since_last_order,
			SUM(t.base_grand_total) as historical_value,
			CASE 
				WHEN DATEDIFF(CURDATE(), MAX(t.transaction_date)) <= 30 THEN 'Active'
				WHEN DATEDIFF(CURDATE(), MAX(t.transaction_date)) <= 90 THEN 'At-Risk'
				ELSE 'Dormant'
			END as status
		FROM `tabSales Order` t
		JOIN `tabCustomer` c ON c.name = t.customer
		WHERE {so_where}
		GROUP BY t.customer
		ORDER BY days_since_last_order DESC LIMIT 100
	""", so_vals, as_dict=True)
