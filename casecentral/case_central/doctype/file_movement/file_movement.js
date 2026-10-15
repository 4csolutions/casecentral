// Copyright (c) 2026, 4C Solutions and Contributors
// See license.txt

frappe.ui.form.on("File Movement", {

    onload: function (frm) {
        setup_scan_outgoing_barcode_input(frm);
        setup_scan_incoming_barcode_input(frm);
        setup_giver_receiver_filter(frm);
    },

    refresh: function (frm) {
        setup_scan_outgoing_barcode_input(frm);
        setup_scan_incoming_barcode_input(frm);
        setup_giver_receiver_filter(frm);

        frm.remove_custom_button("Create Incoming");
        frm.remove_custom_button("Return Missing Files");

        // Single Document Lifecycle:
        // 1. When Outgoing is submitted and Incoming has NOT yet been activated
        if (frm.doc.docstatus === 1 && !frm.doc.has_incoming && frm.doc.status !== "Received") {
            add_create_incoming_button(frm);
        }

        // 2. When Incoming is active and some files are missing
        if (frm.doc.docstatus === 1 && frm.doc.has_incoming && frm.doc.status === "Missing Files") {
            add_return_missing_button(frm);
        }
    },

    giver: function (frm) {
        if (frm.doc.giver && frm.doc.receiver && frm.doc.giver === frm.doc.receiver) {
            frappe.msgprint({
                title: __("Invalid Selection"),
                indicator: "red",
                message: __("Giver and Receiver cannot be the same employee. Please choose a different Receiver.")
            });
            frm.set_value("receiver", "");
        }
    },

    receiver: function (frm) {
        if (frm.doc.giver && frm.doc.receiver && frm.doc.giver === frm.doc.receiver) {
            frappe.msgprint({
                title: __("Invalid Selection"),
                indicator: "red",
                message: __("Giver and Receiver cannot be the same employee. Please choose a different Receiver.")
            });
            frm.set_value("receiver", "");
        }
    },

    scan_outgoing_barcode: function (frm) {
        var val = (frm.doc.scan_outgoing_barcode || "").trim();
        if (!val) return;
        frm.set_value("scan_outgoing_barcode", "");
        process_outgoing_scan(frm, val);
    },

    scan_incoming_barcode: function (frm) {
        var val = (frm.doc.scan_incoming_barcode || "").trim();
        if (!val) return;
        frm.set_value("scan_incoming_barcode", "");
        process_incoming_scan(frm, val);
    }
});


// =========================================================
// GIVER & RECEIVER FILTER (EXCLUDE SAME EMPLOYEE)
// =========================================================

function setup_giver_receiver_filter(frm) {
    frm.set_query("receiver", function () {
        var filters = [];
        if (frm.doc.giver) {
            filters.push(["Employee", "name", "!=", frm.doc.giver]);
        }
        return {
            filters: filters
        };
    });

    frm.set_query("giver", function () {
        var filters = [];
        if (frm.doc.receiver) {
            filters.push(["Employee", "name", "!=", frm.doc.receiver]);
        }
        return {
            filters: filters
        };
    });
}



// =========================================================
// CHILD TABLE: OUTGOING FILES
// =========================================================

frappe.ui.form.on("Barcode File Item", {
    matter: function (frm, cdt, cdn) {
        var row = frappe.get_doc(cdt, cdn);
        if (!row.matter) return;

        // Only auto-expand in outgoing_files when in draft
        if (row.parentfield !== "outgoing_files") return;

        // If a specific case is already selected in this row, don't re-prompt
        if (row.case) return;

        frappe.call({
            method: "casecentral.case_central.doctype.file_movement.file_movement.get_cases_for_matter",
            args: { matter: row.matter },
            freeze: true,
            freeze_message: __("Validating Matter ID & finding Cases..."),
            callback: function (response) {
                var cases = response.message || [];
                if (!cases.length) {
                    frappe.db.get_value("Matter", row.matter, "name").then(res => {
                        if (!res || !res.message || !res.message.name) {
                            frappe.msgprint({
                                title: __("Matter Not Found"),
                                indicator: "red",
                                message: __("Matter ID '<b>{0}</b>' does not exist.", [row.matter])
                            });
                            frappe.model.set_value(cdt, cdn, "matter", "");
                            frappe.model.set_value(cdt, cdn, "case", "");
                            frappe.model.set_value(cdt, cdn, "barcode", "");
                        } else {
                            frappe.show_alert({
                                message: __("Matter {0} added (No linked Cases found).", [row.matter]),
                                indicator: "blue"
                            });
                        }
                    });
                    return;
                }

                if (cases.length === 1) {
                    // Populate single case directly
                    frappe.model.set_value(cdt, cdn, "case", cases[0].name);
                    frappe.model.set_value(cdt, cdn, "barcode", cases[0].barcode || "");
                    frappe.show_alert({
                        message: __("Added Case {0} for Matter {1}.", [cases[0].name, row.matter]),
                        indicator: "green"
                    });
                } else {
                    // Multiple cases exist -> Show selection dialog so user can pick which cases to take
                    show_case_selection_dialog(frm, row.matter, cases, row, function () {
                        if (!row.case) {
                            frappe.model.set_value(cdt, cdn, "matter", "");
                            frappe.model.set_value(cdt, cdn, "barcode", "");
                        }
                    });
                }
            },
            error: function () {
                frappe.model.set_value(cdt, cdn, "matter", "");
                frappe.model.set_value(cdt, cdn, "case", "");
                frappe.model.set_value(cdt, cdn, "barcode", "");
            }
        });
    },

    case: function (frm, cdt, cdn) {
        var row = frappe.get_doc(cdt, cdn);
        if (!row.case) return;

        if (row.parentfield !== "outgoing_files") return;

        frappe.db.get_value("Case", row.case, ["matter", "name"]).then(r => {
            if (r && r.message) {
                if (r.message.matter && !row.matter) {
                    frappe.model.set_value(cdt, cdn, "matter", r.message.matter);
                }
            } else {
                frappe.msgprint({
                    title: __("Case Not Found"),
                    indicator: "red",
                    message: __("Case '<b>{0}</b>' does not exist.", [row.case])
                });
                frappe.model.set_value(cdt, cdn, "case", "");
            }
        });
    }
});


