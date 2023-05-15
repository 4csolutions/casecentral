
frappe.views.calendar["Customer Appointment"] = {
	field_map: {
		"start": "start",
		"end": "end",
		"id": "name",
		"title": "customer",
		"allDay": "allDay",
		"eventColor": "color"
	},
	order_by: "appointment_date",
	gantt: true,
	get_events_method: "casecentral.case_central.doctype.customer_appointment.customer_appointment.get_events"
};
