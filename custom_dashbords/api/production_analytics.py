# Copyright (c) 2026, Administrator and contributors
# For license information, please see license.txt
# Production Analytics Dashboard — Clean Native ERPNext v16 Manufacturing APIs

import frappe
from frappe import _
from frappe.utils import flt, cint, getdate, today, date_diff, nowdate
from custom_dashbords.api.permission_utils import (
	verify_read_permission,
	verify_company_permission,
	get_permission_condition,
	get_default_company,
	get_company_currency,
)


def _verify_production_permission(company=None):
	"""Enforce read permission on production doctypes and company isolation."""
	if frappe.session.user == "Guest":
		frappe.throw(_("Authentication required"), frappe.PermissionError)

	if frappe.session.user != "Administrator" and "System Manager" not in frappe.get_roles():
		has_perm = (
			frappe.has_permission("Work Order", "read")
			or frappe.has_permission("Production Plan", "read")
			or frappe.has_permission("Job Card", "read")
			or frappe.has_permission("Stock Ledger Entry", "read")
		)
		if not has_perm:
			frappe.throw(_("Permission denied for Production Analytics"), frappe.PermissionError)

	if company:
		verify_company_permission(company)


def _parse_filters(kwargs):
	company = kwargs.get("company")
	if not company:
		company = get_default_company()
	return {
		"company": company,
		"from_date": kwargs.get("from_date"),
		"to_date": kwargs.get("to_date"),
		"warehouse": kwargs.get("warehouse"),
		"workstation": kwargs.get("workstation"),
		"status": kwargs.get("status"),
		"production_plan": kwargs.get("production_plan"),
	}


def _plan_end_date_col():
	if frappe.db.has_column("Production Plan", "expected_delivery_date"):
		return "pp.expected_delivery_date"
	return "COALESCE(pp.to_delivery_date, pp.to_date)"


def _mr_join_clause():
	if frappe.db.has_column("Material Request", "production_plan"):
		return """
			INNER JOIN `tabMaterial Request` mr
				ON mr.production_plan = pp.name AND mr.docstatus < 2
		"""
	return """
		INNER JOIN `tabMaterial Request Item` mri
			ON mri.production_plan = pp.name
		INNER JOIN `tabMaterial Request` mr
			ON mr.name = mri.parent AND mr.docstatus < 2
	"""


def _mr_plan_item_qty_col():
	if frappe.db.has_column("Material Request Plan Item", "required_qty"):
		return "mri.required_qty"
	return "mri.quantity"


def _plan_conditions(filters):
	conds = ["pp.docstatus = 1"]
	vals = {}
	if filters.get("company"):
		conds.append("pp.company = %(company)s")
		vals["company"] = filters["company"]

	perm_cond = get_permission_condition("Production Plan", "pp")
	if perm_cond:
		conds.append(perm_cond)

	if filters.get("from_date"):
		conds.append("pp.posting_date >= %(from_date)s")
		vals["from_date"] = filters["from_date"]
	if filters.get("to_date"):
		conds.append("pp.posting_date <= %(to_date)s")
		vals["to_date"] = filters["to_date"]
	if filters.get("status"):
		conds.append("pp.status = %(pp_status)s")
		vals["pp_status"] = filters["status"]
	if filters.get("production_plan"):
		conds.append("pp.name = %(production_plan)s")
		vals["production_plan"] = filters["production_plan"]
	return " AND ".join(conds), vals


def _jc_conditions(filters):
	conds = ["jc.docstatus < 2"]
	vals = {}
	if filters.get("company"):
		conds.append("(jc.company = %(company)s OR wo.company = %(company)s)")
		vals["company"] = filters["company"]

	perm_cond = get_permission_condition("Job Card", "jc")
	if perm_cond:
		conds.append(perm_cond)

	if filters.get("from_date"):
		conds.append("DATE(jc.creation) >= %(from_date)s")
		vals["from_date"] = filters["from_date"]
	if filters.get("to_date"):
		conds.append("DATE(jc.creation) <= %(to_date)s")
		vals["to_date"] = filters["to_date"]
	if filters.get("workstation"):
		conds.append("jc.workstation = %(workstation)s")
		vals["workstation"] = filters["workstation"]
	if filters.get("status"):
		conds.append("jc.status = %(jc_status)s")
		vals["jc_status"] = filters["status"]
	if filters.get("production_plan"):
		conds.append("wo.production_plan = %(production_plan)s")
		vals["production_plan"] = filters["production_plan"]
	return " AND ".join(conds), vals


# ---------------------------------------------------------------------------
# 1. Production Plan KPIs
# ---------------------------------------------------------------------------

