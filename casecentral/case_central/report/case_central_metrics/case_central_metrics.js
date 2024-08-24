// Copyright (c) 2024, 4C Solutions and contributors
// For license information, please see license.txt

frappe.query_reports["Case Central Metrics"] = {
  filters: [
    {
      fieldname: "company",
      label: __("Company"),
      fieldtype: "Link",
      options: "Company",
      default: frappe.defaults.get_user_default("Company"),
      reqd: 1,
    },
    {
      fieldname: "report",
      label: __("Report"),
      fieldtype: "Select",
      options: ["Task", "Matter", "Case"],
      default: "Task",
      reqd: 1,
    },
    {
      fieldname: "filter_based_on",
      label: __("Filter Based On"),
      fieldtype: "Select",
      options: ["Fiscal Year", "Date Range"],
      default: ["Fiscal Year"],
      reqd: 1,
      on_change: function () {
        let filter_based_on =
          frappe.query_report.get_filter_value("filter_based_on");
        frappe.query_report.toggle_filter_display(
          "from_fiscal_year",
          filter_based_on === "Date Range"
        );
        frappe.query_report.toggle_filter_display(
          "to_fiscal_year",
          filter_based_on === "Date Range"
        );
        frappe.query_report.toggle_filter_display(
          "period_start_date",
          filter_based_on === "Fiscal Year"
        );
        frappe.query_report.toggle_filter_display(
          "period_end_date",
          filter_based_on === "Fiscal Year"
        );

        frappe.query_report.refresh();
      },
    },
    {
      fieldname: "periodicity",
      label: __("Periodicity"),
      fieldtype: "Select",
      options: [
        { value: "Monthly", label: __("Monthly") },
        { value: "Quarterly", label: __("Quarterly") },
        { value: "Half-Yearly", label: __("Half-Yearly") },
        { value: "Yearly", label: __("Yearly") },
      ],
      default: "Monthly",
      reqd: 1,
    },
    {
      fieldname: "period_start_date",
      label: __("Start Date"),
      fieldtype: "Date",
      hidden: 1,
      reqd: 1,
    },
    {
      fieldname: "period_end_date",
      label: __("End Date"),
      fieldtype: "Date",
      hidden: 1,
      reqd: 1,
    },
    {
      fieldname: "from_fiscal_year",
      label: __("Start Year"),
      fieldtype: "Link",
      options: "Fiscal Year",
      default: erpnext.utils.get_fiscal_year(frappe.datetime.get_today()),
      reqd: 1,
      on_change: () => {
        frappe.model.with_doc(
          "Fiscal Year",
          frappe.query_report.get_filter_value("from_fiscal_year"),
          function (r) {
            let year_start_date = frappe.model.get_value(
              "Fiscal Year",
              frappe.query_report.get_filter_value("from_fiscal_year"),
              "year_start_date"
            );
            frappe.query_report.set_filter_value({
              period_start_date: year_start_date,
            });
          }
        );
      },
    },
    {
      fieldname: "to_fiscal_year",
      label: __("End Year"),
      fieldtype: "Link",
      options: "Fiscal Year",
      default: erpnext.utils.get_fiscal_year(frappe.datetime.get_today()),
      reqd: 1,
      on_change: () => {
        frappe.model.with_doc(
          "Fiscal Year",
          frappe.query_report.get_filter_value("to_fiscal_year"),
          function (r) {
            let year_end_date = frappe.model.get_value(
              "Fiscal Year",
              frappe.query_report.get_filter_value("to_fiscal_year"),
              "year_end_date"
            );
            frappe.query_report.set_filter_value({
              period_end_date: year_end_date,
            });
          }
        );
      },
    },
  ],
  onload: function () {
    let fiscal_year = erpnext.utils.get_fiscal_year(
      frappe.datetime.get_today()
    );

    frappe.model.with_doc("Fiscal Year", fiscal_year, function (r) {
      var fy = frappe.model.get_doc("Fiscal Year", fiscal_year);
      frappe.query_report.set_filter_value({
        period_start_date: fy.year_start_date,
        period_end_date: fy.year_end_date,
      });
    });
  },
};