// =========================================================
// SCAN OUTGOING BARCODE (DRAFT OUTGOING SECTION)
// =========================================================

function setup_scan_outgoing_barcode_input(frm) {
    if (!frm.fields_dict.scan_outgoing_barcode) return;

    var field = frm.fields_dict.scan_outgoing_barcode;
    if (field.$input) {
        field.$input.attr("placeholder", __("Scan Barcode / Matter ID / Case to Add to Outgoing Files..."));
        field.$input.off("keydown.fm_out_scan").on("keydown.fm_out_scan", function (e) {
            if (e.which === 13) {
                e.preventDefault();
                var val = $(this).val().trim();
                if (val) {
                    $(this).val("");
                    frm.set_value("scan_outgoing_barcode", "");
                    process_outgoing_scan(frm, val);
                }
            }
        });
    }
}

function process_outgoing_scan(frm, code) {
    if (!code) return;

    frappe.call({
        method: "casecentral.case_central.doctype.file_movement.file_movement.get_scan_information",
        args: { value: code },
        freeze: true,
        freeze_message: __("Resolving scan '{0}'...", [code]),
        callback: function (r) {
            var data = r.message;
            if (!data || data.type === "not_found") {
                frappe.msgprint({
                    title: __("Not Found"),
                    indicator: "red",
                    message: (data && data.message) || __("Scanned value '<b>{0}</b>' does not exist in Case Central.", [code])
                });
                return;
            }

            if (data.type === "matter") {
                var cases = data.cases || [];

                if (cases.length === 0) {
                    var exists = (frm.doc.outgoing_files || []).some(function (item) {
                        return item.matter === data.matter && !item.case;
                    });
                    if (!exists) {
                        var row = frm.add_child("outgoing_files");
                        row.matter = data.matter;
                        frm.refresh_field("outgoing_files");
                        frappe.show_alert({
                            message: __("Added Matter <b>{0}</b> (No linked Cases found).", [data.matter]),
                            indicator: "blue"
                        });
                    } else {
                        frappe.show_alert({
                            message: __("Matter <b>{0}</b> is already in Outgoing Files.", [data.matter]),
                            indicator: "orange"
                        });
                    }
                } else if (cases.length === 1) {
                    var c = cases[0];
                    var exists = (frm.doc.outgoing_files || []).some(function (item) {
                        return item.case === c.name;
                    });
                    if (!exists) {
                        var row = frm.add_child("outgoing_files");
                        row.matter = c.matter || data.matter;
                        row.case = c.name || "";
                        row.barcode = c.barcode || "";
                        frm.refresh_field("outgoing_files");
                        frappe.show_alert({
                            message: __("Added Case <b>{0}</b> for Matter <b>{1}</b>.", [c.name, data.matter]),
                            indicator: "green"
                        });
                    } else {
                        frappe.show_alert({
                            message: __("Case <b>{0}</b> is already in Outgoing Files.", [c.name]),
                            indicator: "orange"
                        });
                    }
                } else {
                    // Multiple cases exist -> Show selection modal
                    show_case_selection_dialog(frm, data.matter, cases, null, null);
                }

            } else if (data.type === "case") {
                var exists = (frm.doc.outgoing_files || []).some(function (item) {
                    return item.case === data.case_name;
                });
                if (exists) {
                    frappe.show_alert({
                        message: __("Case <b>{0}</b> is already in Outgoing Files.", [data.case_name]),
                        indicator: "orange"
                    });
                    return;
                }

                var row = frm.add_child("outgoing_files");
                row.matter = data.matter || "";
                row.case = data.case_name;
                row.barcode = data.barcode || "";
                frm.refresh_field("outgoing_files");

                frappe.show_alert({
                    message: __("Added Case <b>{0}</b> to Outgoing Files.", [data.case_name]),
                    indicator: "green"
                });

            } else if (data.type === "case_file") {
                var exists = (frm.doc.outgoing_files || []).some(function (item) {
                    return item.barcode === data.barcode;
                });
                if (exists) {
                    frappe.show_alert({
                        message: __("Barcode <b>{0}</b> is already in Outgoing Files.", [data.barcode]),
                        indicator: "orange"
                    });
                    return;
                }

                var row = frm.add_child("outgoing_files");
                row.matter = data.matter || "";
                row.case = data.case || "";
                row.barcode = data.barcode;
                frm.refresh_field("outgoing_files");

                frappe.show_alert({
                    message: __("Added Barcode <b>{0}</b> to Outgoing Files.", [data.barcode]),
                    indicator: "green"
                });
            }
        }
    });
}


