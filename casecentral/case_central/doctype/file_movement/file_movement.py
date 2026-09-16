# Copyright (c) 2026, 4C Solutions and Contributors
# See license.txt

import json
import frappe
from frappe.model.document import Document


class FileMovement(Document):

    def autoname(self):
        if self.name:
            return

        if self.movement_type == "Outgoing":
            self.name = frappe.model.naming.make_autoname("FMO-.#####")
        elif self.movement_type == "Incoming":
            outgoing_name = (self.original_outgoing_movement or self.get("outgoing_movement") or "").strip()
            if outgoing_name:
                if outgoing_name.startswith("FMO-"):
                    candidate = "FMI-" + outgoing_name[4:]
                elif outgoing_name.startswith("FM-"):
                    candidate = "FMI-" + outgoing_name[3:]
                else:
                    candidate = "FMI-" + outgoing_name

                if frappe.db.exists("File Movement", candidate):
                    idx = 1
                    while frappe.db.exists("File Movement", f"{candidate}-{idx}"):
                        idx += 1
                    self.name = f"{candidate}-{idx}"
                else:
                    self.name = candidate
            else:
                self.name = frappe.model.naming.make_autoname("FMI-.#####")
        else:
            self.name = frappe.model.naming.make_autoname("FMO-.#####")

    def validate(self):
        self.validate_movement()
        self.validate_rows()
        self.validate_duplicate_barcodes()
        self.update_missing_files_and_status()

    def validate_movement(self):
        if self.movement_type not in ["Outgoing", "Incoming"]:
            frappe.throw("Movement Type must be Outgoing or Incoming.")

        if not self.giver:
            frappe.throw("Giver is required.")

        if not self.receiver:
            frappe.throw("Receiver is required.")

        if self.giver == self.receiver:
            frappe.throw("Giver and Receiver cannot be the same employee.")

        if not frappe.db.exists("Employee", self.giver):
            frappe.throw(f"Giver employee '{self.giver}' does not exist.")

        if not frappe.db.exists("Employee", self.receiver):
            frappe.throw(f"Receiver employee '{self.receiver}' does not exist.")

        if not self.get("barcode_files"):
            frappe.throw("Please add at least one row in the Matter Files table.")

    def validate_rows(self):
        for idx, row in enumerate(self.get("barcode_files") or [], start=1):
            # If matter is provided, verify it exists
            if row.matter:
                if not frappe.db.exists("Matter", row.matter):
                    frappe.throw(f"Matter ID '{row.matter}' in row {idx} does not exist.")

                # Auto-populate case if not set and case exists
                if not row.case:
                    case_name = frappe.db.get_value("Case", {"matter": row.matter}, "name")
                    if case_name:
                        row.case = case_name

            # If case is provided, verify it exists
            if row.case:
                if not frappe.db.exists("Case", row.case):
                    frappe.throw(f"Case '{row.case}' in row {idx} does not exist.")

                # Auto-populate matter if not set
                if not row.matter:
                    case_matter = frappe.db.get_value("Case", row.case, "matter")
                    if case_matter:
                        row.matter = case_matter

            # If neither matter nor case nor barcode is provided
            if not row.matter and not row.case and not row.barcode:
                frappe.throw(f"Row {idx} in Matter Files must have a Matter ID, Case, or Barcode.")

    def validate_duplicate_barcodes(self):
        seen_barcodes = set()
        seen_cases = set()
        for idx, row in enumerate(self.get("barcode_files") or [], start=1):
            barcode = (row.barcode or "").strip()
            if barcode:
                if barcode in seen_barcodes:
                    frappe.throw(f"Duplicate barcode '{barcode}' in row {idx}.")
                seen_barcodes.add(barcode)

            case_name = (row.case or "").strip()
            if case_name:
                if case_name in seen_cases:
                    frappe.throw(f"Duplicate Case '{case_name}' in row {idx}.")
                seen_cases.add(case_name)

    def update_missing_files_and_status(self):
        if self.movement_type == "Outgoing":
            if not self.status:
                self.status = "Open"
            self.set("missing_file_items", [])
            return

        missing = calculate_missing_files_from_doc(self)
        self.set_missing_file_table(missing)

        if self.docstatus == 1:
            self.status = "Missing Files" if missing else "Received"
        else:
            if not self.status:
                self.status = "Open"
            elif self.status != "Open":
                self.status = "Missing Files" if missing else "Received"

    def set_missing_file_table(self, missing):
        self.set("missing_file_items", [])
        for item in missing:
            row = self.append("missing_file_items", {})
            row.barcode = item.get("barcode") or ""
            row.matter = item.get("matter") or ""
            row.case = item.get("case") or ""
            row.returned = 0

    def on_submit(self):
        if self.movement_type == "Outgoing":
            self.update_outgoing_linked_statuses()
        elif self.movement_type == "Incoming":
            missing = calculate_missing_files_from_doc(self)
            self.set_missing_file_table(missing)
            self.status = "Missing Files" if missing else "Received"
            self.update_incoming_linked_statuses()

    def on_cancel(self):
        if self.movement_type == "Outgoing":
            self.restore_outgoing_linked_statuses()

    def update_outgoing_linked_statuses(self):
        matters = set()
        for row in self.get("barcode_files") or []:
            if row.matter:
                matters.add(row.matter)
        for matter_name in matters:
            if frappe.db.exists("Matter", matter_name):
                frappe.db.set_value("Matter", matter_name, "status", "Working")

    def update_incoming_linked_statuses(self):
        for row in self.get("barcode_files") or []:
            if row.matter and row.returned:
                if frappe.db.exists("Matter", row.matter):
                    frappe.db.set_value("Matter", row.matter, "status", "Open")

    def restore_outgoing_linked_statuses(self):
        matters = set()
        for row in self.get("barcode_files") or []:
            if row.matter:
                matters.add(row.matter)
        for matter_name in matters:
            if frappe.db.exists("Matter", matter_name):
                frappe.db.set_value("Matter", matter_name, "status", "Open")