@frappe.whitelist()
def get_production_plan_kpis(**kwargs):
	f = _parse_filters(kwargs)
	_verify_production_permission(f["company"])
	where, vals = _plan_conditions(f)

	row = frappe.db.sql(f"""
		SELECT
			COUNT(DISTINCT pp.name) AS active_plans,
			SUM(poi.planned_qty) AS planned_qty,
			SUM(poi.produced_qty) AS produced_qty,
			SUM(CASE WHEN pp.status = 'Delayed' THEN 1 ELSE 0 END) AS delayed_plans
		FROM `tabProduction Plan` pp
		LEFT JOIN `tabProduction Plan Item` poi ON poi.parent = pp.name
		WHERE {where}
	""", vals, as_dict=True)

	kpi = row[0] if row else {}
	planned = flt(kpi.get("planned_qty"))
	produced = flt(kpi.get("produced_qty"))
	pct = round((produced / planned * 100), 2) if planned else 0.0

	mr_cond = ""
	if f.get("company"):
		mr_cond += " AND mr.company = %(company)s"
	if f.get("from_date"):
		mr_cond += " AND mr.transaction_date >= %(from_date)s"
	if f.get("to_date"):
		mr_cond += " AND mr.transaction_date <= %(to_date)s"

	open_mr = frappe.db.sql(f"""
		SELECT COUNT(DISTINCT mr.name) AS cnt
		FROM `tabMaterial Request` mr
		WHERE mr.docstatus = 1 AND mr.material_request_type = 'Manufacture'
		  AND mr.status NOT IN ('Stopped','Cancelled','Transferred') {mr_cond}
	""", vals, as_dict=True)

	return {
		"active_plans": cint(kpi.get("active_plans")),
		"planned_qty": planned,
		"produced_qty": produced,
		"completion_pct": pct,
		"delayed_plans": cint(kpi.get("delayed_plans")),
		"open_mrs": cint(open_mr[0].get("cnt") if open_mr else 0),
	}


# ---------------------------------------------------------------------------
# 2. Job Card KPIs
# ---------------------------------------------------------------------------

@frappe.whitelist()
def get_job_card_kpis(**kwargs):
	f = _parse_filters(kwargs)
	_verify_production_permission(f["company"])
	where, vals = _jc_conditions(f)

	week_start = frappe.utils.get_first_day_of_week(today())
	vals["week_start"] = week_start
	vals["today"] = today()

	rows = frappe.db.sql(f"""
		SELECT
			SUM(CASE WHEN jc.status = 'Open' THEN 1 ELSE 0 END) AS open_count,
			SUM(CASE WHEN jc.status = 'Work In Progress' THEN 1 ELSE 0 END) AS wip_count,
			SUM(CASE WHEN jc.status = 'On Hold' THEN 1 ELSE 0 END) AS on_hold_count,
			SUM(CASE WHEN jc.status = 'Completed' AND DATE(jc.modified) >= %(week_start)s THEN 1 ELSE 0 END) AS completed_this_week,
			SUM(CASE WHEN jc.status != 'Completed' AND wo.planned_end_date < %(today)s THEN 1 ELSE 0 END) AS overdue_count,
			AVG(TIMESTAMPDIFF(MINUTE, jc.actual_start_date, jc.actual_end_date)) AS avg_minutes
		FROM `tabJob Card` jc
		LEFT JOIN `tabWork Order` wo ON wo.name = jc.work_order
		WHERE {where}
	""", vals, as_dict=True)

	r = rows[0] if rows else {}
	avg_min = flt(r.get("avg_minutes"))
	avg_hrs = round(avg_min / 60, 2) if avg_min else 0.0

	return {
		"open": cint(r.get("open_count")),
		"work_in_progress": cint(r.get("wip_count")),
		"on_hold": cint(r.get("on_hold_count")),
		"completed_this_week": cint(r.get("completed_this_week")),
		"overdue": cint(r.get("overdue_count")),
		"avg_completion_hrs": avg_hrs,
	}


# ---------------------------------------------------------------------------
# 3. Item-wise Planned vs Produced
# ---------------------------------------------------------------------------

@frappe.whitelist()
def get_item_wise_planned_vs_produced(**kwargs):
	f = _parse_filters(kwargs)
	_verify_production_permission(f["company"])
	where, vals = _plan_conditions(f)

	data = frappe.db.sql(f"""
		SELECT
			poi.item_code,
			i.item_name,
			SUM(poi.planned_qty) AS planned_qty,
			SUM(poi.produced_qty) AS produced_qty
		FROM `tabProduction Plan` pp
		INNER JOIN `tabProduction Plan Item` poi ON poi.parent = pp.name
		LEFT JOIN `tabItem` i ON i.name = poi.item_code
		WHERE {where}
		GROUP BY poi.item_code, i.item_name
		ORDER BY planned_qty DESC
		LIMIT 20
	""", vals, as_dict=True)

	for r in data:
		p = flt(r.get("planned_qty"))
		r["completion_pct"] = round(flt(r.get("produced_qty")) / p * 100, 2) if p else 0.0

	return data


