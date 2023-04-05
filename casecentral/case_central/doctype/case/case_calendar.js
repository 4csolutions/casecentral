frappe.views.calendar["Case"] = {
	field_map: {
		start: "next_hearing_date",
		end: "next_hearing_date",
		id: "name",
		title: "title",
		status: "status"
	},
    gantt: false,
	get_events_method: "casecentral.case_central.doctype.case.case.get_events",
};
