# Copyright (c) 2026, 4C Solutions and contributors
# For license information, please see license.txt

import frappe
from frappe import _


def execute(filters=None):
	filters = filters or {}
	columns = get_columns()
	data = get_data(filters)
	return columns, data


def get_columns():
	return [
		{
			"label": _("Matter"),
			"fieldname": "matter",
			"fieldtype": "Link",
			"options": "Matter",
			"width": 180,
		},
		{
			"label": _("Creation"),
			"fieldname": "creation",
			"fieldtype": "Datetime",
			"width": 160,
		},
		{
			"label": _("Status"),
			"fieldname": "status",
			"fieldtype": "Data",
			"width": 120,
		},
		{
			"label": _("Matter Type"),
			"fieldname": "matter_type",
			"fieldtype": "Data",
			"width": 120,
		},
		{
			"label": _("Service"),
			"fieldname": "service",
			"fieldtype": "Data",
			"width": 150,
		},
		{
			"label": _("Client"),
			"fieldname": "customer",
			"fieldtype": "Link",
			"options": "Customer",
			"width": 180,
		},
		{
			"label": _("Client Name"),
			"fieldname": "customer_name",
			"fieldtype": "Data",
			"width": 200,
		},
		{
			"label": _("Contact No"),
			"fieldname": "contact_no",
			"fieldtype": "Data",
			"width": 140,
		},
	]


def get_data(filters):
	conditions = [
		"matter_type = 'Court'",
		"docstatus = 1",
		"""(
			SELECT COUNT(*)
			FROM `tabCase`
			WHERE `tabCase`.matter = `tabMatter`.name
		) = 0""",
	]

	query_filters = {}
	if filters.get("service"):
		conditions.append("service IN %(service)s")
		query_filters["service"] = tuple(filters.get("service"))

	if filters.get("status"):
		conditions.append("status IN %(status)s")
		query_filters["status"] = tuple(filters.get("status"))

	where_clause = " AND ".join(conditions)

	query = f"""
		SELECT
			name AS matter,
			creation,
			status,
			matter_type,
			service,
			customer,
			customer_name,
			contact_no
		FROM `tabMatter`
		WHERE {where_clause}
		ORDER BY creation DESC
	"""

	return frappe.db.sql(query, query_filters, as_dict=True)
