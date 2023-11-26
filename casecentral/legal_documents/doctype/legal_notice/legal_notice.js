// Copyright (c) 2023, 4C Solutions and contributors
// For license information, please see license.txt

frappe.ui.form.on('Legal Notice', {
    refresh: function(frm) {
        // Add a custom button to trigger the creation of Postal Orders
		if(frm.doc.docstatus===1){
			frm.add_custom_button(__('Create Postal Orders'), function() {
				createPostalOrders(frm);
			});
		}
    }
});

function createPostalOrders(frm) {
    frappe.call({
        method: 'casecentral.legal_documents.doctype.postal_order.postal_order.create_postal_orders',
        args: {
			doctype: frm.doc.doctype,
            docname: frm.doc.name
        },
        callback: function(response) {
            if (response.message.length) {
                frappe.show_alert({
                    message: __('Postal Orders created successfully.'),
                    indicator: 'green'
                });
                frm.reload_doc();
            } else if(response.message) {
                frappe.show_alert({
                    message: __('Postal Orders already exist.'),
                    indicator: 'orange'
                });
            }
        }
    });
}