// =========================================================
// MULTI-CASE SELECTION DIALOG (WHEN MATTER HAS MULTIPLE CASES)
// =========================================================

function show_case_selection_dialog(frm, matter, cases, target_row, on_cancel) {
    cases = cases || [];
    var existing_cases = new Set(
        (frm.doc.outgoing_files || [])
            .map(function (item) { return (item.case || "").trim(); })
            .filter(Boolean)
    );

    if (target_row && target_row.case) {
        existing_cases.delete(target_row.case.trim());
    }

    var available_count = cases.filter(function (c) {
        return !existing_cases.has(c.name);
    }).length;

    if (available_count === 0) {
        frappe.msgprint({
            title: __("Cases Already Added"),
            indicator: "orange",
            message: __("All {0} case(s) for Matter <b>{1}</b> are already in Outgoing Files.", [cases.length, frappe.utils.escape_html(matter)])
        });
        if (on_cancel) on_cancel();
        return;
    }

    var rows_html = "";
    cases.forEach(function (c) {
        var is_added = existing_cases.has(c.name);
        var barcode_label = c.barcode ? `<span class="badge badge-light" style="font-family: monospace; font-size: 11px; margin-left: 6px; padding: 2px 6px; border: 1px solid var(--border-color);">${frappe.utils.escape_html(c.barcode)}</span>` : "";
        var status_badge = c.status ? `<span class="badge badge-secondary" style="font-size: 11px;">${frappe.utils.escape_html(c.status)}</span>` : "";
        var disabled_attr = is_added ? "disabled" : "";
        var row_style = is_added
            ? "display: flex; align-items: center; justify-content: space-between; padding: 10px 12px; margin-bottom: 6px; border: 1px solid var(--border-color); border-radius: 6px; opacity: 0.6; background: var(--bg-light-gray, #f9f9f9);"
            : "display: flex; align-items: center; justify-content: space-between; padding: 10px 12px; margin-bottom: 6px; border: 1px solid var(--border-color); border-radius: 6px; cursor: pointer; background: var(--card-bg, #fff); transition: background 0.15s ease;";
        var already_added_note = is_added ? `<span class="badge badge-warning" style="margin-left: 6px; font-size: 10px;">${__("Already in Outgoing Files")}</span>` : "";
        var title_html = c.case_title ? `<div class="text-muted" style="font-size: 12px; margin-top: 3px;">${frappe.utils.escape_html(c.case_title)}</div>` : "";
        var search_meta = ((c.name || "") + " " + (c.barcode || "") + " " + (c.case_title || "") + " " + (c.status || "")).toLowerCase();

        rows_html += `
            <div class="case-item-card" data-case-name="${frappe.utils.escape_html(c.name)}" data-search="${frappe.utils.escape_html(search_meta)}" style="${row_style}">
                <div style="display: flex; align-items: flex-start; gap: 12px; flex: 1;">
                    <input type="checkbox" class="case-select-checkbox" data-case-name="${frappe.utils.escape_html(c.name)}" ${disabled_attr} style="margin-top: 3px; cursor: pointer; transform: scale(1.15);">
                    <div style="flex: 1;">
                        <div style="display: flex; align-items: center; flex-wrap: wrap; gap: 4px;">
                            <strong style="font-size: 13px; color: var(--text-color);">${frappe.utils.escape_html(c.name)}</strong>
                            ${barcode_label}
                            ${already_added_note}
                        </div>
                        ${title_html}
                    </div>
                </div>
                <div style="margin-left: 12px; text-align: right;">
                    ${status_badge}
                </div>
            </div>
        `;
    });

    var dialog_content = `
        <div class="matter-case-selector-container">
            <div style="margin-bottom: 12px; display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 8px;">
                <div class="text-muted" style="font-size: 13px;">
                    Matter <b class="text-primary">${frappe.utils.escape_html(matter)}</b> has <b>${cases.length}</b> cases. Select the case(s) you want to take:
                </div>
                <div style="display: flex; gap: 8px; align-items: center;">
                    <button type="button" class="btn btn-xs btn-default btn-select-all" style="font-size: 11px;">${__("Select All")}</button>
                    <button type="button" class="btn btn-xs btn-default btn-clear-all" style="font-size: 11px;">${__("Clear All")}</button>
                    <span class="badge badge-info case-selected-counter" style="font-size: 11px; padding: 4px 8px;">0 of ${available_count} selected</span>
                </div>
            </div>

            <div style="margin-bottom: 10px;">
                <input type="text" class="form-control form-control-sm case-filter-input" placeholder="${__("Type to filter cases by ID, barcode, title, or status...")}">
            </div>

            <div class="case-list-scrollable" style="max-height: 320px; overflow-y: auto; border: 1px solid var(--border-color); border-radius: 6px; padding: 6px; background: var(--control-bg, #fafafa);">
                ${rows_html}
            </div>
        </div>
    `;

    var dialog = new frappe.ui.Dialog({
        title: __("Select Cases to Take — Matter {0}", [matter]),
        fields: [
            {
                fieldtype: "HTML",
                fieldname: "cases_html",
                options: dialog_content
            }
        ],
        primary_action_label: __("Add Selected Cases"),
        primary_action: function () {
            var selected = [];
            dialog.$wrapper.find(".case-select-checkbox:checked").each(function () {
                var c_name = $(this).data("case-name");
                var match = cases.find(function (c) { return c.name === c_name; });
                if (match) {
                    selected.push(match);
                }
            });

            if (!selected.length) {
                frappe.msgprint({
                    title: __("No Cases Selected"),
                    indicator: "orange",
                    message: __("Please select at least one case to take, or click Cancel.")
                });
                return;
            }

            dialog._completed = true;
            add_selected_cases_to_outgoing(frm, matter, selected, target_row);
            dialog.hide();
        }
    });

    function update_counter() {
        var count = dialog.$wrapper.find(".case-select-checkbox:checked").length;
        dialog.$wrapper.find(".case-selected-counter").text(`${count} of ${available_count} selected`);
        if (count > 0) {
            dialog.set_primary_action_label(__("Add Selected ({0})", [count]));
        } else {
            dialog.set_primary_action_label(__("Add Selected Cases"));
        }
    }

    dialog.on_page_show = function () {
        var $wrapper = dialog.$wrapper;

        $wrapper.on("click", ".case-item-card", function (e) {
            if ($(e.target).is("input[type='checkbox']")) {
                update_counter();
                return;
            }
            var $cb = $(this).find(".case-select-checkbox");
            if (!$cb.prop("disabled")) {
                $cb.prop("checked", !$cb.prop("checked"));
                update_counter();
            }
        });

        $wrapper.on("input", ".case-filter-input", function () {
            var q = ($(this).val() || "").toLowerCase().trim();
            $wrapper.find(".case-item-card").each(function () {
                var text = $(this).data("search") || "";
                if (!q || text.indexOf(q) !== -1) {
                    $(this).show();
                } else {
                    $(this).hide();
                }
            });
        });

        $wrapper.on("click", ".btn-select-all", function () {
            $wrapper.find(".case-item-card:visible .case-select-checkbox:not(:disabled)").prop("checked", true);
            update_counter();
        });

        $wrapper.on("click", ".btn-clear-all", function () {
            $wrapper.find(".case-select-checkbox:not(:disabled)").prop("checked", false);
            update_counter();
        });

        update_counter();
    };

    dialog.onhide = function () {
        if (!dialog._completed && on_cancel) {
            on_cancel();
        }
    };

    dialog.show();
}

