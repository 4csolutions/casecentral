# Copyright (c) 2026, 4C Solutions and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document


class FileMovementItem(Document):
	matter: str | None = None
	case: str | None = None
	barcode: str | None = None
