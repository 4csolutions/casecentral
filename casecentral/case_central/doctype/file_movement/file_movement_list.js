frappe.listview_settings["File Movement"] = {
    has_indicator_for_draft: true,
    add_fields: ["status", "has_incoming"],
    get_indicator: function (doc) {
        if (doc.status === "Open") {
            return [__("Open"), "orange", "status,=,Open"];
        } else if (doc.status === "Missing Files") {
            return [__("Missing Files"), "red", "status,=,Missing Files"];
        } else if (doc.status === "Received") {
            return [__("Received"), "green", "status,=,Received"];
        }
    }
};