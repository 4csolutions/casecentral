import frappe
from frappe.utils.data import format_datetime
from frappe.website.utils import get_comment_list

def get_context(context):
    context.show_sidebar = True
    context.no_cache = True
    context.parents = [dict(route='/case', label='Case')]

    name = frappe.form_dict.name
    if not name:
        frappe.throw("Missing Case name")

    case_doc = frappe.get_doc("Case", name)
    context.case = case_doc
    context.title = f"Case Details - {case_doc.name}"
    context.doctype = "Case"
    context.name = case_doc.name

    tasks = frappe.get_all(
        "Task",
        filters={"case": case_doc.name},
        fields="*",
        order_by="modified desc"
    )
    context.tasks = tasks
    # Fetch comments with full name fallback
    context.comment_list = get_comment_list("Case", case_doc.name)
    return context


