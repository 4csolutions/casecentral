// Copyright (c) 2023, 4C Solutions and contributors
// For license information, please see license.txt

frappe.ui.form.on('Legal Service Entry', {
	refresh: function(frm) {
		if(frm.doc.invoiced) {
			frm.disable_save();
		}
		// set filters for case based on matter field
		frm.set_query("case", function () {
			if (frm.doc.matter) {
				return {
					filters : {
						matter : frm.doc.matter,
					}
				}
			}
		});
		frm.set_query("task", function () {
			if (frm.doc.matter) {
				return {
					filters : {
						matter : frm.doc.matter,
					}
				}
			}
		});
	},
});
