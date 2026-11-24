# Copyright (c) 2026, administrator and contributors
# For license information, please see license.txt

import frappe
from frappe import _


def verify_read_permission(doctype: str):
	"""Enforce server-side read permission for the given DocType.
	Throws frappe.PermissionError if the current user lacks read access.
	"""
	if not frappe.has_permission(doctype, ptype="read"):
		frappe.throw(
			_("You do not have permission to access {0} records.").format(_(doctype)),
			frappe.PermissionError,
		)


def get_permission_condition(doctype: str, alias: str = None) -> str:
	"""Retrieve Frappe row-level User Permission conditions for a DocType.
	Safely replaces the table reference with `alias` if supplied, without
	generating invalid 'None.' prefixes.
	"""
	try:
		condition = frappe.permissions.get_doc_condition(doctype)
	except Exception:
		condition = None

	if not condition:
		return ""

	if alias:
		# Replace standard tabDocType prefixes with the specified alias
		condition = condition.replace(f"`tab{doctype}`.", f"`{alias}`.")
		condition = condition.replace(f"tab{doctype}.", f"{alias}.")
		condition = condition.replace(f"{doctype}.", f"{alias}.")

	return condition


def get_company_condition(company: str = None, alias: str = None, field: str = "company") -> tuple[str, dict]:
	"""Build parameterized SQL condition for company data isolation."""
	if not company:
		return "", {}

	prefix = f"{alias}." if alias else ""
	return f"{prefix}{field} = %(company)s", {"company": company}


def get_default_company() -> str:
	"""Dynamically resolve default company for the current session."""
	company = frappe.defaults.get_user_default("Company")
	if not company:
		company = frappe.db.get_single_value("Global Defaults", "default_company")
	if not company:
		companies = frappe.get_all("Company", pluck="name", limit=1)
		company = companies[0] if companies else None
	return company or ""


def get_company_currency(company: str = None) -> str:
	"""Dynamically resolve company default currency."""
	currency = None
	if company:
		currency = frappe.get_cached_value("Company", company, "default_currency")
	if not currency:
		currency = frappe.db.get_single_value("Global Defaults", "default_currency")
	return currency or "INR"
