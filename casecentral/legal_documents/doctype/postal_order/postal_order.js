// Copyright (c) 2023, 4C Solutions and contributors
// For license information, please see license.txt

frappe.ui.form.on('Postal Order', {
	posting_date: function(frm) {
		if(frm.doc.posting_date && frm.doc.status == "") {
			frm.set_value("status", "Posted")
		} else if(!frm.doc.posting_date) {
			frm.set_value("status", "")
		}
	}
});
