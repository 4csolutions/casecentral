import functools
import math
import re
from erpnext.accounts.report.financial_statements import get_period_list
import frappe
from frappe import _
from frappe.utils import flt
from frappe.utils import add_days, add_months, cint, cstr, flt, formatdate, get_first_day, getdate
from erpnext.accounts.utils import get_fiscal_year



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
    total_data, completed_data = [], []

    for entry in data:
        total_data.append(entry.get("total", 0))
        completed_data.append(entry.get("completed", 0))

    datasets = []
    if total_data:
        datasets.append({
            "name": _("Total Tasks"),
            "backgroundColor": "#f39c12",
            "values": total_data
        })
    if completed_data:
        datasets.append({
            "name": _("Completed Tasks"),
            "backgroundColor": "#00a65a",
            "values": completed_data
        })

    chart = {
        "type": "bar",  # or "line" depending on your needs
        "data": {
            "labels": labels,
            "datasets": datasets
        },
        
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
        total = get_task_total(period.from_date, period.to_date, company)
        completed = get_task_completed(period.from_date, period.to_date, company)
        clearance_rate = (completed / total * 100) if total else 0
        data.append({
            "period": period.label,
            "total": total,
            "completed": completed,
            "clearance_rate": clearance_rate
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
    return pending_before + created_in_period

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
        total = get_matter_total(period.from_date, period.to_date, company)
        completed = get_matter_completed(period.from_date, period.to_date, company)
        clearance_rate = (completed / total * 100) if total else 0
        data.append({
            "period": period.label,
            "total": total,
            "completed": completed,
            "clearance_rate": clearance_rate
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
    return pending_before + created_in_period

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
        total = get_case_total(period.from_date, period.to_date, company)
        completed = get_case_completed(period.from_date, period.to_date, company)
        clearance_rate = (completed / total * 100) if total else 0
        data.append({
            "period": period.label,
            "total": total,
            "completed": completed,
            "clearance_rate": clearance_rate
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
    return pending_before + created_in_period

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
        {"fieldname": "total", "label": "Total", "fieldtype": "Int", "width": 150},
        {"fieldname": "completed", "label": "Completed", "fieldtype": "Int", "width": 100},
        {"fieldname": "clearance_rate", "label": "Clearance Rate (%)", "fieldtype": "Percent", "width": 150}
    ]
