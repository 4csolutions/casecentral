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

                // Populate first case in current row
                frappe.model.set_value(cdt, cdn, "case", cases[0].name);
                frappe.model.set_value(cdt, cdn, "barcode", cases[0].barcode || "");

                // If multiple cases exist, add additional rows
                if (cases.length > 1) {
                    for (var i = 1; i < cases.length; i++) {
                        var c = cases[i];
                        var exists = (frm.doc.outgoing_files || []).some(function (item) {
                            return item.matter === (c.matter || row.matter) && item.case === c.name;
                        });

                        if (!exists) {
                            var new_row = frm.add_child("outgoing_files");
                            new_row.matter = c.matter || row.matter;
                            new_row.case = c.name || "";
                            new_row.barcode = c.barcode || "";
                        }
                    }
                    frm.refresh_field("outgoing_files");
                }

                frappe.show_alert({
                    message: __("{0} Case(s) added for Matter {1}.", [cases.length, row.matter]),
                    indicator: "green"
                });
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
                var added_count = 0;
                var cases = data.cases || [];

                if (cases.length === 0) {
                    var exists = (frm.doc.outgoing_files || []).some(function (item) {
                        return item.matter === data.matter && !item.case;
                    });
                    if (!exists) {
                        var row = frm.add_child("outgoing_files");
                        row.matter = data.matter;
                        added_count++;
                    }
                } else {
                    cases.forEach(function (c) {
                        var exists = (frm.doc.outgoing_files || []).some(function (item) {
                            return item.matter === (c.matter || data.matter) && item.case === c.name;
                        });
                        if (!exists) {
                            var row = frm.add_child("outgoing_files");
                            row.matter = c.matter || data.matter;
                            row.case = c.name || "";
                            row.barcode = c.barcode || "";
                            added_count++;
                        }
                    });
                }

                frm.refresh_field("outgoing_files");
                if (added_count > 0) {
                    frappe.show_alert({
                        message: __("Added Matter <b>{0}</b> ({1} Case(s)).", [data.matter, added_count]),
                        indicator: "green"
                    });
                } else {
                    frappe.show_alert({
                        message: __("Matter <b>{0}</b> is already in Outgoing Files.", [data.matter]),
                        indicator: "orange"
                    });
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

        var matched_count = 0;
        items_state.forEach(function (item) {
            if (item.barcode === code || item.case === code || item.matter === code) {
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
                    var api_matched = 0;

                    if (data && data.type !== "not_found") {
                        items_state.forEach(function (item) {
                            if (data.type === "matter" && item.matter === data.matter) {
                                item.scanned = true;
                                api_matched++;
                            } else if (data.type === "case" && item.case === data.case_name) {
                                item.scanned = true;
                                api_matched++;
                            } else if (data.barcode && item.barcode === data.barcode) {
                                item.scanned = true;
                                api_matched++;
                            }
                        });
                    }

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