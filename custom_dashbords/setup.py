# Copyright (c) 2026, Administrator and contributors
# For license information, please see license.txt

import json
import frappe


def setup_workspace_shortcuts():
	"""
	Adds prominent Quick Access shortcuts for the custom dashboards into their
	respective ERPNext workspaces (Selling, Manufacturing, Buying, Stock, Projects).
	Idempotent and safe to run multiple times.
	"""
	workspaces_config = [
		{
			"workspace": "Selling",
			"shortcuts": [
				{
					"label": "Sales Analytics Dashboard",
					"type": "Page",
					"link_to": "sales-analytics",
					"color": "Blue",
				}
			],
			"after_header": "Quick Access",
		},
		{
			"workspace": "Manufacturing",
			"shortcuts": [
				{
					"label": "Production Analytics Dashboard",
					"type": "Page",
					"link_to": "production-analytics",
					"color": "Blue",
				},
				{
					"label": "Work Order",
					"type": "DocType",
					"link_to": "Work Order",
					"color": "Orange",
				},
				{
					"label": "Production Plan",
					"type": "DocType",
					"link_to": "Production Plan",
					"color": "Yellow",
				},
				{
					"label": "Job Card",
					"type": "DocType",
					"link_to": "Job Card",
					"color": "Green",
				},
			],
			"after_header": None,  # Will create Quick Access section
		},
		{
			"workspace": "Buying",
			"shortcuts": [
				{
					"label": "Purchase Tracking & Analytics",
					"type": "Page",
					"link_to": "purchase-analytics",
					"color": "Blue",
				},
				{
					"label": "Purchase Order",
					"type": "DocType",
					"link_to": "Purchase Order",
					"color": "Orange",
				},
				{
					"label": "Supplier",
					"type": "DocType",
					"link_to": "Supplier",
					"color": "Green",
				},
				{
					"label": "Material Request",
					"type": "DocType",
					"link_to": "Material Request",
					"color": "Yellow",
				},
			],
			"after_header": None,
		},
		{
			"workspace": "Stock",
			"shortcuts": [
				{
					"label": "Inventory & Lifecycle Analytics",
					"type": "Page",
					"link_to": "inventory-analytics",
					"color": "Blue",
				},
				{
					"label": "Item",
					"type": "DocType",
					"link_to": "Item",
					"color": "Grey",
				},
				{
					"label": "Stock Entry",
					"type": "DocType",
					"link_to": "Stock Entry",
					"color": "Orange",
				},
				{
					"label": "Delivery Note",
					"type": "DocType",
					"link_to": "Delivery Note",
					"color": "Green",
				},
			],
			"after_header": None,
		},
		{
			"workspace": "Projects",
			"shortcuts": [
				{
					"label": "Project",
					"type": "DocType",
					"link_to": "Project",
					"color": "Blue",
				},
				{
					"label": "Task",
					"type": "DocType",
					"link_to": "Task",
					"color": "Orange",
				},
				{
					"label": "Timesheet",
					"type": "DocType",
					"link_to": "Timesheet",
					"color": "Green",
				},
			],
			"after_header": None,
		},
	]

	for cfg in workspaces_config:
		ws_name = cfg["workspace"]
		if not frappe.db.exists("Workspace", ws_name):
			continue

		doc = frappe.get_doc("Workspace", ws_name)

		# Clean any broken/invalid links that block saving (e.g. non-existent DocTypes/Reports)
		valid_links = []
		for l in doc.links:
			if l.link_type == "DocType" and not frappe.db.exists("DocType", l.link_to):
				continue
			if l.link_type == "Report" and not frappe.db.exists("Report", l.link_to):
				continue
			if l.link_type == "Page" and not frappe.db.exists("Page", l.link_to):
				continue
			valid_links.append(l)
		doc.links = valid_links

		content = json.loads(doc.content) if doc.content else []
		has_quick_access = any(
			b.get("type") == "header" and "Quick Access" in b.get("data", {}).get("text", "")
			for b in content
		)

		# 1. Update doc.shortcuts child table
		for sc in cfg["shortcuts"]:
			existing = [s for s in doc.shortcuts if s.label == sc["label"] or (sc.get("link_to") and s.link_to == sc["link_to"])]
			if not existing:
				doc.append("shortcuts", {
					"type": sc["type"],
					"link_to": sc["link_to"],
					"label": sc["label"],
					"color": sc.get("color", "Blue"),
				})

		# 2. Update doc.content JSON
		if not has_quick_access:
			# Find insertion point: after charts or number cards, before cards
			insert_idx = 0
			for idx, b in enumerate(content):
				if b.get("type") in ("chart", "number_card"):
					insert_idx = idx + 1
				elif b.get("type") == "card":
					break

			new_blocks = [
				{"id": frappe.generate_hash(length=10), "type": "spacer", "data": {"col": 12}},
				{
					"id": frappe.generate_hash(length=10),
					"type": "header",
					"data": {"text": '<span class="h4"><b>Quick Access</b></span>', "col": 12},
				},
			]
			for sc in cfg["shortcuts"]:
				new_blocks.append({
					"id": frappe.generate_hash(length=10),
					"type": "shortcut",
					"data": {"shortcut_name": sc["label"], "col": 3},
				})
			new_blocks.append({"id": frappe.generate_hash(length=10), "type": "spacer", "data": {"col": 12}})
			new_blocks.append({
				"id": frappe.generate_hash(length=10),
				"type": "header",
				"data": {"text": '<span class="h4"><b>Reports &amp; Masters</b></span>', "col": 12},
			})

			for block in reversed(new_blocks):
				content.insert(insert_idx, block)
		else:
			# Add shortcut blocks to existing Quick Access section if missing
			qa_idx = -1
			for idx, b in enumerate(content):
				if b.get("type") == "header" and "Quick Access" in b.get("data", {}).get("text", ""):
					qa_idx = idx
					break

			existing_sc_names = set(
				b.get("data", {}).get("shortcut_name") for b in content if b.get("type") == "shortcut"
			)
			offset = 1
			for sc in cfg["shortcuts"]:
				if sc["label"] not in existing_sc_names:
					content.insert(qa_idx + offset, {
						"id": frappe.generate_hash(length=10),
						"type": "shortcut",
						"data": {"shortcut_name": sc["label"], "col": 3},
					})
					offset += 1

		doc.content = json.dumps(content)
		try:
			doc.save(ignore_permissions=True)
			frappe.db.commit()
			print(f"Updated workspace: {ws_name}")
		except Exception as e:
			frappe.log_error(f"Error updating workspace {ws_name}: {e}")
			print(f"Error updating {ws_name}: {e}")
