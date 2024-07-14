# Copyright (c) 2024, 4C Solutions and contributors
# For license information, please see license.txt

import frappe
import os, io

from frappe.model.document import Document
from docxtpl import DocxTemplate
from frappe.utils import get_files_path
from frappe.utils.file_manager import save_file

class LegalTemplates(Document):
	pass

@frappe.whitelist()
def generate_new_doctype(legal_template_name):
	# Retrieve the Legal Template record
	legal_template_doc = frappe.get_doc("Legal Templates", legal_template_name)
	template_file = legal_template_doc.template_file

	# Check if template file is private
	is_private = 0
	if 'private' in template_file:
		is_private = 1

	file_name = template_file.split("/")[-1]
	file_path = get_files_path(file_name, is_private=is_private)

	# Load the template file using python-docxtpl
	doc = DocxTemplate(os.path.realpath(file_path))

	# Extract variables from the template file
	variables = doc.get_undeclared_template_variables()

	fixed_fields = [
			{
				"fieldname": "naming_series",
				"label": "Naming Series",
				"fieldtype": "Select",
				"options": legal_template_doc.naming_series
			},
			{
				"fieldname": "matter",
				"label": "Matter",
				"fieldtype": "Link",
				"options": "Matter",
				"in_list_view": 1,
				"in_standard_filter": 1,
				"insert_after": "naming_series"
			}
	]
	# Define a new doctype with the extracted variables as fields
	new_doctype = {
		"doctype": "DocType",
		"module": "Legal Documents",  # Replace with your module name
		"name": legal_template_name,
		"track_changes": 1,
		"allow_import": 1,
		"name_case": "Title Case",
		"naming_rule": 'By "Naming Series" field',
		"custom": 1, # Production system needs this check for creating new doctype
		
		"fields": fixed_fields + [
			{
				"fieldname": frappe.scrub(variable),
				"label": variable.replace("_", " ").title(),
				"fieldtype": "Data",
				"insert_after": "fieldname"  # Add other field properties as needed
			} for variable in variables if variable != "name"
		],
		"permissions": [
			{
				"role": "System Manager",
				"read": 1,
				"write": 1,
				"create": 1,
				"delete": 1
			}
		]
	}

	# Create the new doctype
	new_doctype_doc = frappe.get_doc(new_doctype).insert()
	legal_template_doc.related_doctype = legal_template_name
	legal_template_doc.save()

	script = """frappe.ui.form.on('{0}', {{
	onload: function(frm) {{
		// Check if any "Legal Templates" doctype exists with "related_doctype" as this doctype
		frappe.db.get_list('Legal Templates', {{
			filters: {{'related_doctype': '{0}'}},
			fields: ['name']
		}}).then(function(result) {{
			if (result.length > 0) {{
				// Show custom button
				frm.add_custom_button(__('Generate Document'), function() {{
					// Show pop-up to select "Legal Templates"
					frappe.prompt([
						{{
							fieldname: 'legal_template',
							label: __('Legal Template'),
							fieldtype: 'Link',
							options: 'Legal Templates',
							filters: {{'related_doctype': '{0}'}},
							reqd: 1
						}}
					], function(values) {{
						// Call Python function to generate document
						frappe.call({{
							method: 'casecentral.legal_documents.doctype.legal_templates.legal_templates.generate_document',
							args: {{
								doctype: '{0}',
								docname: frm.docname,
								legal_template_name: values.legal_template
							}},
							callback: function(r) {{
								if (r.message) {{
									// Upload generated document
									frm.reload_doc();
								}}
							}}
						}});
					}}, __('Select Legal Template'), __('Generate'));
				}});
			}}
		}});
	}}
}});""".format(legal_template_name)

	client_script = frappe.get_doc({
            'doctype': 'Client Script',
            'name': legal_template_name,
            'dt': legal_template_name,
			'view': 'Form',
			'module': 'Legal Documents',
			'enabled': 1,
            'script': script
        })
	client_script.insert()

	# Redirect to the new doctype
	return new_doctype_doc.name

@frappe.whitelist()
def generate_document(doctype, docname, legal_template_name):
	# Get fields names & values
	doc = frappe.get_doc(doctype, docname)
	context = {}
	for field in doc.meta.fields:
		context[field.fieldname] = doc.get_formatted(field.fieldname)

	for field in doc.meta.default_fields:
		context[field] = doc.get_formatted(field)
		
	# Get template file from selected "Legal Templates"
	legal_template_doc = frappe.get_doc('Legal Templates', legal_template_name)
	template_file = legal_template_doc.template_file

	# Check if template file is private
	is_private = 0
	if 'private' in template_file:
		is_private = 1

	file_name = template_file.split("/")[-1]
	file_path = get_files_path(file_name, is_private=is_private)

	# Load template using docxtpl
	doc = DocxTemplate(os.path.realpath(file_path))

	# Render document
	doc.render(context)

	file_name = f'{docname}.docx'.replace("/","_")
	# Save rendered document
	rendered_doc_path = frappe.get_site_path('public', 'files', file_name)
	doc.save(rendered_doc_path)

	# Create a new File document in ERPNext
	file_doc = frappe.get_doc({
		'doctype': 'File',
		'file_url': '/files/' + file_name,
		'file_name': file_name,
		'attached_to_doctype': doctype,
		'attached_to_name': docname,
		'is_private': 0,
		'folder': 'Home'  # Change to the desired folder
	})
	file_doc.insert()

	return rendered_doc_path