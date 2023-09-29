frappe.ui.form.on('Payment Entry', {
	refresh: function(frm) {
		if (frm.doc.custom_matter) {
			frm.set_value("party_type", "Customer");
			frappe.db.get_value("Matter", frm.doc.custom_matter, "customer").then((result) => {
				if(result.message) {
					frm.set_value("party", result.message.customer);
				}
			});		
		}
		frm.set_query('custom_matter', () => {
			if (frm.doc.party) {
				return {
					filters: {
						'customer': frm.doc.party
					}
				}
			}
		});
	},
	custom_matter: function(frm) {
		frm.set_value("party_type", "Customer");
		frappe.db.get_value("Matter", frm.doc.custom_matter, "customer").then((result) => {
			if(result.message) {
				frm.set_value("party", result.message.customer);
			}
		});
	}
});