function add_selected_cases_to_outgoing(frm, matter, selected_cases, target_row) {
    if (!selected_cases || !selected_cases.length) return;

    var start_idx = 0;
    if (target_row) {
        var first = selected_cases[0];
        frappe.model.set_value(target_row.doctype, target_row.name, "matter", matter);
        frappe.model.set_value(target_row.doctype, target_row.name, "case", first.name);
        frappe.model.set_value(target_row.doctype, target_row.name, "barcode", first.barcode || "");
        start_idx = 1;
    } else {
        var blank_row = (frm.doc.outgoing_files || []).find(function (r) {
            return !r.matter && !r.case && !r.barcode;
        });
        if (blank_row) {
            var first = selected_cases[0];
            blank_row.matter = matter;
            blank_row.case = first.name;
            blank_row.barcode = first.barcode || "";
            start_idx = 1;
        }
    }

    for (var i = start_idx; i < selected_cases.length; i++) {
        var c = selected_cases[i];
        var exists = (frm.doc.outgoing_files || []).some(function (item) {
            return item.case === c.name;
        });
        if (!exists) {
            var new_row = frm.add_child("outgoing_files");
            new_row.matter = matter;
            new_row.case = c.name;
            new_row.barcode = c.barcode || "";
        }
    }

    frm.refresh_field("outgoing_files");
    frappe.show_alert({
        message: __("Added {0} Case(s) for Matter <b>{1}</b> to Outgoing Files.", [selected_cases.length, frappe.utils.escape_html(matter)]),
        indicator: "green"
    });
}


// =========================================================
// RETURN CASE SELECTION DIALOG (WHEN MATTER HAS MULTIPLE MISSING CASES)
// =========================================================

