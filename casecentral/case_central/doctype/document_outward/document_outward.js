// Copyright (c) 2023, 4C Solutions and contributors
// For license information, please see license.txt

frappe.ui.form.on('Document Outward', {
	refresh: function(frm) {
		frm.set_query('case', () => {
			return {
				filters: {
					'matter': frm.doc.matter
				}
			};
		});
	}
});
