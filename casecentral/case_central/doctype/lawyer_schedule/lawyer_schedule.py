# Copyright (c) 2023, 4C Solutions and contributors
# For license information, please see license.txt


from frappe.model.document import Document


class LawyerSchedule(Document):
	def autoname(self):
		self.name = self.schedule_name