# ---------------------------------------------------------------------------
# 4. Plan Status Distribution (Donut Chart)
# ---------------------------------------------------------------------------

@frappe.whitelist()
def get_chart_plan_status_distribution(**kwargs):
	f = _parse_filters(kwargs)
	_verify_production_permission(f["company"])
	where, vals = _plan_conditions(f)

	return frappe.db.sql(f"""
		SELECT pp.status, COUNT(pp.name) AS count
		FROM `tabProduction Plan` pp
		WHERE {where}
		GROUP BY pp.status
		ORDER BY count DESC
	""", vals, as_dict=True)


# ---------------------------------------------------------------------------
# 5. Production Trend (Monthly Line Chart)
# ---------------------------------------------------------------------------

@frappe.whitelist()
def get_chart_production_trend(**kwargs):
	f = _parse_filters(kwargs)
	_verify_production_permission(f["company"])
	where, vals = _plan_conditions(f)

	return frappe.db.sql(f"""
		SELECT
			DATE_FORMAT(pp.posting_date, '%%Y-%%m') AS month,
			SUM(poi.planned_qty) AS planned_qty,
			SUM(poi.produced_qty) AS produced_qty
		FROM `tabProduction Plan` pp
		INNER JOIN `tabProduction Plan Item` poi ON poi.parent = pp.name
		WHERE {where}
		GROUP BY month
		ORDER BY month ASC
	""", vals, as_dict=True)


# ---------------------------------------------------------------------------
# 6. Production Plan Summary (Table)
# ---------------------------------------------------------------------------

@frappe.whitelist()
def get_production_plan_summary(**kwargs):
	f = _parse_filters(kwargs)
	_verify_production_permission(f["company"])
	where, vals = _plan_conditions(f)
	end_col = _plan_end_date_col()

	data = frappe.db.sql(f"""
		SELECT
			pp.name AS plan,
			pp.status AS status,
			SUM(poi.planned_qty) AS planned_qty,
			SUM(poi.produced_qty) AS produced_qty,
			pp.posting_date AS planned_start_date,
			{end_col} AS planned_end_date
		FROM `tabProduction Plan` pp
		LEFT JOIN `tabProduction Plan Item` poi ON poi.parent = pp.name
		WHERE {where}
		GROUP BY pp.name
		ORDER BY pp.posting_date DESC
		LIMIT 100
	""", vals, as_dict=True)

	for r in data:
		planned = flt(r.get("planned_qty"))
		produced = flt(r.get("produced_qty"))
		r["completion_pct"] = round((produced / planned * 100), 2) if planned else 0.0

	return data


# ---------------------------------------------------------------------------
# 7. Job Card Status Distribution (Donut Chart)
# ---------------------------------------------------------------------------

@frappe.whitelist()
def get_chart_jobcard_status_distribution(**kwargs):
	f = _parse_filters(kwargs)
	_verify_production_permission(f["company"])
	where, vals = _jc_conditions(f)

	return frappe.db.sql(f"""
		SELECT jc.status, COUNT(jc.name) AS count
		FROM `tabJob Card` jc
		LEFT JOIN `tabWork Order` wo ON wo.name = jc.work_order
		WHERE {where}
		GROUP BY jc.status
		ORDER BY count DESC
	""", vals, as_dict=True)


# ---------------------------------------------------------------------------
# 8. Workstation Load (Bar Chart)
# ---------------------------------------------------------------------------

@frappe.whitelist()
def get_chart_workstation_load(**kwargs):
	f = _parse_filters(kwargs)
	_verify_production_permission(f["company"])
	where, vals = _jc_conditions(f)

	return frappe.db.sql(f"""
		SELECT IFNULL(jc.workstation, 'Unassigned') AS workstation, jc.status, COUNT(jc.name) AS jc_count
		FROM `tabJob Card` jc
		LEFT JOIN `tabWork Order` wo ON wo.name = jc.work_order
		WHERE {where}
		GROUP BY workstation, status
		ORDER BY workstation, status
	""", vals, as_dict=True)


# ---------------------------------------------------------------------------
# 9. Job Card Throughput (Daily/Weekly Trend)
# ---------------------------------------------------------------------------

@frappe.whitelist()
def get_chart_jobcard_throughput(**kwargs):
	f = _parse_filters(kwargs)
	_verify_production_permission(f["company"])
	where, vals = _jc_conditions(f)
	granularity = kwargs.get("granularity", "day")

	fmt = "%%Y-%%m-%%d" if granularity == "day" else "%%Y-%%u"
	label = "day" if granularity == "day" else "week"

	data = frappe.db.sql(f"""
		SELECT
			DATE_FORMAT(jc.modified, '{fmt}') AS period,
			COUNT(jc.name) AS completed_count
		FROM `tabJob Card` jc
		LEFT JOIN `tabWork Order` wo ON wo.name = jc.work_order
		WHERE {where} AND jc.status = 'Completed'
		GROUP BY period
		ORDER BY period ASC
	""", vals, as_dict=True)

	return {"label": label, "data": data}


