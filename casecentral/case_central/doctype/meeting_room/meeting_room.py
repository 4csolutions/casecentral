# Copyright (c) 2023, 4C Solutions and contributors
# For license information, please see license.txt

import json

import frappe
from frappe import _
from frappe.contacts.address_and_contact import load_address_and_contact
from frappe.utils import cint, cstr
from frappe.model.document import Document


class MeetingRoom(Document):

	def onload(self):
		"""Load address and contacts in `__onload`"""
		load_address_and_contact(self)

	def autoname(self):
		if self.company:
			suffix = " - " + frappe.get_cached_value("Company", self.company, "abbr")
			if not self.meeting_room.endswith(suffix):
				self.name = self.meeting_room + suffix
		else:
			self.name = self.meeting_room


		if self.overlap_appointments:
			if not self.meeting_room_capacity:
				frappe.throw(
					_("Please set a valid Meeting Room Capacity to enable Overlapping Appointments"),
					title=_("Mandatory"),
				)


@frappe.whitelist()
def add_multiple_meeting_rooms(data):
	"""
	data (dict) - company, meeting_room, count, meeting_room_capacity
	"""
	if not data:
		return

	data = json.loads(data)
	company = (
		data.get("company")
		or frappe.defaults.get_defaults().get("company")
		or frappe.db.get_single_value("Global Defaults", "default_company")
	)

	if not data.get("meeting_room") or not company:
		frappe.throw(
			_("Meeting Room Name and Company are mandatory to create Meeting Rooms"),
			title=_("Missing Required Fields"),
		)

	count = cint(data.get("count") or 0)
	if count <= 0:
		frappe.throw(
			_("Number of Meeting Rooms to be created should at least be 1"),
			title=_("Invalid Number of Meeting Rooms"),
		)

	capacity = cint(data.get("meeting_room_capacity") or 1)

	meeting_room = {
		"doctype": "Meeting Room",
		"meeting_room_capacity": capacity if capacity > 0 else 1,
		"company": company,
	}

	M = "{}".format(data.get("meeting_room").strip(" -"))
	meeting_room_name = M

	rooms = frappe.get_all("Meeting Room", filters={"company": company, "name": ["like", f"{M}-%"]}, pluck="name")
	suffixes = []
	for r in rooms:
		parts = r[len(M)+1:].split(" ")
		if parts:
			num_part = parts[0]
			if num_part.isdigit():
				suffixes.append(int(num_part))
	last_suffix = max(suffixes) if suffixes else 0
	start_suffix = cint(last_suffix) + 1

	failed_list = []
	for i in range(start_suffix, count + start_suffix):
		
		meeting_room["meeting_room"] = "{}-{}".format(
			meeting_room_name, cstr("%0*d" % (4, i))
		)
		meeting_room_doc = frappe.get_doc(meeting_room)
		try:
			meeting_room_doc.insert()
		except Exception:
			failed_list.append(meeting_room["meeting_room"])

	return failed_list


def on_doctype_update():
	frappe.db.add_unique(
		"Meeting Room",
		["meeting_room", "company"],
		constraint_name="unique_meeting_room_company",
	)

