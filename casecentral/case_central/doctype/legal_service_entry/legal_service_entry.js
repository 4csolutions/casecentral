// Copyright (c) 2023, 4C Solutions and contributors
// For license information, please see license.txt

frappe.ui.form.on('Legal Service Entry', {
	refresh: function(frm) {
		if(frm.doc.invoiced) {
			frm.disable_save();
		}
	}
});
