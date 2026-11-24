# Copyright (c) 2026, Administrator and contributors
# For license information, please see license.txt

import datetime
import frappe
from frappe import _
from frappe.utils import getdate, today, flt, date_diff, add_months
from custom_dashbords.api.permission_utils import (
	verify_read_permission,
	verify_company_permission,
	get_permission_condition,
	get_default_company,
	get_company_currency,
)


@frappe.whitelist()
def get_inventory_data(
	company=None,
	warehouse=None,
	item_group=None,
	from_date=None,
	to_date=None,
	tab=None,
	**kwargs
):
	"""Fetch stock balances, inventory valuation, velocity/aging, or batch shelf-life.
	Enforces server-side permissions, company isolation, and net batch balance calculation.
	"""
	verify_read_permission("Stock Ledger Entry")

	if not company:
		company = get_default_company()

	verify_company_permission(company)

	if not to_date:
		to_date = today()
	if not from_date:
		from_date = add_months(to_date, -3)

	sle_conditions = ["sle.docstatus < 2", "sle.is_cancelled = 0"]
	values = {}

	if company:
		sle_conditions.append("sle.company = %(company)s")
		values["company"] = company

	# Row-level User Permissions
	perm_cond = get_permission_condition("Stock Ledger Entry", "sle")
	if perm_cond:
		sle_conditions.append(perm_cond)

	if warehouse:
		wh_lft, wh_rgt = frappe.db.get_value("Warehouse", warehouse, ["lft", "rgt"]) or (None, None)
		if wh_lft and wh_rgt:
			child_whs = frappe.db.get_all(
				"Warehouse",
				filters={"lft": (">=", wh_lft), "rgt": ("<=", wh_rgt)},
				pluck="name"
			)
			if child_whs:
				sle_conditions.append("sle.warehouse IN %(warehouses)s")
				values["warehouses"] = child_whs
		else:
			sle_conditions.append("sle.warehouse = %(warehouse)s")
			values["warehouse"] = warehouse

	if item_group:
		ig_lft, ig_rgt = frappe.db.get_value("Item Group", item_group, ["lft", "rgt"]) or (None, None)
		if ig_lft and ig_rgt:
			child_igs = frappe.db.get_all(
				"Item Group",
				filters={"lft": (">=", ig_lft), "rgt": ("<=", ig_rgt)},
				pluck="name"
			)
			if child_igs:
				sle_conditions.append("item.item_group IN %(item_groups)s")
				values["item_groups"] = child_igs
		else:
			sle_conditions.append("item.item_group = %(item_group)s")
			values["item_group"] = item_group

	currency = get_company_currency(company)

	# ── Tab 3: Shelf Life & Expiry Analytics ──────────────────────────────────
	if tab == "expiry":
		sle_conditions.append("sle.posting_date <= %(to_date)s")
		sle_conditions.append("sle.serial_and_batch_bundle IS NOT NULL")
		values["to_date"] = to_date

		where_clause = " AND ".join(sle_conditions)

		# BUG-02 Fix: Properly calculate net batch balance subtracting outward quantities
		query = f"""
			SELECT 
				sle.item_code,
				item.item_name,
				item.item_group,
				sle.warehouse,
				sbl.batch_no,
				batch.expiry_date,
				SUM(CASE WHEN sbl.is_outward = 1 THEN -sbl.qty ELSE sbl.qty END) as bal_qty,
				sle.company,
				IFNULL(bin.valuation_rate, 0) as val_rate
			FROM 
				`tabStock Ledger Entry` sle
			INNER JOIN 
				`tabItem` item ON sle.item_code = item.name
			INNER JOIN
				`tabSerial and Batch Bundle` sabb ON sle.serial_and_batch_bundle = sabb.name
			INNER JOIN
				`tabSerial and Batch Entry` sbl ON sbl.parent = sabb.name
			INNER JOIN 
				`tabBatch` batch ON sbl.batch_no = batch.name
			LEFT JOIN
				`tabBin` bin ON sle.item_code = bin.item_code AND sle.warehouse = bin.warehouse
			WHERE 
				{where_clause}
				AND batch.expiry_date IS NOT NULL
				AND item.has_expiry_date = 1
			GROUP BY 
				sle.item_code, 
				sle.warehouse, 
				sbl.batch_no,
				item.item_name, 
				item.item_group, 
				batch.expiry_date, 
				sle.company,
				bin.valuation_rate
			HAVING 
				SUM(CASE WHEN sbl.is_outward = 1 THEN -sbl.qty ELSE sbl.qty END) > 0
			ORDER BY 
				batch.expiry_date ASC
		"""
		batch_rows = frappe.db.sql(query, values, as_dict=True)

		items_data = []
		expired_val = 0.0
		near_expiry_val = 0.0
		safe_val = 0.0
		total_batched_qty = 0.0

		for row in batch_rows:
			val_rate = flt(row.val_rate)
			row.val_rate = val_rate
			row.bal_qty = flt(row.bal_qty)
			row.bal_val = row.bal_qty * val_rate
			total_batched_qty += row.bal_qty

			if row.expiry_date:
				days_to_expiry = date_diff(row.expiry_date, to_date)
				row.days_to_expiry = days_to_expiry
				if days_to_expiry < 0:
					row.status = "Expired"
					expired_val += row.bal_val
				elif days_to_expiry <= 30:
					row.status = "Expiring < 30 Days"
					near_expiry_val += row.bal_val
				elif days_to_expiry <= 90:
					row.status = "Expiring < 90 Days"
					near_expiry_val += row.bal_val
				else:
					row.status = "Safe"
					safe_val += row.bal_val
			else:
				row.days_to_expiry = 9999
				row.status = "Safe"
				safe_val += row.bal_val

			items_data.append(row)

		return {
			"items": items_data,
			"kpis": {
				"expired_val": expired_val,
				"near_expiry_val": near_expiry_val,
				"safe_val": safe_val,
				"total_qty": total_batched_qty,
			},
			"currency": currency,
		}

	# ── Tab 1 & Tab 2: Valuation / Slow Moving ────────────────────────────────
	values["to_date"] = to_date
	values["from_date"] = from_date
	sle_conditions.append("sle.posting_date <= %(to_date)s")

	query = f"""
		SELECT 
			sle.item_code,
			sle.warehouse,
			item.item_name,
			item.item_group,
			item.stock_uom,
			sle.company,
			SUM(sle.actual_qty) as bal_qty,
			SUM(CASE WHEN sle.posting_date >= %(from_date)s AND sle.actual_qty > 0 THEN sle.actual_qty ELSE 0 END) as in_qty,
			SUM(CASE WHEN sle.posting_date >= %(from_date)s AND sle.actual_qty < 0 THEN -sle.actual_qty ELSE 0 END) as out_qty,
			SUM(CASE WHEN sle.posting_date >= %(from_date)s AND sle.stock_value_difference > 0 THEN sle.stock_value_difference ELSE 0 END) as in_val,
			SUM(CASE WHEN sle.posting_date >= %(from_date)s AND sle.stock_value_difference < 0 THEN -sle.stock_value_difference ELSE 0 END) as out_val,
			MAX(sle.posting_date) as last_date,
			IFNULL(bin.valuation_rate, 0) as val_rate
		FROM 
			`tabStock Ledger Entry` sle
		INNER JOIN 
			`tabItem` item ON sle.item_code = item.name
		LEFT JOIN
			`tabBin` bin ON sle.item_code = bin.item_code AND sle.warehouse = bin.warehouse
		WHERE 
			{" AND ".join(sle_conditions)}
		GROUP BY 
			sle.item_code, 
			sle.warehouse, 
			item.item_name, 
			item.item_group, 
			item.stock_uom, 
			sle.company,
			bin.valuation_rate
		HAVING
			SUM(sle.actual_qty) != 0 OR SUM(CASE WHEN sle.posting_date >= %(from_date)s THEN ABS(sle.actual_qty) ELSE 0 END) > 0
	"""
	entries = frappe.db.sql(query, values, as_dict=True)

	filtered_items = []
	total_val = 0.0
	total_qty = 0.0

	active_val = 0.0
	active_items_count = 0
	slow_moving_val = 0.0
	slow_items_count = 0
	non_moving_val = 0.0
	non_items_count = 0

	for row in entries:
		row["bal_qty"] = flt(row["bal_qty"], 3)
		row["in_qty"] = flt(row["in_qty"], 3)
		row["out_qty"] = flt(row["out_qty"], 3)
		row["in_val"] = flt(row["in_val"], 2)
		row["out_val"] = flt(row["out_val"], 2)
		row["val_rate"] = flt(row["val_rate"])
		row["bal_val"] = flt(row["bal_qty"] * row["val_rate"], 2)

		row["opening_qty"] = flt(row["bal_qty"] - row["in_qty"] + row["out_qty"], 3)
		row["opening_val"] = flt(row["bal_val"] - row["in_val"] + row["out_val"], 2)

		days_inactive = date_diff(to_date, row["last_date"]) if row["last_date"] else 9999
		row["days_inactive"] = days_inactive

		if days_inactive > 90:
			row["status"] = "Non-Moving"
		elif days_inactive > 30:
			row["status"] = "Slow-Moving"
		else:
			row["status"] = "Active"

		filtered_items.append(row)

		if row["bal_qty"] > 0:
			total_val += row["bal_val"]
			total_qty += row["bal_qty"]

			if row["status"] == "Active":
				active_val += row["bal_val"]
				active_items_count += 1
			elif row["status"] == "Slow-Moving":
				slow_moving_val += row["bal_val"]
				slow_items_count += 1
			elif row["status"] == "Non-Moving":
				non_moving_val += row["bal_val"]
				non_items_count += 1

	if tab == "slow_moving":
		kpis = {
			"active_moving_val": active_val,
			"active_items_count": active_items_count,
			"slow_moving_val": slow_moving_val,
			"slow_items_count": slow_items_count,
			"non_moving_val": non_moving_val,
			"non_items_count": non_items_count,
		}
	else:
		kpis = {
			"total_val": total_val,
			"total_qty": total_qty,
			"stocked_items": active_items_count + slow_items_count + non_items_count,
			"zero_stock_items": sum(1 for r in filtered_items if r["bal_qty"] <= 0),
		}

	# Last transaction date
	last_date_conditions = ["docstatus < 2", "is_cancelled = 0"]
	last_date_values = {}
	if company:
		last_date_conditions.append("company = %(company)s")
		last_date_values["company"] = company

	last_transaction_date = frappe.db.sql(f"""
		SELECT MAX(posting_date) FROM `tabStock Ledger Entry`
		WHERE {" AND ".join(last_date_conditions)}
	""", last_date_values)[0][0]

	last_transaction_date = str(last_transaction_date) if last_transaction_date else today()

	return {
		"items": filtered_items,
		"kpis": kpis,
		"currency": currency,
		"last_transaction_date": last_transaction_date,
	}


