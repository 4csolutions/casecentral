(() => {
  // ../casecentral/casecentral/public/js/task_quick_entry.js
  frappe.provide("frappe.ui.form");
  frappe.ui.form.TaskQuickEntryForm = class TaskQuickEntryForm extends frappe.ui.form.QuickEntryForm {
    constructor(doctype, after_insert, init_callback, doc, force) {
      super(doctype, after_insert, init_callback, doc, force);
      this.skip_redirect_on_error = true;
    }
    render_dialog() {
      this.mandatory = this.mandatory.concat(this.get_variant_fields());
      super.render_dialog();
    }
    get_variant_fields() {
      var variant_fields = [{
        fieldtype: "MultiSelectPills",
        fieldname: "assign_to",
        label: __("Assign To"),
        get_data: function(txt) {
          return frappe.db.get_link_options("User", txt, {
            user_type: "System User",
            enabled: 1
          });
        }
      }];
      return variant_fields;
    }
  };
})();
//# sourceMappingURL=casecentral.bundle.PXG6GYSC.js.map
