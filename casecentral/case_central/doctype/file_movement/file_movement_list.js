frappe.listview_settings["File Movement"] = {
    add_fields: ["status", "movement_type"],
    get_indicator: function (doc) {
        if (doc.status === "Open") {
            return [__("Open"), "orange", "status,=,Open"];
        } else if (doc.status === "Missing Files") {
            return [__("Missing Files"), "red", "status,=,Missing Files"];
        } else if (doc.status === "Received") {
            return [__("Received"), "green", "status,=,Received"];
        }
    },
    formatters: {
        name: function (value, df, doc) {
            if (doc.status) {
                return `${value} — ${doc.status}`;
            }
            return value;
        }
    }
};