@frappe.whitelist()
def get_item_analysis_data(
	company=None,
	warehouse=None,
	item_group=None,
	item_code=None,
	to_date=None,
	**kwargs
):
	"""Fetch detailed item analysis: lead times, reorder levels, deficit, and FIFO ageing."""
	verify_read_permission("Stock Ledger Entry")

	if not company:
		company = get_default_company()

	verify_company_permission(company)

	if not to_date:
		to_date = today()

	currency = get_company_currency(company)

	# 1. Resolve item codes list
	item_codes = []
	if item_code:
		item_codes = [item_code]
	elif item_group:
		ig_lft, ig_rgt = frappe.db.get_value("Item Group", item_group, ["lft", "rgt"]) or (None, None)
		if ig_lft and ig_rgt:
			child_igs = frappe.db.get_all(
				"Item Group",
				filters={"lft": (">=", ig_lft), "rgt": ("<=", ig_rgt)},
				pluck="name"
			)
			if child_igs:
				item_codes = frappe.db.get_all("Item", filters={"item_group": ("in", child_igs)}, pluck="name")
		else:
			item_codes = frappe.db.get_all("Item", filters={"item_group": item_group}, pluck="name")

	if not item_codes:
		return {
			"kpis": {"total_qty": 0.0, "total_val": 0.0, "reorder_level": 0.0, "lead_time_days": 0.0},
			"ageing": {"0-30": {"qty": 0.0, "val": 0.0}, "30-60": {"qty": 0.0, "val": 0.0}, "60-90": {"qty": 0.0, "val": 0.0}, ">90": {"qty": 0.0, "val": 0.0}},
			"suppliers": [],
			"reorders": [],
			"urgency_reorders": [],
			"currency": currency,
			"warehouse_distribution": [],
			"monthly_trend": [],
		}

	# 2. Resolve warehouses
	warehouses = []
	if warehouse:
		wh_lft, wh_rgt = frappe.db.get_value("Warehouse", warehouse, ["lft", "rgt"]) or (None, None)
		if wh_lft and wh_rgt:
			warehouses = frappe.db.get_all("Warehouse", filters={"lft": (">=", wh_lft), "rgt": ("<=", wh_rgt)}, pluck="name")
		else:
			warehouses = [warehouse]

	# 3. Stock balances
	sle_conditions = [
		"sle.docstatus < 2",
		"sle.is_cancelled = 0",
		"sle.item_code IN %(item_codes)s",
		"sle.posting_date <= %(to_date)s",
	]
	sle_values = {"item_codes": item_codes, "to_date": to_date}
	if warehouses:
		sle_conditions.append("sle.warehouse IN %(warehouses)s")
		sle_values["warehouses"] = warehouses
	if company:
		sle_conditions.append("sle.company = %(company)s")
		sle_values["company"] = company

	perm_cond = get_permission_condition("Stock Ledger Entry", "sle")
	if perm_cond:
		sle_conditions.append(perm_cond)

	sle_query = f"""
		SELECT 
			sle.item_code,
			sle.warehouse,
			SUM(sle.actual_qty) as bal_qty,
			IFNULL(bin.valuation_rate, 0) as val_rate
		FROM 
			`tabStock Ledger Entry` sle
		LEFT JOIN
			`tabBin` bin ON sle.item_code = bin.item_code AND sle.warehouse = bin.warehouse
		WHERE 
			{" AND ".join(sle_conditions)}
		GROUP BY 
			sle.item_code, 
			sle.warehouse,
			bin.valuation_rate
	"""
	stock_balances = frappe.db.sql(sle_query, sle_values, as_dict=True)

	total_qty = sum(flt(b.bal_qty) for b in stock_balances)
	total_val = sum(flt(b.bal_qty) * flt(b.val_rate) for b in stock_balances)

	# Lead Time from Item master
	lead_time_query = "SELECT AVG(IFNULL(lead_time_days, 0)) FROM `tabItem` WHERE name IN %(item_codes)s"
	lead_time_days = flt(frappe.db.sql(lead_time_query, {"item_codes": item_codes})[0][0])

	# Supplier details
	supplier_query = """
		SELECT 
			parent as item_code,
			supplier,
			0 as lead_time,
			supplier_part_no
		FROM 
			`tabItem Supplier`
		WHERE 
			parent IN %(item_codes)s
		ORDER BY 
			supplier ASC
	"""
	suppliers = frappe.db.sql(supplier_query, {"item_codes": item_codes}, as_dict=True)

	# 4. Reorder Levels and Urgency
	reorder_conditions = ["parent IN %(item_codes)s"]
	reorder_values = {"item_codes": item_codes}
	if warehouses:
		reorder_conditions.append("warehouse IN %(warehouses)s")
		reorder_values["warehouses"] = warehouses

	reorder_query = f"""
		SELECT 
			parent as item_code,
			warehouse,
			warehouse_reorder_level as reorder_level,
			warehouse_reorder_qty as reorder_qty,
			material_request_type
		FROM 
			`tabItem Reorder`
		WHERE 
			{" AND ".join(reorder_conditions)}
	"""
	reorder_configs = frappe.db.sql(reorder_query, reorder_values, as_dict=True)

	stock_map = {}
	for b in stock_balances:
		stock_map[(b.item_code, b.warehouse)] = stock_map.get((b.item_code, b.warehouse), 0.0) + flt(b.bal_qty)

	reorders_list = []
	urgency_reorders = []
	total_reorder_level = 0.0

	for r in reorder_configs:
		item_name = frappe.db.get_value("Item", r.item_code, "item_name")
		curr_qty = stock_map.get((r.item_code, r.warehouse), 0.0)
		reorder_level = flt(r.reorder_level)
		reorder_qty = flt(r.reorder_qty)
		total_reorder_level += reorder_level

		is_reached = 1 if curr_qty <= reorder_level else 0
		deficit = max(0.0, reorder_level - curr_qty)
		ratio = (curr_qty / reorder_level) if reorder_level > 0 else (0.0 if curr_qty <= 0 else 999.0)

		row_data = {
			"item_code": r.item_code,
			"item_name": item_name,
			"warehouse": r.warehouse,
			"bal_qty": curr_qty,
			"reorder_level": reorder_level,
			"reorder_qty": reorder_qty,
			"material_request_type": r.material_request_type,
			"deficit": deficit,
			"ratio": ratio,
			"status": "Reorder Required" if is_reached else "Okay",
		}
		reorders_list.append(row_data)
		if is_reached:
			urgency_reorders.append(row_data)

	urgency_reorders.sort(key=lambda x: x["ratio"])

	# 5. FIFO Stock Ageing (BUG-01 Fix: initialize conditions list properly)
	sle_ageing_conditions = [
		"sle.docstatus < 2",
		"sle.is_cancelled = 0",
		"sle.item_code IN %(item_codes)s",
		"sle.actual_qty > 0",
		"sle.posting_date <= %(to_date)s",
	]
	sle_ageing_values = {"item_codes": item_codes, "to_date": to_date}
	if warehouses:
		sle_ageing_conditions.append("sle.warehouse IN %(warehouses)s")
		sle_ageing_values["warehouses"] = warehouses
	if company:
		sle_ageing_conditions.append("sle.company = %(company)s")
		sle_ageing_values["company"] = company

	if perm_cond:
		sle_ageing_conditions.append(perm_cond)

	ageing_sle_query = f"""
		SELECT 
			sle.item_code,
			sle.warehouse,
			sle.posting_date,
			sle.actual_qty,
			IFNULL(bin.valuation_rate, 0) as val_rate
		FROM 
			`tabStock Ledger Entry` sle
		LEFT JOIN
			`tabBin` bin ON sle.item_code = bin.item_code AND sle.warehouse = bin.warehouse
		WHERE 
			{" AND ".join(sle_ageing_conditions)}
		ORDER BY 
			sle.posting_date DESC,
			sle.posting_time DESC,
			sle.creation DESC
	"""
	inbound_entries = frappe.db.sql(ageing_sle_query, sle_ageing_values, as_dict=True)

	item_wh_balances = {}
	for b in stock_balances:
		if flt(b.bal_qty) > 0:
			item_wh_balances[(b.item_code, b.warehouse)] = {
				"bal_qty": flt(b.bal_qty),
				"val_rate": flt(b.val_rate),
			}

	inbound_map = {}
	for entry in inbound_entries:
		key = (entry.item_code, entry.warehouse)
		inbound_map.setdefault(key, []).append(entry)

	age_buckets = {
		"0-30": {"qty": 0.0, "val": 0.0},
		"30-60": {"qty": 0.0, "val": 0.0},
		"60-90": {"qty": 0.0, "val": 0.0},
		">90": {"qty": 0.0, "val": 0.0},
	}

	for key, bal in item_wh_balances.items():
		qty_to_age = bal["bal_qty"]
		rate = bal["val_rate"]
		entries = inbound_map.get(key, [])

		for entry in entries:
			if qty_to_age <= 0:
				break
			entry_qty = flt(entry.actual_qty)
			age_days = date_diff(to_date, entry.posting_date)

			qty_consumed = min(qty_to_age, entry_qty)
			qty_to_age -= qty_consumed

			if age_days <= 30:
				b_key = "0-30"
			elif age_days <= 60:
				b_key = "30-60"
			elif age_days <= 90:
				b_key = "60-90"
			else:
				b_key = ">90"

			age_buckets[b_key]["qty"] += qty_consumed
			age_buckets[b_key]["val"] += qty_consumed * rate

		if qty_to_age > 0:
			age_buckets[">90"]["qty"] += qty_to_age
			age_buckets[">90"]["val"] += qty_to_age * rate

	warehouse_distribution = []
	for key, bal in item_wh_balances.items():
		_, wh = key
		bal_qty = bal["bal_qty"]
		bal_val = bal_qty * bal["val_rate"]
		if bal_qty > 0 or bal_val > 0:
			warehouse_distribution.append({
				"warehouse": wh,
				"qty": bal_qty,
				"val": bal_val,
			})
	warehouse_distribution.sort(key=lambda x: x["qty"], reverse=True)

	# 6. Monthly trend (last 6 months)
	start_date = add_months(to_date, -5)
	start_date = getdate(start_date).replace(day=1)

	trend_conditions = ["docstatus < 2", "is_cancelled = 0", "item_code IN %(item_codes)s"]
	trend_values = {
		"item_codes": item_codes,
		"start_date": start_date,
		"to_date": to_date,
	}
	if warehouses:
		trend_conditions.append("warehouse IN %(warehouses)s")
		trend_values["warehouses"] = warehouses
	if company:
		trend_conditions.append("company = %(company)s")
		trend_values["company"] = company

	trend_data = frappe.db.sql(f"""
		SELECT
			SUBSTRING(posting_date, 1, 7) as month,
			SUM(CASE WHEN actual_qty > 0 THEN actual_qty ELSE 0 END) as receipts,
			SUM(CASE WHEN actual_qty < 0 THEN ABS(actual_qty) ELSE 0 END) as issues
		FROM `tabStock Ledger Entry`
		WHERE {" AND ".join(trend_conditions)}
		  AND posting_date >= %(start_date)s
		  AND posting_date <= %(to_date)s
		GROUP BY SUBSTRING(posting_date, 1, 7)
		ORDER BY month ASC
	""", trend_values, as_dict=True)

	trend_map = {row["month"]: row for row in trend_data}
	final_trend = []
	current_d = getdate(to_date)
	for i in range(5, -1, -1):
		m = current_d.month - i
		y = current_d.year
		while m <= 0:
			m += 12
			y -= 1
		month_str = f"{y:04d}-{m:02d}"
		row = trend_map.get(month_str, {"receipts": 0.0, "issues": 0.0})
		month_name = datetime.date(y, m, 1).strftime("%b %Y")
		final_trend.append({
			"month": month_str,
			"month_name": month_name,
			"receipts": flt(row["receipts"]),
			"issues": flt(row["issues"]),
		})

	return {
		"kpis": {
			"total_qty": total_qty,
			"total_val": total_val,
			"reorder_level": total_reorder_level,
			"lead_time_days": lead_time_days,
		},
		"ageing": age_buckets,
		"suppliers": suppliers,
		"reorders": reorders_list,
		"urgency_reorders": urgency_reorders,
		"currency": currency,
		"warehouse_distribution": warehouse_distribution,
		"monthly_trend": final_trend,
	}


