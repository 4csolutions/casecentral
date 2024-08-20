import frappe

def after_insert(self, method):
	appointment_status = frappe.db.get_value("Customer Appointment", self.appointment, "status")
	if self.appointment and (appointment_status == 'Open' or 'Scheduled'):
		frappe.db.set_value("Customer Appointment", self.appointment, "status", "In-Progress")

def after_delete(self, method):
	if self.appointment:
		appointment_doc = frappe.get_doc("Customer Appointment", self.appointment)
		if appointment_doc.status == 'In-Progress':
			appointment_doc.set_status()
			appointment_doc.save()

def on_submit(self, method):
	if self.appointment:
		frappe.db.set_value("Customer Appointment", self.appointment, "status", "Closed")

def on_cancel(self, method):
	if self.appointment:
		frappe.db.set_value("Customer Appointment", self.appointment, "status", "Open")