// Copyright (c) 2024, 4C Solutions and contributors
// For license information, please see license.txt

frappe.ui.form.on('Legal Templates', {
	refresh: function(frm) {
		if (frm.doc.template_file) {
			// Option 1 Path: Word document attached -> Open AI Template Studio
			let studio_btn_label = frm.doc.related_doctype ? __('AI Template Studio') : __('AI Template Studio');
			let btn = frm.add_custom_button(studio_btn_label, function() {
				open_ai_template_studio(frm);
			});
			btn.addClass('btn-primary');

			// Download Word template with highlighted Jinja variables
			frm.add_custom_button(__('📥 Download Template (.docx)'), function() {
				window.open(`/api/method/casecentral.legal_documents.doctype.legal_templates.template_studio.download_jinja_template?legal_template_name=${encodeURIComponent(frm.doc.name)}`);
			});

			// Also allow re-drafting from prompt if desired
			frm.add_custom_button(__('✨ Re-draft with AI'), function() {
				open_prompt_drafting_dialog(frm);
			});

			if (!frm.doc.related_doctype) {
				// Standard / Legacy Create New Doctype Button (preserved)
				frm.add_custom_button(__('Create New Doctype (Legacy)'), function() {
					frm.call({
						method: 'generate_new_doctype',
						args: {
							legal_template_name: frm.doc.name
						},
						callback: function(response) {
							if (response.message) {
								frappe.set_route('Form', 'DocType', response.message);
							} else {
								frappe.msgprint(__('Failed to generate new doctype'));
							}
						}
					});
				});
			} else {
				frm.add_custom_button(__('Open Related DocType'), function() {
					frappe.set_route('List', frm.doc.related_doctype);
				});
			}
		} else {
			// No file attached: present both options (Prompt or Attach docx)
			render_template_creation_choices(frm);

			let ai_draft_btn = frm.add_custom_button(__('✨ Draft with AI Prompt'), function() {
				open_prompt_drafting_dialog(frm);
			});
			ai_draft_btn.addClass('btn-primary').css({
				'background-color': '#0f172a',
				'border-color': '#0f172a',
				'color': '#ffffff',
				'font-weight': '600',
				'box-shadow': '0 1px 3px rgba(0,0,0,0.1)'
			});
		}
	}
});

function open_ai_template_studio(frm) {
	frappe.show_progress(__('Loading Studio'), 20, 100, __('Fetching document preview...'));

	// Fetch HTML preview and text
	frappe.call({
		method: 'casecentral.legal_documents.doctype.legal_templates.template_studio.get_document_preview',
		args: {
			legal_template_name: frm.doc.name
		},
		callback: function(r_preview) {
			if (!r_preview.message) {
				frappe.hide_progress();
				frappe.msgprint(__('Failed to generate document preview.'));
				return;
			}

			frappe.show_progress(__('Loading Studio'), 60, 100, __('Generating variables with Flow AI API...'));

			// Detect variables via Frappe Flow AI
			frappe.call({
				method: 'casecentral.legal_documents.doctype.legal_templates.template_studio.detect_variables',
				args: {
					legal_template_name: frm.doc.name
				},
				callback: function(r_vars) {
					frappe.hide_progress();
					let res = r_vars.message || {};
					let detected_vars = Array.isArray(res) ? res : (res.variables || []);
					let meta_info = {
						status: res.status || 'success',
						engine_used: res.engine_used || 'Flow AI',
						token_usage: res.token_usage || null,
						flow_installed: res.flow_installed || false,
						message: res.message || ''
					};
					render_template_studio_dialog(frm, r_preview.message.html, detected_vars, meta_info);

					if (res.status === 'warning') {
						frappe.show_alert({
							message: __(res.message || 'Flow AI temporarily unavailable; using Built-in Smart Legal NLP.'),
							indicator: 'orange'
						}, 7);
					} else if (res.status === 'needs_key') {
						frappe.show_alert({
							message: __('Flow AI API key required to generate variables. Please configure your key in Flow Settings.'),
							indicator: 'orange'
						}, 7);
						// Automatically pop up Flow settings for direct input
						setTimeout(() => {
							$('.studio-ai-key-btn').trigger('click');
						}, 350);
					}
				},
				error: function(err) {
					frappe.hide_progress();
					frappe.show_alert({
						message: __('Flow AI API is currently busy or unavailable. Opened Studio with Built-in Engine.'),
						indicator: 'orange'
					}, 7);
					let meta_info = {
						status: 'warning',
						engine_used: 'Built-in Smart Legal NLP',
						token_usage: null,
						flow_installed: true,
						message: 'Switched to Built-in Engine'
					};
					render_template_studio_dialog(frm, r_preview.message.html, [], meta_info);
				}
			});
		}
	});
}

const FRAPPE_FIELDTYPE_GROUPS = [
	{
		label: __('Standard / Common'),
		items: [
			{ value: 'Data', label: 'Data (Text)' },
			{ value: 'Date', label: 'Date' },
			{ value: 'Datetime', label: 'Datetime' },
			{ value: 'Time', label: 'Time' },
			{ value: 'Duration', label: 'Duration' },
			{ value: 'Currency', label: 'Currency' },
			{ value: 'Int', label: 'Int (Integer)' },
			{ value: 'Float', label: 'Float (Decimal)' },
			{ value: 'Percent', label: 'Percent (%)' },
			{ value: 'Check', label: 'Check (Checkbox / Boolean)' },
			{ value: 'Select', label: 'Select (Dropdown)' },
			{ value: 'Phone', label: 'Phone Number' },
			{ value: 'Signature', label: 'Signature (Digital / Sign)' }
		]
	},
	{
		label: __('Text & Content'),
		items: [
			{ value: 'Small Text', label: 'Small Text (Multi-line Address/Notes)' },
			{ value: 'Text', label: 'Text' },
			{ value: 'Long Text', label: 'Long Text' },
			{ value: 'Text Editor', label: 'Text Editor (Rich Text)' },
			{ value: 'Markdown Editor', label: 'Markdown Editor' },
			{ value: 'HTML Editor', label: 'HTML Editor' },
			{ value: 'HTML', label: 'HTML' },
			{ value: 'Code', label: 'Code' },
			{ value: 'JSON', label: 'JSON' }
		]
	},
	{
		label: __('Relationships & Tables'),
		items: [
			{ value: 'Link', label: 'Link (DocType Reference)' },
			{ value: 'Dynamic Link', label: 'Dynamic Link' },
			{ value: 'Table', label: 'Table (Child Table)' },
			{ value: 'Table MultiSelect', label: 'Table MultiSelect' }
		]
	},
	{
		label: __('Media & Attachments'),
		items: [
			{ value: 'Attach', label: 'Attach (File)' },
			{ value: 'Attach Image', label: 'Attach Image' },
			{ value: 'Attachment Gallery', label: 'Attachment Gallery' },
			{ value: 'Image', label: 'Image' }
		]
	},
	{
		label: __('Special & Controls'),
		items: [
			{ value: 'Autocomplete', label: 'Autocomplete' },
			{ value: 'Barcode', label: 'Barcode' },
			{ value: 'Color', label: 'Color Picker' },
			{ value: 'Geolocation', label: 'Geolocation' },
			{ value: 'Icon', label: 'Icon' },
			{ value: 'Rating', label: 'Rating' },
			{ value: 'Password', label: 'Password' },
			{ value: 'Read Only', label: 'Read Only' },
			{ value: 'Heading', label: 'Heading' },
			{ value: 'Button', label: 'Button' }
		]
	},
	{
		label: __('Layout Break Fields'),
		items: [
			{ value: 'Section Break', label: 'Section Break' },
			{ value: 'Column Break', label: 'Column Break' },
			{ value: 'Tab Break', label: 'Tab Break' },
			{ value: 'Fold', label: 'Fold' }
		]
	}
];