# ---------------------------------------------------------------------------
# 10. Workstation Utilization
# ---------------------------------------------------------------------------

@frappe.whitelist()
def get_workstation_utilization(**kwargs):
	f = _parse_filters(kwargs)
	_verify_production_permission(f["company"])
	where, vals = _jc_conditions(f)

	data = frappe.db.sql(f"""
		SELECT
			jc.workstation,
			COUNT(DISTINCT jc.name) AS jc_count,
			ROUND(SUM(TIMESTAMPDIFF(MINUTE, tl.from_time, tl.to_time)) / 60.0, 2) AS total_hours
		FROM `tabJob Card` jc
		INNER JOIN `tabJob Card Time Log` tl ON tl.parent = jc.name
		LEFT JOIN `tabWork Order` wo ON wo.name = jc.work_order
		WHERE {where} AND tl.from_time IS NOT NULL AND tl.to_time IS NOT NULL
		GROUP BY jc.workstation
		ORDER BY total_hours DESC
	""", vals, as_dict=True)

	return data


# ---------------------------------------------------------------------------
# 11. Delayed Job Cards
# ---------------------------------------------------------------------------

@frappe.whitelist()
def get_delayed_job_cards(**kwargs):
	f = _parse_filters(kwargs)
	_verify_production_permission(f["company"])
	where, vals = _jc_conditions(f)
	vals["today_d"] = today()

	data = frappe.db.sql(f"""
		SELECT
			jc.name AS job_card,
			jc.work_order,
			jc.operation,
			jc.workstation,
			'' AS employee,
			jc.status,
			wo.planned_end_date,
			DATEDIFF(%(today_d)s, wo.planned_end_date) AS delay_days
		FROM `tabJob Card` jc
		LEFT JOIN `tabWork Order` wo ON wo.name = jc.work_order
		WHERE {where}
		  AND jc.status != 'Completed'
		  AND wo.planned_end_date IS NOT NULL
		  AND wo.planned_end_date < %(today_d)s
		ORDER BY delay_days DESC
		LIMIT 100
	""", vals, as_dict=True)

	return data


# ---------------------------------------------------------------------------
# 12. Plan → Work Order → Job Card Drill-down (3-Tier)
# ---------------------------------------------------------------------------

@frappe.whitelist()
def get_plan_workorder_jobcard_drilldown(**kwargs):
	f = _parse_filters(kwargs)
	_verify_production_permission(f["company"])
	where, vals = _plan_conditions(f)

	plans = frappe.db.sql(f"""
		SELECT pp.name AS plan, pp.status,
			   SUM(poi.planned_qty) as total_planned_qty,
			   SUM(poi.produced_qty) as total_produced_qty
		FROM `tabProduction Plan` pp
		LEFT JOIN `tabProduction Plan Item` poi ON poi.parent = pp.name
		WHERE {where}
		GROUP BY pp.name
		ORDER BY pp.posting_date DESC
		LIMIT 50
	""", vals, as_dict=True)

	if not plans:
		return []

	plan_names = [p["plan"] for p in plans]

	items = frappe.db.sql("""
		SELECT poi.parent AS plan, poi.item_code, i.item_name,
			   SUM(poi.planned_qty) as planned_qty, SUM(poi.produced_qty) as produced_qty
		FROM `tabProduction Plan Item` poi
		LEFT JOIN `tabItem` i ON i.name = poi.item_code
		WHERE poi.parent IN %(plans)s
		GROUP BY poi.parent, poi.item_code
	""", {"plans": plan_names}, as_dict=True)

	wo_data = frappe.db.sql("""
		SELECT wo.name AS work_order, wo.production_plan AS plan,
			   wo.status, wo.production_item AS item_code,
			   wo.qty, wo.produced_qty,
			   wo.planned_start_date, wo.planned_end_date
		FROM `tabWork Order` wo
		WHERE wo.production_plan IN %(plans)s AND wo.docstatus < 2
		ORDER BY wo.production_plan, wo.name
	""", {"plans": plan_names}, as_dict=True)

	if not wo_data:
		for p in plans:
			p["items"] = []
		return plans

	wo_names = [w["work_order"] for w in wo_data]
	jc_data = frappe.db.sql("""
		SELECT jc.name AS job_card, jc.work_order,
			   jc.operation, jc.workstation, jc.status,
			   jc.for_quantity, jc.total_completed_qty,
			   jc.actual_start_date, jc.actual_end_date
		FROM `tabJob Card` jc
		WHERE jc.work_order IN %(wos)s AND jc.docstatus < 2
		ORDER BY jc.work_order, jc.name
	""", {"wos": wo_names}, as_dict=True)

	jc_map = {}
	for jc in jc_data:
		jc_map.setdefault(jc["work_order"], []).append(jc)

	mat_data = frappe.db.sql("""
		SELECT woi.parent AS work_order, woi.item_code, woi.item_name,
			   woi.source_warehouse, woi.required_qty, woi.transferred_qty,
			   IFNULL(b.actual_qty, 0) AS actual_qty
		FROM `tabWork Order Item` woi
		LEFT JOIN `tabBin` b ON b.item_code = woi.item_code AND b.warehouse = woi.source_warehouse
		WHERE woi.parent IN %(wos)s
	""", {"wos": wo_names}, as_dict=True)

	mat_map = {}
	for mat in mat_data:
		mat_map.setdefault(mat["work_order"], []).append(mat)

	wo_map = {}
	for wo in wo_data:
		wo["job_cards"] = jc_map.get(wo["work_order"], [])
		wo["materials"] = mat_map.get(wo["work_order"], [])
		wo_map.setdefault((wo["plan"], wo["item_code"]), []).append(wo)

	item_map = {}
	for it in items:
		it["work_orders"] = wo_map.get((it["plan"], it["item_code"]), [])
		item_map.setdefault(it["plan"], []).append(it)

	for p in plans:
		p["items"] = item_map.get(p["plan"], [])

	return plans


