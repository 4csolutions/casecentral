# Copyright (c) 2023, 4C Solutions and contributors
# For license information, please see license.txt

import datetime
import json

import frappe
from erpnext.setup.doctype.employee.employee import is_holiday
from frappe import _
from frappe.core.doctype.sms_settings.sms_settings import send_sms
from frappe.model.document import Document
from frappe.model.mapper import get_mapped_doc
from frappe.utils import flt, format_date, get_link_to_form, get_time, getdate

class MaximumCapacityError(frappe.ValidationError):
	pass


class OverlapError(frappe.ValidationError):
	pass


class CustomerAppointment(Document):
	def validate(self):
		self.validate_overlaps()
		self.set_appointment_datetime()
		self.set_status()
		self.set_title()
		self.update_event()

	def after_insert(self):
		invoice_appointment(self)
		self.insert_calendar_event()

	def set_title(self):
		self.title = _("{0} with {1}").format(
			self.customer_name or self.customer, self.employee_name or self.employee
		)

	def set_status(self):
		today = getdate()
		appointment_date = getdate(self.appointment_date)

		# If appointment is created for today set status as Open else Scheduled
		if appointment_date == today:
			self.status = "Open"
		elif appointment_date > today:
			self.status = "Scheduled"

	def validate_overlaps(self):
		end_time = datetime.datetime.combine(
			getdate(self.appointment_date), get_time(self.appointment_time)
		) + datetime.timedelta(minutes=flt(self.duration))

		# all appointments for both customer and employee overlapping the duration of this appointment
		overlapping_appointments = frappe.db.sql(
			"""
			SELECT
				name, employee, customer, appointment_time, duration, meeting_room
			FROM
				`tabCustomer Appointment`
			WHERE
				appointment_date=%(appointment_date)s AND name!=%(name)s AND status NOT IN ("Closed", "Cancelled") AND
				(employee=%(employee)s OR customer=%(customer)s) AND
				((appointment_time<%(appointment_time)s AND appointment_time + INTERVAL duration MINUTE>%(appointment_time)s) OR
				(appointment_time>%(appointment_time)s AND appointment_time<%(end_time)s) OR
				(appointment_time=%(appointment_time)s))
			""",
			{
				"appointment_date": self.appointment_date,
				"name": self.name,
				"employee": self.employee,
				"customer": self.customer,
				"appointment_time": self.appointment_time,
				"end_time": end_time.time(),
			},
			as_dict=True,
		)

		if not overlapping_appointments:
			return  # No overlaps, nothing to validate!

		if self.meeting_room:  # validate meeting room capacity if overlap enabled
			allow_overlap, meeting_room_capacity = frappe.get_value(
				"Meeting Room", self.meeting_room, ["overlap_appointments", "meeting_room_capacity"]
			)
			if allow_overlap:
				meeting_room_appointments = list(
					filter(
						lambda appointment: appointment["meeting_room"] == self.meeting_room
						and appointment["customer"] != self.customer,
						overlapping_appointments,
					)
				)  # if same customer already booked, it should be an overlap
				if len(meeting_room_appointments) >= (meeting_room_capacity or 1):
					frappe.throw(
						_("Not allowed, {} cannot exceed maximum capacity {}").format(
							frappe.bold(self.meeting_room), frappe.bold(meeting_room_capacity or 1)
						),
						MaximumCapacityError,
					)
				else:  # meeting_room_appointments within capacity, remove from overlapping_appointments
					overlapping_appointments = [
						appointment
						for appointment in overlapping_appointments
						if appointment not in meeting_room_appointments
					]

		if overlapping_appointments:
			frappe.throw(
				_("Not allowed, cannot overlap appointment {}").format(
					frappe.bold(", ".join([appointment["name"] for appointment in overlapping_appointments]))
				),
				OverlapError,
			)

	def set_appointment_datetime(self):
		self.appointment_datetime = "%s %s" % (
			self.appointment_date,
			self.appointment_time or "00:00:00",
		)

	def insert_calendar_event(self):
		starts_on = datetime.datetime.combine(
			getdate(self.appointment_date), get_time(self.appointment_time)
		)
		ends_on = starts_on + datetime.timedelta(minutes=flt(self.duration))
		google_calendar = frappe.db.get_value(
			"Employee", self.employee, "google_calendar"
		)

		if self.appointment_type:
			color = frappe.db.get_value("Appointment Type", self.appointment_type, "color")
		else:
			color = ""

		event = frappe.get_doc(
			{
				"doctype": "Event",
				"subject": f"{self.title} - {self.company}",
				"event_type": "Private",
				"color": color,
				"send_reminder": 1,
				"starts_on": starts_on,
				"ends_on": ends_on,
				"status": "Open",
				"all_day": 0,
				"sync_with_google_calendar": 1 if self.add_video_conferencing and google_calendar else 0,
				"add_video_conferencing": 1 if self.add_video_conferencing and google_calendar else 0,
				"google_calendar": google_calendar,
				"description": f"{self.title} - {self.company}",
				"pulled_from_google_calendar": 0,
			}
		)
		participants = []
		participants.append(
			{"reference_doctype": "Employee", "reference_docname": self.employee}
		)
		participants.append({"reference_doctype": "Customer", "reference_docname": self.customer})

		event.update({"event_participants": participants})

		event.insert(ignore_permissions=True)

		event.reload()
		if self.add_video_conferencing and not event.google_meet_link:
			frappe.msgprint(
				_("Could not add conferencing to this Appointment, please contact System Manager"),
				indicator="error",
				alert=True,
			)

		self.db_set({"event": event.name, "google_meet_link": event.google_meet_link})
		self.notify_update()

	def update_event(self):
		if self.event:
			event_doc = frappe.get_doc("Event", self.event)
			starts_on = datetime.datetime.combine(
				getdate(self.appointment_date), get_time(self.appointment_time)
			)
			ends_on = starts_on + datetime.timedelta(minutes=flt(self.duration))
			if (
				starts_on != event_doc.starts_on
				or self.add_video_conferencing != event_doc.add_video_conferencing
			):
				event_doc.starts_on = starts_on
				event_doc.ends_on = ends_on
				event_doc.add_video_conferencing = self.add_video_conferencing
				event_doc.save()
				event_doc.reload()
				self.google_meet_link = event_doc.google_meet_link

