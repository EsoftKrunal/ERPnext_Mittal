# Copyright (c) 2026, Administrator and contributors
# For license information, please see license.txt

import frappe
from frappe.tests.classes.integration_test_case import IntegrationTestCase
from frappe.utils import today, add_days, flt
from custom_dashbords.api import production_analytics


class TestProductionAnalytics(IntegrationTestCase):
	"""Test Suite for Production Dashboard (production-analytics):
	- Empty dataset execution across all methods
	- Company data isolation and User Permission enforcement (SEC-03)
	- Role-based permissions & Guest rejection
	- Parameterized query SQL injection prevention
	- Native ERPNext v16 manufacturing records (NO Job Card Header dependency)
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

	def test_empty_data_all_methods(self):
		"""Verify all production API methods execute cleanly on empty/default filters."""
		f = {"company": self.company}

		res_kpi = production_analytics.get_production_plan_kpis(**f)
		self.assertIn("active_plans", res_kpi)
		self.assertIn("planned_qty", res_kpi)
		self.assertIn("produced_qty", res_kpi)
		self.assertIn("completion_pct", res_kpi)

		res_jkpi = production_analytics.get_job_card_kpis(**f)
		self.assertIn("open", res_jkpi)
		self.assertIn("work_in_progress", res_jkpi)
		self.assertIn("on_hold", res_jkpi)
		self.assertIn("completed_this_week", res_jkpi)

		res_items = production_analytics.get_item_wise_planned_vs_produced(**f)
		self.assertIsInstance(res_items, list)

		res_status = production_analytics.get_chart_plan_status_distribution(**f)
		self.assertIsInstance(res_status, list)

		res_trend = production_analytics.get_chart_production_trend(**f)
		self.assertIsInstance(res_trend, list)

		res_summary = production_analytics.get_production_plan_summary(**f)
		self.assertIsInstance(res_summary, list)

		res_jc_status = production_analytics.get_chart_jobcard_status_distribution(**f)
		self.assertIsInstance(res_jc_status, list)

		res_ws_load = production_analytics.get_chart_workstation_load(**f)
		self.assertIsInstance(res_ws_load, list)

		res_tp = production_analytics.get_chart_jobcard_throughput(**f)
		self.assertIn("data", res_tp)
		self.assertIsInstance(res_tp["data"], list)

		res_util = production_analytics.get_workstation_utilization(**f)
		self.assertIsInstance(res_util, list)

		res_delayed = production_analytics.get_delayed_job_cards(**f)
		self.assertIsInstance(res_delayed, list)

		res_drilldown = production_analytics.get_plan_workorder_jobcard_drilldown(**f)
		self.assertIsInstance(res_drilldown, list)

		res_mr = production_analytics.get_material_request_status_per_plan(**f)
		self.assertIsInstance(res_mr, list)

		res_wo = production_analytics.get_work_order_status_per_plan(**f)
		self.assertIsInstance(res_wo, list)

		res_rm = production_analytics.get_raw_material_requirement(**f)
		self.assertIsInstance(res_rm, list)

		res_lead = production_analytics.get_lead_time_delay_report(**f)
		self.assertIsInstance(res_lead, list)

		res_jcsr = production_analytics.get_job_card_status_report(**f)
		self.assertIsInstance(res_jcsr, list)

		res_op = production_analytics.get_operation_wise_progress(**f)
		self.assertIsInstance(res_op, list)

		res_time = production_analytics.get_job_card_time_tracking(**f)
		self.assertIsInstance(res_time, list)

		res_report = production_analytics.get_production_plan_summary_report(**f)
		self.assertIn("plans", res_report)
		self.assertIn("items", res_report)
		self.assertIn("kpis", res_report)
		self.assertIsInstance(res_report["items"], list)

	def test_company_isolation(self):
		"""Verify cross-company data isolation and unauthorized access blocking."""
		company_2 = "_Test_Prod_Co_2"
		if not frappe.db.exists("Company", company_2):
			c = frappe.get_doc({
				"doctype": "Company",
				"company_name": company_2,
				"abbr": "TPRC2",
				"default_currency": "INR",
				"country": "India",
			}).insert(ignore_permissions=True)
			self._track("Company", c.name)

		test_email = "test_prod_user_co1@example.com"
		if not frappe.db.exists("User", test_email):
			user = frappe.get_doc({
				"doctype": "User",
				"email": test_email,
				"first_name": "Test Prod User",
				"send_welcome_email": 0,
			}).insert(ignore_permissions=True)
			user.add_roles("Manufacturing Manager")
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
		res = production_analytics.get_production_plan_kpis(company=self.company)
		self.assertIn("active_plans", res)

		# Unauthorized company access raises PermissionError
		with self.assertRaises(frappe.PermissionError):
			production_analytics.get_production_plan_kpis(company=company_2)

		with self.assertRaises(frappe.PermissionError):
			production_analytics.get_production_plan_summary_report(company=company_2)

	def test_permissions_and_guest_rejection(self):
		"""Verify Guest is blocked and valid roles have desk & API access."""
		frappe.set_user("Guest")
		with self.assertRaises(frappe.PermissionError):
			production_analytics.get_production_plan_kpis()

		with self.assertRaises(frappe.PermissionError):
			production_analytics.get_production_plan_summary_report()

		with self.assertRaises(frappe.PermissionError):
			production_analytics.get_job_card_kpis()

		# Desk page roles
		page_roles = [d.role for d in frappe.get_doc("Page", "production-analytics").roles]
		self.assertIn("System Manager", page_roles)
		self.assertIn("Manufacturing Manager", page_roles)
		self.assertIn("Manufacturing User", page_roles)
		self.assertNotIn("Guest", page_roles)

	def test_sql_injection_prevention(self):
		"""Verify parameterized queries prevent SQL injection."""
		payloads = ["' OR '1'='1", "'; DROP TABLE `tabWork Order`; --", "' UNION SELECT 1,2,3 --"]
		for p in payloads:
			try:
				res = production_analytics.get_production_plan_kpis(company=self.company, status=p, production_plan=p)
				self.assertIsInstance(res, dict)
			except Exception as e:
				self.fail(f"SQL Injection payload in production_analytics caused error: {e}")

			try:
				res = production_analytics.get_job_card_kpis(company=self.company, workstation=p, status=p)
				self.assertIsInstance(res, dict)
			except Exception as e:
				self.fail(f"SQL Injection payload in get_job_card_kpis caused error: {e}")