function show_return_case_selection_dialog(matter, cases, on_select, on_cancel) {
    cases = cases || [];
    if (!cases.length) {
        if (on_cancel) on_cancel();
        return;
    }

    var available_count = cases.length;

    var rows_html = "";
    cases.forEach(function (c) {
        var barcode_label = c.barcode ? `<span class="badge badge-light" style="font-family: monospace; font-size: 11px; margin-left: 6px; padding: 2px 6px; border: 1px solid var(--border-color);">${frappe.utils.escape_html(c.barcode)}</span>` : "";
        var status_badge = c.status ? `<span class="badge badge-secondary" style="font-size: 11px;">${frappe.utils.escape_html(c.status)}</span>` : "";
        var title_html = c.case_title ? `<div class="text-muted" style="font-size: 12px; margin-top: 3px;">${frappe.utils.escape_html(c.case_title)}</div>` : "";
        var search_meta = ((c.case || "") + " " + (c.barcode || "") + " " + (c.case_title || "") + " " + (c.status || "")).toLowerCase();

        rows_html += `
            <div class="return-case-item-card" data-case-name="${frappe.utils.escape_html(c.case || '')}" data-search="${frappe.utils.escape_html(search_meta)}" style="display: flex; align-items: center; justify-content: space-between; padding: 10px 12px; margin-bottom: 6px; border: 1px solid var(--border-color); border-radius: 6px; cursor: pointer; background: var(--card-bg, #fff); transition: background 0.15s ease;">
                <div style="display: flex; align-items: flex-start; gap: 12px; flex: 1;">
                    <input type="checkbox" class="return-case-select-checkbox" data-case-name="${frappe.utils.escape_html(c.case || '')}" style="margin-top: 3px; cursor: pointer; transform: scale(1.15);">
                    <div style="flex: 1;">
                        <div style="display: flex; align-items: center; flex-wrap: wrap; gap: 4px;">
                            <strong style="font-size: 13px; color: var(--text-color);">${frappe.utils.escape_html(c.case || c.barcode || '')}</strong>
                            ${barcode_label}
                        </div>
                        ${title_html}
                    </div>
                </div>
                <div style="margin-left: 12px; text-align: right;">
                    ${status_badge}
                </div>
            </div>
        `;
    });

    var dialog_content = `
        <div class="return-matter-case-selector-container">
            <div style="margin-bottom: 12px; display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 8px;">
                <div class="text-muted" style="font-size: 13px;">
                    Matter <b class="text-primary">${frappe.utils.escape_html(matter)}</b> has <b>${cases.length}</b> unreturned file(s). Select which case file(s) are being returned:
                </div>
                <div style="display: flex; gap: 8px; align-items: center;">
                    <button type="button" class="btn btn-xs btn-default btn-return-select-all" style="font-size: 11px;">${__("Select All")}</button>
                    <button type="button" class="btn btn-xs btn-default btn-return-clear-all" style="font-size: 11px;">${__("Clear All")}</button>
                    <span class="badge badge-info return-case-selected-counter" style="font-size: 11px; padding: 4px 8px;">0 of ${available_count} selected</span>
                </div>
            </div>

            <div style="margin-bottom: 10px;">
                <input type="text" class="form-control form-control-sm return-case-filter-input" placeholder="${__("Type to filter cases by ID, barcode, title, or status...")}">
            </div>

            <div class="case-list-scrollable" style="max-height: 300px; overflow-y: auto; border: 1px solid var(--border-color); border-radius: 6px; padding: 6px; background: var(--control-bg, #fafafa);">
                ${rows_html}
            </div>
        </div>
    `;

    var dialog = new frappe.ui.Dialog({
        title: __("Select Case File to Return — Matter {0}", [matter]),
        fields: [
            {
                fieldtype: "HTML",
                fieldname: "cases_html",
                options: dialog_content
            }
        ],
        primary_action_label: __("Return Selected File(s)"),
        primary_action: function () {
            var selected = [];
            dialog.$wrapper.find(".return-case-select-checkbox:checked").each(function () {
                var c_name = $(this).data("case-name");
                var match = cases.find(function (c) { return (c.case || "") === c_name; });
                if (match) {
                    selected.push(match);
                }
            });

            if (!selected.length) {
                frappe.msgprint({
                    title: __("No Cases Selected"),
                    indicator: "orange",
                    message: __("Please select at least one case file to return, or click Cancel.")
                });
                return;
            }

            dialog._completed = true;
            dialog.hide();
            if (on_select) on_select(selected);
        }
    });

    function update_counter() {
        var count = dialog.$wrapper.find(".return-case-select-checkbox:checked").length;
        dialog.$wrapper.find(".return-case-selected-counter").text(`${count} of ${available_count} selected`);
        if (count > 0) {
            dialog.set_primary_action_label(__("Return Selected ({0})", [count]));
        } else {
            dialog.set_primary_action_label(__("Return Selected File(s)"));
        }
    }

    dialog.on_page_show = function () {
        var $wrapper = dialog.$wrapper;

        $wrapper.on("click", ".return-case-item-card", function (e) {
            if ($(e.target).is("input[type='checkbox']")) {
                update_counter();
                return;
            }
            var $cb = $(this).find(".return-case-select-checkbox");
            if (!$cb.prop("disabled")) {
                $cb.prop("checked", !$cb.prop("checked"));
                update_counter();
            }
        });

        $wrapper.on("input", ".return-case-filter-input", function () {
            var q = ($(this).val() || "").toLowerCase().trim();
            $wrapper.find(".return-case-item-card").each(function () {
                var text = $(this).data("search") || "";
                if (!q || text.indexOf(q) !== -1) {
                    $(this).show();
                } else {
                    $(this).hide();
                }
            });
        });

        $wrapper.on("click", ".btn-return-select-all", function () {
            $wrapper.find(".return-case-item-card:visible .return-case-select-checkbox").prop("checked", true);
            update_counter();
        });

        $wrapper.on("click", ".btn-return-clear-all", function () {
            $wrapper.find(".return-case-select-checkbox").prop("checked", false);
            update_counter();
        });

        update_counter();
    };

    dialog.onhide = function () {
        if (!dialog._completed && on_cancel) {
            on_cancel();
        }
    };

    dialog.show();
}


