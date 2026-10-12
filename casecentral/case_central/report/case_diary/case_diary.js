// Copyright (c) 2026, 4C Solutions and contributors
// For license information, please see license.txt

frappe.query_reports["Case Diary"] = {
	filters: [
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
			reqd: 1,
			default: frappe.datetime.get_today(),
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
			reqd: 1,
			default: frappe.datetime.get_today(),
		},
		{
			fieldname: "service",
			label: __("Service"),
			fieldtype: "MultiSelectList",
			get_data: function (txt) {
				return frappe.db.get_link_options("Service", txt, { service_type: "Cases" });
			},
		},
		{
			fieldname: "case_stage",
			label: __("Case Stage"),
			fieldtype: "MultiSelectList",
			get_data: function (txt) {
				return frappe.db.get_link_options("Case Stage", txt);
			},
		},
	],
};
