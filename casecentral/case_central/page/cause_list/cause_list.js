frappe.pages["cause-list"].on_page_load = function (wrapper) {
  let page = frappe.ui.make_app_page({
    parent: wrapper,
    title: "Cause List",
    single_column: true,
  });
  frappe.require("/assets/casecentral/css/cause_list.css");

  // Add date fields to the header
  let from_date = page.add_field({
    label: "From Date",
    fieldtype: "Date",
    fieldname: "from_date",
    default: frappe.datetime.add_days(frappe.datetime.nowdate(), 0),
    // default: frappe.datetime.nowdate(),
  });

  let to_date = page.add_field({
    label: "To Date",
    fieldtype: "Date",
    fieldname: "to_date",
    default: frappe.datetime.add_days(frappe.datetime.nowdate(), 4),
  });

  // Add primary button to fetch cause list
  page.set_primary_action("Fetch Cause List", () => {
    fetch_cause_list(from_date.get_value(), to_date.get_value());
  });

  // Add main content container
  let content = $(`<div class="cause-list-content"></div>`).appendTo(page.body);
  render_loading_page(content)
  fetch_cause_list(from_date.get_value(), to_date.get_value());
  // Helper function to fetch cause list
  function fetch_cause_list(from_date, to_date) {
    if (!from_date || !to_date) {
      frappe.msgprint(__("Please select both dates"));
      return;
    }
    if (frappe.datetime.get_day_diff(to_date, from_date) > 7) {
      frappe.msgprint(__("Date Difference cannot be more than 7 Days"));
      return;
    }
    if (frappe.datetime.get_day_diff(to_date, from_date) < 0) {
      frappe.msgprint(__("From Date cannot be greater than To Date"));
      return;
    }
    const formatted_from_date = formatDate(from_date);
    const formatted_to_date = formatDate(to_date);

    frappe.call({
      method:
        "casecentral.case_central.doctype.case.case.fetch_cause_list_update",
      freeze: true,
      args: {
        from_date: formatted_from_date,
        to_date: formatted_to_date,
        send_mail: false,
      },
      callback: (r) => {
        if (r && r.message) {
          responseLength = Object.keys(r.message).length;
          if (responseLength > 0) {
            render_cause_list(r.message, content);
          } else {
            render_empty_page(content);
          }
        } else {
          frappe.show_alert(
            __("No cause list data available for the selected dates.")
          );
          render_empty_page(content);
        }
      },
      error: () => {
        frappe.msgprint(__("An error occurred while fetching the cause list."));
      },
    });
  }

  // Function to format dates for API calls (DD/MM/YYYY)
  function formatDate(dateStr) {
    if (!dateStr) return "";
    const parts = dateStr.split("-");
    if (parts.length === 3) {
      return `${parts[2]}/${parts[1]}/${parts[0]}`;
    }
    return dateStr;
  }

  // Helper function to safely parse any date format (DD/MM/YYYY, YYYY-MM-DD, ISO)
  function parseDateParts(dateStr) {
    const monthNames = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
    if (!dateStr) {
      let now = new Date();
      return { day: String(now.getDate()).padStart(2, "0"), month: monthNames[now.getMonth()], year: now.getFullYear() };
    }

    let cleanStr = String(dateStr).split("T")[0];
    let parts = cleanStr.split(/[\/\-]/);

    if (parts.length === 3) {
      if (parts[0].length === 4) {
        // YYYY-MM-DD
        let y = parts[0], m = parseInt(parts[1], 10), d = parts[2];
        return { day: d.padStart(2, "0"), month: monthNames[m - 1] || "Jan", year: y };
      } else {
        // DD/MM/YYYY
        let d = parts[0], m = parseInt(parts[1], 10), y = parts[2];
        return { day: d.padStart(2, "0"), month: monthNames[m - 1] || "Jan", year: y };
      }
    }

    return { day: "01", month: "Jan", year: "2026" };
  }

  // Helper function to render the cause list
  function render_cause_list(data, container) {
    container.empty(); // Clear previous data
    
    if (!data || typeof data !== "object" || Object.keys(data).length === 0) {
      render_empty_page(container);
      return;
    }

    for (let [court, cases] of Object.entries(data)) {
      if (!Array.isArray(cases) || cases.length === 0) continue;

      // Section for each court with count badge
      let section = $(`
        <div class="cause-list-section mt-4 mb-4">
            <div class="d-flex align-items-center justify-content-between mb-3 border-bottom pb-2">
                <h4 class="m-0 text-primary" style="font-weight: 600;">${court}</h4>
                <span class="badge badge-info px-2 py-1" style="font-size: 13px;">${cases.length} ${cases.length === 1 ? 'Case' : 'Cases'}</span>
            </div>
            <div class="cases-container"></div>
        </div>
      `).appendTo(container);

      let cardContainer = section.find(".cases-container");

      // Cards for each case
      cases.forEach((case_item) => {
        let { day, month, year } = parseDateParts(case_item.date);

        let courtHall = case_item.court_hall_no ? `Court Hall No: ${case_item.court_hall_no}` : "Court: In Chambers";
        let slNo = case_item.sl_no ? `<div class="info-label highlighted-info">Serial No: ${case_item.sl_no}</div>` : "";
        let causeListNo = case_item.cause_list_no ? `<div class="info-label highlighted-info">Cause List: ${case_item.cause_list_no}</div>` : "";
        
        let caseNumberDisplay = (case_item.case_type || case_item.case_no) 
          ? `${case_item.case_type || ''} ${case_item.case_no || ''}${case_item.case_year ? '/' + case_item.case_year : ''}`.trim()
          : (case_item.case_title || "Case Record");

        let caseName = case_item.case_name || "";
        let caseLink = caseName 
          ? `<a href="/app/case/${encodeURIComponent(caseName)}" class="badge badge-success ml-2 case-link-badge" data-case-name="${frappe.utils.escape_html(caseName)}" style="font-size: 11px; text-decoration: none; cursor: pointer; display: inline-flex; align-items: center; gap: 4px; padding: 4px 8px; border-radius: 4px;"><i class="fa fa-external-link" style="font-size: 9px;"></i> Tracked in CaseCentral</a>`
          : "";

        let card = $(`
        <article class="case-card mb-3" style="cursor: ${caseName ? 'pointer' : 'default'};">
            <div class="card-layout">
              <div class="card-left">
                <div class="date-section">
                  <div class="date-number">${day}</div>
                  <div class="date-text">
                    <div class="month-year">${month} ${year}</div>
                  </div>
                </div>
                <div class="case-number-section">
                  <div class="info-label highlighted-info">${courtHall}</div>
                  ${slNo}
                  ${causeListNo}
                </div>
              </div>

              <div class="card-right case-info">
                <div class="info-row d-flex align-items-center justify-content-between flex-wrap">
                  <div class="case-title font-weight-bold" style="font-size: 15px;">${frappe.utils.escape_html(case_item.case_title || caseNumberDisplay)}</div>
                  ${caseLink}
                </div>
                
                <div>
                  <div class="info-row case-number-info text-muted my-1">
                    <div class="case-number font-weight-semibold">${frappe.utils.escape_html(caseNumberDisplay)}</div>
                    ${case_item.classification ? `<div class="case-number ml-2">| ${frappe.utils.escape_html(case_item.classification)}</div>` : ''}
                  </div>

                  <div class="info-row my-1">
                    <span class="info-label text-secondary font-weight-bold">Purpose:</span>
                    <span class="info-value ml-1">${frappe.utils.escape_html(case_item.purpose || "Hearing")}</span>
                  </div>
                  <div class="info-row my-1">
                    <span class="info-label text-secondary font-weight-bold">Judges:</span>
                    <span class="info-value ml-1">${frappe.utils.escape_html(case_item.judge || "Honorable Court")}</span>
                  </div>
                </div>
                
                ${case_item.business_details ? `
                <div class="business-section mt-2 pt-2 border-top">
                  <div class="business-title text-uppercase text-muted" style="font-size: 11px; letter-spacing: 0.5px;">Business Details</div>
                  <div class="business-content text-dark" style="font-size: 13px;">${frappe.utils.escape_html(case_item.business_details)}</div>
                </div>` : ''}
              </div>
            </div>
        </article>
        `).appendTo(cardContainer);

        if (caseName) {
          card.on("click", function (e) {
            // Prevent duplicate route changes if child link clicked
            e.preventDefault();
            frappe.set_route("Form", "Case", caseName);
          });

          card.find(".case-link-badge").on("click", function (e) {
            e.preventDefault();
            e.stopPropagation();
            frappe.set_route("Form", "Case", caseName);
          });
        }
      });
    }
  }
};

function render_empty_page(container) {
  container.empty(); // Clear previous data

  // Centered, visually appealing empty state
  let section = $(`
    <div class="lcontainer">
      <h3 style="font-weight: 500; margin-bottom: 8px;">No Cause List Data</h3>
      <div style="font-size: 15px;">There is no cause list data for the selected dates.</div>
    </div>
  `).appendTo(container);
}

function render_loading_page(container) {
  container.empty(); // Clear previous data

  // Loading state with spinner
  let section = $(`
    <div class="lcontainer">
      <div class="spinner-border text-primary mb-3" role="status" style="width: 2.2rem; height: 2.2rem;">
        <span class="sr-only">Loading...</span>
      </div>
      <h4 style="font-weight: 500; margin-bottom: 8px;">Fetching Cause List...</h4>
      <div style="font-size: 14px; color: #6c757d;">Please wait while we retrieve the latest cause list entries.</div>
    </div>
  `).appendTo(container);
}