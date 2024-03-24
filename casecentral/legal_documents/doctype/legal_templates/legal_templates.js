// Copyright (c) 2024, 4C Solutions and contributors
// For license information, please see license.txt

frappe.ui.form.on('Legal Templates', {
	refresh: function(frm) {
        // Add a custom button to trigger the generation of a new doctype
        frm.add_custom_button(__('Create New Doctype'), function() {
            frm.call({
                method: 'generate_new_doctype',
                args: {
                    legal_template_name: frm.doc.name
                },
                callback: function(response) {
                    if (response.message) {
                        // Redirect to the new doctype
                        frappe.set_route('Form', 'DocType', response.message);
                    } else {
                        frappe.msgprint(__('Failed to generate new doctype'));
                    }
                }
            });
        });
    }
});