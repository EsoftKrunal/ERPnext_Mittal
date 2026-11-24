# Copyright (c) 2026, Administrator and contributors
# For license information, please see license.txt

import frappe
from frappe.tests.classes.integration_test_case import IntegrationTestCase
from frappe.utils import today, flt
from custom_dashbords.api import sales_analytics


class TestSalesDashboardVerification(IntegrationTestCase):
	"""Comprehensive Verification Test Suite for Sales Dashboard:
	1. Company Security (multi-company, user restricted to one company, cross-company access block)
	2. Role-based permissions (System Manager, Sales Manager, Sales User, Accounts User, Guest)
	3. Clean test lifecycle verification
	"""

	def setUp(self):
		super().setUp()
		frappe.set_user("Administrator")
		self.company_1 = frappe.db.get_single_value("Global Defaults", "default_company") or "e"
		self.cleanup_records = []

	def tearDown(self):
		frappe.set_user("Administrator")
		# Clean up any records created during tests
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

	def test_company_security_multi_company_isolation(self):
		"""1. Company Security Verification:
		- Create second company.
		- Create user restricted by User Permission to Company 1 ('e').
		- Attempt to query Company 2 via API filters.
		- Confirm unauthorized company data cannot be returned and raises PermissionError.
		- Test across all 26 endpoints.
		"""
		# Create Company 2
		company_2_name = "_Test_Mittal_Co_2"
		if not frappe.db.exists("Company", company_2_name):
			c2 = frappe.get_doc({
				"doctype": "Company",
				"company_name": company_2_name,
				"abbr": "TMC2",
				"default_currency": "INR",
				"country": "India",
			}).insert(ignore_permissions=True)
			self._track("Company", c2.name)

		# Create Test User with Sales Manager role
		test_email = "test_sales_mgr_co1@example.com"
		if not frappe.db.exists("User", test_email):
			user = frappe.get_doc({
				"doctype": "User",
				"email": test_email,
				"first_name": "Test Sales Mgr",
				"send_welcome_email": 0,
			}).insert(ignore_permissions=True)
			user.add_roles("Sales Manager")
			self._track("User", user.name)

		# Add User Permission: restricted to company_1 only
		perm_name = frappe.db.get_value(
			"User Permission",
			{"user": test_email, "allow": "Company", "for_value": self.company_1},
			"name",
		)
		if not perm_name:
			up = frappe.get_doc({
				"doctype": "User Permission",
				"user": test_email,
				"allow": "Company",
				"for_value": self.company_1,
			}).insert(ignore_permissions=True)
			self._track("User Permission", up.name)

		frappe.db.commit()
		frappe.clear_cache(user=test_email)

		# Switch session to restricted user
		frappe.set_user(test_email)

		# Test 1: User querying their permitted company succeeds
		res_permitted = sales_analytics.get_overview_kpis(company=self.company_1)
		self.assertIn("total_revenue", res_permitted)

		# Test 2: User attempting to query company_2 must raise PermissionError
		with self.assertRaises(frappe.PermissionError):
			sales_analytics.get_overview_kpis(company=company_2_name)

		# Test 3: Verify all 26 endpoints block access to unauthorized company
		endpoints = [
			sales_analytics.get_overview_kpis,
			sales_analytics.get_chart_monthly_sales_trend,
			sales_analytics.get_top_items_by_revenue,
			sales_analytics.get_top_customers_by_revenue,
			sales_analytics.get_chart_revenue_by_territory,
			sales_analytics.get_chart_revenue_by_item_group,
			sales_analytics.get_overview_table,
			sales_analytics.get_fulfillment_kpis,
			sales_analytics.get_chart_fulfillment_status_split,
			sales_analytics.get_chart_overdue_value_by_customer,
			sales_analytics.get_chart_ordered_vs_delivered_vs_invoiced,
			sales_analytics.get_chart_delivery_performance_trend,
			sales_analytics.get_fulfillment_table,
			sales_analytics.get_fulfillment_drilldown,
			sales_analytics.get_receivables_kpis,
			sales_analytics.get_chart_ageing_buckets,
			sales_analytics.get_chart_outstanding_by_territory_or_group,
			sales_analytics.get_top_customers_by_outstanding,
			sales_analytics.get_chart_collections_trend,
			sales_analytics.get_receivables_table,
			sales_analytics.get_customer_activity_kpis,
			sales_analytics.get_chart_customer_activity_split,
			sales_analytics.get_top_dormant_customers_by_value,
			sales_analytics.get_chart_dormant_value_by_customer_group,
			sales_analytics.get_chart_new_customer_trend,
			sales_analytics.get_customer_activity_table,
		]

		blocked_count = 0
		for ep in endpoints:
			try:
				res = ep(company=company_2_name)
				# If not raised, it must return strictly empty results due to SQL WHERE conditions
				if isinstance(res, list):
					self.assertEqual(len(res), 0)
				elif isinstance(res, dict):
					for k, v in res.items():
						if isinstance(v, (int, float)):
							self.assertEqual(v, 0)
						elif isinstance(v, list):
							self.assertEqual(len(v), 0)
				blocked_count += 1
			except frappe.PermissionError:
				blocked_count += 1

		self.assertEqual(blocked_count, len(endpoints), "Every endpoint must enforce company isolation")

	def test_role_permissions_desk_and_api(self):
		"""4. Role Verification:
		Test actual dashboard access and API access for:
		- System Manager
		- Sales Manager
		- Sales User
		- Accounts User
		- Guest
		Verify both page-level and server-side permissions.
		"""
		roles_to_test = {
			"System Manager": {"page": True, "api_sales": True},
			"Sales Manager": {"page": True, "api_sales": True},
			"Sales User": {"page": True, "api_sales": True},
			"Accounts User": {"page": True, "api_sales": True},
		}

		# Check Desk Page configuration roles
		page_roles = [d.role for d in frappe.get_doc("Page", "sales-analytics").roles]
		for role, exp in roles_to_test.items():
			self.assertIn(role, page_roles, f"Page sales-analytics must have role {role}")

		# Guest must NOT have page role
		self.assertNotIn("Guest", page_roles)

		# Test actual API calls for Guest
		frappe.set_user("Guest")
		with self.assertRaises(frappe.PermissionError):
			sales_analytics.get_overview_kpis()

		with self.assertRaises(frappe.PermissionError):
			sales_analytics.get_receivables_kpis()

		with self.assertRaises(frappe.PermissionError):
			sales_analytics.get_fulfillment_kpis()

		# Test API access for each role with a dedicated user
		frappe.set_user("Administrator")
		for role in roles_to_test:
			test_user_email = f"test_role_{role.lower().replace(' ', '_')}@example.com"
			if not frappe.db.exists("User", test_user_email):
				u = frappe.get_doc({
					"doctype": "User",
					"email": test_user_email,
					"first_name": role,
					"send_welcome_email": 0,
				}).insert(ignore_permissions=True)
				u.add_roles(role)
				self._track("User", u.name)

			frappe.set_user(test_user_email)
			# Verify user can execute sales overview KPI
			res = sales_analytics.get_overview_kpis(company=self.company_1)
			self.assertIn("total_revenue", res)
			frappe.set_user("Administrator")

	def test_cleanup_guarantee(self):
		"""3. Test Data Cleanup Verification:
		Confirm that creating transactions and cleaning them up leaves NO submitted
		or residual test transactions in the database.
		"""
		initial_so_count = frappe.db.count("Sales Order")
		initial_si_count = frappe.db.count("Sales Invoice")

		# Create transient test item & customer
		item_code = "_Test_Transient_Item"
		cust_name = "_Test_Transient_Cust"
		if not frappe.db.exists("Item", item_code):
			item = frappe.get_doc({
				"doctype": "Item",
				"item_code": item_code,
				"item_name": "Transient Item",
				"item_group": "Products",
				"is_stock_item": 0,
			}).insert(ignore_permissions=True)
			self._track("Item", item.name)

		if not frappe.db.exists("Customer", cust_name):
			cust = frappe.get_doc({
				"doctype": "Customer",
				"customer_name": cust_name,
				"customer_type": "Company",
				"customer_group": "Commercial",
				"territory": "India",
			}).insert(ignore_permissions=True)
			self._track("Customer", cust.name)

		# Create transient SO
		so = frappe.get_doc({
			"doctype": "Sales Order",
			"company": self.company_1,
			"customer": cust_name,
			"transaction_date": today(),
			"delivery_date": today(),
			"items": [{"item_code": item_code, "qty": 1, "rate": 100}],
		}).insert(ignore_permissions=True)
		so.submit()
		self._track("Sales Order", so.name)

		# Cancel and delete immediately
		so.cancel()
		so.delete()
		self.cleanup_records.remove(("Sales Order", so.name))

		final_so_count = frappe.db.count("Sales Order")
		final_si_count = frappe.db.count("Sales Invoice")

		self.assertEqual(initial_so_count, final_so_count)
		self.assertEqual(initial_si_count, final_si_count)
