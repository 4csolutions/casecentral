import datetime
import functools
import math
import re
import frappe
from frappe.utils import add_days, add_months, cint, cstr, flt, formatdate, get_first_day, getdate, nowdate
from erpnext.accounts.utils import get_fiscal_year
from frappe import _
from frappe.utils import flt

def execute(filters=None):
    applicable_years = get_applicable_calendar_years()
    filters.from_year = filters.from_year or applicable_years[0]
    filters.to_year = filters.to_year or applicable_years[-1]

    period_list = get_period_list(
        filters.from_year,
        filters.to_year,
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

@frappe.whitelist()
def get_applicable_calendar_years():
    # Fetch the earliest fiscal year start date and the latest fiscal year end date
    first_fiscal_year = frappe.db.get_value("Fiscal Year", {}, "MIN(year_start_date)")
    last_fiscal_year = frappe.db.get_value("Fiscal Year", {}, "MAX(year_end_date)")
    
    # Convert to year format
    start_year = getdate(first_fiscal_year).year
    end_year = getdate(last_fiscal_year).year

    # Ensure the end year is not in the future
    current_year = getdate(nowdate()).year
    if end_year > current_year:
        end_year = current_year

    # Return a list of applicable calendar years
    return list(range(start_year, end_year + 1)), current_year


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


def get_period_list(
	from_year,
	to_year,
	from_fiscal_year,
	to_fiscal_year,
	period_start_date,
	period_end_date,
	filter_based_on,
	periodicity,
	accumulated_values=False,
	company=None,
	reset_period_on_fy_change=True,
	ignore_fiscal_year=False,
):
	"""Get a list of dict {"from_date": from_date, "to_date": to_date, "key": key, "label": label}
	Periodicity can be (Yearly, Quarterly, Monthly)"""

	if filter_based_on == "Fiscal Year":
		fiscal_year = get_fiscal_year_data(from_fiscal_year, to_fiscal_year)
		validate_fiscal_year(fiscal_year, from_fiscal_year, to_fiscal_year)
		year_start_date = getdate(fiscal_year.year_start_date)
		year_end_date = getdate(fiscal_year.year_end_date)
	elif filter_based_on == "Date Range":
		validate_dates(period_start_date, period_end_date)
		year_start_date = getdate(period_start_date)
		year_end_date = getdate(period_end_date)
	else:
		first_fiscal_year = frappe.db.get_value("Fiscal Year", {}, "MIN(year_start_date)")
		last_fiscal_year = frappe.db.get_value("Fiscal Year", {}, "MAX(year_end_date)")
		if int(from_year)==first_fiscal_year.year:
			year_start_date=getdate(first_fiscal_year)
		else:
			year_start_date=getdate(datetime.date(int(from_year), 1, 1))
		if int(to_year)==last_fiscal_year.year:
			year_end_date=getdate(last_fiscal_year)
		else:
			year_end_date=getdate(datetime.date(int(to_year), 12, 31))

	months_to_add = {"Yearly": 12, "Half-Yearly": 6, "Quarterly": 3, "Monthly": 1}[periodicity]

	period_list = []

	start_date = year_start_date
	months = get_months(year_start_date, year_end_date)

	for i in range(cint(math.ceil(months / months_to_add))):
		period = frappe._dict({"from_date": start_date})

		if i == 0 and filter_based_on == "Date Range":
			to_date = add_months(get_first_day(start_date), months_to_add)
		else:
			to_date = add_months(start_date, months_to_add)

		start_date = to_date

		# Subtract one day from to_date, as it may be first day in next fiscal year or month
		to_date = add_days(to_date, -1)

		if to_date <= year_end_date:
			# the normal case
			period.to_date = to_date
		else:
			# if a fiscal year ends before a 12 month period
			period.to_date = year_end_date

		if not ignore_fiscal_year:
			period.to_date_fiscal_year = get_fiscal_year(period.to_date, company=company)[0]
			period.from_date_fiscal_year_start_date = get_fiscal_year(period.from_date, company=company)[1]

		period_list.append(period)

		if period.to_date == year_end_date:
			break

	# common processing
	for opts in period_list:
		key = opts["to_date"].strftime("%b_%Y").lower()
		if periodicity == "Monthly" and not accumulated_values:
			label = formatdate(opts["to_date"], "MMM YYYY")
		else:
			if not accumulated_values:
				label = get_label(periodicity, opts["from_date"], opts["to_date"])
			else:
				if reset_period_on_fy_change:
					label = get_label(periodicity, opts.from_date_fiscal_year_start_date, opts["to_date"])
				else:
					label = get_label(periodicity, period_list[0].from_date, opts["to_date"])

		opts.update(
			{
				"key": key.replace(" ", "_").replace("-", "_"),
				"label": label,
				"year_start_date": year_start_date,
				"year_end_date": year_end_date,
			}
		)

	return period_list


def get_fiscal_year_data(from_fiscal_year, to_fiscal_year):
	fiscal_year = frappe.db.sql(
		"""select min(year_start_date) as year_start_date,
		max(year_end_date) as year_end_date from `tabFiscal Year` where
		name between %(from_fiscal_year)s and %(to_fiscal_year)s""",
		{"from_fiscal_year": from_fiscal_year, "to_fiscal_year": to_fiscal_year},
		as_dict=1,
	)

	return fiscal_year[0] if fiscal_year else {}


def validate_fiscal_year(fiscal_year, from_fiscal_year, to_fiscal_year):
	if not fiscal_year.get("year_start_date") or not fiscal_year.get("year_end_date"):
		frappe.throw(_("Start Year and End Year are mandatory"))

	if getdate(fiscal_year.get("year_end_date")) < getdate(fiscal_year.get("year_start_date")):
		frappe.throw(_("End Year cannot be before Start Year"))


def validate_dates(from_date, to_date):
	if not from_date or not to_date:
		frappe.throw(_("From Date and To Date are mandatory"))

	if to_date < from_date:
		frappe.throw(_("To Date cannot be less than From Date"))


def get_months(start_date, end_date):
	diff = (12 * end_date.year + end_date.month) - (12 * start_date.year + start_date.month)
	return diff + 1


def get_label(periodicity, from_date, to_date):
	if periodicity == "Yearly":
		if formatdate(from_date, "YYYY") == formatdate(to_date, "YYYY"):
			label = formatdate(from_date, "YYYY")
		else:
			label = formatdate(from_date, "YYYY") + "-" + formatdate(to_date, "YYYY")
	else:
		label = formatdate(from_date, "MMM YY") + "-" + formatdate(to_date, "MMM YY")

	return label