# ---------------------------------------------------------------------------
# 13. Auxiliary Reports
# ---------------------------------------------------------------------------

@frappe.whitelist()
def get_material_request_status_per_plan(**kwargs):
	f = _parse_filters(kwargs)
	_verify_production_permission(f["company"])
	where, vals = _plan_conditions(f)
	join_clause = _mr_join_clause()

	return frappe.db.sql(f"""
		SELECT
			pp.name AS production_plan,
			mr.status AS mr_status,
			COUNT(DISTINCT mr.name) AS mr_count
		FROM `tabProduction Plan` pp
		{join_clause}
		WHERE {where}
		GROUP BY pp.name, mr.status
		ORDER BY pp.name
	""", vals, as_dict=True)


@frappe.whitelist()
def get_work_order_status_per_plan(**kwargs):
	f = _parse_filters(kwargs)
	_verify_production_permission(f["company"])
	where, vals = _plan_conditions(f)

	return frappe.db.sql(f"""
		SELECT
			pp.name AS production_plan,
			wo.status AS wo_status,
			COUNT(DISTINCT wo.name) AS wo_count
		FROM `tabProduction Plan` pp
		INNER JOIN `tabWork Order` wo
			ON wo.production_plan = pp.name AND wo.docstatus < 2
		WHERE {where}
		GROUP BY pp.name, wo.status
		ORDER BY pp.name
	""", vals, as_dict=True)


@frappe.whitelist()
def get_raw_material_requirement(**kwargs):
	f = _parse_filters(kwargs)
	_verify_production_permission(f["company"])
	where, vals = _plan_conditions(f)
	qty_col = _mr_plan_item_qty_col()

	bin_cond = "AND b.warehouse = %(warehouse)s" if f.get("warehouse") else ""
	if f.get("warehouse"):
		vals["warehouse"] = f["warehouse"]

	return frappe.db.sql(f"""
		SELECT
			mri.item_code,
			mri.item_name,
			SUM({qty_col}) AS required_qty,
			COALESCE(SUM(b.actual_qty), 0) AS in_stock,
			GREATEST(SUM({qty_col}) - COALESCE(SUM(b.actual_qty), 0), 0) AS shortage_qty
		FROM `tabProduction Plan` pp
		INNER JOIN `tabMaterial Request Plan Item` mri ON mri.parent = pp.name
		LEFT JOIN `tabBin` b ON b.item_code = mri.item_code {bin_cond}
		WHERE {where}
		GROUP BY mri.item_code, mri.item_name
		HAVING required_qty > 0
		ORDER BY shortage_qty DESC
		LIMIT 100
	""", vals, as_dict=True)


@frappe.whitelist()
def get_lead_time_delay_report(**kwargs):
	f = _parse_filters(kwargs)
	_verify_production_permission(f["company"])
	where, vals = _plan_conditions(f)
	end_col = _plan_end_date_col()

	data = frappe.db.sql(f"""
		SELECT
			pp.name AS production_plan,
			pp.posting_date AS planned_start,
			{end_col} AS planned_end,
			MIN(wo.actual_start_date) AS actual_start,
			MAX(wo.actual_end_date) AS actual_end
		FROM `tabProduction Plan` pp
		LEFT JOIN `tabWork Order` wo
			ON wo.production_plan = pp.name AND wo.docstatus < 2
		WHERE {where}
		GROUP BY pp.name
		ORDER BY pp.posting_date DESC
		LIMIT 100
	""", vals, as_dict=True)

	for r in data:
		planned_days = date_diff(r.get("planned_end"), r.get("planned_start")) if r.get("planned_end") and r.get("planned_start") else None
		actual_days = date_diff(r.get("actual_end"), r.get("actual_start")) if r.get("actual_end") and r.get("actual_start") else None
		r["planned_lead_days"] = planned_days
		r["actual_lead_days"] = actual_days
		r["delay_days"] = max(0, (actual_days or 0) - (planned_days or 0)) if planned_days is not None else None

	return data


