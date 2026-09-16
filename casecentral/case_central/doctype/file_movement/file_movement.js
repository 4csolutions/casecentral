// Copyright (c) 2026, 4C Solutions and Contributors
// See license.txt

frappe.ui.form.on("File Movement", {

    onload: function (frm) {
        setup_page_scan_button(frm);
    },

    refresh: function (frm) {
        setup_page_scan_button(frm);

        frm.remove_custom_button("Create Incoming");
        frm.remove_custom_button("Return Missing Files");
        frm.remove_custom_button("Scan Barcode");

        // Direct standalone "Create Incoming" button on submitted Outgoing movement (not inside Actions)
        if (frm.doc.docstatus === 1 && frm.doc.movement_type === "Outgoing") {
            add_create_incoming_button(frm);
        }

        // Direct standalone "Return Missing Files" button on submitted Incoming movement with Missing Files (not inside Actions)
        if (frm.doc.docstatus === 1 && frm.doc.movement_type === "Incoming" && frm.doc.status === "Missing Files") {
            add_return_missing_button(frm);
        }

        // Set field read-only states depending on movement type
        set_form_read_only_states(frm);
    },

    movement_type: function (frm) {
        set_form_read_only_states(frm);
        if (frm.doc.movement_type === "Incoming" && frm.doc.docstatus === 0) {
            update_missing_files_table_and_status_client(frm);
        }
    }
});


// =========================================================
// CHILD TABLE: BARCODE FILE ITEM (MATTER FILES)
// =========================================================

