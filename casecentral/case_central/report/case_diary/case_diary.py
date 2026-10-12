# Copyright (c) 2026, 4C Solutions and contributors
# For license information, please see license.txt

import json
import frappe
from frappe import _


def execute(filters=None):
	filters = filters or {}
	columns = get_columns()
	data = get_data(filters)
	return columns, data


def get_columns():
	return [
		{"label": _("Previous Date"), "fieldname": "business_on_date", "fieldtype": "Date", "width": 110},
		{"label": _("Hearing Date"), "fieldname": "hearing_date", "fieldtype": "Date", "width": 110},
		{"label": _("Court Number and Judge"), "fieldname": "court_number_and_judge", "fieldtype": "Data", "width": 180},
		{"label": _("ID"), "fieldname": "case_id", "fieldtype": "Link", "options": "Case", "width": 140},
		{"label": _("Case Title"), "fieldname": "case_title", "fieldtype": "Data", "width": 240},
		{"label": _("Case Stage"), "fieldname": "case_stage", "fieldtype": "Link", "options": "Case Stage", "width": 140},
		{"label": _("Next Purpose"), "fieldname": "purpose_of_hearing", "fieldtype": "Data", "width": 180},
		{"label": _("Next Hearing Date"), "fieldname": "next_hearing_date", "fieldtype": "Date", "width": 130},
		{"label": _("Assigned To"), "fieldname": "assigned_to", "fieldtype": "Data", "width": 160},
	]


def get_data(filters):
	conditions = []
	query_filters = {
		"from_date": filters.get("from_date"),
		"to_date": filters.get("to_date"),
	}

	if filters.get("service"):
		conditions.append("c.service IN %(service)s")
		query_filters["service"] = tuple(filters.get("service"))

	if filters.get("case_stage"):
		conditions.append("c.case_stage IN %(case_stage)s")
		query_filters["case_stage"] = tuple(filters.get("case_stage"))

	where_clause = ""
	if conditions:
		where_clause = " AND " + " AND ".join(conditions)

	query = f"""
		SELECT
			ch.business_on_date,
			ch.hearing_date,
			c.court_number_and_judge,
			c.name AS case_id,
			CONCAT(COALESCE(c.case_title, ''), '\n', COALESCE(c.registration_number, '')) AS case_title,
			c.case_stage AS case_stage,
			ch.purpose_of_hearing
		FROM
			`tabCase History` ch
			JOIN `tabCase` c ON c.name = ch.parent
		WHERE
			ch.hearing_date BETWEEN %(from_date)s AND %(to_date)s
			{where_clause}
		ORDER BY
			ch.hearing_date ASC
	"""

	result = frappe.db.sql(query, query_filters, as_dict=True)

	for record in result:
		next_hearing_date = (
			frappe.db.get_value(
				"Case History",
				{"business_on_date": record.hearing_date, "parent": record.case_id},
				"hearing_date",
			)
			or ""
		)
		record["next_hearing_date"] = next_hearing_date
		record["assigned_to"] = ""

		formatted_hearing_date = frappe.utils.formatdate(record.hearing_date).replace("-", "")
		task_subject = f"{record.case_id}-Hearing-{formatted_hearing_date}"
		task = frappe.db.exists("Task", {"subject": task_subject})
		if task:
			assigned_to = frappe.db.get_value("Task", task, "_assign")
			emp = json.loads(assigned_to)[0] if assigned_to else ""
			if emp:
				record["assigned_to"] = frappe.db.get_value("User", emp, "full_name") or emp

	return result
