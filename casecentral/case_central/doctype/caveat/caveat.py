# Copyright (c) 2023, 4C Solutions and contributors
# For license information, please see license.txt

import frappe
from frappe.utils import (nowdate)
from frappe.model.document import Document

class Caveat(Document):
	pass

@frappe.whitelist()
def set_expired_status():
	expired_caveats_list = frappe.db.get_list('Caveat', 
		filters = {
		'status': 'Active',
		'expiry_date': ['<', nowdate()]
		}, 
		fields = ['name']
	)

	for cvt in expired_caveats_list:
		caveat = frappe.get_doc("Caveat", cvt.name)
		caveat.status = 'Expired'
		caveat.save(ignore_permissions=True)
		caveat.reload()
	return