function render_fieldtype_select_options(selected_value) {
	let html = '';
	let found = false;
	FRAPPE_FIELDTYPE_GROUPS.forEach(group => {
		html += `<optgroup label="${group.label}">`;
		group.items.forEach(item => {
			let is_sel = (item.value === selected_value);
			if (is_sel) found = true;
			html += `<option value="${item.value}" ${is_sel ? 'selected' : ''}>${item.label}</option>`;
		});
		html += `</optgroup>`;
	});
	if (selected_value && !found) {
		html = `<option value="${frappe.utils.escape_html(selected_value)}" selected>${frappe.utils.escape_html(selected_value)}</option>` + html;
	}
	return html;
}

function get_all_fieldtype_dialog_options() {
	let options = [];
	FRAPPE_FIELDTYPE_GROUPS.forEach(group => {
		group.items.forEach(item => {
			options.push({
				label: `${item.label} [${item.value}]`,
				value: item.value
			});
		});
	});
	return options;
}

function render_template_studio_dialog(frm, doc_html, initial_variables, initial_meta) {
	let variables = [...initial_variables];
	let current_meta = Object.assign({
		status: 'success',
		engine_used: 'Flow AI',
		token_usage: null,
		flow_installed: false
	}, initial_meta || {});

	let d = new frappe.ui.Dialog({
		title: __('AI Legal Template Studio: {0}', [frm.doc.template_name]),
		size: 'extra-large',
		fields: [
			{
				fieldtype: 'HTML',
				fieldname: 'studio_container'
			}
		],
		primary_action_label: __('Finalize Template & Create DocType'),
		primary_action: function() {
			if (variables.length === 0) {
				frappe.msgprint(__('Please keep or add at least one variable before generating.'));
				return;
			}

			if (is_edit_mode) {
				let raw_edited = $wrapper.find('.studio-doc-content').html();
				current_doc_html = strip_marks_from_html(raw_edited);
			}

			d.get_primary_btn().prop('disabled', true).text(__('Generating Template...'));

			frappe.call({
				method: 'casecentral.legal_documents.doctype.legal_templates.template_studio.finalize_template_and_doctype',
				args: {
					legal_template_name: frm.doc.name,
					approved_variables: JSON.stringify(variables),
					edited_html: current_doc_html
				},
				freeze: true,
				freeze_message: __('Transforming Word doc to Jinja and creating DocType...'),
				callback: function(res) {
					d.hide();
					if (res.message && res.message.status === 'success') {
						frappe.show_alert({
							message: __('Template & DocType "{0}" created successfully!', [res.message.doctype_name]),
							indicator: 'green'
						}, 7);

						frm.reload_doc().then(() => {
							frappe.confirm(
								__('DocType "{0}" is ready. Do you want to open it now?', [res.message.doctype_name]),
								function() {
									frappe.set_route('Form', 'DocType', res.message.doctype_name);
								}
							);
						});
					} else {
						frappe.msgprint(__('Failed to finalize template. Please check error logs.'));
					}
				}
			});
		}
	});

	// Build the studio layout HTML
	let html_content = `
		<div class="ai-studio-wrapper" style="display: flex; gap: 14px; height: 75vh; min-height: 560px; max-height: 800px;">
			<!-- LEFT COLUMN: Document Preview & Editor -->
			<div class="doc-preview-pane" style="flex: 1.35; display: flex; flex-direction: column; border: 1px solid var(--border-color); border-radius: 8px; background: #f8fafc; padding: 10px 12px;">
				<div class="doc-preview-header" style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; padding-bottom: 8px; border-bottom: 3px solid #334155; flex-wrap: nowrap;">
					<div style="display: flex; align-items: center; gap: 12px;">
						<span style="font-weight: 700; font-size: 13.5px; color: #0f172a; white-space: nowrap;">
							<i class="fa fa-file-word-o" style="color: #2563eb;"></i> Document Preview
						</span>
						<!-- Mode Switcher Buttons: Preview vs Edit -->
						<div class="studio-mode-buttons" style="display: flex; gap: 8px; align-items: center;">
							<button type="button" class="btn btn-xs studio-mode-btn studio-btn-preview-mode active" style="font-weight: 700; padding: 4px 13px; font-size: 12px; border-radius: 6px; background-color: #dc2626; border: 1.5px solid #b91c1c; color: #ffffff; box-shadow: 0 2px 4px rgba(220, 38, 38, 0.3); transition: all 0.15s ease;">
								<i class="fa fa-eye" style="color: #ffffff; margin-right: 4px;"></i> Preview
							</button>
							<button type="button" class="btn btn-xs studio-mode-btn studio-btn-edit-mode" style="font-weight: 600; padding: 4px 13px; font-size: 12px; border-radius: 6px; background-color: #ffffff; border: 1.5px solid #cbd5e1; color: #475569; transition: all 0.15s ease;">
								<i class="fa fa-pencil" style="color: #d97706; margin-right: 4px;"></i> Edit Content
							</button>
						</div>
					</div>
					<div style="display: flex; gap: 6px; align-items: center; white-space: nowrap;">
						<button type="button" class="btn btn-xs studio-download-tpl-btn" title="Download Word template (.docx) with highlighted Jinja variables" style="font-weight: 600; padding: 3px 9px; font-size: 11.5px; border-radius: 5px; background: #ffffff; border: 1.5px solid #0284c7; color: #0284c7; cursor: pointer;">
							<i class="fa fa-download" style="color: #0284c7; margin-right: 3px;"></i> Download (.docx)
						</button>
						<span class="badge studio-engine-badge" style="background: #eef2ff; color: #4338ca; border: 1px solid #c7d2fe; font-weight: 600; padding: 3px 8px; border-radius: 4px; font-size: 11px;">
							<i class="fa fa-bolt" style="color: #6366f1;"></i> <span class="engine-name">${frappe.utils.escape_html(current_meta.engine_used)}</span>
						</span>
						<span class="badge badge-info studio-var-counter" style="padding: 3px 8px; font-size: 11px;">${variables.length} Variables</span>
					</div>
				</div>

				<!-- EDITING TOOLBAR (Slim & Single-line, visible in Edit Mode) -->
				<div class="studio-edit-toolbar" style="display: none; background: #ffffff; border: 1px solid #cbd5e1; border-radius: 6px; padding: 4px 8px; margin-bottom: 6px; box-shadow: 0 1px 2px rgba(0,0,0,0.04); align-items: center; justify-content: space-between;">
					<div style="display: flex; gap: 4px; align-items: center; flex-wrap: nowrap;">
						<div class="btn-group btn-group-xs">
							<button type="button" class="btn btn-default studio-tb-cmd" data-cmd="bold" title="Bold (Ctrl+B)"><b>B</b></button>
							<button type="button" class="btn btn-default studio-tb-cmd" data-cmd="italic" title="Italic (Ctrl+I)"><i>I</i></button>
							<button type="button" class="btn btn-default studio-tb-cmd" data-cmd="underline" title="Underline (Ctrl+U)"><u>U</u></button>
						</div>
						<div class="btn-group btn-group-xs">
							<button type="button" class="btn btn-default studio-tb-cmd" data-cmd="formatBlock" data-val="<h2>" title="Section Heading 2"><b>H2</b></button>
							<button type="button" class="btn btn-default studio-tb-cmd" data-cmd="formatBlock" data-val="<h3>" title="Heading 3"><b>H3</b></button>
							<button type="button" class="btn btn-default studio-tb-cmd" data-cmd="formatBlock" data-val="<p>" title="Paragraph">¶</button>
						</div>
						<div class="btn-group btn-group-xs">
							<button type="button" class="btn btn-default studio-tb-cmd" data-cmd="insertUnorderedList" title="Bullet List"><i class="fa fa-list-ul"></i></button>
							<button type="button" class="btn btn-default studio-tb-cmd" data-cmd="insertOrderedList" title="Numbered List"><i class="fa fa-list-ol"></i></button>
						</div>
						<span style="font-size: 11px; color: #64748b; margin-left: 6px;">
							<i class="fa fa-pencil" style="color: #d97706;"></i> Edit text directly below. Type <code>{{ var_name }}</code> for tags.
						</span>
					</div>
					<div style="display: flex; gap: 6px; align-items: center; white-space: nowrap;">
						<button type="button" class="btn btn-xs btn-default studio-btn-cancel-edit" style="padding: 2px 8px; font-size: 11px;">Cancel</button>
						<button type="button" class="btn btn-xs btn-success studio-btn-save-edit" style="padding: 2px 10px; font-size: 11px; font-weight: 600;">
							<i class="fa fa-check"></i> Done Editing
						</button>
					</div>
				</div>

				<div class="studio-doc-content" style="flex: 1; height: 100%; min-height: 480px; overflow-y: auto; background: #ffffff; padding: 18px 22px; border-radius: 6px; box-shadow: 0 1px 3px rgba(0,0,0,0.06); font-family: 'Georgia', serif; font-size: 14px; line-height: 1.65; color: #1e293b; user-select: text; border: 1px solid #e2e8f0; transition: all 0.2s ease;">
					<!-- Content injected dynamically -->
				</div>
			</div>

			<!-- RIGHT COLUMN: Variables Management Sidebar -->
			<div class="vars-manager-pane" style="flex: 1; display: flex; flex-direction: column; border: 1px solid var(--border-color); border-radius: 8px; background: #ffffff; padding: 10px 12px;">
				<div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; border-bottom: 2px solid #cbd5e1; padding-bottom: 8px;">
					<h6 style="margin: 0; font-weight: 600;"><i class="fa fa-sliders" style="color: #10b981;"></i> Detected Variables</h6>
					<div style="display: flex; gap: 6px;">
						<button class="btn btn-xs btn-default studio-ai-key-btn" title="Frappe Flow Client AI Models & Settings"><i class="fa fa-bolt" style="color: #6366f1;"></i> Flow AI Settings</button>
						<button class="btn btn-xs btn-default studio-add-var-btn"><i class="fa fa-plus"></i> Add Variable</button>
					</div>
				</div>
				<div class="studio-vars-list" style="flex: 1; overflow-y: auto; padding-right: 4px;">
					<!-- Variables cards rendered dynamically -->
				</div>
			</div>
		</div>
	`;

	// Inject layout into container
	d.fields_dict.studio_container.$wrapper.html(html_content);

	// Show dialog FIRST so all DOM nodes are attached to document body
	d.show();

	// Expand dialog dimensions on extra-large screen for maximum document editing visibility
	d.$wrapper.find('.modal-dialog').css({ 'max-width': '1240px', 'width': '95vw' });
	d.$wrapper.find('.modal-content').css({ 'border-radius': '10px' });
	d.$wrapper.find('.modal-body').css({ 'padding': '10px 14px' });

	// Scope all DOM queries strictly to this dialog instance
	const $wrapper = d.$wrapper;

	function strip_marks_from_html(html) {
		let $temp = $('<div>').html(html || '');
		$temp.find('mark.studio-mark').each(function() {
			$(this).find('span').remove();
			$(this).replaceWith($(this).text());
		});
		return $temp.html();
	}

	let current_doc_html = strip_marks_from_html(doc_html || '');
	let is_edit_mode = false;

	// Mode button state toggler: selected button turns RED (#dc2626)
	function set_mode_button_state(mode) {
		let $btnPreview = $wrapper.find('.studio-btn-preview-mode');
		let $btnEdit = $wrapper.find('.studio-btn-edit-mode');

		if (mode === 'edit') {
			$btnEdit.addClass('active').css({
				'background-color': '#dc2626',
				'border-color': '#b91c1c',
				'color': '#ffffff',
				'font-weight': '700',
				'box-shadow': '0 2px 4px rgba(220, 38, 38, 0.3)'
			});
			$btnEdit.find('i').css('color', '#ffffff');

			$btnPreview.removeClass('active').css({
				'background-color': '#ffffff',
				'border-color': '#cbd5e1',
				'color': '#475569',
				'font-weight': '600',
				'box-shadow': 'none'
			});
			$btnPreview.find('i').css('color', '#2563eb');
		} else {
			$btnPreview.addClass('active').css({
				'background-color': '#dc2626',
				'border-color': '#b91c1c',
				'color': '#ffffff',
				'font-weight': '700',
				'box-shadow': '0 2px 4px rgba(220, 38, 38, 0.3)'
			});
			$btnPreview.find('i').css('color', '#ffffff');

			$btnEdit.removeClass('active').css({
				'background-color': '#ffffff',
				'border-color': '#cbd5e1',
				'color': '#475569',
				'font-weight': '600',
				'box-shadow': 'none'
			});
			$btnEdit.find('i').css('color', '#d97706');
		}
	}

	function enter_edit_mode() {
		is_edit_mode = true;
		set_mode_button_state('edit');
		$wrapper.find('.studio-edit-toolbar').slideDown(120);

		let $content = $wrapper.find('.studio-doc-content');
		$content.attr('contenteditable', 'true');
		$content.html(current_doc_html);
		$content.css({
			'border': '2px solid #dc2626',
			'box-shadow': '0 0 0 3px rgba(220, 38, 38, 0.12)',
			'background': '#ffffff'
		});
		$content.focus();
	}

	function exit_and_save_edit_mode() {
		let edited = $wrapper.find('.studio-doc-content').html();
		let cleaned = strip_marks_from_html(edited);
		current_doc_html = cleaned;

		// Detect any typed Jinja variables like {{ my_var }}
		let matches = cleaned.matchAll(/\{\{\s*([a-zA-Z0-9_]+)\s*\}\}/g);
		for (let m of matches) {
			let vname = m[1].trim();
			if (!variables.some(v => v.variable_name === vname)) {
				variables.push({
					original_text: m[0],
					variable_name: vname,
					label: vname.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase()),
					fieldtype: 'Data'
				});
			}
		}

		// Save to server in background
		frappe.call({
			method: 'casecentral.legal_documents.doctype.legal_templates.template_studio.save_template_content',
			args: {
				legal_template_name: frm.doc.name,
				edited_html: current_doc_html
			},
			callback: function(r_save) {
				if (r_save.message && r_save.message.status === 'success') {
					frappe.show_alert({ message: __('Document edits saved to Word template!'), indicator: 'green' }, 4);
				}
			}
		});

		is_edit_mode = false;
		set_mode_button_state('preview');
		$wrapper.find('.studio-edit-toolbar').slideUp(120);

		let $content = $wrapper.find('.studio-doc-content');
		$content.attr('contenteditable', 'false');
		$content.css({
			'border': '1px solid #e2e8f0',
			'box-shadow': '0 1px 3px rgba(0,0,0,0.06)'
		});

		update_preview_and_vars();
	}

	function cancel_edit_mode() {
		is_edit_mode = false;
		set_mode_button_state('preview');
		$wrapper.find('.studio-edit-toolbar').slideUp(120);

		let $content = $wrapper.find('.studio-doc-content');
		$content.attr('contenteditable', 'false');
		$content.css({
			'border': '1px solid #e2e8f0',
			'box-shadow': '0 1px 3px rgba(0,0,0,0.06)'
		});

		update_preview_and_vars();
	}

	function update_preview_and_vars() {
		if (is_edit_mode) return;

		// Sort variables according to their order of appearance in the document text (top-to-bottom)
		let search_source = (current_doc_html || '').toLowerCase();
		variables.sort((a, b) => {
			let posA = search_source.indexOf((a.original_text || '').toLowerCase());
			let posB = search_source.indexOf((b.original_text || '').toLowerCase());
			if (posA === -1) posA = 999999;
			if (posB === -1) posB = 999999;
			return posA - posB;
		});

		// Update Counter Badges & Engine Status
		$wrapper.find('.studio-var-counter').text(`${variables.length} Variables`);
		$wrapper.find('.studio-engine-badge .engine-name').text(current_meta.engine_used || 'Built-in Smart Legal NLP');
		if (current_meta.token_usage && current_meta.token_usage.total_tokens) {
			$wrapper.find('.studio-tokens-badge .token-count').text(current_meta.token_usage.total_tokens.toLocaleString());
			$wrapper.find('.studio-tokens-badge')
				.attr('title', `Prompt: ${current_meta.token_usage.prompt_tokens || 0} tokens | Output: ${current_meta.token_usage.completion_tokens || 0} tokens`)
				.show();
		} else {
			$wrapper.find('.studio-tokens-badge').hide();
		}

		// Build highlighted HTML safely with tokenization to prevent nested tag duplication
		let highlighted = current_doc_html || '';
		try {
			let sorted = [...variables].sort((a, b) => (b.original_text || '').length - (a.original_text || '').length);
			let tokens = [];

			sorted.forEach((v, i) => {
				if (!v.original_text) return;
				let token = `___VAR_TOKEN_${i}___`;

				let is_already_jinja = (v.original_text || '').trim().startsWith('{{') && (v.original_text || '').trim().endsWith('}}');
				let pattern = is_already_jinja
					? `\\{\\{\\s*${v.variable_name}\\s*\\}\\}`
					: v.original_text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

				let regex = new RegExp(`(${pattern})`, 'gi');
				highlighted = highlighted.replace(regex, token);

				let mark_inner = is_already_jinja
					? `<span style="font-family: monospace; font-weight: 600; color: #1e293b;">{{ ${v.variable_name} }}</span>`
					: `${frappe.utils.escape_html(v.original_text)} <span style="font-size: 11px; background: #eab308; color: #ffffff; padding: 1px 4px; border-radius: 3px; font-family: monospace;">{{${v.variable_name}}}</span>`;

				tokens.push({
					token: token,
					html: `<mark class="studio-mark" data-var="${v.variable_name}" title="Click to delete this variable" style="background-color: #fef08a; padding: 2px 6px; border-radius: 4px; font-weight: 600; border: 1px solid #facc15; cursor: pointer; color: #1e293b;">${mark_inner}</mark>`
				});
			});

			tokens.forEach(t => {
				highlighted = highlighted.split(t.token).join(t.html);
			});
		} catch (err) {
			console.error("Highlighting error:", err);
			highlighted = current_doc_html;
		}

		$wrapper.find('.studio-doc-content').html(highlighted);

		// Render Variables List Cards
		if (variables.length === 0) {
			let empty_msg = current_meta.status === 'needs_key'
				? `Flow AI is the mandatory generation engine.<br><button class="btn btn-primary btn-xs mt-3 studio-prompt-key-btn"><i class="fa fa-bolt"></i> Configure Flow AI Key</button>`
				: `No variables defined yet.<br>Click 'Flow AI Settings' or select text on the left to add a variable.`;
			$wrapper.find('.studio-vars-list').html(`
				<div class="text-center text-muted" style="padding: 40px 10px;">
					<i class="fa fa-bolt fa-2x" style="margin-bottom: 10px; color: #6366f1;"></i>
					<p>${empty_msg}</p>
				</div>
			`);
			$wrapper.find('.studio-prompt-key-btn').on('click', function() {
				$wrapper.find('.studio-ai-key-btn').trigger('click');
			});
			return;
		}

		let cards_html = variables.map((v, idx) => {
			let is_jinja = (v.original_text || '').trim().startsWith('{{') && (v.original_text || '').trim().endsWith('}}');
			let match_desc = is_jinja
				? `<span style="color: #059669; font-weight: 500;"><i class="fa fa-check-circle" style="color: #10b981;"></i> Template Jinja Tag (<code>{{ ${v.variable_name} }}</code>)</span>`
				: `<strong>Matches text:</strong> <span style="font-style: italic;">"${frappe.utils.escape_html(v.original_text)}"</span>`;

			return `
			<div class="var-card" style="border: 1px solid var(--border-color); border-radius: 6px; padding: 10px; margin-bottom: 8px; background: #f8fafc; transition: all 0.2s ease;">
				<div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
					<div>
						<span style="font-family: monospace; font-weight: 600; color: #0284c7; background: #e0f2fe; padding: 2px 6px; border-radius: 4px; font-size: 12px;">{{ ${v.variable_name} }}</span>
					</div>
					<button class="btn btn-xs studio-remove-var" data-idx="${idx}" style="border: 1px solid #f87171; color: #b91c1c; background: #fee2e2; border-radius: 4px; padding: 2px 8px; font-size: 11px; font-weight: 600; cursor: pointer; transition: all 0.2s;" title="Delete this variable">
						✕ Delete
					</button>
				</div>
				<div style="font-size: 12px; color: #475569; margin-bottom: 6px;">
					${match_desc}
				</div>
				<div style="display: flex; gap: 8px;">
					<div style="flex: 1;">
						<label style="font-size: 11px; color: #64748b; margin-bottom: 2px;">Label</label>
						<input type="text" class="form-control input-xs studio-var-label" data-idx="${idx}" value="${frappe.utils.escape_html(v.label || v.variable_name)}">
					</div>
					<div style="flex: 1;">
						<label style="font-size: 11px; color: #64748b; margin-bottom: 2px;">Field Type</label>
						<select class="form-control input-xs studio-var-fieldtype" data-idx="${idx}" style="font-size: 11.5px; height: 26px; padding: 2px 4px;">
							${render_fieldtype_select_options(v.fieldtype || 'Data')}
						</select>
					</div>
				</div>
			</div>
			`;
		}).join('');

		$wrapper.find('.studio-vars-list').html(cards_html);
	}

	// Initial render now that d is shown
	update_preview_and_vars();

	// Event Handlers (scoped strictly to $wrapper):

	// Mode Switchers & Editor actions
	$wrapper.find('.studio-btn-edit-mode').on('click', function() {
		if (!is_edit_mode) {
			enter_edit_mode();
		}
	});

	$wrapper.find('.studio-btn-preview-mode').on('click', function() {
		if (is_edit_mode) {
			exit_and_save_edit_mode();
		}
	});

	$wrapper.find('.studio-btn-save-edit').on('click', function() {
		exit_and_save_edit_mode();
	});

	$wrapper.find('.studio-btn-cancel-edit').on('click', function() {
		cancel_edit_mode();
	});

	$wrapper.find('.studio-tb-cmd').on('click', function(e) {
		e.preventDefault();
		let cmd = $(this).attr('data-cmd');
		let val = $(this).attr('data-val') || null;
		document.execCommand(cmd, false, val);
		$wrapper.find('.studio-doc-content').focus();
	});

	// 1. Mouse selection in document preview to add new variable
	$wrapper.find('.studio-doc-content').on('mouseup', function() {
		if (is_edit_mode) return;
		let selection = window.getSelection();
		let selected_text = selection ? selection.toString().trim() : '';

		if (selected_text && selected_text.length >= 2 && selected_text.length <= 120) {
			prompt_add_variable(selected_text);
		}
	});

	// 1b. Direct click on any highlighted variable to delete it
	$wrapper.on('click', '.studio-mark', function(e) {
		if (is_edit_mode) return;
		e.stopPropagation();
		let var_name = $(this).attr('data-var');
		let found_idx = variables.findIndex(v => v.variable_name === var_name);
		if (found_idx !== -1) {
			frappe.confirm(
				__('Delete variable "{{ {0} }}"?', [var_name]),
				function() {
					variables.splice(found_idx, 1);
					update_preview_and_vars();
					frappe.show_alert({ message: __('Variable "{{ {0} }}" removed', [var_name]), indicator: 'orange' });
				}
			);
		}
	});

	function prompt_add_variable(default_text = '') {
		let default_varname = frappe.scrub(default_text).substring(0, 30);
		if (!default_varname || /^\d+$/.test(default_varname)) {
			default_varname = `var_${variables.length + 1}`;
		}

		let prompt_d = new frappe.ui.Dialog({
			title: __('Create Variable from Selection'),
			fields: [
				{
					fieldtype: 'Data',
					fieldname: 'original_text',
					label: __('Text to Replace in Document'),
					default: default_text,
					reqd: 1
				},
				{
					fieldtype: 'Data',
					fieldname: 'variable_name',
					label: __('Variable Name (Jinja & Fieldname)'),
					default: default_varname,
					reqd: 1
				},
				{
					fieldtype: 'Data',
					fieldname: 'label',
					label: __('Field Label'),
					default: default_varname.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase()),
					reqd: 1
				},
				{
					fieldtype: 'Select',
					fieldname: 'fieldtype',
					label: __('Field Type'),
					options: get_all_fieldtype_dialog_options(),
					default: 'Data',
					reqd: 1
				}
			],
			primary_action_label: __('Add Variable'),
			primary_action: function(values) {
				variables.push({
					original_text: values.original_text.trim(),
					variable_name: frappe.scrub(values.variable_name),
					label: values.label.trim(),
					fieldtype: values.fieldtype
				});
				prompt_d.hide();
				update_preview_and_vars();
			}
		});
		prompt_d.show();
	}

	// 2. Add variable manual button
	$wrapper.find('.studio-add-var-btn').on('click', function() {
		prompt_add_variable('');
	});

	// 2a. Download Word Template (.docx) with highlighted Jinja variables
	$wrapper.find('.studio-download-tpl-btn').on('click', function(e) {
		e.preventDefault();
		if (!frm || !frm.doc || !frm.doc.name) {
			frappe.msgprint(__('Template document record not found.'));
			return;
		}
		window.open(`/api/method/casecentral.legal_documents.doctype.legal_templates.template_studio.download_jinja_template?legal_template_name=${encodeURIComponent(frm.doc.name)}`);
	});

	// 2b. AI Key & Flow Settings Modal
	$wrapper.find('.studio-ai-key-btn').on('click', function() {
		frappe.call({
			method: 'casecentral.legal_documents.doctype.legal_templates.template_studio.get_available_ai_engines',
			freeze: true,
			freeze_message: __('Loading Flow AI Configuration...'),
			callback: function(r_eng) {
				let engines = r_eng.message || {};
				let flow_installed = engines.flow_installed;
				let flow_models = engines.flow_models || [];
				let flow_providers = engines.flow_providers || [];

				let providers_badges = flow_providers.length > 0
					? flow_providers.map(p => `<span class="badge badge-success" style="margin-right: 4px;">${p.name}</span>`).join('')
					: `<span class="text-muted">None configured yet</span>`;

				let models_badges = flow_models.length > 0
					? flow_models.map(m => `<span class="badge badge-info" style="margin-right: 4px;">${m.title} (${m.model_id})</span>`).join('')
					: `<span class="text-muted">None configured yet</span>`;

				let info_markup = `
					<div style="background: #f8fafc; border: 1px solid var(--border-color); border-radius: 8px; padding: 14px; margin-bottom: 14px;">
						<div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
							<div>
								<strong style="color: #1e293b; font-size: 13.5px;"><i class="fa fa-plug" style="color: #6366f1;"></i> Frappe Flow Client AI</strong>
								<div style="font-size: 11.5px; color: #64748b; margin-top: 2px;">
									${flow_installed ? 'Installed & synced with Flow Provider & Flow Model DocTypes.' : 'App not detected; please install Frappe Flow.'}
								</div>
							</div>
							<span class="badge ${flow_installed ? 'badge-success' : 'badge-warning'}">
								${flow_installed ? 'Flow AI Active' : 'Flow App Missing'}
							</span>
						</div>

						<div style="font-size: 12px; margin-bottom: 6px;">
							<strong>Configured Providers:</strong> ${providers_badges}
						</div>
						<div style="font-size: 12px; margin-bottom: 10px;">
							<strong>Active Models:</strong> ${models_badges}
						</div>

						<div style="display: flex; gap: 8px; margin-top: 8px;">
							<button type="button" class="btn btn-default btn-xs" id="studio-open-flow-providers">
								<i class="fa fa-external-link"></i> Manage Flow Providers
							</button>
							<button type="button" class="btn btn-default btn-xs" id="studio-open-flow-models">
								<i class="fa fa-external-link"></i> Manage Flow Models
							</button>
						</div>
					</div>

					<div style="font-size: 12px; color: #475569; margin-bottom: 10px;">
						Enter or update an API Key below (e.g. <strong>Google Gemini</strong> starting with <code>AIza...</code> or <strong>Groq</strong> starting with <code>gsk_...</code>).
						It will be saved securely into Frappe Flow Provider credentials.
					</div>
				`;

				let key_dialog = new frappe.ui.Dialog({
					title: __('Flow AI & LLM Engine Settings'),
					fields: [
						{
							fieldtype: 'HTML',
							fieldname: 'flow_status_html',
							options: info_markup
						},
						{
							fieldtype: 'Password',
							fieldname: 'api_key',
							label: __('AI API Key (Gemini / Groq / OpenAI)'),
							description: __('Paste your API key here to link with Flow AI')
						}
					],
					primary_action_label: __('Save & Re-detect Template'),
					primary_action: function(vals) {
						let entered_key = (vals.api_key || '').trim();
						frappe.call({
							method: 'casecentral.legal_documents.doctype.legal_templates.template_studio.save_ai_key',
							args: {
								api_key: entered_key
							},
							freeze: true,
							freeze_message: __('Configuring Flow Provider and analyzing document...'),
							callback: function(save_res) {
								key_dialog.hide();
								// Re-run detection
								frappe.call({
									method: 'casecentral.legal_documents.doctype.legal_templates.template_studio.detect_variables',
									args: {
										legal_template_name: frm.doc.name,
										api_key: entered_key
									},
									freeze: true,
									freeze_message: __('Re-detecting variables with Flow AI...'),
									callback: function(r_new) {
										let res = r_new.message || {};
										let new_vars = Array.isArray(res) ? res : (res.variables || []);
										if (new_vars.length > 0) {
											variables = [...new_vars];
											current_meta.engine_used = res.engine_used || 'Flow AI';
											current_meta.token_usage = res.token_usage || null;
											current_meta.flow_installed = res.flow_installed || false;
											update_preview_and_vars();
											let token_str = current_meta.token_usage ? ` (${current_meta.token_usage.total_tokens} tokens)` : '';
											frappe.show_alert({
												message: __('Variables re-detected via {0}! ({1} variables found{2})', [current_meta.engine_used, variables.length, token_str]),
												indicator: 'green'
											}, 6);
										} else {
											frappe.msgprint(__('No variables found or AI call failed.'));
										}
									}
								});
							}
						});
					}
				});

				key_dialog.show();

				key_dialog.$wrapper.find('#studio-open-flow-providers').on('click', function() {
					key_dialog.hide();
					frappe.set_route('List', 'Flow Provider');
				});
				key_dialog.$wrapper.find('#studio-open-flow-models').on('click', function() {
					key_dialog.hide();
					frappe.set_route('List', 'Flow Model');
				});
			}
		});
	});

	// 3. Remove variable
	$wrapper.on('click', '.studio-remove-var', function() {
		let idx = parseInt($(this).attr('data-idx'));
		variables.splice(idx, 1);
		update_preview_and_vars();
	});

	// 4. Update variable label inline
	$wrapper.on('change', '.studio-var-label', function() {
		let idx = parseInt($(this).attr('data-idx'));
		if (variables[idx]) {
			variables[idx].label = $(this).val();
		}
	});

	// 5. Update variable fieldtype inline
	$wrapper.on('change', '.studio-var-fieldtype', function() {
		let idx = parseInt($(this).attr('data-idx'));
		if (variables[idx]) {
			variables[idx].fieldtype = $(this).val();
		}
	});
}


