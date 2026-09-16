// Copyright (c) 2023, 4C Solutions and contributors
// For license information, please see license.txt
/* eslint-disable */

frappe.ui.reports["Matter Analytics"] = {
    // "filters": [
    //     {
    //         "fieldname":"matter_type",
    //         "label": __("Matter Type"),
    //         "fieldtype": "Link",
    //         "options": "Matter Type"
    //     },
    //     {
    //         "fieldname":"service_type",
    //         "label": __("Service Type"),
    //         "fieldtype": "Link",
    //         "options": "Service Type"
    //     },
    //     {
    //         "fieldname":"service",
    //         "label": __("Service"),
    //         "fieldtype": "Link",
    //         "options": "Service"
    //     },
    //     {
    //         "fieldname":"customer",
    //         "label": __("Customer"),
    //         "fieldtype": "Link",
    //         "options": "Customer"
    //     },
    //     {
    //         "fieldname":"from_date",
    //         "label": __("From Date"),
    //         "fieldtype": "Date",
    //         "default": frappe.datetime.add_months(frappe.datetime.get_today(), -1),
    //         "reqd": 1
    //     },
    //     {
    //         "fieldname":"to_date",
    //         "label": __("To Date"),
    //         "fieldtype": "Date",
    //         "default": frappe.datetime.get_today(),
    //         "reqd": 1
    //     },
    //     {
    //         "fieldname":"chart",
    //         "label": __("Chart"),
    //         "fieldtype": "Select",
    //         "options": "\nMatter Status\nMatter Distribution by Service"
    //     }
    // ],
    "formatter": function(value, row, column, data, default_formatter) {
        if (column.fieldname === "status") {
            value = __(value);
            if (value === "Open") {
                return '<span class="label label-danger">' + value + '</span>';
            } else if (value === "In Progress") {
                return '<span class="label label-warning">' + value + '</span>';
            } else if (value === "Completed") {
                return '<span class="label label-success">' + value + '</span>';
            }
        }
        return default_formatter(value, row, column, data);
    },
    "onload": function(report) {
        report.page.add_menu_item(__("Export as CSV"), function() {
            report.export_report("CSV");
        });
    }
};