# =========================================================
# SCAN & QUERY APIS
# =========================================================

@frappe.whitelist()
def get_scan_information(value):
    value = str(value or "").strip()
    if not value:
        return None

    # 1. Check if exact Matter ID
    if frappe.db.exists("Matter", value):
        return {
            "type": "matter",
            "matter": value,
            "cases": get_cases_for_matter(value)
        }

    # 2. Check if exact Case Name
    if frappe.db.exists("Case", value):
        case_doc = frappe.get_doc("Case", value)
        return {
            "type": "case",
            "case_name": case_doc.name,
            "matter": case_doc.get("matter") or "",
            "barcode": get_case_barcode(case_doc)
        }

    # 3. Check if Case Barcode
    case_name = find_case_by_barcode(value)
    if case_name:
        case_doc = frappe.get_doc("Case", case_name)
        return {
            "type": "case",
            "case_name": case_doc.name,
            "matter": case_doc.get("matter") or "",
            "barcode": value
        }

    # 4. Check if Case_Files record
    if frappe.db.exists("Case_Files", value) or frappe.db.exists("Case_Files", {"case_number": value}):
        cf_name = value if frappe.db.exists("Case_Files", value) else frappe.db.get_value("Case_Files", {"case_number": value}, "name")
        return {
            "type": "case_file",
            "case_file": cf_name,
            "barcode": value,
            "matter": "",
            "case": ""
        }

    # If it does not match anything in the system
    return {
        "type": "not_found",
        "value": value,
        "message": f"Scanned value '{value}' does not match any existing Matter ID, Case, or Barcode."
    }


@frappe.whitelist()
def get_cases_for_matter(matter):
    matter = str(matter or "").strip()
    if not matter:
        return []

    if not frappe.db.exists("Matter", matter):
        frappe.throw(f"Matter ID '{matter}' does not exist.")

    cases = frappe.get_all(
        "Case",
        filters={"matter": matter},
        fields=["name", "matter"],
        order_by="name asc"
    )

    result = []
    for c in cases:
        case_doc = frappe.get_doc("Case", c.name)
        result.append({
            "name": c.name,
            "matter": c.matter or matter,
            "barcode": get_case_barcode(case_doc)
        })

    return result


def get_case_barcode(case_doc):
    meta = frappe.get_meta("Case")
    for fieldname in ["barcode", "case_barcode", "file_barcode"]:
        if meta.has_field(fieldname):
            val = case_doc.get(fieldname)
            if val:
                return str(val).strip()
    return case_doc.name


def find_case_by_barcode(barcode):
    barcode = str(barcode or "").strip()
    if not barcode:
        return None

    meta = frappe.get_meta("Case")
    for fieldname in ["barcode", "case_barcode", "file_barcode"]:
        if meta.has_field(fieldname):
            case_name = frappe.db.get_value("Case", {fieldname: barcode}, "name")
            if case_name:
                return case_name
    return None


# =========================================================
# INCOMING & MISSING FILES WORKFLOW
# =========================================================

