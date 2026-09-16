# Copyright (c) 2024, 4C Solutions and contributors
# For license information, please see license.txt

import frappe
import os, io
from docx import Document as Documentx
from html4docx import HtmlToDocx
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

	# Redirect to the new doctype
	return new_doctype_doc.name

@frappe.whitelist()
def generate_document(doctype, docname, legal_template_name):
	# Get fields names & values
	erp_doc = frappe.get_doc(doctype, docname)
	
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

	context = {}
	for field in erp_doc.meta.fields:
		if field.fieldtype == "Text Editor":
			subdoc_path_name = docname.replace('/','_')+"_"+field.fieldname+"_subdoc.docx"
			rendered_subdoc_path = frappe.get_site_path('public', 'files', subdoc_path_name)
			render_doc_with_html(erp_doc.get_formatted(field.fieldname), rendered_subdoc_path)
			context[field.fieldname] = doc.new_subdoc(rendered_subdoc_path)
			os.remove(rendered_subdoc_path)
		else:
			context[field.fieldname] = erp_doc.get_formatted(field.fieldname)

	for field in erp_doc.meta.default_fields:
		context[field] = erp_doc.get_formatted(field)
		
	# Render document
	doc.render(context)

	output_stream = io.BytesIO()
	doc.save(output_stream)

	file_name = f'{docname}.docx'.replace("/","_")
	frappe.response["filecontent"] = output_stream.getvalue()
	frappe.response["filename"] = file_name
	frappe.response["type"] = "download"
	frappe.response["display_content_as"] = "attachment"
	output_stream.close()

def render_doc_with_html( html_content, output_path):

	subdoc_doc = Documentx()
	parser = HtmlToDocx()
	parser.add_html_to_document(html_content, subdoc_doc)
	subdoc_doc.save(output_path)
	
	return output_path
