# Copyright (c) 2022, 4C Solutions and contributors
# For license information, please see license.txt

import frappe
from frappe.utils import flt
from frappe.model.document import Document

class Matter(Document):
	def on_cancel(self):
		self.db_set("status", "Cancelled")

		for task in frappe.get_all("Task", dict(matter=self.name)):
			frappe.db.set_value("Task", task.name, "status", "Cancelled")

	def update_matter_status(self):
		if self.status == "Cancelled":
			return

		if frappe.db.exists("Case", dict(matter=self.name)):
			case_status = frappe.db.get_all("Case", filters={"matter": self.name}, pluck="status")[0]
			if case_status in ["InProgress", "Pending"]:
				self.status = "Working"
			else:
				self.status = "Completed"
		else:
			total = frappe.db.count("Task", dict(matter=self.name))
			cancelled = frappe.db.sql(
					"""select count(name) from tabTask where
					matter=%s and status in ('Cancelled')""",
					self.name,
				)[0][0]
			
			if not total:
				self.status = "Open"
			elif flt(cancelled) == total:
				self.status = "Cancelled"
			else:
				open = frappe.db.sql(
					"""select count(name) from tabTask where
					matter=%s and status in ('Open', 'Cancelled')""",
					self.name,
				)[0][0]
				if flt(open) == total:
					self.status = "Open"
				else:
					self.status = "Working"
				
				completed = frappe.db.sql(
					"""select count(name) from tabTask where
					matter=%s and status in ('Completed', 'Cancelled')""",
					self.name,
				)[0][0]
				if flt(completed) == total:
					self.status = "Completed"
				else:
					pending = frappe.db.sql(
						"""select count(name) from tabTask where
						matter=%s and status in ('Pending Review', 'Cancelled')""",
						self.name,
					)[0][0]
					if flt(pending) == total:
						self.status = "Pending"
		
		self.db_update()
		self.reload()
	
	@frappe.whitelist()
	def get_billing_info(self):
		filters = {'docstatus': 1, 'customer': self.customer, 'matter': self.name}

		total_advances = 0
		matter_total_advances = frappe.db.sql("""select 
												custom_matter, sum(unallocated_amount) as total_advances
											from `tabPayment Entry` pe											 
											where												
												docstatus = 1 and unallocated_amount > 0
												and custom_matter=%s 												
										""", (self.name), as_dict=1)
		total_advances = flt(matter_total_advances[0]["total_advances"])

		fields = ["customer", "sum(grand_total) as grand_total", "sum(base_grand_total) as base_grand_total"]
		matter_grand_total = frappe.get_all("Sales Invoice", filters=filters, fields=fields)

		filters['status'] = ['not in', 'Paid']
		fields = ["customer", "sum(outstanding_amount) as outstanding_amount"]
		matter_total_unpaid = frappe.get_all("Sales Invoice", filters=filters, fields=fields)

		company = frappe.defaults.get_user_default('company')
		if not company:
			company = frappe.db.get_value("Global Defaults", None, "default_company")

		company_default_currency = frappe.db.get_value("Company", company, 'default_currency')
		from erpnext.accounts.party import get_party_account_currency
		party_account_currency = get_party_account_currency("Customer", self.customer, company)

		if party_account_currency==company_default_currency:
			billing_this_year = flt(matter_grand_total[0]["base_grand_total"])
		else:
			billing_this_year = flt(matter_grand_total[0]["grand_total"])

		total_unpaid = flt(matter_total_unpaid[0]["outstanding_amount"])

		info = {}
		info["total_billing"] = flt(billing_this_year) if billing_this_year else 0
		info["currency"] = party_account_currency
		info["total_unpaid"] = flt(total_unpaid) if total_unpaid else 0
		info['total_advances'] = flt(total_advances)
		return info
