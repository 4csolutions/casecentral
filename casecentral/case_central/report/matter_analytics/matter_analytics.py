# Copyright (c) 2023, 4C Solutions and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import getdate

def execute(filters=None):
	columns = [
		{"label": _("Matter"), "fieldname": "matter", "fieldtype": "Link", "options": "Matter"},
		{"label": _("Customer"), "fieldname": "customer", "fieldtype": "Link", "options": "Customer"},
		{"label": _("Customer Name"), "fieldname": "customer_name", "fieldtype": "Data"},
		{"label": _("Posting Date"), "fieldname": "posting_date", "fieldtype": "Date"},
		{"label": _("Status"), "fieldname": "status", "fieldtype": "Data"},
		{"label": _("Matter Type"), "fieldname": "matter_type", "fieldtype": "Link", "options": "Matter Type"},
		{"label": _("Service Type"), "fieldname": "service_type", "fieldtype": "Link", "options": "Service Type"},
		{"label": _("Service"), "fieldname": "service", "fieldtype": "Link", "options": "Service"},
		{"label": _("Task Count"), "fieldname": "task_count", "fieldtype": "Int"},
		{"label": _("Completed Tasks"), "fieldname": "completed_tasks", "fieldtype": "Int"},
		{"label": _("Pending Tasks"), "fieldname": "pending_tasks", "fieldtype": "Int"}
	]

	filters = filters or {}

	conditions = "1=1"

	if filters.get("matter_type"):
		conditions += f" and matter.matter_type = '{filters.get('matter_type')}'"
		
	if filters.get("service_type"):
		conditions += f" and matter.service_type = '{filters.get('service_type')}'"
		
	if filters.get("service"):
		conditions += f" and matter.service = '{filters.get('service')}'"
		
	if filters.get("customer"):
		conditions += f" and matter.customer = '{filters.get('customer')}'"
		
	if filters.get("from_date"):
		from_date = getdate(filters["from_date"])
		conditions += f" and matter.posting_date >= '{from_date}'"
		
	if filters.get("to_date"):
		to_date = getdate(filters["to_date"])
		conditions += f" and matter.posting_date <= '{to_date}'"

	data = []
	# matter_status_counts = {"Open": 0, "Working": 0, "Pending": 0, "Completed": 0, "Cancelled": 0}
	matter_status_counts = {}
	matter_distribution_by_service = {}

	matters = frappe.db.sql(f"""
		select
			matter.name as matter,
			matter.customer as customer,
			matter.customer_name as customer_name,
			matter.posting_date as posting_date,
			matter.status as status,
			matter.matter_type as matter_type,
			matter.service_type as service_type,
			matter.service as service
		from
			`tabMatter` matter
		where
			{conditions}
		order by
			matter.posting_date asc
	""", as_dict=True)

	for matter in matters:
		row = {
			"matter": matter.matter,
			"customer": matter.customer,
			"customer_name": matter.customer_name,
			"posting_date": matter.posting_date,
			"status": matter.status,
			"matter_type": matter.matter_type,
			"service_type": matter.service_type,
			"service": matter.service
		}
		
		# get task count and completed tasks
		tasks = frappe.get_all("Task", filters={"matter": matter.matter}, fields=["status"])
		if tasks:
			row.update({
				"completed_tasks": sum(1 for task in tasks if task.status == "Completed"),
				"pending_tasks": sum(1 for task in tasks if task.status != "Completed"),
				"task_count": len(tasks)
			})
		else:
			row.update({
				"completed_tasks": 0,
				"pending_tasks": 0,
				"task_count": 0
			})
	
		# update matter status count
		if matter.status in matter_status_counts:
			matter_status_counts[matter.status] += 1
		else:
			matter_status_counts[matter.status] = 1
		# matter_status_counts[matter.status] += 1
		
		# update matter distribution by service
		if matter.service in matter_distribution_by_service:
			matter_distribution_by_service[matter.service] += 1
		else:
			matter_distribution_by_service[matter.service] = 1
		
		data.append(row)
    
	chart = None

	if filters.get("chart"):
		chart_data = []
		
		if filters.get("chart") == "Matter Status":
			chart_data = [{"name": k, "value": v} for k, v in matter_status_counts.items()]
		elif filters.get("chart") == "Matter Distribution by Service":
			chart_data = [{"name": k, "value": v} for k, v in matter_distribution_by_service.items()]
		
		chart = {
			"type": "pie",
			"data": {
				"labels": [x["name"] for x in chart_data],
				"datasets": [
					{
						"data": [x["value"] for x in chart_data],
						"backgroundColor": [
							"#36A2EB",
							"#FFCE56",
							"#FF6384",
							"#4BC0C0",
							"#9966FF",
							"#FF9F40"
						]
					}
				]
			},
			"title": {
				"display": True,
				"text": filters.get("chart")
			}
		}

	return {"columns": columns, "data": data, "chart": chart}

