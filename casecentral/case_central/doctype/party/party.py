# Copyright (c) 2024, 4C Solutions and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document

class Party(Document):
	def get_address(self):
		address = ""
		if self.salutation:
			address += self.salutation + " "
		if self.first_name:
			address += self.first_name
		if self.relationship:
			address += " " + self.relationship
		if self.relatives_name:
			address += " " + self.relatives_name
		if self.address_line_1:
			address += "\n" + self.address_line_1
		if self.address_line_2:
			address += "\n" + self.address_line_2
		if self.mobile_number:
			address += "\n" + self.mobile_number
		return address