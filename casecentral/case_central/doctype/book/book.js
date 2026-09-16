// Copyright (c) 2023, 4C Solutions and contributors
// For license information, please see license.txt

frappe.ui.form.on('Book', {
	refresh: function(frm) {
		if(frm.doc.status == 'Available') {
			frm.add_custom_button(__('Lend Book'),function() {
				var doc = frappe.model.get_new_doc("Lend Book");
				doc.book_id = frm.doc.name;
				frappe.set_route('Form','Lend Book', doc.name);										
			});
		}
	},
	isbn: function(frm) {
		if(frm.doc.isbn) {
			frappe.call({
				method: 'casecentral.case_central.doctype.book.book.fetch_book_details',
				args: {
					isbn: frm.doc.isbn
				},
				callback: (r) => {
					if( r && r.message ) {
						var book_details = r.message;
						// Update the form fields with fetched book details using frm.set_value()
						Object.keys(book_details).forEach(function(key){
							frm.set_value(key, book_details[key]);
						});
					} else {
						frappe.msgprint(__("The Book details could not be fetched from Google Books"));
					}	
				}
			});
		}
	}
	
});