// =========================================================
// SCAN INCOMING BARCODE (SUBMITTED INCOMING SECTION)
// =========================================================

function setup_scan_incoming_barcode_input(frm) {
    if (!frm.fields_dict.scan_incoming_barcode) return;

    var field = frm.fields_dict.scan_incoming_barcode;
    if (field.$input) {
        field.$input.attr("placeholder", __("Scan Barcode / Matter ID / Case to Receive into Incoming Files..."));
        field.$input.off("keydown.fm_inc_scan").on("keydown.fm_inc_scan", function (e) {
            if (e.which === 13) {
                e.preventDefault();
                var val = $(this).val().trim();
                if (val) {
                    $(this).val("");
                    frm.set_value("scan_incoming_barcode", "");
                    process_incoming_scan(frm, val);
                }
            }
        });
    }
}

function process_incoming_scan(frm, code) {
    if (!code) return;

    frappe.call({
        method: "casecentral.case_central.doctype.file_movement.file_movement.scan_incoming_file",
        args: {
            movement_name: frm.doc.name,
            value: code
        },
        freeze: true,
        freeze_message: __("Recording incoming scan '{0}'...", [code]),
        callback: function (r) {
            if (!r.message) return;
            var res = r.message;

            if (res.status === "error") {
                frappe.msgprint({
                    title: __("Not Found in Outgoing Files"),
                    indicator: "red",
                    message: res.message
                });
            } else if (res.status === "warning") {
                frappe.show_alert({
                    message: res.message,
                    indicator: "orange"
                });
            } else if (res.status === "multiple_cases") {
                // Matter has multiple unreturned files -> Prompt user to select which one(s) to return
                show_return_case_selection_dialog(res.matter, res.cases, function (selected_cases) {
                    frappe.call({
                        method: "casecentral.case_central.doctype.file_movement.file_movement.return_missing_files",
                        args: {
                            movement_name: frm.doc.name,
                            files: JSON.stringify(selected_cases)
                        },
                        freeze: true,
                        freeze_message: __("Returning selected case file(s)..."),
                        callback: function (resp) {
                            if (resp.message) {
                                var ret_res = resp.message;
                                frappe.show_alert({
                                    message: ret_res.status === "Received"
                                        ? __("All missing files returned! Movement marked as Received.")
                                        : __("Returned {0} case file(s) for Matter <b>{1}</b>.", [selected_cases.length, frappe.utils.escape_html(res.matter)]),
                                    indicator: ret_res.status === "Received" ? "green" : "blue"
                                });
                                frm.reload_doc();
                            }
                        }
                    });
                });
            } else if (res.status === "success") {
                frappe.show_alert({
                    message: res.message,
                    indicator: res.movement_status === "Received" ? "green" : "blue"
                });
                frm.reload_doc();
            }
        }
    });
}


// =========================================================
// ACTION: CREATE INCOMING (STANDALONE PRIMARY BUTTON)
// =========================================================

function add_create_incoming_button(frm) {
    var btn = frm.add_custom_button(__("Create Incoming"), function () {
        frappe.confirm(
            __("Do you want to initialize the Incoming Files workflow for this movement?"),
            function () {
                frappe.call({
                    method: "casecentral.case_central.doctype.file_movement.file_movement.create_incoming",
                    args: {
                        movement_name: frm.doc.name
                    },
                    freeze: true,
                    freeze_message: __("Initializing Incoming Files..."),
                    callback: function (r) {
                        if (r.message) {
                            frappe.show_alert({
                                message: __("Incoming Files table activated. You can now scan returned files."),
                                indicator: "green"
                            });
                            frm.reload_doc();
                        }
                    }
                });
            }
        );
    });

    if (btn) {
        btn.addClass("btn-primary");
    }
}


// =========================================================
// ACTION: RETURN MISSING FILES (SCANNER MODAL)
// =========================================================

function add_return_missing_button(frm) {
    var btn = frm.add_custom_button(__("Return Missing Files"), function () {
        frappe.call({
            method: "casecentral.case_central.doctype.file_movement.file_movement.get_missing_files",
            args: {
                movement_name: frm.doc.name
            },
            freeze: true,
            freeze_message: __("Loading missing files..."),
            callback: function (r) {
                var missing_files = r.message || [];
                if (!missing_files.length) {
                    frappe.msgprint(__("There are no missing files in this movement."));
                    return;
                }
                show_return_missing_modal(frm, missing_files);
            }
        });
    });

    if (btn) {
        btn.addClass("btn-primary");
    }
}

