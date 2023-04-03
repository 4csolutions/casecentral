// Copyright (c) 2023, 4C Solutions and contributors
// For license information, please see license.txt

frappe.ui.form.on('Case', {
	// refresh: function(frm) {
		
	// },
	after_save: function(frm) {
		if(frm.doc.status == "Pending" && frm.doc.registration_number) {
			frm.doc.status = "InProgress";
		}
		if(frm.doc.status=="Pending" || frm.doc.status=="InProgress") {
			frm.doc.documents_handover = 0;
		}
	},
	petitioner: function(frm){
		if (frm.doc.petitioner && frm.doc.respondent) {
			frm.set_value("case_title", frm.doc.petitioner + " V/s " + frm.doc.respondent);
		}
	},
	respondent: function(frm){
		if (frm.doc.petitioner && frm.doc.respondent) {
			frm.set_value("case_title", frm.doc.petitioner + " V/s " + frm.doc.respondent);
		}
	},
	ecase_type: function(frm){
		var ct_str = frm.doc.ecase_type.split("-")[0].trim().replace(/\./g, "");
		frm.set_value("case_type_abbr", ct_str);
		set_registration_number(frm);
	},
	case_no: function(frm){
		set_registration_number(frm);
	},
	case_year: function(frm){
		set_registration_number(frm);
	}
});

frappe.ui.form.on('Case History', {
	case_history_add: function(frm, cdt, cdn) {
		var rows = Object.entries(locals[cdt]);
		var current_row = locals[cdt][cdn];
		// The index in locals starts from 1 whereas in rows it starts from 0 as such 2 is subtracted
    	var previous_row = locals[cdt][rows[current_row.idx - 2][0]];
		if (previous_row) {
			current_row.judge = previous_row.judge;
			current_row.business_on_date = previous_row.hearing_date;
			current_row.purpose_of_hearing = previous_row.purpose_of_hearing;
			refresh_field('case_history');
		}
	}
});

var set_registration_number = function(frm) {
	if (frm.doc.case_type_abbr && frm.doc.case_no && frm.doc.case_year) {
		frm.set_value("registration_number", frm.doc.case_type_abbr + "_" + frm.doc.case_no + "_" + frm.doc.case_year);
	} else {
		frm.set_value("registration_number", "");
	}
}