import json
import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import today, getdate, formatdate


class Case(Document):
    def on_update(self):
        # Fetch the most recent hearing date from Case History
        case_history = frappe.db.get_all(
            "Case History",
            filters={"parent": self.name},
            fields=["hearing_date"],
            order_by="hearing_date desc",
            as_list=True,
        )
        if case_history and self.next_hearing_date and getdate(self.next_hearing_date) < getdate(
            case_history[0][0]
        ):
            next_hearing_date = case_history[0][0]  # Get the latest hearing date
            frappe.db.set_value(
                self.doctype, self.name, "next_hearing_date", next_hearing_date
            )
            self.reload()

        if not self.next_hearing_date:
            return

        # Format the hearing date according to system settings and strip hyphens
        formatted_hearing_date = formatdate(self.next_hearing_date).replace("-", "")
        task_subject = f"{self.name}-Hearing-{formatted_hearing_date}"

        # Check if a Task with the same subject already exists
        if getdate(self.next_hearing_date) > getdate() and not frappe.db.exists(
            "Task", {"subject": task_subject}
        ):
            task_type_id = frappe.db.get_value(
                "Task Type", {"description": "Hearing"}, "name"
            )

            if not task_type_id:
                frappe.throw(_("Task Type with description 'Hearing' not found."))

            task = frappe.new_doc("Task")
            task.update(
                {
                    "subject": task_subject,
                    "type": task_type_id,
                    "is_group": 0,
                    "is_template": 0,
                    "status": "Open",
                    "priority": "Low",
                    "exp_start_date": self.next_hearing_date,
                    "expected_time": 0.000,
                    "exp_end_date": self.next_hearing_date,
                    "progress": 0,
                    "case": self.name,
                    "is_milestone": 0,
                    "description": task_subject,
                    "matter": self.matter,
                }
            )
            task.insert(ignore_permissions=True)
            frappe.db.commit()


@frappe.whitelist()
def get_events(start, end, filters=None):
    """Returns events for Gantt / Calendar view rendering.
    :param start: Start date-time.
    :param end: End date-time.
    :param filters: Filters (JSON).
    """
    if isinstance(filters, str):
        filters = json.loads(filters)

    filters = filters or {}
    filters.update({
        "status": "InProgress",
        "next_hearing_date": ["between", [start, end]]
    })

    data = frappe.get_all(
        "Case",
        filters=filters,
        fields=["name", "registration_number", "status", "next_hearing_date"]
    )

    for item in data:
        item.title = f"{item.name}\r{item.registration_number or ''}"

    return data


@frappe.whitelist()
def get_case_stage(doctype, txt, searchfield, start, page_len, filters):
    if not filters:
        return []
    case_stages = frappe.get_all(
        "Service List",
        filters={
            "parenttype": "Case Stage",
            "service": filters.get("service"),
        },
        pluck="parent",
    )

    if not case_stages:
        return []

    case_stage_list = [[p] for p in case_stages]

    if txt:
        search_list = []
        for case_stage in case_stage_list:
            if txt.lower() in case_stage[0].lower():
                search_list.append([case_stage[0]])

        return search_list

    return case_stage_list