@frappe.whitelist()
def get_job_card_status_report(**kwargs):
	f = _parse_filters(kwargs)
	_verify_production_permission(f["company"])
	where, vals = _jc_conditions(f)

	return frappe.db.sql(f"""
		SELECT
			jc.name AS job_card,
			jc.work_order,
			jc.operation,
			jc.workstation,
			'' AS employee,
			jc.status,
			jc.actual_start_date,
			jc.actual_end_date,
			jc.for_quantity AS planned_qty,
			jc.total_completed_qty AS completed_qty
		FROM `tabJob Card` jc
		LEFT JOIN `tabWork Order` wo ON wo.name = jc.work_order
		WHERE {where}
		ORDER BY jc.creation DESC
		LIMIT 100
	""", vals, as_dict=True)


@frappe.whitelist()
def get_operation_wise_progress(**kwargs):
	f = _parse_filters(kwargs)
	_verify_production_permission(f["company"])
	where, vals = _jc_conditions(f)

	data = frappe.db.sql(f"""
		SELECT
			jc.operation,
			COUNT(jc.name) AS total_jc,
			SUM(CASE WHEN jc.status = 'Completed' THEN 1 ELSE 0 END) AS completed,
			SUM(CASE WHEN jc.status != 'Completed' THEN 1 ELSE 0 END) AS pending
		FROM `tabJob Card` jc
		LEFT JOIN `tabWork Order` wo ON wo.name = jc.work_order
		WHERE {where}
		GROUP BY jc.operation
		ORDER BY total_jc DESC
		LIMIT 50
	""", vals, as_dict=True)

	for r in data:
		total = cint(r.get("total_jc"))
		r["completion_pct"] = round(cint(r.get("completed")) / total * 100, 2) if total else 0.0

	return data


@frappe.whitelist()
def get_job_card_time_tracking(**kwargs):
	f = _parse_filters(kwargs)
	_verify_production_permission(f["company"])
	where, vals = _jc_conditions(f)

	return frappe.db.sql(f"""
		SELECT
			jc.name AS job_card,
			jc.work_order,
			jc.operation,
			jc.workstation,
			tl.employee,
			tl.from_time,
			tl.to_time,
			tl.completed_qty,
			ROUND(TIMESTAMPDIFF(MINUTE, tl.from_time, tl.to_time) / 60.0, 2) AS hours_worked
		FROM `tabJob Card` jc
		INNER JOIN `tabJob Card Time Log` tl ON tl.parent = jc.name
		LEFT JOIN `tabWork Order` wo ON wo.name = jc.work_order
		WHERE {where} AND tl.from_time IS NOT NULL AND tl.to_time IS NOT NULL
		ORDER BY tl.from_time DESC
		LIMIT 100
	""", vals, as_dict=True)


# ---------------------------------------------------------------------------
# 17. Production Plan Summary Report (High Detail Tree & KPIs)
# ---------------------------------------------------------------------------