def invoice_appointment(appointment_doc):
	appointment_invoiced = frappe.db.get_value(
		"Customer Appointment", appointment_doc.name, "invoiced"
	)

def check_is_new_customer(customer, name=None):
	filters = {"customer": customer, "status": ("!=", "Cancelled")}
	if name:
		filters["name"] = ("!=", name)

	has_previous_appointment = frappe.db.exists("Customer Appointment", filters)
	return not has_previous_appointment


def cancel_appointment(appointment_id):
	appointment = frappe.get_doc("Customer Appointment", appointment_id)
	if appointment.event:
		event_doc = frappe.get_doc("Event", appointment.event)
		event_doc.event_type = "Cancelled"
		event_doc.save()

@frappe.whitelist()
def get_availability_data(date, employee):
	"""
	Get availability data of 'employee' on 'date'
	:param date: Date to check in schedule
	:param employee: Name of the employee
	:return: dict containing a list of available slots, list of appointments and time of appointments
	"""

	date = getdate(date)
	weekday = date.strftime("%A")

	employee_doc = frappe.get_doc("Employee", employee)

	check_employee_wise_availability(date, employee_doc)

	if employee_doc.employee_schedules:
		slot_details = get_available_slots(employee_doc, date)
	else:
		frappe.throw(
			_(
				"{0} does not have a Lawyer Schedule. Add it in Employee master"
			).format(employee),
			title=_("Lawyer Schedule Not Found"),
		)

	if not slot_details:
		# TODO: return available slots in nearby dates
		frappe.throw(
			_("Employee not available on {0}").format(weekday), title=_("Not Available")
		)

	return {"slot_details": slot_details}


def check_employee_wise_availability(date, employee_doc):
	employee = None
	if employee_doc.employee:
		employee = employee_doc.employee
	elif employee_doc.user_id:
		employee = frappe.db.get_value("Employee", {"user_id": employee_doc.user_id}, "name")

	if employee:
		# check holiday
		if is_holiday(employee, date):
			frappe.throw(_("{0} is a holiday".format(date)), title=_("Not Available"))

		# check leave status
		if "hrms" in frappe.get_installed_apps():
			leave_record = frappe.db.sql(
				"""select half_day from `tabLeave Application`
				where employee = %s and %s between from_date and to_date
				and docstatus = 1""",
				(employee, date),
				as_dict=True,
			)
			if leave_record:
				if leave_record[0].half_day:
					frappe.throw(
						_("{0} is on a Half day Leave on {1}").format(employee_doc.name, date),
						title=_("Not Available"),
					)
				else:
					frappe.throw(
						_("{0} is on Leave on {1}").format(employee_doc.name, date), title=_("Not Available")
					)