function render_template_creation_choices(frm) {
	if (frm.doc.template_file) return;

	let field = frm.get_field('template_file');
	if (!field || !field.$wrapper) return;

	if (field.$wrapper.find('.template-creation-choice-banner').length) return;

	let banner_html = `
		<div class="template-creation-choice-banner" style="background: linear-gradient(135deg, #f8fafc 0%, #f1f5f9 100%); border: 1px solid #cbd5e1; border-radius: 8px; padding: 14px 16px; margin-bottom: 15px;">
			<div style="font-weight: 700; font-size: 13px; color: #0f172a; margin-bottom: 6px; display: flex; align-items: center; gap: 6px;">
				<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="#4f46e5" stroke-width="2.2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline><line x1="12" y1="18" x2="12" y2="12"></line><line x1="9" y1="15" x2="15" y2="15"></line></svg>
				Choose How You Want to Create This Template:
			</div>
			<div style="display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-top: 10px;">
				<div style="background: #ffffff; border: 1px solid #e2e8f0; border-radius: 6px; padding: 12px;">
					<div style="font-weight: 600; font-size: 12.5px; color: #1e293b; margin-bottom: 4px;">
						📄 Option 1: Attach Word Document (.docx)
					</div>
					<div style="font-size: 11.5px; color: #64748b; line-height: 1.4; margin-bottom: 8px;">
						Upload an existing contract file from your computer below, then open AI Template Studio to convert it to Jinja.
					</div>
					<span style="font-size: 11px; color: #0284c7; font-weight: 500;">Attach file in the field below ↓</span>
				</div>
				<div style="background: #ffffff; border: 1px solid #c7d2fe; border-radius: 6px; padding: 12px; box-shadow: 0 1px 3px rgba(99, 102, 241, 0.08);">
					<div style="font-weight: 600; font-size: 12.5px; color: #4338ca; margin-bottom: 4px;">
						✨ Option 2: Draft with Flow AI Prompt
					</div>
					<div style="font-size: 11.5px; color: #64748b; line-height: 1.4; margin-bottom: 8px;">
						Don't have a Word document? Enter your agreement requirements and Flow AI will generate the contract, particulars table, and Jinja tags automatically.
					</div>
					<button type="button" class="btn btn-xs btn-primary btn-draft-with-prompt" style="background-color: #4338ca; border-color: #4338ca; font-weight: 600;">
						✨ Draft Template from Prompt
					</button>
				</div>
			</div>
		</div>
	`;

	field.$wrapper.prepend(banner_html);
	field.$wrapper.find('.btn-draft-with-prompt').on('click', function(e) {
		e.preventDefault();
		open_prompt_drafting_dialog(frm);
	});
}


