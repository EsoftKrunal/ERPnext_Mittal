# Copyright (c) 2026, Administrator and contributors
# For license information, please see license.txt

import frappe
from frappe.tests.classes.integration_test_case import IntegrationTestCase
from frappe.utils import today, nowdate, flt
from custom_dashbords.api import sales_analytics


class TestSalesAnalytics(IntegrationTestCase):
	def setUp(self):
		super().setUp()
		frappe.set_user("Administrator")
		self.company = frappe.db.get_single_value("Global Defaults", "default_company") or "e"

	def tearDown(self):
		frappe.set_user("Administrator")
		super().tearDown()

	def test_all_endpoints_empty_data(self):
		"""Verify that all 26 endpoints execute cleanly without exceptions on empty/default filters."""
		f = {"company": self.company}

		# Tab 1: Overview
		res_kpi = sales_analytics.get_overview_kpis(**f)
		self.assertIn("total_revenue", res_kpi)
		self.assertIn("total_so_value", res_kpi)
		self.assertIn("order_count", res_kpi)
		self.assertIn("aov", res_kpi)

		res_trend = sales_analytics.get_chart_monthly_sales_trend(**f)
		self.assertIn("booked", res_trend)
		self.assertIn("invoiced", res_trend)

		res_items = sales_analytics.get_top_items_by_revenue(**f)
		self.assertIsInstance(res_items, list)

		res_cust = sales_analytics.get_top_customers_by_revenue(**f)
		self.assertIsInstance(res_cust, list)

		res_terr = sales_analytics.get_chart_revenue_by_territory(**f)
		self.assertIsInstance(res_terr, list)

		res_ig = sales_analytics.get_chart_revenue_by_item_group(**f)
		self.assertIsInstance(res_ig, list)

		res_tbl = sales_analytics.get_overview_table(**f)
		self.assertIsInstance(res_tbl, list)

		# Tab 2: Fulfillment
		res_fkpi = sales_analytics.get_fulfillment_kpis(**f)
		self.assertIn("pending_delivery", res_fkpi)
		self.assertIn("partial_delivery", res_fkpi)
		self.assertIn("completed_delivery", res_fkpi)
		self.assertIn("value_stuck", res_fkpi)

		res_fsplit = sales_analytics.get_chart_fulfillment_status_split(**f)
		self.assertIsInstance(res_fsplit, list)

		res_fover = sales_analytics.get_chart_overdue_value_by_customer(**f)
		self.assertIsInstance(res_fover, list)

		res_fodi = sales_analytics.get_chart_ordered_vs_delivered_vs_invoiced(**f)
		self.assertIsInstance(res_fodi, list)

		res_fdp = sales_analytics.get_chart_delivery_performance_trend(**f)
		self.assertIsInstance(res_fdp, list)

		res_ftbl = sales_analytics.get_fulfillment_table(**f)
		self.assertIsInstance(res_ftbl, list)

		res_fdd = sales_analytics.get_fulfillment_drilldown(**f)
		self.assertIsInstance(res_fdd, list)

		# Tab 3: Receivables
		res_rkpi = sales_analytics.get_receivables_kpis(**f)
		self.assertIn("total_outstanding", res_rkpi)
		self.assertIn("total_overdue", res_rkpi)
		self.assertIn("current_amount", res_rkpi)

		res_rage = sales_analytics.get_chart_ageing_buckets(**f)
		self.assertIsInstance(res_rage, list)

		res_rterr = sales_analytics.get_chart_outstanding_by_territory_or_group(**f)
		self.assertIsInstance(res_rterr, list)

		res_rcust = sales_analytics.get_top_customers_by_outstanding(**f)
		self.assertIsInstance(res_rcust, list)

		res_rtrend = sales_analytics.get_chart_collections_trend(**f)
		self.assertIsInstance(res_rtrend, list)

		res_rtbl = sales_analytics.get_receivables_table(**f)
		self.assertIsInstance(res_rtbl, list)

		# Tab 4: Customer Activity
		res_akpi = sales_analytics.get_customer_activity_kpis(**f)
		self.assertIn("active_count", res_akpi)
		self.assertIn("at_risk_count", res_akpi)
		self.assertIn("dormant_count", res_akpi)
		self.assertIn("new_customers", res_akpi)

		res_asplit = sales_analytics.get_chart_customer_activity_split(**f)
		self.assertIsInstance(res_asplit, list)

		res_adorm = sales_analytics.get_top_dormant_customers_by_value(**f)
		self.assertIsInstance(res_adorm, list)

		res_adgrp = sales_analytics.get_chart_dormant_value_by_customer_group(**f)
		self.assertIsInstance(res_adgrp, list)

		res_atrend = sales_analytics.get_chart_new_customer_trend(**f)
		self.assertIsInstance(res_atrend, list)

		res_atbl = sales_analytics.get_customer_activity_table(**f)
		self.assertIsInstance(res_atbl, list)

	def test_company_data_isolation(self):
		"""Verify that filtering by a non-existent company returns zero records."""
		res_real = sales_analytics.get_overview_kpis(company=self.company)
		res_fake = sales_analytics.get_overview_kpis(company="NonExistentCompany_999")

		self.assertEqual(res_fake["total_revenue"], 0.0)
		self.assertEqual(res_fake["total_so_value"], 0.0)
		self.assertEqual(res_fake["order_count"], 0)
		self.assertEqual(res_fake["invoice_count"], 0)

	def test_sql_injection_prevention(self):
		"""Verify parameterized queries prevent SQL injection payloads."""
		payloads = [
			"' OR '1'='1",
			"'; DROP TABLE `tabCustomer`; --",
			"' UNION SELECT 1, 2, 3 --",
		]

		for p in payloads:
			# Test customer_group and territory injection
			try:
				res = sales_analytics.get_chart_new_customer_trend(customer_group=p)
				self.assertIsInstance(res, list)
			except Exception as e:
				self.fail(f"SQL Injection payload in get_chart_new_customer_trend caused error: {e}")

			try:
				res = sales_analytics.get_customer_activity_kpis(customer_group=p, territory=p)
				self.assertIsInstance(res, dict)
			except Exception as e:
				self.fail(f"SQL Injection payload in get_customer_activity_kpis caused error: {e}")

			try:
				res = sales_analytics.get_overview_kpis(customer_group=p, territory=p, customer=p)
				self.assertIsInstance(res, dict)
			except Exception as e:
				self.fail(f"SQL Injection payload in get_overview_kpis caused error: {e}")

	def test_permission_enforcement(self):
		"""Verify server-side read permission enforcement blocks unauthorized users."""
		frappe.set_user("Guest")
		with self.assertRaises(frappe.PermissionError):
			sales_analytics.get_overview_kpis()

		with self.assertRaises(frappe.PermissionError):
			sales_analytics.get_receivables_kpis()

		with self.assertRaises(frappe.PermissionError):
			sales_analytics.get_fulfillment_kpis()

	def test_kpi_calculations_with_sample_records(self):
		"""Create sample submitted SO and SI to verify calculations and KPI metrics."""
		# Ensure Item exists
		item_code = "_Test_Dashboard_Item"
		if not frappe.db.exists("Item", item_code):
			item = frappe.get_doc({
				"doctype": "Item",
				"item_code": item_code,
				"item_name": "Test Dashboard Item",
				"item_group": "Products",
				"is_stock_item": 0,
			}).insert(ignore_permissions=True)

		# Ensure Customer exists
		customer_name = "_Test_Dashboard_Customer"
		if not frappe.db.exists("Customer", customer_name):
			cust = frappe.get_doc({
				"doctype": "Customer",
				"customer_name": customer_name,
				"customer_type": "Company",
				"customer_group": "Commercial",
				"territory": "India",
			}).insert(ignore_permissions=True)

		# Create and submit Sales Order
		so = frappe.get_doc({
			"doctype": "Sales Order",
			"company": self.company,
			"customer": customer_name,
			"transaction_date": today(),
			"delivery_date": today(),
			"items": [{
				"item_code": item_code,
				"qty": 2,
				"rate": 500,
			}],
		}).insert(ignore_permissions=True)
		so.submit()

		# Create and submit Sales Invoice
		si = frappe.get_doc({
			"doctype": "Sales Invoice",
			"company": self.company,
			"customer": customer_name,
			"debit_to": "Debtors - E",
			"posting_date": today(),
			"due_date": today(),
			"items": [{
				"item_code": item_code,
				"qty": 2,
				"rate": 500,
				"income_account": "Sales - E",
			}],
		}).insert(ignore_permissions=True)
		si.submit()

		# Verify Overview KPIs include SI
		res_kpi = sales_analytics.get_overview_kpis(company=self.company)
		self.assertGreaterEqual(res_kpi["total_so_value"], 1000.0)
		self.assertGreaterEqual(res_kpi["total_revenue"], 1000.0)
		self.assertGreaterEqual(res_kpi["order_count"], 1)
		self.assertGreaterEqual(res_kpi["invoice_count"], 1)
		self.assertGreater(res_kpi["aov"], 0)

		# Verify Top Items & Top Customers
		top_items = sales_analytics.get_top_items_by_revenue(company=self.company)
		self.assertTrue(any(r["item_code"] == item_code for r in top_items))

		top_cust = sales_analytics.get_top_customers_by_revenue(company=self.company)
		self.assertTrue(any(r["customer"] == customer_name for r in top_cust))

		# Verify Receivables KPIs
		res_rkpi = sales_analytics.get_receivables_kpis(company=self.company)
		self.assertGreaterEqual(res_rkpi["total_outstanding"], 1000.0)

		# Verify Receivables Table
		res_rtbl = sales_analytics.get_receivables_table(company=self.company)
		self.assertTrue(any(r["invoice_no"] == si.name for r in res_rtbl))

		# Verify Fulfillment KPIs
		res_fkpi = sales_analytics.get_fulfillment_kpis(company=self.company)
		self.assertGreaterEqual(res_fkpi["pending_delivery"], 1)
		self.assertGreaterEqual(flt(res_fkpi["value_stuck"]), 1000.0)

		# Verify Overview Table
		res_tbl = sales_analytics.get_overview_table(company=self.company)
		so_names = [r["docname"] for r in res_tbl]
		self.assertIn(so.name, so_names)

		# Verify Isolation: SO and SI do not appear under another company
		res_isolated_tbl = sales_analytics.get_overview_table(company="NonExistentCompany_999")
		iso_names = [r["docname"] for r in res_isolated_tbl]
		self.assertNotIn(so.name, iso_names)

		res_isolated_rtbl = sales_analytics.get_receivables_table(company="NonExistentCompany_999")
		iso_si_names = [r["invoice_no"] for r in res_isolated_rtbl]
		self.assertNotIn(si.name, iso_si_names)
