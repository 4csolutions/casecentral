// Copyright (c) 2023, 4C Solutions and contributors
// For license information, please see license.txt

frappe.ui.form.on('Caveat', {
	refresh: function(frm) {
		frm.set_query('matter', () => {
			return {
				filters: {
					'service_type': 'Caveats'
				}
			};
		});
	},
	petitioner: function(frm){
		if (frm.doc.petitioner && frm.doc.respondent) {
			frm.set_value("caveat_title", frm.doc.petitioner + " V/s " + frm.doc.respondent);
		}
	},
	respondent: function(frm){
		if (frm.doc.petitioner && frm.doc.respondent) {
			frm.set_value("caveat_title", frm.doc.petitioner + " V/s " + frm.doc.respondent);
		}
	},
	filing_date: function(frm) {
		var expiry_date = frappe.datetime.add_days(frm.doc.filing_date, 90);
		frm.set_value('expiry_date', expiry_date);
	}
});
