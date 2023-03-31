# Copyright (c) 2023, 4C Solutions and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

class Case(Document):
	def on_update(self):
		case_history = frappe.db.get_all('Case History', filters = {'parent': self.name}, 
				   fields=['hearing_date'], order_by='hearing_date desc', as_list=True)
		if case_history:
			frappe.db.set_value(self.doctype, self.name, 'next_hearing_date', case_history[0][0])
			self.reload()