@frappe.whitelist()
def get_production_plan_summary_report(**kwargs):
	"""
	Returns high-detail Production Plan Summary data compatible with ERPNext's standard
	Production Plan Summary report, enhanced with company security, multi-plan support,
	and structured hierarchical items and sub-assemblies for modern UI rendering.
	"""
	f = _parse_filters(kwargs)
	_verify_production_permission(f["company"])
	where, vals = _plan_conditions(f)

	# Fetch available plans matching filter criteria
	plans = frappe.db.sql(f"""
		SELECT
			pp.name,
			pp.posting_date,
			pp.status,
			pp.total_planned_qty,
			pp.total_produced_qty
		FROM `tabProduction Plan` pp
		WHERE {where}
		ORDER BY pp.posting_date DESC, pp.creation DESC
		LIMIT 50
	""", vals, as_dict=True)

	selected_plan = f.get("production_plan")
	if not selected_plan and plans:
		selected_plan = plans[0]["name"]

	if not selected_plan:
		return {
			"plans": [],
			"selected_plan": None,
			"kpis": {
				"total_fg_items": 0,
				"total_sub_items": 0,
				"total_planned_qty": 0.0,
				"total_produced_qty": 0.0,
				"total_pending_qty": 0.0,
				"completion_pct": 0.0,
				"status": "No Plans",
				"posting_date": None,
			},
			"items": [],
		}

	# Ensure the selected plan belongs to the permitted company
	plan_meta = frappe.db.get_value(
		"Production Plan",
		selected_plan,
		["name", "company", "status", "posting_date", "total_planned_qty", "total_produced_qty"],
		as_dict=True,
	)
	if not plan_meta or (f.get("company") and plan_meta.company != f["company"]):
		frappe.throw(_("Production Plan not found or company mismatch."), frappe.PermissionError)

	# Fetch Finished Good items
	fg_items = frappe.db.sql("""
		SELECT
			poi.name AS plan_item_name,
			poi.item_code,
			COALESCE(i.item_name, poi.item_code) AS item_name,
			poi.sales_order,
			poi.planned_qty,
			poi.produced_qty,
			poi.pending_qty,
			poi.bom_no,
			poi.warehouse
		FROM `tabProduction Plan Item` poi
		LEFT JOIN `tabItem` i ON i.name = poi.item_code
		WHERE poi.parent = %(plan)s
		ORDER BY poi.idx ASC
	""", {"plan": selected_plan}, as_dict=True)

	# Fetch Work Orders linked to this plan
	work_orders = frappe.db.sql("""
		SELECT
			wo.name,
			wo.status,
			wo.production_item,
			wo.qty,
			wo.produced_qty,
			wo.sales_order,
			wo.production_plan_item,
			wo.production_plan_sub_assembly_item,
			wo.planned_start_date,
			wo.planned_end_date,
			wo.actual_start_date,
			wo.actual_end_date
		FROM `tabWork Order` wo
		WHERE wo.production_plan = %(plan)s AND wo.docstatus < 2
		ORDER BY wo.creation ASC
	""", {"plan": selected_plan}, as_dict=True)

	# Map Work Orders by production_plan_item and sub_assembly
	wo_by_item = {}
	wo_by_sub = {}
	for wo in work_orders:
		if wo.get("production_plan_item"):
			wo_by_item.setdefault(wo["production_plan_item"], []).append(wo)
		if wo.get("production_plan_sub_assembly_item"):
			wo_by_sub.setdefault(wo["production_plan_sub_assembly_item"], []).append(wo)

	# Fetch Sub-assemblies for this plan
	sub_assemblies = frappe.db.sql("""
		SELECT
			sub.name AS sub_assembly_id,
			sub.production_plan_item,
			sub.production_item AS item_code,
			COALESCE(sub.item_name, sub.production_item) AS item_name,
			sub.parent_item_code,
			sub.bom_level,
			sub.type_of_manufacturing,
			sub.qty AS planned_qty,
			sub.wo_produced_qty,
			sub.received_qty,
			sub.indent,
			sub.supplier,
			sub.purchase_order
		FROM `tabProduction Plan Sub Assembly Item` sub
		WHERE sub.parent = %(plan)s
		ORDER BY sub.idx ASC
	""", {"plan": selected_plan}, as_dict=True)

	sub_by_item = {}
	for sub in sub_assemblies:
		parent_item_key = sub.get("production_plan_item") or sub.get("parent_item_code")
		sub_by_item.setdefault(parent_item_key, []).append(sub)

	# Fetch Purchase Orders linked to sub-assemblies if any
	sub_po_map = {}
	po_items = frappe.db.sql("""
		SELECT
			poi.parent AS po_name,
			poi.name AS po_item_name,
			poi.production_plan_sub_assembly_item,
			poi.qty,
			poi.received_qty,
			po.status AS po_status
		FROM `tabPurchase Order Item` poi
		INNER JOIN `tabPurchase Order` po ON po.name = poi.parent
		WHERE poi.production_plan = %(plan)s AND po.docstatus < 2
	""", {"plan": selected_plan}, as_dict=True)
	for poi in po_items:
		if poi.get("production_plan_sub_assembly_item"):
			sub_po_map.setdefault(poi["production_plan_sub_assembly_item"], []).append(poi)

	# Construct structured report rows
	report_items = []
	tot_planned = 0.0
	tot_produced = 0.0

	for fg in fg_items:
		fg_planned = flt(fg.get("planned_qty"))
		fg_produced = flt(fg.get("produced_qty"))
		linked_wos = wo_by_item.get(fg["plan_item_name"], [])

		if not fg_produced and linked_wos:
			fg_produced = sum(flt(w.get("produced_qty")) for w in linked_wos)

		fg_pending = max(0.0, fg_planned - fg_produced)
		fg_pct = round((fg_produced / fg_planned * 100), 2) if fg_planned else 0.0

		tot_planned += fg_planned
		tot_produced += fg_produced

		# Build sub-assembly detail rows
		fg_subs = sub_by_item.get(fg["plan_item_name"]) or sub_by_item.get(fg["item_code"]) or []
		structured_subs = []
		for s in fg_subs:
			s_planned = flt(s.get("qty"))
			s_type = s.get("type_of_manufacturing") or "Manufacture"
			s_wos = wo_by_sub.get(s["sub_assembly_id"], [])
			s_pos = sub_po_map.get(s["sub_assembly_id"], [])

			if s_type == "Subcontract":
				doc_type = "Purchase Order"
				doc_name = s_pos[0]["po_name"] if s_pos else (s.get("purchase_order") or "")
				s_produced = sum(flt(p.get("received_qty")) for p in s_pos) if s_pos else flt(s.get("received_qty"))
				doc_status = s_pos[0]["po_status"] if s_pos else ("Submitted" if doc_name else "Pending")
			else:
				doc_type = "Work Order"
				doc_name = s_wos[0]["name"] if s_wos else ""
				s_produced = sum(flt(w.get("produced_qty")) for w in s_wos) if s_wos else flt(s.get("wo_produced_qty"))
				doc_status = s_wos[0]["status"] if s_wos else ("Submitted" if doc_name else "Pending")

			s_pending = max(0.0, s_planned - s_produced)
			s_pct = round((s_produced / s_planned * 100), 2) if s_planned else 0.0

			structured_subs.append({
				"sub_assembly_id": s["sub_assembly_id"],
				"item_code": s["item_code"],
				"item_name": s["item_name"],
				"bom_level": cint(s.get("bom_level") or 1),
				"type": s_type,
				"document_type": doc_type,
				"document_name": doc_name,
				"status": doc_status,
				"planned_qty": s_planned,
				"produced_qty": s_produced,
				"pending_qty": s_pending,
				"completion_pct": s_pct,
			})

		report_items.append({
			"plan_item_name": fg["plan_item_name"],
			"item_code": fg["item_code"],
			"item_name": fg["item_name"],
			"sales_order": fg.get("sales_order") or "",
			"bom_no": fg.get("bom_no") or "",
			"planned_qty": fg_planned,
			"produced_qty": fg_produced,
			"pending_qty": fg_pending,
			"completion_pct": fg_pct,
			"work_orders": [{
				"name": w["name"],
				"status": w["status"],
				"qty": flt(w["qty"]),
				"produced_qty": flt(w["produced_qty"]),
				"actual_start": str(w.get("actual_start_date") or ""),
				"actual_end": str(w.get("actual_end_date") or ""),
			} for w in linked_wos],
			"sub_assemblies": structured_subs,
		})

	tot_pending = max(0.0, tot_planned - tot_produced)
	overall_pct = round((tot_produced / tot_planned * 100), 2) if tot_planned else 0.0

	return {
		"plans": plans,
		"selected_plan": selected_plan,
		"kpis": {
			"total_fg_items": len(fg_items),
			"total_sub_items": len(sub_assemblies),
			"total_planned_qty": tot_planned,
			"total_produced_qty": tot_produced,
			"total_pending_qty": tot_pending,
			"completion_pct": overall_pct,
			"status": plan_meta.status,
			"posting_date": str(plan_meta.posting_date or ""),
		},
		"items": report_items,
	}


