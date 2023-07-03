// Copyright (c) 2023, 4C Solutions and contributors
// For license information, please see license.txt

frappe.ui.form.on('Lend Book', {
	refresh: function(frm) {

	},

	after_save: function(frm) {

		var bookId = frm.doc.book_id;
		var lendBookId = frm.doc.name;
		var returnDate = frm.doc.return_date;

		frappe.call({
			method: 'frappe.client.set_value',
			args: {
				doctype: 'Book',
				name: bookId,
				fieldname: 'status',
				value: returnDate ? 'Available' : 'Issued'
			},
			callback: function(response) {
				if (response.message) {
					frappe.show_alert('Book status updated successfully');
				} else {
					frappe.show_alert('Failed to update Lend Book status');
				}
			}
		});	
		
		frappe.call({
			method: 'frappe.client.set_value',
			args: {
				doctype: 'Lend Book',
				name: lendBookId,
				fieldname: 'status',
				value: returnDate ? 'Returned' : 'Issued'
			},
			callback: function(response) {
				if (response.message) {
					frappe.show_alert('Lend Book status updated successfully');
				} else {
					frappe.show_alert('Failed to update Lend Book status');
				}
			}
		});

	}	
});
