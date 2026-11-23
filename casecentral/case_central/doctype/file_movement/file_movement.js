// Copyright (c) 2026, 4C Solutions and Contributors
// See license.txt

frappe.listview_settings = frappe.listview_settings || {};
frappe.listview_settings["File Movement"] = {
    has_indicator_for_draft: true,
    add_fields: ["status", "has_incoming"],
    get_indicator: function (doc) {
        if (doc.status === "Received") {
            return [__("Received"), "green", "status,=,Received"];
        } else if (doc.status === "Missing Files") {
            return [__("Missing Files"), "red", "status,=,Missing Files"];
        } else if (doc.status === "Taken Away / Incoming Created" || doc.status === "Incoming Created") {
            return [__("Taken Away / Incoming Created"), "blue", "status,=,Taken Away / Incoming Created"];
        } else if (doc.status === "Taken Away") {
            return [__("Taken Away"), "orange", "status,=,Taken Away"];
        } else if (doc.status === "Incoming Cancelled") {
            return [__("Taken Away"), "orange", "status,=,Taken Away"];
        } else if (doc.status === "Cancelled" || doc.docstatus === 2) {
            return [__("Cancelled"), "red", "status,=,Cancelled"];
        } else if (doc.status === "Draft" || doc.docstatus === 0) {
            return [__("Draft"), "grey", "status,=,Draft"];
        }
    }
};

function update_form_indicator(frm) {
    if (!frm.page) return;
    if (frm.doc.status === "Draft" || frm.doc.docstatus === 0) {
        frm.page.set_indicator(__("Draft"), "grey");
    } else if (frm.doc.status === "Cancelled" || frm.doc.docstatus === 2) {
        frm.page.set_indicator(__("Cancelled"), "red");
    } else if (frm.doc.status === "Received") {
        frm.page.set_indicator(__("Received"), "green");
    } else if (frm.doc.status === "Missing Files") {
        frm.page.set_indicator(__("Missing Files"), "red");
    } else if (frm.doc.status === "Taken Away / Incoming Created" || frm.doc.status === "Incoming Created") {
        frm.page.set_indicator(__("Taken Away / Incoming Created"), "blue");
    } else {
        frm.page.set_indicator(__("Taken Away"), "orange");
    }
}

function invalidate_file_movement_listview() {
    if (frappe.views && frappe.views.list_view && frappe.views.list_view["File Movement"]) {
        var lv = frappe.views.list_view["File Movement"];
        lv.last_args = null;
        if (lv.$page && lv.$page.is(":visible")) {
            lv.refresh();
        }
    }
    if (window.cur_list && cur_list.doctype === "File Movement") {
        cur_list.last_args = null;
        if (cur_list.$page && cur_list.$page.is(":visible")) {
            cur_list.refresh();
        }
    }
}