@frappe.whitelist()
def get_daily_transactions(
	company=None,
	warehouse=None,
	item_group=None,
	item_code=None,
	from_date=None,
	to_date=None,
	**kwargs
):
	"""Fetch daily stock ledger movement records (Receipts and Issues)."""
	verify_read_permission("Stock Ledger Entry")

	if not company:
		company = get_default_company()

	verify_company_permission(company)

	to_date = getdate(to_date) if to_date else getdate(today())
	from_date = getdate(from_date) if from_date else frappe.utils.add_days(to_date, -30)

	conditions = [
		"sle.docstatus < 2",
		"sle.is_cancelled = 0",
		"sle.posting_date >= %(from_date)s",
		"sle.posting_date <= %(to_date)s",
	]
	values = {"from_date": from_date, "to_date": to_date}

	if company:
		conditions.append("sle.company = %(company)s")
		values["company"] = company

	perm_cond = get_permission_condition("Stock Ledger Entry", "sle")
	if perm_cond:
		conditions.append(perm_cond)

	if warehouse:
		wh_lft, wh_rgt = frappe.db.get_value("Warehouse", warehouse, ["lft", "rgt"]) or (None, None)
		if wh_lft and wh_rgt:
			child_whs = frappe.db.get_all(
				"Warehouse",
				filters={"lft": (">=", wh_lft), "rgt": ("<=", wh_rgt)},
				pluck="name"
			)
			if child_whs:
				conditions.append("sle.warehouse IN %(warehouses)s")
				values["warehouses"] = child_whs
		else:
			conditions.append("sle.warehouse = %(warehouse)s")
			values["warehouse"] = warehouse

	if item_code:
		conditions.append("sle.item_code = %(item_code)s")
		values["item_code"] = item_code
	elif item_group:
		ig_lft, ig_rgt = frappe.db.get_value("Item Group", item_group, ["lft", "rgt"]) or (None, None)
		if ig_lft and ig_rgt:
			child_igs = frappe.db.get_all(
				"Item Group",
				filters={"lft": (">=", ig_lft), "rgt": ("<=", ig_rgt)},
				pluck="name"
			)
			if child_igs:
				conditions.append("item.item_group IN %(item_groups)s")
				values["item_groups"] = child_igs
		else:
			conditions.append("item.item_group = %(item_group)s")
			values["item_group"] = item_group

	rows = frappe.db.sql(f"""
		SELECT
			sle.posting_date,
			sle.voucher_type,
			sle.voucher_no,
			sle.item_code,
			item.item_name,
			sle.warehouse,
			sle.actual_qty,
			ABS(sle.stock_value_difference) as value_change
		FROM `tabStock Ledger Entry` sle
		INNER JOIN `tabItem` item ON sle.item_code = item.name
		WHERE {" AND ".join(conditions)}
		ORDER BY sle.posting_date DESC, sle.creation DESC
		LIMIT 500
	""", values, as_dict=True)

	for row in rows:
		row["direction"] = "Received" if flt(row["actual_qty"]) > 0 else "Issued"
		row["actual_qty"] = flt(row["actual_qty"], 3)
		row["value_change"] = flt(row["value_change"], 2)

	return rows


