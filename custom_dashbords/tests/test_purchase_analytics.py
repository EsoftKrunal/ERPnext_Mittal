# Copyright (c) 2026, Administrator and contributors
# For license information, please see license.txt

import frappe
from frappe.tests.classes.integration_test_case import IntegrationTestCase
from frappe.utils import today, add_days, flt
from custom_dashbords.api import purchase_analytics


class TestPurchaseAnalytics(IntegrationTestCase):
	"""Test Suite for Purchase Dashboard (purchase-analytics):
	- Empty dataset execution
	- Company data isolation and User Permission enforcement
	- Role-based permissions & Guest rejection
	- Parameterized query SQL injection prevention
	- Calculation verification (overdue, aging, pending bill qty/val)
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

	def test_empty_data_execution(self):
		"""Verify get_po_data runs cleanly on empty or default filters."""
		res = purchase_analytics.get_po_data(company=self.company)
		self.assertIn("items", res)
		self.assertIn("kpis", res)
		self.assertIn("currency", res)
		self.assertIsInstance(res["items"], list)
		self.assertIn("total_open_pos", res["kpis"])
		self.assertIn("total_outstanding_qty", res["kpis"])
		self.assertIn("total_outstanding_val", res["kpis"])
		self.assertIn("total_pending_bill_val", res["kpis"])
		self.assertIn("overdue_count", res["kpis"])

	def test_company_isolation(self):
		"""Verify cross-company data isolation and unauthorized access blocking."""
		# Create second company
		company_2 = "_Test_Purch_Co_2"
		if not frappe.db.exists("Company", company_2):
			c = frappe.get_doc({
				"doctype": "Company",
				"company_name": company_2,
				"abbr": "TPC2",
				"default_currency": "INR",
				"country": "India",
			}).insert(ignore_permissions=True)
			self._track("Company", c.name)

		# Test user restricted to self.company
		test_email = "test_purch_user_co1@example.com"
		if not frappe.db.exists("User", test_email):
			user = frappe.get_doc({
				"doctype": "User",
				"email": test_email,
				"first_name": "Test Purch User",
				"send_welcome_email": 0,
			}).insert(ignore_permissions=True)
			user.add_roles("Purchase Manager")
			self._track("User", user.name)

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
		res = purchase_analytics.get_po_data(company=self.company)
		self.assertIsInstance(res["items"], list)

		# Unauthorized company access raises PermissionError
		with self.assertRaises(frappe.PermissionError):
			purchase_analytics.get_po_data(company=company_2)

	def test_permissions_and_guest_rejection(self):
		"""Verify Guest is blocked and valid roles have desk & API access."""
		# Guest rejected
		frappe.set_user("Guest")
		with self.assertRaises(frappe.PermissionError):
			purchase_analytics.get_po_data()

		# Desk page configuration check
		page_roles = [d.role for d in frappe.get_doc("Page", "purchase-analytics").roles]
		self.assertIn("System Manager", page_roles)
		self.assertIn("Purchase Manager", page_roles)
		self.assertIn("Purchase User", page_roles)
		self.assertNotIn("Guest", page_roles)

	def test_sql_injection_prevention(self):
		"""Verify parameterized queries neutralize SQL injection payloads."""
		payloads = ["' OR '1'='1", "'; DROP TABLE `tabPurchase Order`; --", "' UNION SELECT 1,2,3 --"]
		for p in payloads:
			try:
				res = purchase_analytics.get_po_data(company=self.company, supplier=p, item_code=p)
				self.assertIsInstance(res["items"], list)
			except Exception as e:
				self.fail(f"SQL Injection payload in purchase_analytics.get_po_data caused error: {e}")

	def test_calculations_with_sample_po(self):
		"""Create sample submitted PO to verify calculations and cleanup."""
		item_code = "_Test_PO_Item"
		if not frappe.db.exists("Item", item_code):
			it = frappe.get_doc({
				"doctype": "Item",
				"item_code": item_code,
				"item_name": "Test PO Item",
				"item_group": "Products",
				"is_stock_item": 1,
			}).insert(ignore_permissions=True)
			self._track("Item", it.name)

		supplier_name = "_Test_PO_Supplier"
		if not frappe.db.exists("Supplier", supplier_name):
			sup = frappe.get_doc({
				"doctype": "Supplier",
				"supplier_name": supplier_name,
				"supplier_group": "Local",
			}).insert(ignore_permissions=True)
			self._track("Supplier", sup.name)

		# Create PO with past schedule_date (to test overdue)
		past_date = add_days(today(), -10)
		po = frappe.get_doc({
			"doctype": "Purchase Order",
			"company": self.company,
			"supplier": supplier_name,
			"transaction_date": past_date,
			"schedule_date": past_date,
			"items": [{
				"item_code": item_code,
				"qty": 5,
				"rate": 200,
				"schedule_date": past_date,
			}],
		}).insert(ignore_permissions=True)
		po.submit()
		self._track("Purchase Order", po.name)

		res = purchase_analytics.get_po_data(company=self.company)
		po_items = [r for r in res["items"] if r.po_no == po.name]
		self.assertEqual(len(po_items), 1)

		row = po_items[0]
		self.assertEqual(row.ordered_qty, 5.0)
		self.assertEqual(row.outstanding_qty, 5.0)
		self.assertEqual(row.outstanding_amount, 1000.0)
		self.assertEqual(row.pending_billed_qty, 5.0)
		self.assertEqual(row.pending_bill_val, 1000.0)
		self.assertEqual(row.is_overdue, 1)

		# Status filter "Overdue Only" includes it
		res_overdue = purchase_analytics.get_po_data(company=self.company, status_filter="Overdue Only")
		self.assertTrue(any(r.po_no == po.name for r in res_overdue["items"]))

		# Status filter "Pending Only" excludes it
		res_pending = purchase_analytics.get_po_data(company=self.company, status_filter="Pending Only")
		self.assertFalse(any(r.po_no == po.name for r in res_pending["items"]))