frappe.ui.form.on("Barcode File Item", {
    matter: function (frm, cdt, cdn) {
        var row = frappe.get_doc(cdt, cdn);
        if (!row.matter) return;

        frappe.call({
            method: "casecentral.case_central.doctype.file_movement.file_movement.get_cases_for_matter",
            args: { matter: row.matter },
            freeze: true,
            freeze_message: __("Validating Matter ID & finding Cases..."),
            callback: function (response) {
                var cases = response.message || [];
                if (!cases.length) {
                    // Check if matter itself exists
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

                // If multiple cases exist for this matter, add additional rows for the remaining cases
                if (cases.length > 1) {
                    for (var i = 1; i < cases.length; i++) {
                        var c = cases[i];
                        var exists = (frm.doc.barcode_files || []).some(function (item) {
                            return item.matter === (c.matter || row.matter) && item.case === c.name;
                        });

                        if (!exists) {
                            var new_row = frm.add_child("barcode_files");
                            new_row.matter = c.matter || row.matter;
                            new_row.case = c.name || "";
                            new_row.barcode = c.barcode || "";
                            new_row.returned = 0;
                        }
                    }
                    frm.refresh_field("barcode_files");
                }

                frappe.show_alert({
                    message: __("{0} Case(s) added for Matter {1}.", [cases.length, row.matter]),
                    indicator: "green"
                });

                if (frm.doc.movement_type === "Incoming") {
                    update_missing_files_table_and_status_client(frm);
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
    },

    returned: function (frm) {
        if (frm.doc.movement_type === "Incoming") {
            update_missing_files_table_and_status_client(frm);
        }
    }
});


// =========================================================
// FORM FIELD READ-ONLY STATES
// =========================================================

function set_form_read_only_states(frm) {
    var is_incoming = frm.doc.movement_type === "Incoming";
    frm.set_df_property("original_outgoing_movement", "read_only", is_incoming && frm.doc.docstatus === 1 ? 1 : 0);
    frm.refresh_fields();
}


// =========================================================
// SCAN BARCODE BUTTON (ONLY IN PAGE BELOW RECEIVER)
// =========================================================

function setup_page_scan_button(frm) {
    if (!frm.fields_dict.scan_barcode_btn) return;

    var btn_html =
        '<div style="margin-top: 8px; margin-bottom: 8px;">' +
        '<button type="button" class="btn btn-primary btn-sm btn-page-scan-barcode" style="font-weight: 500; padding: 7px 18px; border-radius: 6px; box-shadow: 0 1px 2px rgba(0,0,0,0.05);">' +
        '<i class="fa fa-barcode" style="margin-right: 6px;"></i>' + __("Scan Barcode / Matter ID") +
        '</button>' +
        '</div>';

    frm.fields_dict.scan_barcode_btn.$wrapper.html(btn_html);

    frm.fields_dict.scan_barcode_btn.$wrapper.find(".btn-page-scan-barcode").off("click").on("click", function (e) {
        e.preventDefault();
        open_scan_dialog(frm);
    });
}


// =========================================================
// SCAN BARCODE DIALOG (SCANNER GUN & CAMERA)
// =========================================================

function open_scan_dialog(frm) {
    var dialog = new frappe.ui.Dialog({
        title: __("Scan Barcode / Matter ID"),
        fields: [
            {
                fieldname: "barcode",
                label: __("Barcode / Matter ID / Case"),
                fieldtype: "Data",
                description: __("Scan using barcode gun, enter Matter ID (e.g. MID-26-001), or type barcode and press Enter")
            },
            {
                fieldname: "camera_area",
                fieldtype: "HTML"
            }
        ],
        primary_action_label: __("Add / Process"),
        primary_action: function () {
            var value = (dialog.get_value("barcode") || "").trim();
            if (!value) {
                frappe.msgprint(__("Please scan or enter a value."));
                return;
            }
            process_scan(frm, value, dialog);
        }
    });

    dialog.show();

    // Auto focus barcode input field
    setTimeout(function () {
        var $input = dialog.fields_dict.barcode.$input;
        if ($input) {
            $input.focus();
            $input.on("keydown", function (e) {
                if (e.which === 13) { // Enter key from scanner gun
                    e.preventDefault();
                    var val = $(this).val().trim();
                    if (val) {
                        process_scan(frm, val, dialog);
                    }
                }
            });
        }
    }, 200);

    // Camera scanner area
    var html =
        '<div style="margin-top:15px; padding-top: 15px; border-top: 1px solid #d1d8dd;">' +
        '<button type="button" class="btn btn-default btn-sm start-camera" style="margin-right: 5px;">' +
        '<i class="fa fa-camera" style="margin-right: 5px;"></i>' + __("Start Camera Scanner") +
        '</button>' +
        '<button type="button" class="btn btn-danger btn-sm stop-camera" style="display:none;">' + __("Stop Camera") + '</button>' +
        '<video class="barcode-video" style="width:100%;max-height:260px;margin-top:12px;display:none;border:1px solid #ddd;border-radius:6px;object-fit:cover;" autoplay muted playsinline></video>' +
        '<div class="camera-message" style="margin-top:8px;font-size:12px;"></div>' +
        '</div>';

    dialog.fields_dict.camera_area.$wrapper.html(html);

    var wrapper = dialog.fields_dict.camera_area.$wrapper;
    var video = wrapper.find(".barcode-video")[0];
    var start_button = wrapper.find(".start-camera");
    var stop_button = wrapper.find(".stop-camera");
    var camera_message = wrapper.find(".camera-message");

    var stream = null;
    var scanning = false;
    var scan_interval = null;

    start_button.on("click", function () {
        if (navigator.mediaDevices && navigator.mediaDevices.getUserMedia) {
            navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment" } })
                .then(function (s) {
                    stream = s;
                    video.srcObject = s;
                    video.style.display = "block";
                    start_button.hide();
                    stop_button.show();
                    camera_message.html("<span class='text-muted'>" + __("Point camera at barcode...") + "</span>");
                    scanning = true;
                    start_camera_detection();
                })
                .catch(function (err) {
                    camera_message.html("<span class='text-danger'>" + __("Camera error: {0}", [err.message]) + "</span>");
                });
        } else {
            camera_message.html("<span class='text-danger'>" + __("Camera not supported on this device.") + "</span>");
        }
    });

    stop_button.on("click", function () {
        stop_camera();
    });

    dialog.on_page_show = function () {
        dialog.fields_dict.barcode?.$input?.focus();
    };

    dialog.$wrapper.on("hidden.bs.modal", function () {
        stop_camera();
    });

    function stop_camera() {
        scanning = false;
        if (scan_interval) {
            clearInterval(scan_interval);
            scan_interval = null;
        }
        if (stream) {
            stream.getTracks().forEach(function (track) { track.stop(); });
            stream = null;
        }
        video.style.display = "none";
        start_button.show();
        stop_button.hide();
        camera_message.html("");
    }

    function start_camera_detection() {
        if ("BarcodeDetector" in window) {
            var barcodeDetector = new BarcodeDetector();
            scan_interval = setInterval(function () {
                if (!scanning || !video.videoWidth) return;
                barcodeDetector.detect(video)
                    .then(function (barcodes) {
                        if (barcodes.length > 0 && scanning) {
                            var detected_code = barcodes[0].rawValue;
                            stop_camera();
                            process_scan(frm, detected_code, dialog);
                        }
                    })
                    .catch(function () {});
            }, 300);
        } else {
            camera_message.html("<span class='text-warning'>" + __("Live camera detection not supported by browser. Please type or scan using barcode gun.") + "</span>");
        }
    }
}


// =========================================================
// PROCESS SCANNED VALUE
// =========================================================

function process_scan(frm, value, dialog) {
    if (!value) return;
    value = value.trim();

    frappe.call({
        method: "casecentral.case_central.doctype.file_movement.file_movement.get_scan_information",
        args: { value: value },
        freeze: true,
        freeze_message: __("Validating scanned code..."),
        callback: function (r) {
            var data = r.message;

            // STRICT REJECTION IF VALUE DOES NOT MATCH ANYTHING
            if (!data || data.type === "not_found") {
                frappe.msgprint({
                    title: __("Not Found"),
                    indicator: "red",
                    message: __("Scanned value '<b>{0}</b>' does not match any existing Matter ID, Case, or Barcode.<br><br>The table was <b>not</b> populated.", [value])
                });

                if (dialog) {
                    dialog.set_value("barcode", "");
                    dialog.fields_dict.barcode?.$input?.focus();
                }
                return;
            }

            // OUTGOING MOVEMENT SCAN HANDLING
            if (frm.doc.movement_type === "Outgoing") {
                handle_outgoing_scan(frm, data, value);
            }
            // INCOMING MOVEMENT SCAN HANDLING
            else if (frm.doc.movement_type === "Incoming") {
                handle_incoming_scan(frm, data, value);
            }

            if (dialog) {
                dialog.set_value("barcode", "");
                dialog.fields_dict.barcode?.$input?.focus();
            }
        }
    });
}

function handle_outgoing_scan(frm, data, original_value) {
    var added_count = 0;

    if (data.type === "matter") {
        var cases = data.cases || [];
        if (cases.length > 0) {
            cases.forEach(function (c) {
                var exists = (frm.doc.barcode_files || []).some(function (item) {
                    return item.matter === (c.matter || data.matter) && item.case === c.name;
                });

                if (!exists) {
                    var row = frm.add_child("barcode_files");
                    row.matter = c.matter || data.matter;
                    row.case = c.name || "";
                    row.barcode = c.barcode || "";
                    row.returned = 0;
                    added_count++;
                }
            });
        } else {
            var exists = (frm.doc.barcode_files || []).some(function (item) {
                return item.matter === data.matter;
            });
            if (!exists) {
                var row = frm.add_child("barcode_files");
                row.matter = data.matter;
                row.case = "";
                row.barcode = "";
                row.returned = 0;
                added_count++;
            }
        }

        frm.refresh_field("barcode_files");

        if (added_count > 0) {
            frappe.show_alert({
                message: __("Added Matter <b>{0}</b> ({1} Case(s)).", [data.matter, added_count]),
                indicator: "green"
            });
        } else {
            frappe.show_alert({
                message: __("Matter <b>{0}</b> is already in the table.", [data.matter]),
                indicator: "orange"
            });
        }
    } else if (data.type === "case") {
        var exists = (frm.doc.barcode_files || []).some(function (item) {
            return item.case === data.case_name;
        });

        if (!exists) {
            var row = frm.add_child("barcode_files");
            row.matter = data.matter || "";
            row.case = data.case_name || "";
            row.barcode = data.barcode || original_value;
            row.returned = 0;
            frm.refresh_field("barcode_files");

            frappe.show_alert({
                message: __("Added Case <b>{0}</b> (Matter: {1}).", [data.case_name, data.matter || "N/A"]),
                indicator: "green"
            });
        } else {
            frappe.show_alert({
                message: __("Case <b>{0}</b> is already in the table.", [data.case_name]),
                indicator: "orange"
            });
        }
    } else if (data.type === "case_file") {
        var exists = (frm.doc.barcode_files || []).some(function (item) {
            return item.barcode === data.barcode;
        });

        if (!exists) {
            var row = frm.add_child("barcode_files");
            row.matter = data.matter || "";
            row.case = data.case || "";
            row.barcode = data.barcode || original_value;
            row.returned = 0;
            frm.refresh_field("barcode_files");

            frappe.show_alert({
                message: __("Added Barcode <b>{0}</b>.", [data.barcode]),
                indicator: "green"
            });
        } else {
            frappe.show_alert({
                message: __("Barcode <b>{0}</b> is already in the table.", [data.barcode]),
                indicator: "orange"
            });
        }
    }
}

function handle_incoming_scan(frm, data, original_value) {
    var matched_rows = [];

    (frm.doc.barcode_files || []).forEach(function (row) {
        if (data.type === "matter" && row.matter === data.matter) {
            matched_rows.push(row);
        } else if (data.type === "case" && row.case === data.case_name) {
            matched_rows.push(row);
        } else if (row.barcode === original_value || (data.barcode && row.barcode === data.barcode)) {
            matched_rows.push(row);
        }
    });

    if (matched_rows.length > 0) {
        matched_rows.forEach(function (row) {
            row.returned = 1;
        });
        frm.refresh_field("barcode_files");
        update_missing_files_table_and_status_client(frm);

        frappe.show_alert({
            message: __("Marked returned: <b>{0}</b> ({1} item(s)).", [original_value, matched_rows.length]),
            indicator: "green"
        });
    } else {
        frappe.msgprint({
            title: __("Not in Movement"),
            indicator: "orange",
            message: __("Scanned item '<b>{0}</b>' was not found in this Incoming movement.", [original_value])
        });
    }
}


// =========================================================
// REAL-TIME MISSING FILES TABLE CALCULATION (CLIENT-SIDE)
// =========================================================

function update_missing_files_table_and_status_client(frm) {
    if (frm.doc.movement_type !== "Incoming") {
        frm.set_value("missing_file_items", []);
        return;
    }

    var missing = [];

    (frm.doc.barcode_files || []).forEach(function (row) {
        if (!row.returned) {
            missing.push({
                barcode: row.barcode || "",
                matter: row.matter || "",
                case: row.case || "",
                returned: 0
            });
        }
    });

    frm.set_value("missing_file_items", missing);

    var new_status = missing.length > 0 ? "Missing Files" : "Received";
    if (frm.doc.status !== new_status) {
        frm.set_value("status", new_status);
    }
}


// =========================================================
// ACTION: CREATE INCOMING (STANDALONE PRIMARY BUTTON)
// =========================================================

function add_create_incoming_button(frm) {
    var btn = frm.add_custom_button(__("Create Incoming"), function () {
        frappe.call({
            method: "casecentral.case_central.doctype.file_movement.file_movement.create_incoming",
            args: {
                outgoing_name: frm.doc.name
            },
            freeze: true,
            freeze_message: __("Creating Incoming File Movement..."),
            callback: function (r) {
                if (r.message) {
                    frappe.show_alert({
                        message: __("Incoming File Movement created: {0}", [r.message]),
                        indicator: "green"
                    });
                    frappe.set_route("Form", "File Movement", r.message);
                }
            }
        });
    });

    if (btn) {
        btn.addClass("btn-primary");
    }
}


// =========================================================
// ACTION: RETURN MISSING FILES (STANDALONE PRIMARY BUTTON)
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
    var fields = [
        {
            fieldname: "quick_scan",
            label: __("Scan Barcode / Matter to Return"),
            fieldtype: "Data",
            description: __("Scan barcode gun or type code to check off returned items")
        },
        {
            fieldname: "missing_items_section",
            fieldtype: "Section Break",
            label: __("Select Missing Items to Return ({0})", [missing_files.length])
        }
    ];

    missing_files.forEach(function (item, idx) {
        var label_parts = [];
        if (item.matter) label_parts.push(__("Matter: {0}", [item.matter]));
        if (item.case) label_parts.push(__("Case: {0}", [item.case]));
        if (item.barcode) label_parts.push(__("Barcode: {0}", [item.barcode]));

        fields.push({
            fieldname: "item_" + idx,
            label: label_parts.join(" | ") || __("Item {0}", [idx + 1]),
            fieldtype: "Check",
            default: 1
        });
    });

    var dialog = new frappe.ui.Dialog({
        title: __("Return Missing Files"),
        fields: fields,
        primary_action_label: __("Return Selected Files"),
        primary_action: function (values) {
            var selected_items = [];

            missing_files.forEach(function (item, idx) {
                if (values["item_" + idx]) {
                    selected_items.push(item);
                }
            });

            if (!selected_items.length) {
                frappe.msgprint(__("Please select at least one file to return."));
                return;
            }

            frappe.call({
                method: "casecentral.case_central.doctype.file_movement.file_movement.return_missing_files",
                args: {
                    movement_name: frm.doc.name,
                    files: JSON.stringify(selected_items)
                },
                freeze: true,
                freeze_message: __("Returning files..."),
                callback: function (response) {
                    if (response.message) {
                        var res = response.message;
                        frappe.show_alert({
                            message: res.status === "Received"
                                ? __("All missing files returned successfully!")
                                : __("Files returned. Some files remain missing."),
                            indicator: res.status === "Received" ? "green" : "orange"
                        });
                        dialog.hide();
                        frm.reload_doc();
                    }
                }
            });
        }
    });

    dialog.show();

    // Bind quick scanner in modal
    setTimeout(function () {
        var $input = dialog.fields_dict.quick_scan?.$input;
        if ($input) {
            $input.focus();
            $input.on("keydown", function (e) {
                if (e.which === 13) {
                    e.preventDefault();
                    var code = $(this).val().trim();
                    if (!code) return;

                    var matched = false;
                    missing_files.forEach(function (item, idx) {
                        if (item.barcode === code || item.case === code || item.matter === code) {
                            dialog.set_value("item_" + idx, 1);
                            matched = true;
                        }
                    });

                    if (matched) {
                        frappe.show_alert({
                            message: __("Checked item: <b>{0}</b>", [code]),
                            indicator: "green"
                        });
                    } else {
                        frappe.show_alert({
                            message: __("Code <b>{0}</b> is not in the missing list.", [code]),
                            indicator: "orange"
                        });
                    }
                    dialog.set_value("quick_scan", "");
                    setTimeout(function () { $input.focus(); }, 50);
                }
            });
        }
    }, 200);
}