function show_return_missing_modal(frm, missing_files) {
    var items_state = missing_files.map(function (item) {
        return {
            barcode: item.barcode || "",
            matter: item.matter || "",
            case: item.case || "",
            case_title: item.case_title || "",
            status: item.status || "",
            scanned: false
        };
    });

    var dialog = new frappe.ui.Dialog({
        title: __("Return Missing Files"),
        fields: [
            {
                fieldname: "quick_scan",
                label: __("Scan Barcode / Matter ID / Case to Return"),
                fieldtype: "Data",
                options: "Barcode",
                description: __("Scan using barcode gun, click scanner icon for camera, or enter Matter ID / Case ID")
            },
            {
                fieldname: "missing_table_area",
                fieldtype: "HTML"
            }
        ],
        primary_action_label: __("Return Scanned Files"),
        primary_action: function () {
            var selected_items = items_state.filter(function (item) {
                return item.scanned;
            });

            if (!selected_items.length) {
                frappe.msgprint({
                    title: __("No Files Scanned"),
                    indicator: "orange",
                    message: __("Please scan or enter at least one missing Matter ID, Case, or Barcode before submitting return.")
                });
                return;
            }

            frappe.call({
                method: "casecentral.case_central.doctype.file_movement.file_movement.return_missing_files",
                args: {
                    movement_name: frm.doc.name,
                    files: JSON.stringify(selected_items)
                },
                freeze: true,
                freeze_message: __("Returning scanned files into Incoming Files..."),
                callback: function (response) {
                    if (response.message) {
                        var res = response.message;
                        frappe.show_alert({
                            message: res.status === "Received"
                                ? __("All missing files returned successfully! Movement marked as Received.")
                                : __("{0} file(s) returned. Some files remain missing.", [selected_items.length]),
                            indicator: res.status === "Received" ? "green" : "orange"
                        });
                        dialog.hide();
                        frm.reload_doc();
                    }
                }
            });
        }
    });

    function update_table_view() {
        var html = render_missing_table_html(items_state);
        dialog.fields_dict.missing_table_area.$wrapper.html(html);
    }

    dialog.show();
    update_table_view();

    function match_and_mark_scanned(code) {
        if (!code) return;
        code = code.trim();

        // 1. Check if scanned code matches a Matter in missing items
        var matter_matches = items_state.filter(function (item) {
            return (item.matter || "").trim().toLowerCase() === code.toLowerCase();
        });

        if (matter_matches.length > 0) {
            var unscanned = matter_matches.filter(function (item) { return !item.scanned; });
            if (unscanned.length === 0) {
                frappe.show_alert({
                    message: __("All files for Matter <b>{0}</b> are already marked for return.", [code]),
                    indicator: "orange"
                });
                dialog.set_value("quick_scan", "");
                return;
            }

            if (unscanned.length === 1) {
                unscanned[0].scanned = true;
                update_table_view();
                frappe.show_alert({
                    message: __("Scanned & verified file for Matter <b>{0}</b>.", [code]),
                    indicator: "green"
                });
                dialog.set_value("quick_scan", "");
                setTimeout(function () {
                    dialog.fields_dict.quick_scan?.$input?.focus();
                }, 100);
                return;
            }

            // Multiple unreturned files for this matter -> prompt selection dialog!
            show_return_case_selection_dialog(matter_matches[0].matter, unscanned, function (selected_cases) {
                selected_cases.forEach(function (sel) {
                    var target = items_state.find(function (item) {
                        return item.matter === sel.matter && item.case === sel.case;
                    });
                    if (target) {
                        target.scanned = true;
                    }
                });
                update_table_view();
                frappe.show_alert({
                    message: __("Verified {0} file(s) for Matter <b>{1}</b>.", [selected_cases.length, code]),
                    indicator: "green"
                });
                dialog.set_value("quick_scan", "");
                setTimeout(function () {
                    dialog.fields_dict.quick_scan?.$input?.focus();
                }, 100);
            });
            return;
        }

        // 2. Direct match by barcode or case
        var matched_count = 0;
        items_state.forEach(function (item) {
            if (item.barcode === code || item.case === code) {
                item.scanned = true;
                matched_count++;
            }
        });

        if (matched_count > 0) {
            update_table_view();
            frappe.show_alert({
                message: __("Scanned & verified: <b>{0}</b> ({1} item(s)).", [code, matched_count]),
                indicator: "green"
            });
            dialog.set_value("quick_scan", "");
            setTimeout(function () {
                dialog.fields_dict.quick_scan?.$input?.focus();
            }, 100);
        } else {
            frappe.call({
                method: "casecentral.case_central.doctype.file_movement.file_movement.get_scan_information",
                args: { value: code },
                callback: function (r) {
                    var data = r.message;
                    if (!data || data.type === "not_found") {
                        frappe.show_alert({
                            message: __("Code <b>{0}</b> is not in the missing files list for this movement.", [code]),
                            indicator: "orange"
                        });
                        dialog.set_value("quick_scan", "");
                        setTimeout(function () {
                            dialog.fields_dict.quick_scan?.$input?.focus();
                        }, 100);
                        return;
                    }

                    if (data.type === "matter") {
                        var m_unscanned = items_state.filter(function (item) {
                            return item.matter === data.matter && !item.scanned;
                        });
                        if (m_unscanned.length === 0) {
                            frappe.show_alert({
                                message: __("All files for Matter <b>{0}</b> are already marked for return.", [data.matter]),
                                indicator: "orange"
                            });
                        } else if (m_unscanned.length === 1) {
                            m_unscanned[0].scanned = true;
                            update_table_view();
                            frappe.show_alert({
                                message: __("Scanned & verified file for Matter <b>{0}</b>.", [data.matter]),
                                indicator: "green"
                            });
                        } else {
                            show_return_case_selection_dialog(data.matter, m_unscanned, function (selected_cases) {
                                selected_cases.forEach(function (sel) {
                                    var target = items_state.find(function (item) {
                                        return item.matter === sel.matter && item.case === sel.case;
                                    });
                                    if (target) {
                                        target.scanned = true;
                                    }
                                });
                                update_table_view();
                                frappe.show_alert({
                                    message: __("Marked {0} file(s) for Matter <b>{1}</b> as returned.", [selected_cases.length, data.matter]),
                                    indicator: "green"
                                });
                            });
                        }
                    } else {
                        var api_matched = 0;
                        items_state.forEach(function (item) {
                            if (data.type === "case" && item.case === data.case_name) {
                                item.scanned = true;
                                api_matched++;
                            } else if (data.barcode && item.barcode === data.barcode) {
                                item.scanned = true;
                                api_matched++;
                            }
                        });

                        if (api_matched > 0) {
                            update_table_view();
                            frappe.show_alert({
                                message: __("Scanned & verified: <b>{0}</b> ({1} item(s)).", [code, api_matched]),
                                indicator: "green"
                            });
                        } else {
                            frappe.show_alert({
                                message: __("Code <b>{0}</b> is not in the missing files list for this movement.", [code]),
                                indicator: "orange"
                            });
                        }
                    }

                    dialog.set_value("quick_scan", "");
                    setTimeout(function () {
                        dialog.fields_dict.quick_scan?.$input?.focus();
                    }, 100);
                }
            });
        }
    }

    setTimeout(function () {
        var field = dialog.fields_dict.quick_scan;
        var $input = field?.$input;
        if ($input) {
            $input.focus();

            $input.off("keydown.return_scan").on("keydown.return_scan", function (e) {
                if (e.which === 13) {
                    e.preventDefault();
                    var code = $(this).val().trim();
                    if (code) {
                        $(this).val("");
                        match_and_mark_scanned(code);
                    }
                }
            });

            $input.off("change.return_scan").on("change.return_scan", function () {
                var code = $(this).val().trim();
                if (code) {
                    $(this).val("");
                    match_and_mark_scanned(code);
                }
            });
        }
    }, 200);
}

