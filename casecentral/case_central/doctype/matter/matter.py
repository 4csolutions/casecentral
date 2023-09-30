# Copyright (c) 2022, 4C Solutions and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import flt
from frappe.model.document import Document
from frappe.utils import add_days, flt, get_datetime, get_time, get_url, nowtime, today

from erpnext import get_default_company
from erpnext.setup.doctype.holiday_list.holiday_list import is_holiday

class Matter(Document):
	def on_submit(self):
		if self.project_template:
			self.copy_from_template()

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

	def copy_from_template(self):
		"""	
		Copy tasks from template		
		"""
		if self.project_template and not frappe.db.get_all("Task", dict(matter=self.name), limit=1):

			# has a template, and no loaded tasks, so lets create
			if not self.expected_start_date:
				# project starts today
				self.expected_start_date = today()

			template = frappe.get_doc("Project Template", self.project_template)

			# create tasks from template
			matter_tasks = []
			tmp_task_details = []
			for task in template.tasks:
				template_task_details = frappe.get_doc("Task", task.task)
				tmp_task_details.append(template_task_details)
				task = self.create_task_from_template(template_task_details)
				matter_tasks.append(task)
			self.dependency_mapping(tmp_task_details, matter_tasks)

	def create_task_from_template(self, task_details):
		return frappe.get_doc(
			dict(
				doctype="Task",
				subject=task_details.subject,
				matter=self.name,
				status="Open",
				exp_start_date=self.calculate_start_date(task_details),
				exp_end_date=self.calculate_end_date(task_details),
				description=task_details.description,
				task_weight=task_details.task_weight,
				type=task_details.type,
				issue=task_details.issue,
				is_group=task_details.is_group,
				color=task_details.color,
				template_task=task_details.name,
			)
		).insert()

	def calculate_start_date(self, task_details):
		self.start_date = add_days(self.expected_start_date, task_details.start)
		self.start_date = self.update_if_holiday(self.start_date)
		return self.start_date

	def calculate_end_date(self, task_details):
		self.end_date = add_days(self.start_date, task_details.duration)
		return self.update_if_holiday(self.end_date)

	def update_if_holiday(self, date):
		holiday_list = get_holiday_list()
		while is_holiday(holiday_list, date):
			date = add_days(date, 1)
		return date

	def dependency_mapping(self, template_tasks, matter_tasks):
		for matter_task in matter_tasks:
			if matter_task.get("template_task"):
				template_task = frappe.get_doc("Task", matter_task.template_task)
			else:
				template_task = list(filter(lambda x: x.subject == matter_task.subject, template_tasks))[0]
				template_task = frappe.get_doc("Task", template_task.name)

			self.check_depends_on_value(template_task, matter_task, matter_tasks)
			self.check_for_parent_tasks(template_task, matter_task, matter_tasks)

	def check_depends_on_value(self, template_task, matter_task, matter_tasks):
		if template_task.get("depends_on") and not matter_task.get("depends_on"):
			for child_task in template_task.get("depends_on"):
				child_task_subject = frappe.db.get_value("Task", child_task.task, "subject")
				corresponding_matter_task = list(
					filter(lambda x: x.subject == child_task_subject, matter_tasks)
				)
				if len(corresponding_matter_task):
					matter_task.reload()  # reload, as it might have been updated in the previous iteration
					matter_task.append("depends_on", {"task": corresponding_matter_task[0].name})
					matter_task.save()

	def check_for_parent_tasks(self, template_task, matter_task, matter_tasks):
		if template_task.get("parent_task") and not matter_task.get("parent_task"):
			parent_task_subject = frappe.db.get_value("Task", template_task.get("parent_task"), "subject")
			corresponding_matter_task = list(
				filter(lambda x: x.subject == parent_task_subject, matter_tasks)
			)
			if len(corresponding_matter_task):
				matter_task.parent_task = corresponding_matter_task[0].name
				matter_task.save()

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
	
def get_holiday_list(company=None):
	if not company:
		company = get_default_company() or frappe.get_all("Company")[0].name

	holiday_list = frappe.get_cached_value("Company", company, "default_holiday_list")
	if not holiday_list:
		frappe.throw(
			_("Please set a default Holiday List for Company {0}").format(
				frappe.bold(get_default_company())
			)
		)
	return holiday_list
