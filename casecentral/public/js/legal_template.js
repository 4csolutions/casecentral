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
                if (templates && templates.length > 0) {
                    render_template_dashboard(frm, templates[0]);
                    inject_legal_doc_styles();

                    // Add polished primary action button
                    const gen_btn = frm.add_custom_button(__('Generate Document'), function () {
                        if (frm.is_new()) {
                            frappe.msgprint({
                                title: __('Document Not Saved'),
                                indicator: 'orange',
                                message: __('Please save this record before generating the legal document.')
                            });
                            return;
                        }
                        if (frm.is_dirty()) {
                            frappe.msgprint({
                                title: __('Unsaved Changes'),
                                indicator: 'orange',
                                message: __('You have unsaved changes. Please save the record first before generating.')
                            });
                            return;
                        }
                        show_smart_template_dialog(doctype, frm.docname, templates);
                    });

                    // Executive Dark styling with SVG icon
                    gen_btn.removeClass('btn-default').addClass('btn-primary').css({
                        'background-color': '#0f172a',
                        'border-color': '#0f172a',
                        'color': '#ffffff',
                        'font-weight': '600',
                        'font-size': '12.5px',
                        'box-shadow': '0 1px 3px rgba(0,0,0,0.12), 0 1px 2px rgba(0,0,0,0.08)',
                        'display': 'inline-flex',
                        'align-items': 'center',
                        'gap': '7px',
                        'padding': '5px 14px',
                        'border-radius': '6px',
                        'letter-spacing': '0.01em',
                        'transition': 'all 0.15s ease'
                    });

                    gen_btn.html(`
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" style="color: #38bdf8;">
                            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
                            <polyline points="14 2 14 8 20 8"></polyline>
                            <line x1="16" y1="13" x2="8" y2="13"></line>
                            <line x1="16" y1="17" x2="8" y2="17"></line>
                            <polyline points="10 9 9 9 8 9"></polyline>
                        </svg>
                        <span>${__('Generate Document')}</span>
                    `);
                }
            });
        }
    });
}

function render_template_dashboard(frm, template) {
    if (!frm.dashboard) return;

    frm.dashboard.clear_headline();
    const tpl_name = template.name;
    const matter = frm.doc.matter || '';
    const status_val = frm.doc.document_status || frm.doc.status || 'Draft';

    let pill_class = 'orange';
    if (status_val === 'Executed') pill_class = 'green';
    else if (status_val === 'Pending Execution') pill_class = 'blue';
    else if (status_val === 'Archived') pill_class = 'gray';

    const matter_badge = matter ? `
        <span style="display: inline-flex; align-items: center; gap: 5px; background: var(--control-bg); padding: 2px 8px; border-radius: 4px; border: 1px solid var(--border-color); font-size: 11.5px; color: var(--text-color);">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="color: #8b5cf6;"><circle cx="12" cy="12" r="10"></circle><path d="M8 12h8"></path><path d="M12 8v8"></path></svg>
            Matter: <strong><a href="/desk#Form/Matter/${encodeURIComponent(matter)}" style="color: inherit; text-decoration: underline;">${frappe.utils.escape_html(matter)}</a></strong>
        </span>
    ` : '';

    const headline_html = `
        <div class="legal-doc-headline" style="display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 10px; padding: 6px 0;">
            <div style="display: flex; align-items: center; gap: 10px; flex-wrap: wrap;">
                <span class="indicator-pill ${pill_class}" style="font-weight: 700; text-transform: uppercase; font-size: 11px; letter-spacing: 0.05em; padding: 3px 8px; border-radius: 4px;">
                    ${frappe.utils.escape_html(status_val)}
                </span>
                <span style="color: var(--text-muted); font-size: 12.5px; display: inline-flex; align-items: center; gap: 6px;">
                    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="color: #6366f1;"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline></svg>
                    Legal Template: <strong style="color: var(--text-color);">${frappe.utils.escape_html(tpl_name)}</strong>
                </span>
                ${matter_badge}
            </div>
            <div style="display: flex; align-items: center; gap: 6px; font-size: 11.5px; color: var(--text-muted);">
                <span style="display: inline-block; width: 6px; height: 6px; border-radius: 50%; background: #10b981;"></span>
                Ready for Word (.docx) & PDF generation
            </div>
        </div>
    `;

    frm.dashboard.set_headline(headline_html);
}

function inject_legal_doc_styles() {
    if ($('#legal-doc-custom-styles').length) return;

    const css = `
        <style id="legal-doc-custom-styles">
            .form-layout .form-section {
                border-top: 1px solid var(--border-color, #e2e8f0);
                margin-top: 20px;
                padding-top: 14px;
            }
            .form-layout .form-section:first-child {
                border-top: none;
                margin-top: 0;
                padding-top: 0;
            }
            .form-layout .section-head {
                font-size: 12px !important;
                font-weight: 700 !important;
                letter-spacing: 0.06em !important;
                text-transform: uppercase !important;
                color: var(--text-color, #1e293b) !important;
                margin-bottom: 14px !important;
                display: flex !important;
                align-items: center !important;
                gap: 8px !important;
            }
            .form-layout .section-head::before {
                content: "";
                display: inline-block;
                width: 4px;
                height: 14px;
                border-radius: 2px;
                background: #3b82f6;
            }
            .form-layout .form-column {
                padding: 0 15px;
            }
            .form-layout .frappe-control[data-fieldtype="Small Text"] textarea {
                border-radius: 6px;
                line-height: 1.5;
                font-size: 13px;
            }
            .form-layout .frappe-control input.form-control {
                border-radius: 6px;
                font-size: 13px;
            }
        </style>
    `;
    $('head').append(css);
}

function fetch_legal_templates(doctype) {
    return frappe.db.get_list('Legal Templates', {
        filters: { 'related_doctype': doctype },
        fields: ['name', 'template_file']
    });
}

function show_smart_template_dialog(doctype, docname, templates) {
    if (templates.length === 1) {
        // Direct single-click generation with confirmation
        const tpl_name = templates[0].name;
        frappe.confirm(
            __('Generate Word (.docx) agreement for <strong>{0}</strong> using template <strong>{1}</strong>?', [docname, tpl_name]),
            function () {
                open_url_post('/api/method/casecentral.legal_documents.doctype.legal_templates.legal_templates.generate_document', {
                    doctype: doctype,
                    docname: docname,
                    legal_template_name: tpl_name
                });
            }
        );
    } else {
        // Multiple templates available: prompt user to pick
        frappe.prompt([
            {
                fieldname: 'legal_template',
                label: __('Legal Template'),
                fieldtype: 'Link',
                options: 'Legal Templates',
                filters: { 'related_doctype': doctype },
                default: templates[0].name,
                reqd: 1
            }
        ], function (values) {
            open_url_post('/api/method/casecentral.legal_documents.doctype.legal_templates.legal_templates.generate_document', {
                doctype: doctype,
                docname: docname,
                legal_template_name: values.legal_template
            });
        }, __('Generate Document'), __('Download Word Document'));
    }
}