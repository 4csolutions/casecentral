import frappe

def on_submit(self, method):
	if self.appointment:
		frappe.db.set_value("Customer Appointment", self.appointment, "status", "Closed")

def on_cancel(self, method):
	if self.appointment:
		frappe.db.set_value("Customer Appointment", self.appointment, "status", "Open")