// Copyright (c) 2023, 4C Solutions and contributors
// For license information, please see license.txt

frappe.ui.form.on('Legal Service', {
	refresh: function(frm) {
		frm.set_df_property('item_code', 'read_only', frm.doc.__islocal ? 0 : 1);
		if (!frm.doc.__islocal) {
			frm.add_custom_button(__('Change Item Code'), function() {
				change_item_code(cur_frm, frm.doc);
			});
		}
	},

	legal_service: function(frm) {
		set_item_details(frm);
		mark_change_in_item(frm);
	},

	rate: function(frm) {
		mark_change_in_item(frm);
	},

	item_group: function(frm) {
		mark_change_in_item(frm);
	},

	description: function(frm) {
		mark_change_in_item(frm);
	},

	disabled: function(frm) {
		mark_change_in_item(frm);
	}
});

let set_item_details = function(frm) {
	if (frm.doc.__islocal) {
		frm.set_value('item_code', frm.doc.legal_service);
		frm.set_value('description', frm.doc.legal_service);
		if (!frm.doc.item_group)
			frm.set_value('item_group', 'Services');
	}
};

let mark_change_in_item = function(frm) {
	if (!frm.doc.__islocal) {
		frm.doc.change_in_item = 1;
	}
};

let change_item_code = function(frm, doc) {
	let d = new frappe.ui.Dialog({
		title: __('Change Item Code'),
		fields: [
			{
				'fieldtype': 'Data',
				'label': 'Item Code',
				'fieldname': 'item_code',
				'default': doc.item_code,
				reqd: 1,
			}
		],
		primary_action: function() {
			let values = d.get_values();
			if (values) {
				frappe.call({
					"method": "casecentral.case_central.doctype.legal_service.legal_service.change_item_code",
					"args": {item: doc.item, item_code: values['item_code'], doc_name: doc.name},
					callback: function () {
						cur_frm.reload_doc();
						frappe.show_alert({
							message: 'Item Code renamed successfully',
							indicator: 'green'
						});
					}
				});
			}
			d.hide();
		},
		primary_action_label: __("Change Template Code")
	});

	d.show();
	d.set_values({
		'Item Code': frm.doc.item_code
	});
};
