import frappe
from erpnext.setup.utils import insert_record
from frappe import _

def after_install():
	item_group = {
		"doctype": "Item Group",
		"item_group_name": _("All Item Groups"),
		"is_group": 1,
		"parent_item_group": "",
	}
	if not frappe.db.exists(item_group["doctype"], item_group["item_group_name"]):
		insert_record([item_group])
	if not frappe.db.exists("Item Group", "Books"):
		insert_record([
			{
				"doctype": "Item Group",
				"item_group_name": _("Books"),
				"name": _("Books"),
				"is_group": 0,
				"parent_item_group": _("All Item Groups"),
			}
		])

	if not frappe.db.exists("Legal Service", "Hearing Fee"):
		insert_record([
			{
				"doctype": "Legal Service",
				"legal_service": "Hearing Fee",
				"item_code": "Hearing Fee",
				"item_group": "Services",
				"description": "Hearing Fee",
				"uom": "Nos",
			}
		])

	if not frappe.db.get_value("Task Type", {"description": "Hearing"}, "name"):
		insert_record([
			{
				"doctype": "Task Type",
				"description": "Hearing",
			}
		])
		
	frappe.db.commit()
