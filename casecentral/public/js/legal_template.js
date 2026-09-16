frappe.router.on("change", page_changed);

function page_changed(event) {
    frappe.after_ajax(function () {
        var route = frappe.get_route();
        if (route[1] == "DocType") return;
        if (route[0] == "Form") {
            setup_legal_template_button(route[1]);
        }
    });
}

function setup_legal_template_button(doctype) {
    frappe.ui.form.on(doctype, {
        refresh: function (frm) {
            fetch_legal_templates(doctype).then(function (templates) {
                if (templates.length > 0) {
                    frm.add_custom_button(__('Generate Document'), function () {
                        show_legal_template_prompt(doctype, frm.docname);
                    });
                }
            });
        }
    });
}

function fetch_legal_templates(doctype) {
    return frappe.db.get_list('Legal Templates', {
        filters: { 'related_doctype': doctype },
        fields: ['name']
    });
}

function show_legal_template_prompt(doctype, docname) {
    frappe.prompt([
        {
            fieldname: 'legal_template',
            label: __('Legal Template'),
            fieldtype: 'Link',
            options: 'Legal Templates',
            filters: { 'related_doctype': doctype },
            reqd: 1
        }
    ], function (values) {
        open_url_post('/api/method/casecentral.legal_documents.doctype.legal_templates.legal_templates.generate_document', {
            doctype: doctype,
            docname: docname,
            legal_template_name: values.legal_template
        });
    }, __('Select Legal Template'), __('Generate'));
}