import frappe

def after_insert(self, method):
	appointment_status = frappe.db.get_value("Customer Appointment", self.appointment, "status")
	if self.appointment and appointment_status == 'Open':
		frappe.db.set_value("Customer Appointment", self.appointment, "status", "In-Progress")

def after_delete(self, method):
	appointment_status = frappe.db.get_value("Customer Appointment", self.appointment, "status")
	if self.appointment and appointment_status == 'In-Progress':
		frappe.db.set_value("Customer Appointment", self.appointment, "status", "Open")

def on_submit(self, method):
	if self.appointment:
		frappe.db.set_value("Customer Appointment", self.appointment, "status", "Closed")

def on_cancel(self, method):
	if self.appointment:
		frappe.db.set_value("Customer Appointment", self.appointment, "status", "Open")