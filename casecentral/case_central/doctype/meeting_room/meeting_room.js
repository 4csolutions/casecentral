// Copyright (c) 2023, 4C Solutions and contributors

// For license information, please see license.txt

frappe.ui.form.on('Meeting Room', {
	refresh: function(frm) {
		frm.toggle_display(['address_html', 'contact_html'], !frm.is_new());

		if (!frm.is_new()) {
			frappe.contacts.render_address_and_contact(frm);
			frappe.dynamic_link = {doc: frm.doc, fieldname: 'name', doctype: 'Meeting Room'}
		} else {
			frappe.contacts.clear_address_and_contact(frm);
		}
	},

	allow_appointments: function(frm) {
		if (!frm.doc.allow_appointments) {
			frm.set_value('overlap_appointments', false);
		}
	},

	overlap_appointments: function(frm) {
		if (frm.doc.overlap_appointments == 0) {
			frm.set_value('meeting_room_capacity', '');
		}
	}
});