@frappe.whitelist()
def get_pending_production_items_report(**kwargs):
	"""
	Returns data matching the 'Pending Production Item V1 - All Companies' report
	with optional company filtering, parameterized SQL, and company permissions.
	"""
	company = kwargs.get("company")
	if company:
		_verify_production_permission(company)

	params = {}
	company_clause = ""
	if company:
		company_clause = "AND so.company = %(company)s"
		params["company"] = company

	query = f"""
		SELECT
			COALESCE(ig.parent_item_group, '') AS parent_item_group,
			i.item_group AS item_group,
			ROUND(SUM(soi.qty - IFNULL(soi.delivered_qty, 0))) AS pending_qty,
			soi.uom AS uom
		FROM
			`tabSales Order` so
		INNER JOIN
			`tabSales Order Item` soi
				ON soi.parent = so.name
		LEFT JOIN
			`tabItem` i
				ON i.name = soi.item_code
		LEFT JOIN
			`tabItem Group` ig
				ON ig.name = i.item_group
		WHERE
			so.docstatus = 1
			AND so.status NOT IN (
				'Closed',
				'Stopped',
				'On Hold',
				'Completed'
			)
			AND (
				soi.qty - IFNULL(soi.delivered_qty, 0)
			) > 0
			{company_clause}
		GROUP BY
			i.item_group,
			ig.parent_item_group,
			soi.uom
		ORDER BY
			i.item_group ASC
	"""

	rows = frappe.db.sql(query, params, as_dict=True)

	total_qty = sum(flt(r.get("pending_qty", 0)) for r in rows)
	parent_groups = len(set(r.get("parent_item_group") for r in rows if r.get("parent_item_group")))

	return {
		"columns": [
			{"label": "Parent Item Group", "fieldname": "parent_item_group", "width": 180},
			{"label": "Item Group", "fieldname": "item_group", "width": 220},
			{"label": "Pending Qty", "fieldname": "pending_qty", "width": 140, "type": "Int"},
			{"label": "UOM", "fieldname": "uom", "width": 100},
		],
		"rows": rows,
		"summary": {
			"total_pending_qty": total_qty,
			"total_rows": len(rows),
			"total_parent_groups": parent_groups,
			"company": company or "All Companies",
		},
	}