def get_available_slots(employee_doc, date):
	available_slots = slot_details = []
	weekday = date.strftime("%A")
	employee = employee_doc.name

	for schedule_entry in employee_doc.employee_schedules:
		validate_employee_schedules(schedule_entry, employee)
		lawyer_schedule = frappe.get_doc("Lawyer Schedule", schedule_entry.schedule)

		if lawyer_schedule and not lawyer_schedule.disabled:
			available_slots = []
			for time_slot in lawyer_schedule.time_slots:
				if weekday == time_slot.day:
					available_slots.append(time_slot)

			if available_slots:
				appointments = []
				allow_overlap = 0
				meeting_room_capacity = 0
				# fetch all appointments to employee by meeting room
				filters = {
					"employee": employee,
					"meeting_room": schedule_entry.meeting_room,
					"appointment_date": date,
					"status": ["not in", ["Cancelled"]],
				}

				if schedule_entry.meeting_room:
					slot_name = f"{schedule_entry.schedule}"
					allow_overlap, meeting_room_capacity = frappe.get_value(
						"Meeting Room",
						schedule_entry.meeting_room,
						["overlap_appointments", "meeting_room_capacity"],
					)
					if not allow_overlap:
						# fetch all appointments to meeting room
						filters.pop("employee")
				else:
					slot_name = schedule_entry.schedule
					# fetch all appointments to employee without meeting room
					filters["employee"] = employee
					filters.pop("meeting_room")

				appointments = frappe.get_all(
					"Customer Appointment",
					filters=filters,
					fields=["name", "appointment_time", "duration", "status"],
				)

				slot_details.append(
					{
						"slot_name": slot_name,
						"meeting_room": schedule_entry.meeting_room,
						"avail_slot": available_slots,
						"appointments": appointments,
						"allow_overlap": allow_overlap,
						"meeting_room_capacity": meeting_room_capacity,
						"tele_conf": lawyer_schedule.allow_video_conferencing,
					}
				)

	return slot_details


def validate_employee_schedules(schedule_entry, employee):
	if schedule_entry.schedule:
		if not schedule_entry.meeting_room:
			frappe.throw(
				_(
					"Employee {0} does not have a Meeting Room set against the Lawyer Schedule {1}."
				).format(
					get_link_to_form("Employee", employee),
					frappe.bold(schedule_entry.schedule),
				),
				title=_("Meeting Room Not Found"),
			)

	else:
		frappe.throw(
			_("Employee {0} does not have a Lawyer Schedule assigned.").format(
				get_link_to_form("Employee", employee)
			),
			title=_("Lawyer Schedule Not Found"),
		)


@frappe.whitelist()
def update_status(appointment_id, status):
	frappe.db.set_value("Customer Appointment", appointment_id, "status", status)
	appointment_booked = True
	if status == "Cancelled":
		appointment_booked = False
		cancel_appointment(appointment_id)


@frappe.whitelist()
def make_timesheet(source_name, target_doc=None):
	doc = get_mapped_doc(
		"Customer Appointment",
		source_name,
		{
			"Customer Appointment": {
				"doctype": "Timesheet",
				"field_map": [
					["appointment", "name"],
					["customer", "customer"],
					["employee", "employee"],
					["invoiced", "invoiced"],
					["company", "company"],
				],
			}
		},
		target_doc,
	)
	return doc


@frappe.whitelist()
def get_events(start, end, filters=None):
	"""Returns events for Gantt / Calendar view rendering.

	:param start: Start date-time.
	:param end: End date-time.
	:param filters: Filters (JSON).
	"""
	from frappe.desk.calendar import get_event_conditions

	conditions = get_event_conditions("Customer Appointment", filters)

	data = frappe.db.sql(
		"""
		select
		`tabCustomer Appointment`.name, `tabCustomer Appointment`.customer,
		`tabCustomer Appointment`.employee, `tabCustomer Appointment`.status,
		`tabCustomer Appointment`.duration,
		timestamp(`tabCustomer Appointment`.appointment_date, `tabCustomer Appointment`.appointment_time) as 'start',
		`tabAppointment Type`.color
		from
		`tabCustomer Appointment`
		left join `tabAppointment Type` on `tabCustomer Appointment`.appointment_type=`tabAppointment Type`.name
		where
		(`tabCustomer Appointment`.appointment_date between %(start)s and %(end)s)
		and `tabCustomer Appointment`.status != 'Cancelled' and `tabCustomer Appointment`.docstatus < 2 {conditions}""".format(
			conditions=conditions
		),
		{"start": start, "end": end},
		as_dict=True,
		update={"allDay": 0},
	)

	for item in data:
		item.end = item.start + datetime.timedelta(minutes=item.duration)

	return data

def update_appointment_status():
	# update the status of appointments daily
	appointments = frappe.get_all(
		"Customer Appointment", {"status": ("not in", ["Closed", "Cancelled"])}
	)

	for appointment in appointments:
		appointment_doc = frappe.get_doc("Customer Appointment", appointment.name)
		appointment_doc.set_status()
		appointment_doc.save()