frappe.ui.form.on("File Movement", {

    onload: function (frm) {
        clear_initial_blank_outgoing_row(frm);
        setup_scan_barcode_input(frm);
        setup_giver_receiver_filter(frm);
        setup_table_grids(frm);

        if (frm.page && frm.page.wrapper) {
            frm.page.wrapper.on("hide", function () {
                invalidate_file_movement_listview();
            });
        }
    },

    after_save: function (frm) {
        invalidate_file_movement_listview();
    },

    on_submit: function (frm) {
        invalidate_file_movement_listview();
    },

    after_cancel: function (frm) {
        invalidate_file_movement_listview();
    },

    refresh: function (frm) {
        clear_initial_blank_outgoing_row(frm);
        setup_scan_barcode_input(frm);
        setup_giver_receiver_filter(frm);
        setup_table_grids(frm);

        frm.remove_custom_button("Create Incoming");
        frm.remove_custom_button("Re-open Incoming");
        frm.remove_custom_button("Cancel Incoming");
        frm.remove_custom_button("Return Missing Files");

        // Single Document Lifecycle:
        // 1. When Outgoing is submitted and Incoming has NOT yet been activated
        if (frm.doc.docstatus === 1 && !frm.doc.has_incoming && frm.doc.status !== "Received" && frm.doc.status !== "Cancelled") {
            add_create_incoming_button(frm);
        }

        // 2. When Incoming is active (Taken Away / Incoming Created, Missing Files, or Received)
        if (frm.doc.docstatus === 1 && frm.doc.has_incoming && frm.doc.status !== "Cancelled") {
            add_cancel_incoming_button(frm);
            if (frm.doc.status === "Missing Files") {
                add_return_missing_button(frm);
            }
        }

        update_form_indicator(frm);
        setTimeout(function () {
            update_form_indicator(frm);
        }, 150);
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

    scan_barcode: function (frm) {
        var val = (frm.doc.scan_barcode || "").trim();
        if (!val) return;
        handle_barcode_scan(frm, val);
    }
});


function clear_initial_blank_outgoing_row(frm) {
    if (frm.is_new() && frm.doc.outgoing_files && frm.doc.outgoing_files.length === 1) {
        var r = frm.doc.outgoing_files[0];
        if (!r.matter && !r.case && !r.barcode) {
            frm.clear_table("outgoing_files");
            frm.refresh_field("outgoing_files");
        }
    }
}

function setup_table_grids(frm) {
    // 1. Outgoing Files table: allow deleting rows in draft
    if (frm.fields_dict.outgoing_files && frm.fields_dict.outgoing_files.grid) {
        var out_grid = frm.fields_dict.outgoing_files.grid;
        out_grid.df.cannot_delete_rows = false;
        out_grid.cannot_delete_rows = false;
    }

    // 2. Incoming Files table: fully editable and allow deleting rows on submitted doc
    if (frm.doc.docstatus === 1 && frm.doc.has_incoming && frm.fields_dict.incoming_files && frm.fields_dict.incoming_files.grid) {
        frm.set_df_property("incoming_files", "read_only", 0);
        var inc_grid = frm.fields_dict.incoming_files.grid;
        inc_grid.static_rows = false;
        inc_grid.cannot_add_rows = false;
        inc_grid.df.cannot_add_rows = false;
        inc_grid.df.cannot_delete_rows = false;
        inc_grid.wrapper.find(".grid-remove-rows, .grid-remove-all-rows, .grid-add-row").removeClass("hidden d-none");
        inc_grid.refresh();
    }
}


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
// HELPER: INCOMING FILE MATCHING & DEDUPLICATION
// =========================================================

function is_file_in_incoming(target, incoming_files, exclude_row) {
    if (!target) return false;
    var t_case = (target.case || "").trim().toLowerCase();
    var t_bc = (target.barcode || "").trim().toLowerCase();
    var t_matter = (target.matter || "").trim().toLowerCase();

    return (incoming_files || []).some(function (r) {
        if (exclude_row && (r === exclude_row || (r.name && exclude_row.name && r.name === exclude_row.name))) {
            return false;
        }
        var r_case = (r.case || "").trim().toLowerCase();
        var r_bc = (r.barcode || "").trim().toLowerCase();
        var r_matter = (r.matter || "").trim().toLowerCase();

        // 1. Direct Case match
        if (t_case && r_case && t_case === r_case) return true;
        // 2. Direct Barcode match
        if (t_bc && r_bc && t_bc === r_bc) return true;
        // 3. Cross-match: Case matches Barcode
        if (t_case && r_bc && t_case === r_bc) return true;
        if (t_bc && r_case && t_bc === r_case) return true;
        // 4. Pure Matter match when neither side has Case or Barcode
        if (!t_case && !t_bc && !r_case && !r_bc && t_matter && r_matter && t_matter === r_matter) {
            return true;
        }
        return false;
    });
}

function is_code_or_item_in_incoming(code, incoming_files) {
    if (!code) return false;
    var c_lower = (code || "").trim().toLowerCase();
    return (incoming_files || []).some(function (r) {
        var r_case = (r.case || "").trim().toLowerCase();
        var r_bc = (r.barcode || "").trim().toLowerCase();
        return (r_case && r_case === c_lower) || (r_bc && r_bc === c_lower);
    });
}


// =========================================================
// CHILD TABLE: OUTGOING & INCOMING FILES
// =========================================================

frappe.ui.form.on("File Movement Item", {
    matter: function (frm, cdt, cdn) {
        var row = frappe.get_doc(cdt, cdn);
        if (!row.matter) return;
        if (row.case) return;

        if (row.parentfield === "incoming_files") {
            var outgoing = frm.doc.outgoing_files || [];
            var incoming = frm.doc.incoming_files || [];
            var unreturned = outgoing.filter(function (out_r) {
                if ((out_r.matter || "").trim().toLowerCase() !== (row.matter || "").trim().toLowerCase()) return false;
                return !is_file_in_incoming(out_r, incoming, row);
            });

            if (!unreturned.length) {
                frappe.msgprint({
                    title: __("Already Returned"),
                    indicator: "orange",
                    message: __("All files for Matter '<b>{0}</b>' are already scanned in Incoming Files.", [frappe.utils.escape_html(row.matter)])
                });
                frappe.model.set_value(cdt, cdn, "matter", "");
                frappe.model.set_value(cdt, cdn, "case", "");
                frappe.model.set_value(cdt, cdn, "barcode", "");
                return;
            }

            if (unreturned.length === 1) {
                frappe.model.set_value(cdt, cdn, "case", unreturned[0].case || "");
                frappe.model.set_value(cdt, cdn, "barcode", unreturned[0].barcode || "");
                update_client_missing_files_and_status(frm);
            } else if (unreturned.length > 1) {
                show_return_case_selection_dialog(row.matter, unreturned, function (selected) {
                    if (selected && selected.length) {
                        frappe.model.set_value(cdt, cdn, "case", selected[0].case || "");
                        frappe.model.set_value(cdt, cdn, "barcode", selected[0].barcode || "");
                        for (var i = 1; i < selected.length; i++) {
                            if (!is_file_in_incoming(selected[i], frm.doc.incoming_files || [])) {
                                var nr = frm.add_child("incoming_files");
                                nr.matter = row.matter;
                                nr.case = selected[i].case || "";
                                nr.barcode = selected[i].barcode || "";
                            }
                        }
                        update_client_missing_files_and_status(frm);
                    }
                });
            }
            return;
        }

        // Outgoing Files
        frappe.call({
            method: "casecentral.case_central.doctype.file_movement.file_movement.get_cases_for_matter",
            args: { matter: row.matter },
            freeze: true,
            freeze_message: __("Validating Matter ID & finding Cases..."),
            callback: function (response) {
                var cases = response.message || [];
                if (!cases.length) {
                    frappe.call({
                        method: "casecentral.case_central.doctype.file_movement.file_movement.get_scan_information",
                        args: { value: row.matter },
                        callback: function (res) {
                            if (!res.message || res.message.type === "not_found") {
                                frappe.msgprint({
                                    title: __("Matter Not Found"),
                                    indicator: "red",
                                    message: __("Matter ID '<b>{0}</b>' does not exist.", [row.matter])
                                });
                                frappe.model.set_value(cdt, cdn, "matter", "");
                                frappe.model.set_value(cdt, cdn, "case", "");
                                frappe.model.set_value(cdt, cdn, "barcode", "");
                                return;
                            }
                            if (row.parentfield === "outgoing_files" && res.message.taken_away) {
                                var m_name = res.message.taken_away_movement || (res.message.taken_away_info && res.message.taken_away_info.movement) || "";
                                frappe.msgprint({
                                    title: __("Matter Already Taken Away"),
                                    indicator: "orange",
                                    message: __(
                                        "Matter '<b>{0}</b>' has already been taken away in File Movement <b>{1}</b> and has not been returned. It cannot be added to Outgoing Files.",
                                        [frappe.utils.escape_html(row.matter), frappe.utils.escape_html(m_name)]
                                    )
                                });
                                frappe.model.set_value(cdt, cdn, "matter", "");
                                frappe.model.set_value(cdt, cdn, "case", "");
                                frappe.model.set_value(cdt, cdn, "barcode", "");
                                if (frm.fields_dict.outgoing_files && frm.fields_dict.outgoing_files.grid) {
                                    var grid_row = frm.fields_dict.outgoing_files.grid.grid_rows_by_docname[cdn];
                                    if (grid_row) {
                                        grid_row.remove();
                                    }
                                }
                                frm.refresh_field("outgoing_files");
                                return;
                            }
                            frappe.show_alert({
                                message: __("Matter {0} added (No linked Cases found).", [row.matter]),
                                indicator: "blue"
                            });
                        }
                    });
                    return;
                }

                if (cases.length === 1) {
                    if (cases[0].taken_away) {
                        var m_name = cases[0].taken_away_info ? cases[0].taken_away_info.movement : (cases[0].taken_away_movement || "");
                        frappe.msgprint({
                            title: __("Case Already Taken Away"),
                            indicator: "orange",
                            message: __(
                                "Case '<b>{0}</b>' for Matter '<b>{1}</b>' has already been taken away in File Movement <b>{2}</b> and has not been returned. It cannot be added to Outgoing Files.",
                                [frappe.utils.escape_html(cases[0].name), frappe.utils.escape_html(row.matter), frappe.utils.escape_html(m_name)]
                            )
                        });
                        frappe.model.set_value(cdt, cdn, "matter", "");
                        frappe.model.set_value(cdt, cdn, "case", "");
                        frappe.model.set_value(cdt, cdn, "barcode", "");
                        if (frm.fields_dict.outgoing_files && frm.fields_dict.outgoing_files.grid) {
                            var grid_row = frm.fields_dict.outgoing_files.grid.grid_rows_by_docname[cdn];
                            if (grid_row) {
                                grid_row.remove();
                            }
                        }
                        frm.refresh_field("outgoing_files");
                        return;
                    }
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
                            if (frm.fields_dict.outgoing_files && frm.fields_dict.outgoing_files.grid) {
                                var grid_row = frm.fields_dict.outgoing_files.grid.grid_rows_by_docname[cdn];
                                if (grid_row) {
                                    grid_row.remove();
                                }
                            }
                            frm.refresh_field("outgoing_files");
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

        frappe.call({
            method: "casecentral.case_central.doctype.file_movement.file_movement.get_scan_information",
            args: { value: row.case },
            callback: function (r) {
                if (!r.message) return;

                if (row.parentfield === "outgoing_files") {
                    var outgoing = frm.doc.outgoing_files || [];
                    var is_dup = outgoing.some(function (r) {
                        if (r === row || (r.name && row.name && r.name === row.name)) return false;
                        var rc = (r.case || "").trim().toLowerCase();
                        var tc = (row.case || "").trim().toLowerCase();
                        return rc && tc && rc === tc;
                    });
                    if (is_dup) {
                        frappe.msgprint({
                            title: __("Duplicate Case"),
                            indicator: "orange",
                            message: __("Case '<b>{0}</b>' is already present in Outgoing Files.", [frappe.utils.escape_html(row.case)])
                        });
                        frappe.model.set_value(cdt, cdn, "case", "");
                        frappe.model.set_value(cdt, cdn, "matter", "");
                        frappe.model.set_value(cdt, cdn, "barcode", "");
                        return;
                    }
                }

                if (row.parentfield === "incoming_files") {
                    var outgoing = frm.doc.outgoing_files || [];
                    var in_outgoing = outgoing.some(function (out_r) {
                        var o_case = (out_r.case || "").trim().toLowerCase();
                        var r_case = (row.case || "").trim().toLowerCase();
                        return o_case && r_case && o_case === r_case;
                    });
                    if (!in_outgoing) {
                        frappe.msgprint({
                            title: __("Invalid File"),
                            indicator: "red",
                            message: __("Case '<b>{0}</b>' is not part of Outgoing Files in this movement.", [frappe.utils.escape_html(row.case)])
                        });
                        frappe.model.set_value(cdt, cdn, "case", "");
                        frappe.model.set_value(cdt, cdn, "barcode", "");
                        frappe.model.set_value(cdt, cdn, "matter", "");
                        return;
                    }

                    var incoming = frm.doc.incoming_files || [];
                    var is_dup = incoming.some(function (r) {
                        if (r === row || (r.name && row.name && r.name === row.name)) return false;
                        var rc = (r.case || "").trim().toLowerCase();
                        var tc = (row.case || "").trim().toLowerCase();
                        return rc && tc && rc === tc;
                    });
                    if (is_dup) {
                        frappe.msgprint({
                            title: __("Duplicate File"),
                            indicator: "orange",
                            message: __("Case '<b>{0}</b>' is already present in Incoming Files.", [frappe.utils.escape_html(row.case)])
                        });
                        frappe.model.set_value(cdt, cdn, "case", "");
                        frappe.model.set_value(cdt, cdn, "barcode", "");
                        frappe.model.set_value(cdt, cdn, "matter", "");
                        return;
                    }
                }

                if (row.parentfield === "outgoing_files" && r.message.taken_away) {
                    var m_name = (r.message.taken_away_info && r.message.taken_away_info.movement) || r.message.taken_away_movement || "";
                    frappe.msgprint({
                        title: __("Case Already Taken Away"),
                        indicator: "orange",
                        message: __(
                            "Case '<b>{0}</b>' has already been taken away in File Movement <b>{1}</b> and has not been returned. It cannot be added to Outgoing Files.",
                            [frappe.utils.escape_html(row.case), frappe.utils.escape_html(m_name)]
                        )
                    });
                    frappe.model.set_value(cdt, cdn, "case", "");
                    frappe.model.set_value(cdt, cdn, "matter", "");
                    frappe.model.set_value(cdt, cdn, "barcode", "");
                    if (frm.fields_dict.outgoing_files && frm.fields_dict.outgoing_files.grid) {
                        var grid_row = frm.fields_dict.outgoing_files.grid.grid_rows_by_docname[cdn];
                        if (grid_row) {
                            grid_row.remove();
                        }
                    }
                    frm.refresh_field("outgoing_files");
                    return;
                }

                if (r.message.type === "case" || r.message.type === "taken_away") {
                    if (r.message.matter) {
                        frappe.model.set_value(cdt, cdn, "matter", r.message.matter);
                    }
                    if (r.message.barcode) {
                        frappe.model.set_value(cdt, cdn, "barcode", r.message.barcode);
                    }
                    if (row.parentfield === "incoming_files") {
                        update_client_missing_files_and_status(frm);
                    }
                } else if (r.message.type === "not_found") {
                    frappe.msgprint({
                        title: __("Case Not Found"),
                        indicator: "red",
                        message: __("Case '<b>{0}</b>' does not exist.", [frappe.utils.escape_html(row.case)])
                    });
                    frappe.model.set_value(cdt, cdn, "case", "");
                }
            }
        });
    },

    barcode: function (frm, cdt, cdn) {
        var row = frappe.get_doc(cdt, cdn);
        if (!row.barcode) return;

        frappe.call({
            method: "casecentral.case_central.doctype.file_movement.file_movement.get_scan_information",
            args: { value: row.barcode },
            callback: function (r) {
                if (!r.message) return;

                if (row.parentfield === "outgoing_files") {
                    var outgoing = frm.doc.outgoing_files || [];
                    var is_dup = outgoing.some(function (r) {
                        if (r === row || (r.name && row.name && r.name === row.name)) return false;
                        var rb = (r.barcode || "").trim().toLowerCase();
                        var tb = (row.barcode || "").trim().toLowerCase();
                        return rb && tb && rb === tb;
                    });
                    if (is_dup) {
                        frappe.msgprint({
                            title: __("Duplicate Barcode"),
                            indicator: "orange",
                            message: __("Barcode '<b>{0}</b>' is already present in Outgoing Files.", [frappe.utils.escape_html(row.barcode)])
                        });
                        frappe.model.set_value(cdt, cdn, "barcode", "");
                        frappe.model.set_value(cdt, cdn, "case", "");
                        frappe.model.set_value(cdt, cdn, "matter", "");
                        return;
                    }
                }

                if (row.parentfield === "incoming_files") {
                    var incoming = frm.doc.incoming_files || [];
                    var is_dup = incoming.some(function (r) {
                        if (r === row || (r.name && row.name && r.name === row.name)) return false;
                        var rb = (r.barcode || "").trim().toLowerCase();
                        var tb = (row.barcode || "").trim().toLowerCase();
                        return rb && tb && rb === tb;
                    });
                    if (is_dup) {
                        frappe.msgprint({
                            title: __("Duplicate Barcode"),
                            indicator: "orange",
                            message: __("Barcode '<b>{0}</b>' is already present in Incoming Files.", [frappe.utils.escape_html(row.barcode)])
                        });
                        frappe.model.set_value(cdt, cdn, "barcode", "");
                        frappe.model.set_value(cdt, cdn, "case", "");
                        frappe.model.set_value(cdt, cdn, "matter", "");
                        return;
                    }
                }

                if (row.parentfield === "outgoing_files" && r.message.taken_away) {
                    var m_name = (r.message.taken_away_info && r.message.taken_away_info.movement) || r.message.taken_away_movement || "";
                    frappe.msgprint({
                        title: __("Barcode Already Taken Away"),
                        indicator: "orange",
                        message: __(
                            "Barcode '<b>{0}</b>' has already been taken away in File Movement <b>{1}</b> and has not been returned. It cannot be added to Outgoing Files.",
                            [frappe.utils.escape_html(row.barcode), frappe.utils.escape_html(m_name)]
                        )
                    });
                    frappe.model.set_value(cdt, cdn, "barcode", "");
                    frappe.model.set_value(cdt, cdn, "case", "");
                    frappe.model.set_value(cdt, cdn, "matter", "");
                    if (frm.fields_dict.outgoing_files && frm.fields_dict.outgoing_files.grid) {
                        var grid_row = frm.fields_dict.outgoing_files.grid.grid_rows_by_docname[cdn];
                        if (grid_row) {
                            grid_row.remove();
                        }
                    }
                    frm.refresh_field("outgoing_files");
                    return;
                }

                if (r.message.type === "case") {
                    frappe.model.set_value(cdt, cdn, "case", r.message.case_name || "");
                    if (r.message.matter) {
                        frappe.model.set_value(cdt, cdn, "matter", r.message.matter);
                    }
                } else if (r.message.type === "matter") {
                    frappe.model.set_value(cdt, cdn, "matter", r.message.matter);
                }
                if (row.parentfield === "incoming_files") {
                    update_client_missing_files_and_status(frm);
                }
            }
        });
    },

    incoming_files_remove: function (frm) {
        update_client_missing_files_and_status(frm);
    },

    incoming_files_add: function (frm) {
        update_client_missing_files_and_status(frm);
    }
});


// =========================================================
// SCAN BARCODE (UNIFIED OUTGOING & INCOMING SCANNER)
// =========================================================

function show_single_scan_error(msg) {
    frappe.hide_msgprint(true);
    frappe.msgprint({
        title: __("Invalid Scan"),
        indicator: "red",
        message: msg,
        clear: true
    });
}

var _scan_in_flight = false;
var _last_scan_code = "";
var _last_scan_time = 0;

function handle_barcode_scan(frm, val) {
    val = (val || "").trim();
    if (!val) return;

    var now = Date.now();
    if (val === _last_scan_code && (now - _last_scan_time) < 1200) {
        return;
    }
    if (_scan_in_flight) {
        return;
    }

    _last_scan_code = val;
    _last_scan_time = now;
    _scan_in_flight = true;

    if (frm.fields_dict.scan_barcode) {
        if (frm.fields_dict.scan_barcode.$input) {
            frm.fields_dict.scan_barcode.$input.val("");
        }
        frm.doc.scan_barcode = "";
    }

    var is_incoming = Boolean(
        frm.doc.docstatus === 1 &&
        frm.doc.has_incoming &&
        frm.doc.status !== "Received" &&
        frm.doc.status !== "Cancelled"
    );

    if (frm.doc.docstatus === 0) {
        process_outgoing_scan(frm, val);
    } else if (is_incoming) {
        process_incoming_scan(frm, val);
    } else {
        _scan_in_flight = false;
        frappe.show_alert({
            message: __("Scanner is inactive for current movement status ({0}).", [frm.doc.status]),
            indicator: "orange"
        });
    }
}

function get_or_add_outgoing_row(frm) {
    var blank = (frm.doc.outgoing_files || []).find(function (r) {
        return !r.matter && !r.case && !r.barcode;
    });
    return blank || frm.add_child("outgoing_files");
}

function setup_scan_barcode_input(frm) {
    if (!frm.fields_dict.scan_barcode) return;

    var is_incoming = Boolean(frm.doc.has_incoming);
    var label = is_incoming ? __("Scan Incoming") : __("Scan Outgoing");
    var placeholder = is_incoming
        ? __("Scan Barcode / Matter ID / Case to Receive into Incoming Files...")
        : __("Scan Barcode / Matter ID / Case to Add to Outgoing Files...");

    frm.set_df_property("scan_barcode", "label", label);

    var field = frm.fields_dict.scan_barcode;
    if (field.$wrapper) {
        field.$wrapper.find(".control-label, label").css({
            "font-weight": "700",
            "font-size": "13px",
            "color": "var(--text-color)"
        });
    }

    if (field.$input) {
        field.$input.attr("placeholder", placeholder);
        field.$input.off("keydown.fm_scan").on("keydown.fm_scan", function (e) {
            if (e.which === 13 || e.which === 9) {
                e.preventDefault();
                e.stopPropagation();
                var val = $(this).val().trim();
                if (val) {
                    handle_barcode_scan(frm, val);
                }
            }
        });
        field.$input.off("change.fm_scan").on("change.fm_scan", function () {
            var val = $(this).val().trim();
            if (val) {
                handle_barcode_scan(frm, val);
            }
        });
    }
}

function process_outgoing_scan(frm, code) {
    if (!code) {
        _scan_in_flight = false;
        return;
    }

    frappe.call({
        method: "casecentral.case_central.doctype.file_movement.file_movement.get_scan_information",
        args: { value: code },
        freeze: true,
        freeze_message: __("Resolving scan '{0}'...", [code]),
        always: function () {
            _scan_in_flight = false;
        },
        callback: function (r) {
            var data = r.message;
            if (!data || data.type === "not_found") {
                var err_msg = (data && data.message) || __("No such Matter ID or Case exists: '<b>{0}</b>'", [frappe.utils.escape_html(code)]);
                show_single_scan_error(err_msg);
                return;
            }

            if (data.taken_away) {
                var m_name = (data.taken_away_info && data.taken_away_info.movement) || data.taken_away_movement || "";
                var item_desc = data.case_name || data.barcode || data.matter || code;
                frappe.msgprint({
                    title: __("File Already Taken Away"),
                    indicator: "orange",
                    message: __(
                        "'{0}' has already been taken away in File Movement <b>{1}</b> and has not been returned. It cannot be added to Outgoing Files.",
                        [frappe.utils.escape_html(item_desc), frappe.utils.escape_html(m_name)]
                    )
                });
                clear_initial_blank_outgoing_row(frm);
                return;
            }

            if (data.type === "matter") {
                var cases = data.cases || [];

                if (cases.length === 0) {
                    var exists = (frm.doc.outgoing_files || []).some(function (item) {
                        return item.matter === data.matter && !item.case;
                    });
                    if (!exists) {
                        var row = get_or_add_outgoing_row(frm);
                        row.matter = data.matter;
                        row.case = "";
                        row.barcode = "";
                        frm.refresh_field("outgoing_files");
                        frm.dirty();
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
                    if (c.taken_away) {
                        var m_name = c.taken_away_info ? c.taken_away_info.movement : (c.taken_away_movement || "");
                        frappe.msgprint({
                            title: __("Case Already Taken Away"),
                            indicator: "orange",
                            message: __(
                                "Case '<b>{0}</b>' for Matter '<b>{1}</b>' has already been taken away in File Movement <b>{2}</b> and has not been returned.",
                                [frappe.utils.escape_html(c.name), frappe.utils.escape_html(data.matter), frappe.utils.escape_html(m_name)]
                            )
                        });
                        return;
                    }
                    var exists = (frm.doc.outgoing_files || []).some(function (item) {
                        return item.case === c.name;
                    });
                    if (!exists) {
                        var row = get_or_add_outgoing_row(frm);
                        row.matter = c.matter || data.matter;
                        row.case = c.name || "";
                        row.barcode = c.barcode || "";
                        frm.refresh_field("outgoing_files");
                        frm.dirty();
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

                var row = get_or_add_outgoing_row(frm);
                row.matter = data.matter || "";
                row.case = data.case_name;
                row.barcode = data.barcode || "";
                frm.refresh_field("outgoing_files");
                frm.dirty();

                frappe.show_alert({
                    message: __("Added Case <b>{0}</b> to Outgoing Files.", [data.case_name]),
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
        return !existing_cases.has(c.name) && !c.taken_away;
    }).length;

    if (available_count === 0) {
        var all_taken = cases.length > 0 && cases.every(function (c) { return Boolean(c.taken_away); });
        var msg = all_taken
            ? __("All {0} case(s) for Matter <b>{1}</b> have already been taken away in active File Movements and have not been returned.", [cases.length, frappe.utils.escape_html(matter)])
            : __("All {0} case(s) for Matter <b>{1}</b> are already in Outgoing Files or taken away.", [cases.length, frappe.utils.escape_html(matter)]);
        frappe.msgprint({
            title: all_taken ? __("Cases Already Taken Away") : __("Cases Unavailable"),
            indicator: "orange",
            message: msg
        });
        if (target_row) {
            frappe.model.set_value(target_row.doctype, target_row.name, "matter", "");
            frappe.model.set_value(target_row.doctype, target_row.name, "case", "");
            frappe.model.set_value(target_row.doctype, target_row.name, "barcode", "");
            if (frm.fields_dict.outgoing_files && frm.fields_dict.outgoing_files.grid) {
                var grid_row = frm.fields_dict.outgoing_files.grid.grid_rows_by_docname[target_row.name];
                if (grid_row) {
                    grid_row.remove();
                }
            }
            frm.refresh_field("outgoing_files");
        }
        if (on_cancel) on_cancel();
        return;
    }

    var rows_html = "";
    cases.forEach(function (c) {
        var is_added = existing_cases.has(c.name);
        var is_taken = Boolean(c.taken_away);
        var is_disabled = is_added || is_taken;
        var barcode_label = c.barcode ? `<span class="badge badge-light" style="font-family: monospace; font-size: 11px; margin-left: 6px; padding: 2px 6px; border: 1px solid var(--border-color);">${frappe.utils.escape_html(c.barcode)}</span>` : "";
        var status_badge = c.status ? `<span class="badge badge-secondary" style="font-size: 11px;">${frappe.utils.escape_html(c.status)}</span>` : "";
        var disabled_attr = is_disabled ? "disabled" : "";
        var row_style = is_disabled
            ? "display: flex; align-items: center; justify-content: space-between; padding: 10px 12px; margin-bottom: 6px; border: 1px solid var(--border-color); border-radius: 6px; opacity: 0.6; cursor: not-allowed; background: var(--subtle-accent-bg, var(--control-bg));"
            : "display: flex; align-items: center; justify-content: space-between; padding: 10px 12px; margin-bottom: 6px; border: 1px solid var(--border-color); border-radius: 6px; cursor: pointer; background: var(--card-bg, var(--fg-color)); transition: background 0.15s ease;";
        var note_badge = "";
        if (is_taken) {
            var m_name = c.taken_away_movement || (c.taken_away_info && c.taken_away_info.movement) || "";
            note_badge = `<span class="badge" style="margin-left: 6px; font-size: 10px; background-color: var(--bg-red-100, rgba(239, 68, 68, 0.18)); color: var(--text-red-700, #b91c1c);">${__("Taken Away in {0}", [frappe.utils.escape_html(m_name)])}</span>`;
        } else if (is_added) {
            note_badge = `<span class="badge badge-warning" style="margin-left: 6px; font-size: 10px;">${__("Already in Outgoing Files")}</span>`;
        }
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
                            ${note_badge}
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

            <div class="case-list-scrollable" style="max-height: 320px; overflow-y: auto; border: 1px solid var(--border-color); border-radius: 6px; padding: 6px; background: var(--control-bg, var(--subtle-accent-bg));">
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
            dialog.$wrapper.find(".case-select-checkbox:checked:not(:disabled)").each(function () {
                var c_name = $(this).data("case-name");
                var match = cases.find(function (c) { return c.name === c_name && !c.taken_away; });
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
            <div class="return-case-item-card" data-case-name="${frappe.utils.escape_html(c.case || '')}" data-search="${frappe.utils.escape_html(search_meta)}" style="display: flex; align-items: center; justify-content: space-between; padding: 10px 12px; margin-bottom: 6px; border: 1px solid var(--border-color); border-radius: 6px; cursor: pointer; background: var(--card-bg, var(--fg-color)); transition: background 0.15s ease;">
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

            <div class="case-list-scrollable" style="max-height: 300px; overflow-y: auto; border: 1px solid var(--border-color); border-radius: 6px; padding: 6px; background: var(--control-bg, var(--subtle-accent-bg));">
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



function update_client_missing_files_and_status(frm) {
    if (!frm.doc.has_incoming) return;

    var outgoing = frm.doc.outgoing_files || [];
    var incoming = frm.doc.incoming_files || [];

    var valid_incoming = incoming.filter(function (r) {
        return ((r.matter || "").trim() || (r.case || "").trim() || (r.barcode || "").trim());
    });

    var missing = [];
    outgoing.forEach(function (out_r) {
        if (!is_file_in_incoming(out_r, valid_incoming)) {
            missing.push({
                matter: (out_r.matter || "").trim(),
                case: (out_r.case || "").trim(),
                barcode: (out_r.barcode || "").trim()
            });
        }
    });

    frm.clear_table("missing_file_items");
    if (valid_incoming.length === 0) {
        frm.set_value("status", frm.doc.has_incoming ? "Taken Away / Incoming Created" : "Taken Away");
    } else if (missing.length === 0) {
        frm.set_value("status", "Received");
    } else {
        missing.forEach(function (item) {
            var r = frm.add_child("missing_file_items");
            r.matter = item.matter;
            r.case = item.case;
            r.barcode = item.barcode;
        });
        frm.set_value("status", "Missing Files");
    }

    frm.refresh_field("missing_file_items");
    frm.refresh_field("status");
    frm.refresh_field("incoming_files");
    frm.dirty();
    update_form_indicator(frm);
}

function process_incoming_scan(frm, code) {
    if (!code) {
        _scan_in_flight = false;
        return;
    }

    var outgoing = frm.doc.outgoing_files || [];

    var match_bc = outgoing.filter(function (r) {
        return (r.barcode || "").trim() === code;
    });
    var match_case = outgoing.filter(function (r) {
        return (r.case || "").trim() === code;
    });
    var match_matter = outgoing.filter(function (r) {
        return (r.matter || "").trim() === code;
    });

    if (match_bc.length || match_case.length || match_matter.length) {
        var matches = match_bc.length ? match_bc : (match_case.length ? match_case : match_matter);
        apply_incoming_matches(frm, matches, code);
        return;
    }

    frappe.call({
        method: "casecentral.case_central.doctype.file_movement.file_movement.get_scan_information",
        args: { value: code },
        freeze: true,
        freeze_message: __("Resolving scan '{0}'...", [code]),
        always: function () {
            _scan_in_flight = false;
        },
        callback: function (r) {
            var data = r.message;
            if (!data || data.type === "not_found") {
                show_single_scan_error(__("No such Matter ID or Case exists in Outgoing Files: '<b>{0}</b>'", [frappe.utils.escape_html(code)]));
                return;
            }

            var matches = [];
            if (data.type === "case") {
                matches = outgoing.filter(function (r) {
                    return r.case === data.case_name || (data.barcode && r.barcode === data.barcode);
                });
            } else if (data.type === "matter") {
                matches = outgoing.filter(function (r) {
                    return r.matter === data.matter;
                });
            }

            if (!matches.length) {
                show_single_scan_error(__("Scanned file '<b>{0}</b>' is not part of Outgoing Files in this movement.", [frappe.utils.escape_html(code)]));
                return;
            }

            apply_incoming_matches(frm, matches, code);
        }
    });
}

function apply_incoming_matches(frm, matches, code) {
    _scan_in_flight = false;
    var incoming = frm.doc.incoming_files || [];

    var unreturned = matches.filter(function (out_r) {
        return !is_file_in_incoming(out_r, incoming);
    });

    if (!unreturned.length) {
        frappe.show_alert({
            message: __("All matching files for '<b>{0}</b>' are already scanned in Incoming Files.", [frappe.utils.escape_html(code)]),
            indicator: "orange"
        });
        return;
    }

    if (unreturned.length > 1) {
        show_return_case_selection_dialog(matches[0].matter || code, unreturned, function (selected) {
            if (selected && selected.length) {
                var added_count = 0;
                selected.forEach(function (s) {
                    if (!is_file_in_incoming(s, frm.doc.incoming_files || [])) {
                        var r = frm.add_child("incoming_files");
                        r.matter = s.matter || "";
                        r.case = s.case || "";
                        r.barcode = s.barcode || "";
                        added_count++;
                    }
                });
                if (added_count > 0) {
                    update_client_missing_files_and_status(frm);
                    frappe.show_alert({
                        message: __("Added {0} file(s) to Incoming Files. Click 'Update' to save.", [added_count]),
                        indicator: "green"
                    });
                }
            }
        });
    } else {
        var s = unreturned[0];
        if (!is_file_in_incoming(s, frm.doc.incoming_files || [])) {
            var r = frm.add_child("incoming_files");
            r.matter = s.matter || "";
            r.case = s.case || "";
            r.barcode = s.barcode || "";
            update_client_missing_files_and_status(frm);
            frappe.show_alert({
                message: __("Added Case <b>{0}</b> to Incoming Files. Click 'Update' to save.", [s.case || s.barcode]),
                indicator: "green"
            });
        } else {
            frappe.show_alert({
                message: __("File '<b>{0}</b>' is already scanned in Incoming Files.", [frappe.utils.escape_html(s.case || s.barcode || code)]),
                indicator: "orange"
            });
        }
    }
}


// =========================================================
// ACTION: CREATE INCOMING
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
                            invalidate_file_movement_listview();
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
// ACTION: CANCEL INCOMING
// =========================================================

function add_cancel_incoming_button(frm) {
    var btn = frm.add_custom_button(__("Cancel Incoming"), function () {
        frappe.confirm(
            __("Are you sure you want to cancel the Incoming workflow? This will reset the status to 'Taken Away'."),
            function () {
                frappe.call({
                    method: "casecentral.case_central.doctype.file_movement.file_movement.cancel_incoming",
                    args: {
                        movement_name: frm.doc.name
                    },
                    freeze: true,
                    freeze_message: __("Cancelling Incoming workflow..."),
                    callback: function (r) {
                        if (r.message) {
                            invalidate_file_movement_listview();
                            frappe.show_alert({
                                message: __("Incoming workflow cancelled. Status updated to 'Taken Away'."),
                                indicator: "orange"
                            });
                            frm.reload_doc();
                        }
                    }
                });
            }
        );
    });

    if (btn) {
        btn.addClass("btn-danger-light");
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
                var incoming = frm.doc.incoming_files || [];
                var unreturned_missing = missing_files.filter(function (m) {
                    return !is_file_in_incoming(m, incoming);
                });

                if (!unreturned_missing.length) {
                    if (missing_files.length > 0 || (incoming && incoming.length > 0)) {
                        frappe.msgprint(__("All missing files have already been added to Incoming Files. Click 'Update' to save."));
                    } else {
                        frappe.msgprint(__("There are no missing files in this movement."));
                    }
                    return;
                }
                show_return_missing_modal(frm, unreturned_missing);
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

            var added_count = 0;
            selected_items.forEach(function (s) {
                if (!is_file_in_incoming(s, frm.doc.incoming_files || [])) {
                    var r = frm.add_child("incoming_files");
                    r.matter = s.matter || "";
                    r.case = s.case || "";
                    r.barcode = s.barcode || "";
                    added_count++;
                }
            });

            if (added_count > 0) {
                update_client_missing_files_and_status(frm);
                frappe.show_alert({
                    message: __("Added {0} file(s) to Incoming Files. Click 'Update' to save.", [added_count]),
                    indicator: "green"
                });
            } else {
                frappe.show_alert({
                    message: __("Selected file(s) are already present in Incoming Files."),
                    indicator: "orange"
                });
            }
            dialog.hide();
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

        // 0. Check if scanned code corresponds to a file already added to frm.doc.incoming_files
        if (is_code_or_item_in_incoming(code, frm.doc.incoming_files || [])) {
            frappe.show_alert({
                message: __("File '<b>{0}</b>' is already added to Incoming Files.", [frappe.utils.escape_html(code)]),
                indicator: "orange"
            });
            dialog.set_value("quick_scan", "");
            setTimeout(function () {
                dialog.fields_dict.quick_scan?.$input?.focus();
            }, 100);
            return;
        }

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
        } else {
            // Check if code matches a Matter that exists in Outgoing Files (all its files already returned)
            var outgoing_matter_matches = (frm.doc.outgoing_files || []).filter(function (r) {
                return (r.matter || "").trim().toLowerCase() === code.toLowerCase();
            });
            if (outgoing_matter_matches.length > 0) {
                frappe.show_alert({
                    message: __("All files for Matter <b>{0}</b> are already added to Incoming Files.", [frappe.utils.escape_html(code)]),
                    indicator: "orange"
                });
                dialog.set_value("quick_scan", "");
                setTimeout(function () {
                    dialog.fields_dict.quick_scan?.$input?.focus();
                }, 100);
                return;
            }
        }

        // 2. Direct match by barcode or case in missing items state
        var matched_count = 0;
        var already_scanned_count = 0;
        var code_lower = code.toLowerCase();
        items_state.forEach(function (item) {
            var b_lower = (item.barcode || "").toLowerCase();
            var cs_lower = (item.case || "").toLowerCase();
            if (b_lower === code_lower || cs_lower === code_lower) {
                if (item.scanned) {
                    already_scanned_count++;
                } else {
                    item.scanned = true;
                    matched_count++;
                }
            }
        });

        if (already_scanned_count > 0 && matched_count === 0) {
            frappe.show_alert({
                message: __("File '<b>{0}</b>' is already marked for return.", [frappe.utils.escape_html(code)]),
                indicator: "orange"
            });
            dialog.set_value("quick_scan", "");
            setTimeout(function () {
                dialog.fields_dict.quick_scan?.$input?.focus();
            }, 100);
            return;
        }

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
            return;
        }

        // 3. Fallback to server resolver
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

                // Check if resolved case or barcode is already in incoming_files
                var resolved_code = data.case_name || data.barcode || "";
                if (resolved_code && is_code_or_item_in_incoming(resolved_code, frm.doc.incoming_files || [])) {
                    frappe.show_alert({
                        message: __("File '<b>{0}</b>' is already added to Incoming Files.", [frappe.utils.escape_html(resolved_code)]),
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
                    var api_already = 0;
                    items_state.forEach(function (item) {
                        var is_match = (data.type === "case" && item.case === data.case_name) ||
                                       (data.barcode && item.barcode === data.barcode);
                        if (is_match) {
                            if (item.scanned) {
                                api_already++;
                            } else {
                                item.scanned = true;
                                api_matched++;
                            }
                        }
                    });

                    if (api_matched > 0) {
                        update_table_view();
                        frappe.show_alert({
                            message: __("Scanned & verified: <b>{0}</b> ({1} item(s)).", [code, api_matched]),
                            indicator: "green"
                        });
                    } else if (api_already > 0) {
                        frappe.show_alert({
                            message: __("File '<b>{0}</b>' is already marked for return.", [frappe.utils.escape_html(code)]),
                            indicator: "orange"
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
        var row_bg = item.scanned ? "background-color: var(--bg-green-50, rgba(34, 197, 94, 0.08));" : "";
        var badge_html = item.scanned
            ? '<span class="badge" style="background-color: var(--bg-green-100, rgba(34, 197, 94, 0.18)); color: var(--text-green-700, #15803d); font-weight: 600; padding: 4px 8px; border-radius: 4px;"><i class="fa fa-check" style="margin-right: 4px;"></i>' + __("Scanned to Return") + '</span>'
            : '<span class="badge" style="background-color: var(--bg-yellow-100, rgba(234, 179, 8, 0.18)); color: var(--text-yellow-700, #b45309); font-weight: 500; padding: 4px 8px; border-radius: 4px;">' + __("Pending Scan") + '</span>';

        return '<tr style="' + row_bg + '">' +
            '<td style="text-align: center; color: var(--text-muted); font-weight: 500;">' + (idx + 1) + '</td>' +
            '<td style="font-weight: 600; color: var(--text-color);">' + frappe.utils.escape_html(item.matter || "-") + '</td>' +
            '<td style="color: var(--text-color);">' + frappe.utils.escape_html(item.case || "-") + '</td>' +
            '<td><code>' + frappe.utils.escape_html(item.barcode || "-") + '</code></td>' +
            '<td style="text-align: center;">' + badge_html + '</td>' +
            '</tr>';
    }).join("");

    return '<div style="margin-top: 15px;">' +
        '<div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">' +
        '<span style="font-size: 13px; font-weight: 600; color: var(--heading-color, var(--text-color));">' + __("Missing Files List ({0})", [total_count]) + '</span>' +
        '<span style="font-size: 12px; font-weight: 600; color: ' + (scanned_count > 0 ? 'var(--text-green-700, #16a34a)' : 'var(--text-muted)') + ';">' +
        __("{0} of {1} Scanned", [scanned_count, total_count]) +
        '</span>' +
        '</div>' +
        '<div style="max-height: 240px; overflow-y: auto; border: 1px solid var(--border-color); border-radius: 6px;">' +
        '<table class="table table-bordered table-condensed" style="margin: 0; font-size: 12px;">' +
        '<thead style="background-color: var(--table-header-bg, var(--control-bg)); position: sticky; top: 0; z-index: 1;">' +
        '<tr>' +
        '<th style="width: 35px; text-align: center; color: var(--text-muted);">#</th>' +
        '<th style="color: var(--text-muted);">' + __("Matter") + '</th>' +
        '<th style="color: var(--text-muted);">' + __("Case") + '</th>' +
        '<th style="color: var(--text-muted);">' + __("Barcode") + '</th>' +
        '<th style="width: 140px; text-align: center; color: var(--text-muted);">' + __("Status") + '</th>' +
        '</tr>' +
        '</thead>' +
        '<tbody>' +
        rows_html +
        '</tbody>' +
        '</table>' +
        '</div>' +
        '</div>';
}