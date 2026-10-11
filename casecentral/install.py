import frappe
from erpnext.setup.utils import insert_record
from frappe import _

def after_install():
	# Ensure root Item Group exists
	item_group = {
		"doctype": "Item Group",
		"item_group_name": _("All Item Groups"),
		"is_group": 1,
		"parent_item_group": "",
	}
	if not frappe.db.exists(item_group["doctype"], item_group["item_group_name"]):
		insert_record([item_group])

	# Ensure Services item group exists
	if not frappe.db.exists("Item Group", "Services"):
		insert_record([
			{
				"doctype": "Item Group",
				"item_group_name": _("Services"),
				"name": _("Services"),
				"is_group": 0,
				"parent_item_group": _("All Item Groups"),
			}
		])

	# Ensure Books item group exists
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
		task_type_data = {
			"doctype": "Task Type",
			"description": "Hearing",
		}
		if frappe.get_meta("Task Type").has_field("naming_series"):
			task_type_data["naming_series"] = "TT-.###"
		else:
			task_type_data["name"] = "Hearing"

		doc = frappe.get_doc(task_type_data)
		doc.insert(ignore_permissions=True, ignore_if_duplicate=True)
		
	frappe.db.commit()
