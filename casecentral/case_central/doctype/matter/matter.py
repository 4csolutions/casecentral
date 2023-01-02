# Copyright (c) 2022, 4C Solutions and contributors
# For license information, please see license.txt

import frappe
from frappe.utils import flt
from frappe.model.document import Document

class Matter(Document):
	def on_cancel(self):
		self.status = "Cancelled"

		for task in frappe.get_all("Task", dict(matter=self.name)):
			frappe.db.set_value("Task", task.name, "status", "Cancelled")

	def update_matter_status(self):
		if self.status == "Cancelled":
			return

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