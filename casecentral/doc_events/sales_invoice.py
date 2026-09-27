import frappe
from frappe import _

def manage_invoice_submit_cancel(doc, method):
	if doc.items:
		for item in doc.items:
			if item.get("reference_doctype") and item.get("reference_name"):
				if frappe.get_meta(item.reference_doctype).has_field("invoiced"):
					set_invoiced(item, method, doc.name)

def set_invoiced(item, method, ref_invoice=None):
    invoiced = False
    if method == 'on_submit':
        validate_invoiced_on_submit(item)
        invoiced = True
    
    frappe.db.set_value(item.reference_doctype, item.reference_name, "invoiced", invoiced)

def validate_invoiced_on_submit(item):
	is_invoiced = frappe.db.get_value(item.reference_doctype, item.reference_name, "invoiced")
	if is_invoiced:
		frappe.throw(
			_("The item referenced by {0} - {1} is already invoiced").format(
				item.reference_doctype, item.reference_name
			)
		)