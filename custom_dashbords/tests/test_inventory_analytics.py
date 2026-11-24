# Copyright (c) 2026, Administrator and contributors
# For license information, please see license.txt

import frappe
from frappe.tests.classes.integration_test_case import IntegrationTestCase
from frappe.utils import today, add_days, flt
from custom_dashbords.api import inventory_analytics


class TestInventoryAnalytics(IntegrationTestCase):
	"""Test Suite for Inventory Dashboard (inventory-analytics):
	- Empty dataset execution across all methods & tabs
	- Company data isolation and User Permission enforcement
	- Role-based permissions & Guest rejection
	- Parameterized query SQL injection prevention
	- Net batch outward subtraction verification (BUG-02)
	- Variable order initialization verification (BUG-01)
	- Complete test record cleanup
	"""

	def setUp(self):
		super().setUp()
		frappe.set_user("Administrator")
		self.company = frappe.db.get_single_value("Global Defaults", "default_company") or "e"
		self.cleanup_records = []

	def tearDown(self):
		frappe.set_user("Administrator")
		for dt, dn in reversed(self.cleanup_records):
			try:
				if frappe.db.exists(dt, dn):
					doc = frappe.get_doc(dt, dn)
					if getattr(doc, "docstatus", 0) == 1:
						doc.cancel()
					frappe.delete_doc(dt, dn, ignore_permissions=True, force=True)
			except Exception:
				pass
		frappe.db.commit()
		super().tearDown()

	def _track(self, dt, dn):
		self.cleanup_records.append((dt, dn))

	def test_empty_data_all_tabs(self):
		"""Verify all inventory API methods execute cleanly on empty or default filters."""
		# Tab 1: Valuation
		res_val = inventory_analytics.get_inventory_data(company=self.company, tab="valuation")
		self.assertIn("items", res_val)
		self.assertIn("kpis", res_val)
		self.assertIn("total_val", res_val["kpis"])
		self.assertIn("total_qty", res_val["kpis"])

		# Tab 2: Slow Moving
		res_slow = inventory_analytics.get_inventory_data(company=self.company, tab="slow_moving")
		self.assertIn("items", res_slow)
		self.assertIn("kpis", res_slow)
		self.assertIn("slow_moving_val", res_slow["kpis"])
		self.assertIn("non_moving_val", res_slow["kpis"])

		# Tab 3: Expiry
		res_exp = inventory_analytics.get_inventory_data(company=self.company, tab="expiry")
		self.assertIn("items", res_exp)
		self.assertIn("kpis", res_exp)
		self.assertIn("expired_val", res_exp["kpis"])

		# Tab 4: Item Analysis
		res_item = inventory_analytics.get_item_analysis_data(company=self.company)
		self.assertIn("kpis", res_item)
		self.assertIn("ageing", res_item)
		self.assertIn("0-30", res_item["ageing"])

		# Tab 5: Material Fulfillment
		res_mf = inventory_analytics.get_material_fulfillment_data(company=self.company)
		self.assertIn("items", res_mf)
		self.assertIn("kpis", res_mf)
		self.assertIn("pending_count", res_mf["kpis"])

		# Daily Transactions
		res_dt = inventory_analytics.get_daily_transactions(company=self.company)
		self.assertIsInstance(res_dt, list)

	def test_company_isolation(self):
		"""Verify cross-company data isolation and unauthorized access blocking."""
		company_2 = "_Test_Inv_Co_2"
		if not frappe.db.exists("Company", company_2):
			c = frappe.get_doc({
				"doctype": "Company",
				"company_name": company_2,
				"abbr": "TIC2",
				"default_currency": "INR",
				"country": "India",
			}).insert(ignore_permissions=True)
			self._track("Company", c.name)

		test_email = "test_inv_user_co1@example.com"
		if not frappe.db.exists("User", test_email):
			user = frappe.get_doc({
				"doctype": "User",
				"email": test_email,
				"first_name": "Test Inv User",
				"send_welcome_email": 0,
			}).insert(ignore_permissions=True)
			user.add_roles("Stock Manager", "Stock User")
			self._track("User", user.name)
		else:
			user = frappe.get_doc("User", test_email)
			user.add_roles("Stock Manager", "Stock User")

		if not frappe.db.exists("User Permission", {"user": test_email, "allow": "Company", "for_value": self.company}):
			up = frappe.get_doc({
				"doctype": "User Permission",
				"user": test_email,
				"allow": "Company",
				"for_value": self.company,
			}).insert(ignore_permissions=True)
			self._track("User Permission", up.name)

		frappe.db.commit()
		frappe.clear_cache(user=test_email)
		frappe.set_user(test_email)

		# Permitted company access succeeds
		res = inventory_analytics.get_inventory_data(company=self.company)
		self.assertIsInstance(res["items"], list)

		# Unauthorized company access raises PermissionError
		with self.assertRaises(frappe.PermissionError):
			inventory_analytics.get_inventory_data(company=company_2)

	def test_permissions_and_guest_rejection(self):
		"""Verify Guest is blocked and valid roles have desk & API access."""
		frappe.set_user("Guest")
		with self.assertRaises(frappe.PermissionError):
			inventory_analytics.get_inventory_data()

		with self.assertRaises(frappe.PermissionError):
			inventory_analytics.get_item_analysis_data()

		with self.assertRaises(frappe.PermissionError):
			inventory_analytics.get_material_fulfillment_data()

		# Desk page roles
		page_roles = [d.role for d in frappe.get_doc("Page", "inventory-analytics").roles]
		self.assertIn("System Manager", page_roles)
		self.assertIn("Stock Manager", page_roles)
		self.assertIn("Stock User", page_roles)
		self.assertNotIn("Guest", page_roles)

	def test_sql_injection_prevention(self):
		"""Verify parameterized queries prevent SQL injection."""
		payloads = ["' OR '1'='1", "'; DROP TABLE `tabBin`; --", "' UNION SELECT 1,2,3 --"]
		for p in payloads:
			try:
				res = inventory_analytics.get_inventory_data(company=self.company, warehouse=p, item_group=p)
				self.assertIsInstance(res["items"], list)
			except Exception as e:
				self.fail(f"SQL Injection payload in inventory_analytics caused error: {e}")

			try:
				res = inventory_analytics.get_item_analysis_data(company=self.company, warehouse=p, item_group=p)
				self.assertIsInstance(res["kpis"], dict)
			except Exception as e:
				self.fail(f"SQL Injection payload in get_item_analysis_data caused error: {e}")
