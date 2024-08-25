import functools
import math
import re
from erpnext.accounts.report.financial_statements import get_period_list
import frappe
from frappe import _
from frappe.utils import flt

def execute(filters=None):
    period_list = get_period_list(
        filters.from_fiscal_year,
        filters.to_fiscal_year,
        filters.period_start_date,
        filters.period_end_date,
        filters.filter_based_on,
        filters.periodicity,
        company=filters.company,
    )
    columns = get_columns()
    data = get_data(filters, period_list)
    message = filters.get('report'), 's Report'
    chart = get_chart_data(filters,columns,data)
    return columns, data, message, chart


def get_chart_data(filters, columns, data):
    labels = [d.get("period") for d in data]

    # Prepare datasets for total and completed tasks
    total_data, pending_total, new_total, completed_data = [], [], [], []

    for entry in data:
        pending_total.append(entry.get("pending", 0))
        new_total.append(entry.get("new", 0))
        total_data.append(entry.get("total", 0))
        completed_data.append(entry.get("completed", 0))

    datasets = []
    if pending_total:
        datasets.append({
            "name": _("Pending ") + filters.report,
            "values": pending_total,
        })
    if new_total:
        datasets.append({
            "name": _("New ") + filters.report,
            "values": new_total,
        })
    if total_data:
        datasets.append({
            "name": _("Total ") + filters.report,
            "values": total_data,
        })
    if completed_data:
        datasets.append({
            "name": _("Completed ") + filters.report,
            "values": completed_data,
        })

    chart = {
        "type": "line",  # or "line" depending on your needs
        "data": {
            "labels": labels,
            "datasets": datasets
        },
        "colors": ["#F683AE", "#318AD8", "#F39C12", "#48BB74"],
        "options": {
            "responsive": True,
            "scales": {
                "x": {
                    "stacked": True 
                },
                "y": {
                    "beginAtZero": True
                }
            }
        }
    }
    

    return chart

def get_data(filters, period_list):
    data = []
    if filters.report == "Task":
        data = get_task_clearance_data(period_list, filters.company)
    elif filters.report == "Matter":
        data = get_matter_clearance_data(period_list, filters.company)
    elif filters.report == "Case":
        data = get_case_clearance_data(period_list, filters.company)
    return data

# Task Clearance Data
def get_task_clearance_data(period_list, company):
    data = []
    for period in period_list:
        pending, new = get_task_total(period.from_date, period.to_date, company)
        total = pending + new
        completed = get_task_completed(period.from_date, period.to_date, company)
        absolute_clearance_rate = (completed / new * 100) if new else (completed * 100)
        clearance_rate = (completed / total * 100) if total else (completed * 100)
        data.append({
            "period": period.label,
            "pending": pending,
            "new": new,
            "total": total,
            "completed": completed,
            "absolute_clearance_rate": flt(absolute_clearance_rate, 2),
            "clearance_rate": flt(clearance_rate, 2)
        })
        
    return data

def get_task_total(from_date, to_date, company):
    pending_before = frappe.db.count("Task", filters={
        'status': ['not in', ['Cancelled', 'Completed']],
        'creation': ['<', from_date],
        'company': company
    })
    created_in_period = frappe.db.count("Task", filters={
        'status': ['!=', 'Cancelled'],
        'creation': ['between', [from_date, to_date]],
        'company': company
    })
    return pending_before, created_in_period

def get_task_completed(from_date, to_date, company):
    return frappe.db.count("Task", filters={
        'status': ['=', 'Completed'],
        'completed_on': ['between', [from_date, to_date]],
        'company': company
    })

# Matter Clearance Data
def get_matter_clearance_data(period_list, company):
    data = []
    for period in period_list:
        pending, new = get_matter_total(period.from_date, period.to_date, company)
        total = pending + new
        completed = get_matter_completed(period.from_date, period.to_date, company)
        absolute_clearance_rate = (completed / new * 100) if new else (completed * 100)
        clearance_rate = (completed / total * 100) if total else (completed * 100)
        data.append({
            "period": period.label,
            "pending": pending,
            "new": new,
            "total": total,
            "completed": completed,
            "absolute_clearance_rate": flt(absolute_clearance_rate, 2),
            "clearance_rate": flt(clearance_rate, 2)
        })

    return data

def get_matter_total(from_date, to_date, company):
    pending_before = frappe.db.count("Matter", filters={
        'status': ['not in', ['Cancelled', 'Completed']],
        'creation': ['<', from_date],
        'company': company
    })
    created_in_period = frappe.db.count("Matter", filters={
        'status': ['!=', 'Cancelled'],
        'creation': ['between', [from_date, to_date]],
        'company': company
    })
    return pending_before, created_in_period

def get_matter_completed(from_date, to_date, company):
    return frappe.db.count("Matter", filters={
        'status': ['=', 'Completed'],
        'modified': ['between', [from_date, to_date]],
        'company': company
    })

# Case Clearance Data
def get_case_clearance_data(period_list, company):
    data = []
    for period in period_list:
        pending, new = get_case_total(period.from_date, period.to_date, company)
        total = pending + new
        completed = get_case_completed(period.from_date, period.to_date, company)
        absolute_clearance_rate = (completed / new * 100) if new else (completed * 100)
        clearance_rate = (completed / total * 100) if total else (completed * 100)
        data.append({
            "period": period.label,
            "pending": pending,
            "new": new,
            "total": total,
            "completed": completed,
            "absolute_clearance_rate": flt(absolute_clearance_rate, 2),
            "clearance_rate": flt(clearance_rate, 2)
        })

    return data

def get_case_total(from_date, to_date, company):
    pending_before = frappe.db.count("Case", filters={
        'status': ['not in', ['Disposed', 'NOC']],
        'creation': ['<', from_date],
        'company': company
    })
    created_in_period = frappe.db.count("Case", filters={
        'status': ['!=', 'Cancelled'],
        'creation': ['between', [from_date, to_date]],
        'company': company
    })
    return pending_before, created_in_period

def get_case_completed(from_date, to_date, company):
    return frappe.db.count("Case", filters={
        'status': ['=', 'Disposed'],
        'date_of_disposal': ['between', [from_date, to_date]],
        'company': company
    })

# Column Definition
def get_columns():
    return [
        {"fieldname": "period", "label": "Period", "fieldtype": "Data", "width": 300},
        {"fieldname": "pending", "label": "Pending", "fieldtype": "Data", "width": 100},
        {"fieldname": "new", "label": "New", "fieldtype": "Data", "width": 100},
        {"fieldname": "total", "label": "Total", "fieldtype": "Int", "width": 100},
        {"fieldname": "completed", "label": "Completed", "fieldtype": "Int", "width": 100},
        {"fieldname": "absolute_clearance_rate", "label": "Absolute Clearance Rate (%)", "fieldtype": "Percent", "width": 250},
        {"fieldname": "clearance_rate", "label": "Clearance Rate (%)", "fieldtype": "Percent", "width": 200}
    ]