function open_prompt_drafting_dialog(frm) {
	frappe.call({
		method: 'casecentral.legal_documents.doctype.legal_templates.template_studio.get_available_ai_engines',
		callback: function(r) {
			let engines = r.message || {};
			let model_options = [];
			let default_model = '';

			if (engines.flow_models && engines.flow_models.length > 0) {
				model_options = engines.flow_models.map(m => m.name);
				default_model = model_options[0];
			} else {
				model_options = ['gemini/gemini-2.5-flash', 'groq/llama-3.3-70b-versatile', 'openai/gpt-4o-mini'];
				default_model = 'gemini/gemini-2.5-flash';
			}

			let has_saved_key = engines.has_active_key;
			let key_label = has_saved_key 
				? __('Flow AI API Key (Saved in Flow Provider ✓)') 
				: __('Flow AI API Key (Required for LLM Generation)');
			let key_desc = has_saved_key
				? __('Active key is configured in Flow Provider. Leave blank to use it, or enter a new key to update.')
				: __('Enter your Gemini API key (starts with AIzaSy...) or Groq key (starts with gsk_...) to generate this template via Flow AI.');

			let d = new frappe.ui.Dialog({
				title: __('✨ Generate Legal Template from AI Prompt'),
				fields: [
					{
						fieldname: 'info_html',
						fieldtype: 'HTML',
						options: `
							<div style="background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 12px 14px; margin-bottom: 12px;">
								<div style="font-weight: 600; font-size: 13px; color: #0f172a; margin-bottom: 4px; display: flex; align-items: center; gap: 6px;">
									<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#6366f1" stroke-width="2.2"><path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83"/></svg>
									Flow AI Agreement Generator
								</div>
								<div style="font-size: 12px; color: #64748b; line-height: 1.45;">
									Enter your agreement requirements below. Flow AI will generate the clauses, format an executive Word (.docx) document with Jinja tags using your Flow API key, and open AI Template Studio.
								</div>
							</div>
						`
					},
					{
						fieldname: 'template_name',
						label: __('Template Name'),
						fieldtype: 'Data',
						default: frm && frm.doc ? (frm.doc.template_name || '') : '',
						placeholder: __('e.g. Consultancy Service Agreement, Employment Contract, NDA')
					},
					{
						fieldname: 'naming_series',
						label: __('Naming Series Prefix'),
						fieldtype: 'Data',
						default: frm && frm.doc ? (frm.doc.naming_series || '') : '',
						placeholder: __('e.g. CON-.YYYY.-.##### (Auto-generated if left blank)')
					},
					{
						fieldname: 'engine_mode',
						label: __('Generation Engine'),
						fieldtype: 'Select',
						options: [
							{ label: __('Flow AI Cloud LLM (Gemini / Groq / OpenAI)'), value: 'flow_ai' },
							{ label: __('Built-in Legal Synthesis Engine (No API key needed)'), value: 'builtin' }
						],
						default: has_saved_key ? 'flow_ai' : 'builtin'
					},
					{
						fieldname: 'flow_model',
						label: __('Flow AI Model'),
						fieldtype: 'Select',
						options: model_options.join('\n'),
						default: default_model,
						depends_on: 'eval:doc.engine_mode == "flow_ai"'
					},
					{
						fieldname: 'api_key',
						label: key_label,
						fieldtype: 'Password',
						description: key_desc,
						depends_on: 'eval:doc.engine_mode == "flow_ai"'
					},
					{
						fieldname: 'prompt_chips_html',
						fieldtype: 'HTML',
						options: `
							<div style="margin-top: 4px; margin-bottom: 8px;">
								<span style="font-size: 11px; font-weight: 600; color: #64748b; text-transform: uppercase; letter-spacing: 0.04em;">Quick Starters:</span>
								<div style="display: flex; flex-wrap: wrap; gap: 6px; margin-top: 5px;" class="prompt-starter-chips">
									<button type="button" class="btn btn-xs btn-default prompt-chip" data-type="consulting" style="border-radius: 12px; font-size: 11.5px; background: #fff;">🤝 Consulting Agreement</button>
									<button type="button" class="btn btn-xs btn-default prompt-chip" data-type="employment" style="border-radius: 12px; font-size: 11.5px; background: #fff;">💼 Employment Contract</button>
									<button type="button" class="btn btn-xs btn-default prompt-chip" data-type="lease" style="border-radius: 12px; font-size: 11.5px; background: #fff;">🏢 Commercial Lease</button>
									<button type="button" class="btn btn-xs btn-default prompt-chip" data-type="nda" style="border-radius: 12px; font-size: 11.5px; background: #fff;">🔒 Non-Disclosure (NDA)</button>
									<button type="button" class="btn btn-xs btn-default prompt-chip" data-type="rental" style="border-radius: 12px; font-size: 11.5px; background: #fff;">🏠 Residential Rental</button>
								</div>
							</div>
						`
					},
					{
						fieldname: 'prompt',
						label: __('Drafting Instructions / Prompt'),
						fieldtype: 'Small Text',
						reqd: 1,
						placeholder: __('Describe the contract you want. Specify parties, financial terms, dates, durations, and key covenants.')
					}
				],
				primary_action_label: __('Draft Agreement & Open Studio'),
				primary_action: function(values) {
					if (!values.prompt || !values.prompt.trim()) {
						frappe.msgprint(__('Please provide prompt instructions for the contract.'));
						return;
					}

					if (values.engine_mode === 'flow_ai' && !has_saved_key && (!values.api_key || !values.api_key.trim())) {
						frappe.msgprint(__('Please provide your Flow AI API Key, or switch "Generation Engine" to "Built-in Legal Synthesis Engine" if you do not have an API key yet.'));
						return;
					}

					let loading_text = values.engine_mode === 'flow_ai' ? 'Calling Flow AI API...' : 'Synthesizing Template...';
					d.get_primary_btn().prop('disabled', true).html(`<i class="fa fa-spinner fa-spin"></i> ${loading_text}`);

					frappe.call({
						method: 'casecentral.legal_documents.doctype.legal_templates.template_studio.generate_template_from_prompt',
						args: {
							prompt: values.prompt,
							template_name: values.template_name,
							naming_series: values.naming_series,
							flow_model: values.flow_model,
							api_key: values.api_key,
							legal_template_name: frm && frm.doc ? frm.doc.name : null,
							engine_mode: values.engine_mode
						},
						callback: function(r_gen) {
							d.get_primary_btn().prop('disabled', false).html(__('Draft Agreement & Open Studio'));
							let res = r_gen.message;

							if (!res) {
								frappe.msgprint(__('Failed to generate template from prompt.'));
								return;
							}

							if (res.status === 'needs_key') {
								frappe.msgprint(res.message || __('Flow AI API Key is required.'));
								return;
							}

							d.hide();
							frappe.show_alert({
								message: res.message || __('Template drafted successfully!'),
								indicator: 'green'
							}, 6);

							let target_template_name = res.legal_template_name;

							// If we are currently viewing this exact document form
							if (frm && frm.doc && frm.doc.name === target_template_name) {
								frm.reload_doc().then(() => {
									let meta_info = {
										status: 'success',
										engine_used: res.engine_used || 'Flow AI',
										token_usage: res.token_usage || null,
										flow_installed: true,
										message: res.message
									};
									render_template_studio_dialog(frm, res.html_preview, res.variables || [], meta_info);
								});
							} else {
								// User was either on a new unsaved form ('new-legal-templates-1') or on List view or another doc
								if (frm && frm.is_new && frm.is_new()) {
									// Clear unsaved dummy doc from local state so Frappe router does not block navigation
									frm.doc.__unsaved = 0;
									frappe.model.clear_doc(frm.doc.doctype, frm.doc.name);
								}
								frappe.set_route('Form', 'Legal Templates', target_template_name).then(() => {
									let interval_checks = 0;
									let poll_timer = setInterval(() => {
										interval_checks++;
										if (cur_frm && cur_frm.doc && cur_frm.doc.name === target_template_name && cur_frm.doc.template_file) {
											clearInterval(poll_timer);
											let meta_info = {
												status: 'success',
												engine_used: res.engine_used || 'Flow AI',
												token_usage: res.token_usage || null,
												flow_installed: true,
												message: res.message
											};
											render_template_studio_dialog(cur_frm, res.html_preview, res.variables || [], meta_info);
										} else if (interval_checks > 30) {
											clearInterval(poll_timer);
											if (cur_frm && cur_frm.doc && cur_frm.doc.name === target_template_name) {
												cur_frm.reload_doc().then(() => {
													let meta_info = {
														status: 'success',
														engine_used: res.engine_used || 'Flow AI',
														token_usage: res.token_usage || null,
														flow_installed: true,
														message: res.message
													};
													render_template_studio_dialog(cur_frm, res.html_preview, res.variables || [], meta_info);
												});
											}
										}
									}, 150);
								});
							}
						}
					});
				}
			});

			d.show();

			// Auto-derive Naming Series Prefix when user types Template Name
			d.$wrapper.find('input[data-fieldname="template_name"]').on('input', function() {
				let val = $(this).val().trim();
				let current_prefix = d.get_value('naming_series');
				if (!current_prefix || current_prefix.endsWith('-.YYYY.-.#####')) {
					let letters = val.replace(/[^a-zA-Z]/g, '');
					let pfx = (letters.length >= 3 ? letters.substring(0, 3) : 'LEG').toUpperCase();
					d.set_value('naming_series', `${pfx}-.YYYY.-.#####`);
				}
			});

			// Chip click handlers
			d.$wrapper.find('.prompt-chip').on('click', function() {
				let type = $(this).attr('data-type');
				if (type === 'consulting') {
					d.set_value('template_name', 'Consulting Agreement');
					d.set_value('naming_series', 'CON-.YYYY.-.#####');
					d.set_value('prompt', 'Draft an Independent Consultancy Service Agreement between Client Company and Software Consultant. Include scope of software architecture advisory services, monthly retainer fee of ₹80,000 INR, milestone performance bonus, 30 days notice period, intellectual property assignment, confidentiality obligations, and Mumbai jurisdiction.');
				} else if (type === 'employment') {
					d.set_value('template_name', 'Employment Contract');
					d.set_value('naming_series', 'EMP-.YYYY.-.#####');
					d.set_value('prompt', 'Draft a Comprehensive Employment Agreement between Employer Company and Employee for the role of Senior Developer. Include monthly basic salary of ₹1,00,000 INR, annual CTC, 3 months probation period, 30 days notice period, standard working hours, non-compete covenants, confidentiality, and Bangalore jurisdiction.');
				} else if (type === 'lease') {
					d.set_value('template_name', 'Commercial Lease Agreement');
					d.set_value('naming_series', 'COM-.YYYY.-.#####');
					d.set_value('prompt', 'Draft a Commercial Lease Agreement between Landlord and Tenant for commercial office premises. Include monthly rent of ₹65,000 INR, refundable security deposit of ₹3,00,000 INR, 36 months lease term, 5% annual escalation, lock-in period of 12 months, permitted commercial use, and Delhi jurisdiction.');
				} else if (type === 'nda') {
					d.set_value('template_name', 'Non-Disclosure Agreement');
					d.set_value('naming_series', 'NDA-.YYYY.-.#####');
					d.set_value('prompt', 'Draft a Mutual Non-Disclosure and Confidentiality Agreement between Disclosing Party and Receiving Party for exploring business collaboration. Include definition of confidential information, non-disclosure obligations, 2 years confidentiality term, return of materials, and exclusive jurisdiction in Mumbai.');
				} else if (type === 'rental') {
					d.set_value('template_name', 'Residential Rental Agreement');
					d.set_value('naming_series', 'RNT-.YYYY.-.#####');
					d.set_value('prompt', 'Draft a Residential Rental Agreement between Landlord and Tenant for a residential apartment. Include monthly rent of ₹35,000 INR, security deposit of ₹1,00,000 INR, 11 months term, 30 days notice period, utilities payment obligations, and Mumbai jurisdiction.');
				}
			});
		}
	});
}
window.open_prompt_drafting_dialog = open_prompt_drafting_dialog;
window.render_template_studio_dialog = render_template_studio_dialog;
