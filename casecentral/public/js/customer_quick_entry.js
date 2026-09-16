frappe.provide('frappe.ui.form');

// Desk environment doesn't have frappe.ready, and casecentral loads last, so we can patch directly or via a short timeout
setTimeout(() => {
    if (frappe.ui.form.CustomerQuickEntryForm) {
        const original_insert = frappe.ui.form.CustomerQuickEntryForm.prototype.insert;
        
        frappe.ui.form.CustomerQuickEntryForm.prototype.insert = function() {
            if (this.doctype === 'Customer') {
                return new Promise((resolve, reject) => {
                    
                    // india_compliance uses _mobile_no, erpnext uses mobile_number, frappe standard uses mobile_no
                    const mobile_no = this.dialog.get_value('_mobile_no') || this.dialog.get_value('mobile_number') || this.dialog.get_value('mobile_no');
                    if (!mobile_no) {
                        original_insert.call(this).then(resolve).catch(reject);
                        return;
                    }

                    frappe.call({
                        method: "frappe.client.get_value",
                        args: {
                            doctype: "Customer",
                            filters: { mobile_no: mobile_no },
                            fieldname: "name"
                        },
                        callback: (r) => {
                            if (r.message && r.message.name && r.message.name !== this.doc.name) {
                                frappe.confirm(
                                    __('Mobile number {0} already exists for Customer {1}. Do you want to continue?', [mobile_no, r.message.name]),
                                    () => {
                                        original_insert.call(this).then(resolve).catch(reject);
                                    },
                                    () => {
                                        this.dialog.working = false;
                                        if (this.dialog.clear_message) {
                                            this.dialog.clear_message();
                                        }
                                        resolve();
                                    }
                                );
                            } else {
                                original_insert.call(this).then(resolve).catch(reject);
                            }
                        }
                    });
                });
            } else {
                return original_insert.call(this);
            }
        };
    } else {
        console.warn("CustomerQuickEntryForm not found!");
    }
}, 500);
