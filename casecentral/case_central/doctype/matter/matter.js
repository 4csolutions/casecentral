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
			} else {
				frappe.msgprint({
					title: __('Notification'),
					indicator: 'red',
					message: __('Please choose matter type first')
				});
			}
		});
		frm.set_query('service', () => {
			if (frm.doc.service_type) {
				return {
					filters: {
						'service_type': frm.doc.service_type
					}
				};
			} else {
				frappe.msgprint({
					title: __('Notification'),
					indicator: 'red',
					message: __('Please choose service type first')
				});
			}
		});
		frappe.call({
			method: 'get_billing_info',
			doc: frm.doc,
			callback: function(r) {
			    frm.dashboard.stats_area_row.empty();
			    frm.dashboard.add_indicator(__('Total Matter Billing: {0}', [format_currency(r.message.total_billing)]), 'blue');
                frm.dashboard.add_indicator(__('Total Unpaid: {0}', [format_currency(r.message.total_unpaid)]), 'orange');
                frm.dashboard.add_indicator(__('Total Matter Advances: {0}', [format_currency(r.message.total_advances)]), 'green');
			}
		});
	}
});