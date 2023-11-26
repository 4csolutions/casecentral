# Copyright (c) 2023, 4C Solutions and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document

class PostalOrder(Document):
	pass

@frappe.whitelist()
def create_postal_orders(doctype, docname):
	legal_document = frappe.get_doc(doctype, docname)
	addressees = legal_document.get("addressee")

	message = []
	if addressees:
		for addressee in addressees:
			if not frappe.db.exists("Postal Order", {"legal_document": docname, "to": addressee.name1}):
				postal_order = frappe.new_doc("Postal Order")
				postal_order.to = addressee.name1
				postal_order.legal_document_type = doctype
				postal_order.legal_document = docname
				postal_order.save()
				message.append(postal_order.name)
		return message
	else:
		frappe.msgprint(_("No Addressees found."))