@frappe.whitelist()
def get_material_fulfillment_data(
	company=None,
	warehouse=None,
	item_group=None,
	from_date=None,
	to_date=None,
	**kwargs
):
	"""Material Request Requested vs Issued Qty analysis."""
	verify_read_permission("Stock Ledger Entry")

	if not company:
		company = get_default_company()

	verify_company_permission(company)

	to_date = getdate(to_date) if to_date else getdate(today())
	from_date = getdate(from_date) if from_date else add_months(to_date, -3)

	conditions = [
		"mri.docstatus = 1",
		"mr.docstatus = 1",
		"mr.transaction_date >= %(from_date)s",
		"mr.transaction_date <= %(to_date)s",
	]
	values = {"from_date": from_date, "to_date": to_date}

	if company:
		conditions.append("mr.company = %(company)s")
		values["company"] = company

	perm_cond = get_permission_condition("Material Request", "mr")
	if perm_cond:
		conditions.append(perm_cond)

	if item_group:
		ig_lft, ig_rgt = frappe.db.get_value("Item Group", item_group, ["lft", "rgt"]) or (None, None)
		if ig_lft and ig_rgt:
			child_igs = frappe.db.get_all(
				"Item Group",
				filters={"lft": (">=", ig_lft), "rgt": ("<=", ig_rgt)},
				pluck="name"
			)
			if child_igs:
				conditions.append("item.item_group IN %(item_groups)s")
				values["item_groups"] = child_igs
		else:
			conditions.append("item.item_group = %(item_group)s")
			values["item_group"] = item_group

	rows = frappe.db.sql(f"""
		SELECT
			mr.name as mr_no,
			mr.transaction_date as mr_date,
			mr.material_request_type,
			mr.owner as requested_by,
			mri.item_code,
			item.item_name,
			item.item_group,
			mri.qty as requested_qty,
			mri.stock_uom,
			mri.warehouse as target_warehouse,
			mri.schedule_date as required_date,
			mri.production_plan,
			mr.work_order,
			IFNULL((
				SELECT SUM(sed.qty)
				FROM `tabStock Entry Detail` sed
				INNER JOIN `tabStock Entry` se ON sed.parent = se.name
				WHERE se.docstatus = 1
				  AND sed.material_request = mr.name
				  AND sed.item_code = mri.item_code
			), 0) as issued_qty
		FROM `tabMaterial Request Item` mri
		INNER JOIN `tabMaterial Request` mr ON mri.parent = mr.name
		INNER JOIN `tabItem` item ON mri.item_code = item.name
		WHERE {" AND ".join(conditions)}
		ORDER BY mr.transaction_date DESC, mr.name
		LIMIT 1000
	""", values, as_dict=True)

	pending_count = 0
	partial_count = 0
	fulfilled_count = 0
	overdue_count = 0
	item_group_summary = {}
	purpose_summary = {}

	for row in rows:
		req = flt(row["requested_qty"], 3)
		issued = flt(row["issued_qty"], 3)
		row["requested_qty"] = req
		row["issued_qty"] = issued
		row["pending_qty"] = flt(max(0, req - issued), 3)
		row["pct_fulfilled"] = round((issued / req * 100), 1) if req > 0 else 0.0

		if issued <= 0:
			row["status"] = "Pending"
			pending_count += 1
		elif issued >= req:
			row["status"] = "Fulfilled"
			fulfilled_count += 1
		else:
			row["status"] = "Partial"
			partial_count += 1

		days_overdue = 0
		is_overdue = False
		if row["status"] != "Fulfilled" and row["required_date"]:
			diff = date_diff(today(), row["required_date"])
			if diff > 0:
				days_overdue = diff
				is_overdue = True
				overdue_count += 1
		row["days_overdue"] = days_overdue
		row["is_overdue"] = is_overdue

		if row["status"] != "Fulfilled":
			ig = row["item_group"] or "Not Specified"
			item_group_summary[ig] = item_group_summary.get(ig, 0) + 1
			purpose = row["material_request_type"] or "Not Specified"
			purpose_summary[purpose] = purpose_summary.get(purpose, 0) + 1

	ig_list = [{"item_group": k, "count": v} for k, v in item_group_summary.items()]
	ig_list.sort(key=lambda x: x["count"], reverse=True)

	purpose_list = [{"purpose": k, "count": v} for k, v in purpose_summary.items()]
	purpose_list.sort(key=lambda x: x["count"], reverse=True)

	kpis = {
		"total_items": len(rows),
		"pending_count": pending_count,
		"partial_count": partial_count,
		"fulfilled_count": fulfilled_count,
		"overdue_count": overdue_count,
	}
	return {
		"items": rows,
		"kpis": kpis,
		"item_groups": ig_list[:10],
		"purposes": purpose_list[:10],
	}