function render_missing_table_html(items) {
    var scanned_count = items.filter(function (it) { return it.scanned; }).length;
    var total_count = items.length;

    var rows_html = items.map(function (item, idx) {
        var row_bg = item.scanned ? "background-color: #f0fdf4;" : "";
        var badge_html = item.scanned
            ? '<span class="badge" style="background-color: #dcfce7; color: #15803d; font-weight: 600; padding: 4px 8px; border-radius: 4px;"><i class="fa fa-check" style="margin-right: 4px;"></i>' + __("Scanned to Return") + '</span>'
            : '<span class="badge" style="background-color: #fef3c7; color: #b45309; font-weight: 500; padding: 4px 8px; border-radius: 4px;">' + __("Pending Scan") + '</span>';

        return '<tr style="' + row_bg + '">' +
            '<td style="text-align: center; color: #64748b; font-weight: 500;">' + (idx + 1) + '</td>' +
            '<td style="font-weight: 600; color: #1e293b;">' + (item.matter || "-") + '</td>' +
            '<td>' + (item.case || "-") + '</td>' +
            '<td><code>' + (item.barcode || "-") + '</code></td>' +
            '<td style="text-align: center;">' + badge_html + '</td>' +
            '</tr>';
    }).join("");

    return '<div style="margin-top: 15px;">' +
        '<div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">' +
        '<span style="font-size: 13px; font-weight: 600; color: #334155;">' + __("Missing Files List ({0})", [total_count]) + '</span>' +
        '<span style="font-size: 12px; font-weight: 600; color: ' + (scanned_count > 0 ? '#16a34a' : '#64748b') + ';">' +
        __("{0} of {1} Scanned", [scanned_count, total_count]) +
        '</span>' +
        '</div>' +
        '<div style="max-height: 240px; overflow-y: auto; border: 1px solid #e2e8f0; border-radius: 6px;">' +
        '<table class="table table-bordered table-condensed" style="margin: 0; font-size: 12px;">' +
        '<thead style="background-color: #f8fafc; position: sticky; top: 0; z-index: 1;">' +
        '<tr>' +
        '<th style="width: 35px; text-align: center; color: #475569;">#</th>' +
        '<th style="color: #475569;">' + __("Matter") + '</th>' +
        '<th style="color: #475569;">' + __("Case") + '</th>' +
        '<th style="color: #475569;">' + __("Barcode") + '</th>' +
        '<th style="width: 140px; text-align: center; color: #475569;">' + __("Status") + '</th>' +
        '</tr>' +
        '</thead>' +
        '<tbody>' +
        rows_html +
        '</tbody>' +
        '</table>' +
        '</div>' +
        '</div>';
}