@frappe.whitelist()
def create_incoming(outgoing_name):
    outgoing_name = str(outgoing_name or "").strip()
    if not outgoing_name:
        frappe.throw("Outgoing movement is required.")

    outgoing = frappe.get_doc("File Movement", outgoing_name)

    if outgoing.docstatus != 1:
        frappe.throw("Outgoing movement must be submitted first.")

    if outgoing.movement_type != "Outgoing":
        frappe.throw("The selected movement is not Outgoing.")

    incoming = frappe.new_doc("File Movement")
    incoming.movement_type = "Incoming"
    incoming.status = "Open"
    incoming.giver = outgoing.receiver
    incoming.receiver = outgoing.giver
    incoming.original_outgoing_movement = outgoing.name

    # Copy Matter Files
    incoming.set("barcode_files", [])
    for row in outgoing.barcode_files or []:
        incoming.append("barcode_files", {
            "barcode": row.barcode or "",
            "matter": row.matter or "",
            "case": row.case or "",
            "returned": 0
        })

    # Initially all copied files are missing
    missing = calculate_missing_files_from_doc(incoming)
    incoming.set_missing_file_table(missing)

    incoming.insert(ignore_permissions=True)
    return incoming.name


def calculate_missing_files_from_doc(doc):
    missing = []
    for row in doc.get("barcode_files") or []:
        if not row.returned:
            missing.append({
                "barcode": row.barcode or "",
                "matter": row.matter or "",
                "case": row.case or ""
            })
    return missing


@frappe.whitelist()
def get_missing_files(movement_name):
    movement_name = str(movement_name or "").strip()
    if not movement_name:
        return []

    doc = frappe.get_doc("File Movement", movement_name)
    if doc.movement_type != "Incoming":
        frappe.throw("Only Incoming movements can have missing files.")

    return calculate_missing_files_from_doc(doc)


@frappe.whitelist()
def return_missing_files(
    movement_name,
    files=None,
    selected_barcodes=None,
    selected_matters=None,
    selected_cases=None
):
    movement_name = str(movement_name or "").strip()
    if not movement_name:
        frappe.throw("Movement name is required.")

    doc = frappe.get_doc("File Movement", movement_name)
    if doc.movement_type != "Incoming":
        frappe.throw("Only Incoming movements can return missing files.")

    items_to_return = set()

    # Parse files arg if passed as json or list
    if isinstance(files, str):
        try:
            files = json.loads(files)
        except Exception:
            files = [files]
    if isinstance(files, list):
        for f in files:
            if isinstance(f, dict):
                if f.get("barcode"):
                    items_to_return.add(str(f["barcode"]).strip())
                if f.get("case"):
                    items_to_return.add(str(f["case"]).strip())
                if f.get("matter"):
                    items_to_return.add(str(f["matter"]).strip())
            elif str(f).strip():
                items_to_return.add(str(f).strip())

    for b in selected_barcodes or []:
        if str(b).strip():
            items_to_return.add(str(b).strip())
    for m in selected_matters or []:
        if str(m).strip():
            items_to_return.add(str(m).strip())
    for c in selected_cases or []:
        if str(c).strip():
            items_to_return.add(str(c).strip())

    if not items_to_return:
        frappe.throw("Please select at least one file or matter to return.")

    # Mark returned in barcode_files (Matter Files table)
    for row in doc.barcode_files or []:
        if (row.barcode and row.barcode in items_to_return) or \
           (row.case and row.case in items_to_return) or \
           (row.matter and row.matter in items_to_return):
            row.returned = 1
            frappe.db.set_value("Barcode File Item", row.name, "returned", 1)

    # Recalculate remaining missing
    remaining_missing = calculate_missing_files_from_doc(doc)
    doc.set_missing_file_table(remaining_missing)

    doc.status = "Missing Files" if remaining_missing else "Received"
    frappe.db.set_value("File Movement", doc.name, "status", doc.status)

    # Update missing table in DB
    frappe.db.delete("Missing File Items", {"parent": doc.name})
    for row in doc.missing_file_items:
        row.parent = doc.name
        row.parenttype = "File Movement"
        row.parentfield = "missing_file_items"
        row.db_insert()

    # Update matter status
    doc.update_incoming_linked_statuses()

    return {
        "status": doc.status,
        "missing": remaining_missing,
        "remaining_barcodes": [item["barcode"] for item in remaining_missing if item.get("barcode")],
        "remaining_matters": [item["matter"] for item in remaining_missing if item.get("matter")],
        "remaining_cases": [item["case"] for item in remaining_missing if item.get("case")]
    }