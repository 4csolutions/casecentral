<<<<<<< HEAD
=======
import json
>>>>>>> 92d53e089c992e179715961a85936eeb4063cc9a
import frappe
from frappe.model.document import Document

class Case(Document):
<<<<<<< HEAD
    def on_update(self):
        # Fetch the latest hearing date from Case History
        case_history = frappe.db.get_all('Case History', filters={'parent': self.name},
                                         fields=['hearing_date'], order_by='hearing_date desc', as_list=True)
        if case_history:
            next_hearing_date = case_history[0][0]
            frappe.db.set_value(self.doctype, self.name, 'next_hearing_date', next_hearing_date)
            self.reload()

            # Create or Update Task for the hearing
            task_id = f"{self.name}-Hearing-{next_hearing_date}"
            task_exists = frappe.db.exists("Task", task_id)

            if not task_exists:
                task = frappe.new_doc("Task")
                task.update({
                    'name': task_id,
                    'subject': f"{self.name}-Hearing-{next_hearing_date}",
                    'type': 'Hearing',  # Assuming 'Hearing' is a valid type
                    'is_group': 0,
                    'is_template': 0,
                    'status': 'Open',
                    'priority': 'Low',  # Default priority
                    'exp_start_date': next_hearing_date,
                    'expected_time': 0.000,
                    'exp_end_date': next_hearing_date,
                    'progress': 0,
                    'is_milestone': 0,
                    'description': f"Hearing Task - {next_hearing_date}",
                    'matter': self.matter,  # Automatically use the matter field from the Case document
                    'case': self.name,      # Automatically use the case name from the Case document
                    'case_title': self.case_title  # Automatically use the case_title field from the Case document
                })
                task.insert(ignore_permissions=True)
                frappe.db.commit()
=======
	def on_update(self):
		case_history = frappe.db.get_all('Case History', filters={'parent': self.name}, 
										fields=['hearing_date'], order_by='hearing_date desc', as_list=True)
		if case_history:
			next_hearing_date = case_history[0][0]
			frappe.db.set_value(self.doctype, self.name, 'next_hearing_date', next_hearing_date)
			self.reload()
>>>>>>> 92d53e089c992e179715961a85936eeb4063cc9a

			# Create or Update Task for the hearing
			task_id = f"{self.name}-Hearing-{next_hearing_date}"
			task_exists = frappe.db.exists("Task", task_id)

			if not task_exists:
				task = frappe.new_doc("Task")
				task.update({
					'name': task_id,
					'subject': f"{self.name}-Hearing-{next_hearing_date}",
					'type': 'Hearing',  # Assuming 'Hearing' is a valid type
					'is_group': 0,
					'is_template': 0,
					'status': 'Open',
					'priority': 'Low',  # Default priority
					'exp_start_date': next_hearing_date,
					'expected_time': 0.000,
					'exp_end_date': next_hearing_date,
					'progress': 0,
					'is_milestone': 0,
					'description': f"Hearing Task - {next_hearing_date}",
				})
				task.insert(ignore_permissions=True)
				frappe.db.commit()

@frappe.whitelist()
def get_events(start, end, filters=None):
    """Returns events for Gantt / Calendar view rendering.

    :param start: Start date-time.
    :param end: End date-time.
    :param filters: Filters (JSON).
    """
    from frappe.desk.calendar import get_event_conditions

    conditions = get_event_conditions("Case", filters)

    data = frappe.db.sql(
        """
<<<<<<< HEAD
        SELECT
            name, CONCAT(name, CHAR(13), registration_number) AS title, status, next_hearing_date
        FROM
            `tabCase`
        WHERE status = "InProgress"
            AND (next_hearing_date BETWEEN %(start)s AND %(end)s)
=======
        select
            name, concat(name, CHAR(13), registration_number) as title, status, next_hearing_date
        from
            `tabCase`
        where status="InProgress"
            and (next_hearing_date between %(start)s and %(end)s)
>>>>>>> 92d53e089c992e179715961a85936eeb4063cc9a
            {conditions}
        """.format(
            conditions=conditions
        ),
        {"start": start, "end": end},
        as_dict=True
    )
    return data
