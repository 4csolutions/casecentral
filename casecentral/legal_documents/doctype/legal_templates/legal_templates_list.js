frappe.listview_settings["Legal Templates"] = {
	add_fields: ["related_doctype", "template_file"],
	onload: function(listview) {
		let btn = listview.page.add_button(__('✨ Draft with AI Prompt'), function() {
			open_prompt_drafting_dialog();
		}, 'btn-primary');
		btn.css({
			'background-color': '#0f172a',
			'border-color': '#0f172a',
			'color': '#ffffff',
			'font-weight': '600',
			'box-shadow': '0 1px 3px rgba(0,0,0,0.1)'
		});
	},
	get_indicator: function (doc) {
		if (doc.related_doctype) {
			return [__("DocType Created"), "green", "related_doctype,is,set"];
		} else if (doc.template_file) {
			return [__("Ready for AI Studio"), "blue", "template_file,is,set"];
		} else {
			return [__("Draft / No File"), "orange", "template_file,is,not set"];
		}
	},
	button: {
		show: function (doc) {
			return !doc.related_doctype && doc.template_file;
		},
		get_label: function () {
			return __("AI Studio");
		},
		get_description: function (doc) {
			return __("Open AI Template Studio");
		},
		action: function (doc) {
			frappe.set_route("Form", "Legal Templates", doc.name);
		}
	}
};

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
				model_options = ['gemini/gemini-3.5-flash', 'groq/llama-3.3-70b-versatile', 'openai/gpt-4o-mini'];
				default_model = 'gemini/gemini-3.5-flash';
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
									Enter your agreement requirements below. Flow AI will generate the clauses, format an executive Word (.docx) document with Jinja tags, and open AI Template Studio.
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

							if (frm && frm.doc && frm.doc.name === target_template_name) {
								frm.reload_doc().then(() => {
									let meta_info = {
										status: 'success',
										engine_used: res.engine_used || 'Flow AI',
										token_usage: res.token_usage || null,
										flow_installed: true,
										message: res.message
									};
									let studio_fn = window.render_template_studio_dialog || render_template_studio_dialog;
									if (studio_fn) {
										studio_fn(frm, res.html_preview, res.variables || [], meta_info);
									}
								});
							} else {
								if (frm && frm.is_new && frm.is_new()) {
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
											let studio_fn = window.render_template_studio_dialog;
											if (studio_fn) {
												studio_fn(cur_frm, res.html_preview, res.variables || [], meta_info);
											}
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
													let studio_fn = window.render_template_studio_dialog;
													if (studio_fn) {
														studio_fn(cur_frm, res.html_preview, res.variables || [], meta_info);
													}
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
