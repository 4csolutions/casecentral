// Copyright (c) 2022, 4C Solutions and contributors
// For license information, please see license.txt

frappe.ui.form.on('Matter', {
	refresh: function(frm) {
		frm.set_query('service_type', () => { 
			if (frm.doc.matter_type) {
				return {
					filters: {
						'matter_type': frm.doc.matter_type
					}
				};
			}
		});
		frm.set_query('service', () => { 
			if (frm.doc.service_type) {
				return {
					filters: {
						'service_type': frm.doc.service_type
					}
				};
			}
		});
	}
});
