# Copyright (c) 2023, 4C Solutions and contributors
# For license information, please see license.txt

import json

import frappe
from frappe.model.document import Document

class Case(Document):
	def on_update(self):
		case_history = frappe.db.get_all('Case History', filters = {'parent': self.name}, 
				   fields=['hearing_date'], order_by='hearing_date desc', as_list=True)
		if case_history:
			frappe.db.set_value(self.doctype, self.name, 'next_hearing_date', case_history[0][0])
			self.reload()

@frappe.whitelist()
def get_events(start, end, filters=None):
	"""Returns events for Gantt / Calendar view rendering.

	:param start: Start date-time.
	:param end: End date-time.
	:param filters: Filters (JSON).
	"""
	from frappe.desk.calendar import get_event_conditions

	conditions = get_event_conditions("Case", filters)

	data = frappe.db.sql(
		"""
		select
			name, concat(name, CHAR(13), registration_number) as title, status, next_hearing_date
		from
			`tabCase`
		where status="InProgress"
			and (next_hearing_date between %(start)s and %(end)s)
			{conditions}
		""".format(
			conditions=conditions
		),
		{"start": start, "end": end},
		as_dict=True
	)
	return data