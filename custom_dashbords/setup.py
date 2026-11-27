# Copyright (c) 2026, Administrator and contributors
# For license information, please see license.txt

import json
import frappe


def setup_workspace_shortcuts():
	"""
	Adds prominent Quick Access shortcuts for the custom dashboards into their
	respective ERPNext workspaces (Selling, Manufacturing, Buying, Stock, Projects),
	ensures roles allow all users to access the dashboard pages, and prevents
	label truncation.
	"""
	# 1. Ensure all logged-in users have permission on all 4 dashboard pages
	pages = ["sales-analytics", "production-analytics", "purchase-analytics", "inventory-analytics"]
	for p_name in pages:
		if frappe.db.exists("Page", p_name):
			p_doc = frappe.get_doc("Page", p_name)
			current_roles = [r.role for r in p_doc.roles]
			if "All" not in current_roles:
				p_doc.append("roles", {"role": "All"})
				p_doc.save(ignore_permissions=True)

	# 2. Workspaces configuration
	workspaces_config = [
		{
			"workspace": "Selling",
			"dashboard_shortcut": {
				"label": "Sales Dashboard",
				"type": "Page",
				"link_to": "sales-analytics",
				"color": "Blue",
				"col": 4,
			},
			"other_shortcuts": [
				{"label": "Sales Order", "type": "DocType", "link_to": "Sales Order", "color": "Yellow", "col": 4},
				{"label": "Item", "type": "DocType", "link_to": "Item", "color": "Grey", "col": 4},
			],
			"remove_shortcuts": ["Sales Analytics", "Sales Analytics Dashboard"],
		},
		{
			"workspace": "Manufacturing",
			"dashboard_shortcut": {
				"label": "Production Dashboard",
				"type": "Page",
				"link_to": "production-analytics",
				"color": "Blue",
				"col": 4,
			},
			"other_shortcuts": [
				{"label": "Work Order", "type": "DocType", "link_to": "Work Order", "color": "Orange", "col": 4},
				{"label": "Production Plan", "type": "DocType", "link_to": "Production Plan", "color": "Yellow", "col": 4},
				{"label": "Job Card", "type": "DocType", "link_to": "Job Card", "color": "Green", "col": 4},
			],
			"remove_shortcuts": ["Production Analytics Dashboard"],
		},
		{
			"workspace": "Buying",
			"dashboard_shortcut": {
				"label": "Purchase Dashboard",
				"type": "Page",
				"link_to": "purchase-analytics",
				"color": "Blue",
				"col": 4,
			},
			"other_shortcuts": [
				{"label": "Purchase Order", "type": "DocType", "link_to": "Purchase Order", "color": "Orange", "col": 4},
				{"label": "Supplier", "type": "DocType", "link_to": "Supplier", "color": "Green", "col": 4},
				{"label": "Material Request", "type": "DocType", "link_to": "Material Request", "color": "Yellow", "col": 4},
			],
			"remove_shortcuts": ["Purchase Tracking & Analytics"],
		},
		{
			"workspace": "Stock",
			"dashboard_shortcut": {
				"label": "Inventory Dashboard",
				"type": "Page",
				"link_to": "inventory-analytics",
				"color": "Blue",
				"col": 4,
			},
			"other_shortcuts": [
				{"label": "Item", "type": "DocType", "link_to": "Item", "color": "Grey", "col": 4},
				{"label": "Stock Entry", "type": "DocType", "link_to": "Stock Entry", "color": "Orange", "col": 4},
				{"label": "Delivery Note", "type": "DocType", "link_to": "Delivery Note", "color": "Green", "col": 4},
			],
			"remove_shortcuts": ["Inventory & Lifecycle Analytics"],
		},
		{
			"workspace": "Projects",
			"dashboard_shortcut": None,
			"other_shortcuts": [
				{"label": "Project", "type": "DocType", "link_to": "Project", "color": "Blue", "col": 4},
				{"label": "Task", "type": "DocType", "link_to": "Task", "color": "Orange", "col": 4},
				{"label": "Timesheet", "type": "DocType", "link_to": "Timesheet", "color": "Green", "col": 4},
			],
			"remove_shortcuts": [],
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

		# Collect targets to remove (like old redundant report shortcuts)
		remove_labels = set(cfg.get("remove_shortcuts", []))

		# Desired shortcuts for this workspace
		all_desired = []
		if cfg["dashboard_shortcut"]:
			all_desired.append(cfg["dashboard_shortcut"])
		for s in cfg["other_shortcuts"]:
			all_desired.append(s)

		desired_labels = set(s["label"] for s in all_desired)

		# Filter shortcuts child table: remove unwanted and existing desired (so we re-add cleanly)
		clean_shortcuts = []
		for s in doc.shortcuts:
			if s.label in remove_labels or s.label in desired_labels or (cfg["dashboard_shortcut"] and s.link_to == cfg["dashboard_shortcut"]["link_to"]):
				continue
			clean_shortcuts.append(s)
		doc.shortcuts = clean_shortcuts

		# Add desired shortcuts to child table
		for s in all_desired:
			doc.append("shortcuts", {
				"type": s["type"],
				"link_to": s["link_to"],
				"label": s["label"],
				"color": s.get("color", "Blue"),
			})

		# Update doc.content JSON
		content = json.loads(doc.content) if doc.content else []

		# Remove old shortcuts from content
		content = [
			b for b in content
			if not (b.get("type") == "shortcut" and b.get("data", {}).get("shortcut_name") in (remove_labels | desired_labels))
		]

		# Check if Quick Access header exists
		qa_idx = -1
		for idx, b in enumerate(content):
			if b.get("type") == "header" and "Quick Access" in b.get("data", {}).get("text", ""):
				qa_idx = idx
				break

		if qa_idx == -1:
			# Find insertion point: after charts / number cards, before cards
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
			for s in all_desired:
				new_blocks.append({
					"id": frappe.generate_hash(length=10),
					"type": "shortcut",
					"data": {"shortcut_name": s["label"], "col": s.get("col", 4)},
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
			# Insert right below Quick Access header
			offset = 1
			for s in all_desired:
				content.insert(qa_idx + offset, {
					"id": frappe.generate_hash(length=10),
					"type": "shortcut",
					"data": {"shortcut_name": s["label"], "col": s.get("col", 4)},
				})
				offset += 1

		doc.content = json.dumps(content)
		try:
			doc.save(ignore_permissions=True)
			frappe.db.commit()
			print(f"Successfully updated workspace: {ws_name}")
		except Exception as e:
			frappe.log_error(f"Error updating workspace {ws_name}: {e}")
			print(f"Error updating {ws_name}: {e}")
