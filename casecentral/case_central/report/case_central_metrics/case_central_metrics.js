// case_central_metrics.js

frappe.query_reports["Case Central Metrics"] = {
  onload: function (report) {
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
    frappe.call({
      method:
        "casecentral.case_central.report.case_central_metrics.case_central_metrics.get_applicable_calendar_years",
      callback: function (r) {
        if (r.message) {
          const applicable_years = r.message;
          let from_year_filter = report.get_filter("from_year");
          let to_year_filter = report.get_filter("to_year");
          // Set options for from_year and to_year
          from_year_filter.df.options = applicable_years[0].join("\n");
          to_year_filter.df.options = applicable_years[0].join("\n");

          // Set defaults
          from_year_filter.set_input(
            applicable_years[applicable_years.length - 1]
          );
          to_year_filter.set_input(
            applicable_years[applicable_years.length - 1]
          );

          from_year_filter.refresh();
          to_year_filter.refresh();
        }
      },
    });
  },

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
      options: ["Calendar Year", "Date Range", "Fiscal Year"],
      default: "Calendar Year",
      reqd: 1,
      on_change: function () {
        let filter_based_on =
          frappe.query_report.get_filter_value("filter_based_on");
        if (filter_based_on === "Calendar Year") {
          frappe.query_report.toggle_filter_display("from_year", false);
          frappe.query_report.toggle_filter_display("to_year", false);
          frappe.query_report.toggle_filter_display("period_start_date", true);
          frappe.query_report.toggle_filter_display("period_end_date", true);
          frappe.query_report.toggle_filter_display("from_fiscal_year", true);
          frappe.query_report.toggle_filter_display("to_fiscal_year", true);
        }
        if (filter_based_on === "Date Range") {
          frappe.query_report.toggle_filter_display("from_year", true);
          frappe.query_report.toggle_filter_display("to_year", true);
          frappe.query_report.toggle_filter_display("period_start_date", false);
          frappe.query_report.toggle_filter_display("period_end_date", false);
          frappe.query_report.toggle_filter_display("from_fiscal_year", true);
          frappe.query_report.toggle_filter_display("to_fiscal_year", true);
        }
        if (filter_based_on === "Fiscal Year") {
          frappe.query_report.toggle_filter_display("from_year", true);
          frappe.query_report.toggle_filter_display("to_year", true);
          frappe.query_report.toggle_filter_display("period_start_date", true);
          frappe.query_report.toggle_filter_display("period_end_date", true);
          frappe.query_report.toggle_filter_display("from_fiscal_year", false);
          frappe.query_report.toggle_filter_display("to_fiscal_year", false);
        }

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
      fieldname: "from_year",
      label: __("Start Year"),
      fieldtype: "Select",
      reqd: 1,
    },
    {
      fieldname: "to_year",
      label: __("End Year"),
      fieldtype: "Select",
      reqd: 1,
    },
    {
      fieldname: "from_fiscal_year",
      label: __("Start Year"),
      fieldtype: "Link",
      options: "Fiscal Year",
      default: erpnext.utils.get_fiscal_year(frappe.datetime.get_today()),
      hidden: 1,
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
      hidden: 1,
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
};
