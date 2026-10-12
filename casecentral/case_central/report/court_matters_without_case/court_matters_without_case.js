// Copyright (c) 2026, 4C Solutions and contributors
// For license information, please see license.txt

frappe.query_reports["Court Matters without Case"] = {
	filters: [
		{
			fieldname: "service",
			label: __("Service"),
			fieldtype: "MultiSelectList",
			get_data: function (txt) {
				return frappe.db.get_link_options("Service", txt, { service_type: "Cases" });
			},
		},
		{
			fieldname: "status",
			label: __("Status"),
			fieldtype: "MultiSelectList",
			get_data: function (txt) {
				return [
					"Open",
					"Working",
					"Pending",
					"Completed",
					"Cancelled",
				]
					.filter((d) => d.toLowerCase().includes((txt || "").toLowerCase()))
					.map((d) => ({ value: d, description: d }));
			},
		},
	],
};
