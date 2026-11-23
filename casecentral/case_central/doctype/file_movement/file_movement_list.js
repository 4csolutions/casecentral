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
    },

    onload: function (listview) {
        // Automatically clear throttle cache and refresh when navigating to the list view
        if (listview.page && listview.page.wrapper) {
            listview.page.wrapper.on("show", function () {
                listview.last_args = null;
                listview.refresh();
            });
        }

        frappe.router.on("change", function () {
            var route = frappe.get_route();
            if (route && route[0] === "List" && route[1] === "File Movement") {
                if (listview && listview.page && listview.page.wrapper.is(":visible")) {
                    listview.last_args = null;
                    listview.refresh();
                }
            }
        });

        if (frappe.realtime) {
            frappe.realtime.on("doc_update", function (data) {
                if (data && data.doctype === "File Movement") {
                    listview.last_args = null;
                    listview.refresh();
                }
            });
            frappe.realtime.on("list_update", function (data) {
                if (data && data.doctype === "File Movement") {
                    listview.last_args = null;
                    listview.refresh();
                }
            });
            frappe.realtime.on("file_movement_updated", function () {
                listview.last_args = null;
                listview.refresh();
            });
        }
    },

    refresh: function (listview) {
        // Reset last_args so any subsequent route or view change always re-queries
        setTimeout(function () {
            if (listview) {
                listview.last_args = null;
            }
        }, 100);
    }
};
