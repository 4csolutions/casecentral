import frappe
from frappe.website.utils import get_comment_list

def get_context(context):
	context.show_sidebar = True
	context.no_cache = True
	context.parents = [dict(route='/matter', label='Matter')]

	matter_name = frappe.form_dict.name
	if not matter_name:
		frappe.throw("Missing Matter name")
	matter_doc = frappe.get_doc("Matter", matter_name)
	context.matter = matter_doc
	context.title = f"Matter Details - {matter_doc.name}"
	context.doctype = "Matter"
	context.name = matter_doc.name

	tasks = frappe.get_all(
        "Task",
        filters={"matter": matter_doc.name},
        fields="*",
        order_by="modified desc"
    )
	context.tasks = tasks
	# Fetch comments with full name fallback
	context.comment_list = get_comment_list("Matter", matter_doc.name)

	return context