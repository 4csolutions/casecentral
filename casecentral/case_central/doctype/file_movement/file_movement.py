# Copyright (c) 2026, 4C Solutions and Contributors
# See license.txt

import json
import frappe
from frappe.model.document import Document


class FileMovement(Document):

    def autoname(self):
        if self.name:
            return
        self.name = frappe.model.naming.make_autoname("FM-.#####")

    def validate(self):
        self.validate_movement()
        self.validate_rows()
        self.validate_duplicate_barcodes()
        self.update_missing_files_and_status()

    def validate_movement(self):
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

        if not self.get("outgoing_files"):
            frappe.throw("Please add at least one row in the Outgoing Files table.")

    def validate_rows(self):
        for idx, row in enumerate(self.get("outgoing_files") or [], start=1):
            if row.matter:
                if not frappe.db.exists("Matter", row.matter):
                    frappe.throw(f"Matter ID '{row.matter}' in row {idx} does not exist.")
                if not row.case:
                    case_name = frappe.db.get_value("Case", {"matter": row.matter}, "name")
                    if case_name:
                        row.case = case_name

            if row.case:
                if not frappe.db.exists("Case", row.case):
                    frappe.throw(f"Case '{row.case}' in row {idx} does not exist.")
                if not row.matter:
                    case_matter = frappe.db.get_value("Case", row.case, "matter")
                    if case_matter:
                        row.matter = case_matter

            if not row.matter and not row.case and not row.barcode:
                frappe.throw(f"Row {idx} in Outgoing Files must have a Matter ID, Case, or Barcode.")

    def validate_duplicate_barcodes(self):
        # Validate uniqueness inside outgoing_files
        seen_barcodes = set()
        seen_cases = set()
        for idx, row in enumerate(self.get("outgoing_files") or [], start=1):
            barcode = (row.barcode or "").strip()
            if barcode:
                if barcode in seen_barcodes:
                    frappe.throw(f"Duplicate barcode '{barcode}' in Outgoing Files row {idx}.")
                seen_barcodes.add(barcode)

            case_name = (row.case or "").strip()
            if case_name:
                if case_name in seen_cases:
                    frappe.throw(f"Duplicate Case '{case_name}' in Outgoing Files row {idx}.")
                seen_cases.add(case_name)

        # Validate uniqueness inside incoming_files
        seen_inc_barcodes = set()
        seen_inc_cases = set()
        for idx, row in enumerate(self.get("incoming_files") or [], start=1):
            barcode = (row.barcode or "").strip()
            if barcode:
                if barcode in seen_inc_barcodes:
                    frappe.throw(f"Duplicate barcode '{barcode}' in Incoming Files row {idx}.")
                seen_inc_barcodes.add(barcode)

            case_name = (row.case or "").strip()
            if case_name:
                if case_name in seen_inc_cases:
                    frappe.throw(f"Duplicate Case '{case_name}' in Incoming Files row {idx}.")
                seen_inc_cases.add(case_name)

    def update_missing_files_and_status(self):
        if not self.has_incoming and not self.get("incoming_files"):
            self.status = "Open"
            self.set("missing_file_items", [])
            return

        missing = calculate_missing_files_from_doc(self)
        self.set_missing_file_table(missing)
        self.status = "Received" if len(missing) == 0 else "Missing Files"

    def set_missing_file_table(self, missing):
        self.set("missing_file_items", [])
        for item in missing:
            row = self.append("missing_file_items", {})
            row.barcode = item.get("barcode") or ""
            row.matter = item.get("matter") or ""
            row.case = item.get("case") or ""

    def on_submit(self):
        self.status = "Open"
        self.db_set("status", "Open")
        self.update_outgoing_linked_statuses()

    def on_cancel(self):
        self.restore_outgoing_linked_statuses()

    def update_outgoing_linked_statuses(self):
        matters = set()
        for row in self.get("outgoing_files") or []:
            if row.matter:
                matters.add(row.matter)
        for matter_name in matters:
            recalculate_matter_status_from_movements(matter_name)

    def restore_outgoing_linked_statuses(self):
        matters = set()
        for row in self.get("outgoing_files") or []:
            if row.matter:
                matters.add(row.matter)
        for matter_name in matters:
            recalculate_matter_status_from_movements(matter_name)


def recalculate_matter_status_from_movements(matter_name):
    """
    Checks whether all cases and files for a Matter have been returned.
    If there are active unreturned movements (docstatus=1, status!='Received'),
    Matter status is set to 'Working'. Once all files are returned, status is 'Open'.
    """
    if not matter_name or not frappe.db.exists("Matter", matter_name):
        return

    # Find unreturned movements containing this matter in outgoing_files
    unreturned = frappe.db.sql("""
        SELECT bfi.name, bfi.`case`, bfi.barcode, fm.name as movement_name
        FROM `tabBarcode File Item` bfi
        INNER JOIN `tabFile Movement` fm ON fm.name = bfi.parent
        WHERE fm.docstatus = 1 
          AND fm.status != 'Received'
          AND bfi.parentfield = 'outgoing_files'
          AND bfi.matter = %s
    """, (matter_name,), as_dict=True)

    if not unreturned:
        frappe.db.set_value("Matter", matter_name, "status", "Open")
        return

    has_unreturned = False
    for out_row in unreturned:
        # Check if this outgoing item has been added into incoming_files of this movement
        inc = frappe.db.sql("""
            SELECT name FROM `tabBarcode File Item`
            WHERE parent = %s 
              AND parentfield = 'incoming_files'
              AND (
                  (`case` = %s AND %s != '') OR 
                  (barcode = %s AND %s != '') OR 
                  (matter = %s)
              )
        """, (out_row.movement_name, out_row.get("case") or "", out_row.get("case") or "", out_row.get("barcode") or "", out_row.get("barcode") or "", matter_name))

        if not inc:
            has_unreturned = True
            break

    if has_unreturned:
        frappe.db.set_value("Matter", matter_name, "status", "Working")
    else:
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
# SINGLE DOCUMENT INCOMING & RETURN WORKFLOW
# =========================================================

def is_item_returned(out_row, incoming_rows):
    """
    Checks if an item from outgoing_files is present in incoming_rows.
    """
    out_case = (out_row.get("case") or "").strip()
    out_barcode = (out_row.get("barcode") or "").strip()
    out_matter = (out_row.get("matter") or "").strip()

    for inc_row in incoming_rows:
        inc_case = (inc_row.get("case") or "").strip()
        inc_barcode = (inc_row.get("barcode") or "").strip()
        inc_matter = (inc_row.get("matter") or "").strip()

        # 1. Match by case if both have case
        if out_case and inc_case and out_case == inc_case:
            return True

        # 2. Match by barcode if both have barcode
        if out_barcode and inc_barcode and out_barcode == inc_barcode:
            return True

        # 3. Match by matter
        if out_matter and inc_matter and out_matter == inc_matter:
            if not out_case and not inc_case:
                return True
            if out_case and inc_case and out_case == inc_case:
                return True

    return False


def calculate_missing_files_from_doc(doc):
    """
    Compares doc.outgoing_files against doc.incoming_files.
    Any outgoing item not present in incoming_files is missing.
    """
    outgoing = doc.get("outgoing_files") or []
    incoming = doc.get("incoming_files") or []

    missing = []
    for out_row in outgoing:
        if not is_item_returned(out_row, incoming):
            missing.append({
                "barcode": out_row.barcode or "",
                "matter": out_row.matter or "",
                "case": out_row.case or ""
            })
    return missing


@frappe.whitelist()
def create_incoming(movement_name):
    """
    Activates incoming workflow on the SAME File Movement document:
    - Sets has_incoming = 1
    - Initializes incoming_date
    - Computes missing files (all outgoing items not in incoming_files)
    - Updates status and persists missing_file_items
    """
    movement_name = str(movement_name or "").strip()
    if not movement_name or not frappe.db.exists("File Movement", movement_name):
        frappe.throw("File Movement not found.")

    doc = frappe.get_doc("File Movement", movement_name)

    if doc.docstatus != 1:
        frappe.throw("File Movement must be submitted before creating incoming.")

    doc.has_incoming = 1
    if not doc.incoming_date:
        doc.incoming_date = frappe.utils.now_datetime()

    missing = calculate_missing_files_from_doc(doc)
    doc.set_missing_file_table(missing)
    doc.status = "Missing Files" if missing else "Received"

    frappe.db.set_value("File Movement", doc.name, {
        "has_incoming": 1,
        "incoming_date": doc.incoming_date,
        "status": doc.status
    })

    frappe.db.delete("Missing File Items", {"parent": doc.name})
    for row in doc.missing_file_items:
        row.parent = doc.name
        row.parenttype = "File Movement"
        row.parentfield = "missing_file_items"
        row.db_insert()

    return {
        "name": doc.name,
        "has_incoming": 1,
        "status": doc.status,
        "missing_count": len(missing)
    }


@frappe.whitelist()
def scan_incoming_file(movement_name, value):
    """
    Scans a barcode, Case ID, or Matter ID into incoming_files for this movement:
    - Verifies the item belongs to outgoing_files
    - Appends to incoming_files
    - Recalculates missing files and status (Received / Missing Files)
    - Updates DB and Matter status in real time
    """
    movement_name = str(movement_name or "").strip()
    value = str(value or "").strip()

    if not movement_name or not frappe.db.exists("File Movement", movement_name):
        frappe.throw("File Movement not found.")

    if not value:
        frappe.throw("Barcode or ID is required.")

    doc = frappe.get_doc("File Movement", movement_name)
    if doc.docstatus != 1:
        frappe.throw("Movement must be submitted before receiving files.")

    outgoing = doc.get("outgoing_files") or []
    items_to_add = []

    # 1. Check direct matches in outgoing_files by barcode, case, or matter
    direct_bc = [r for r in outgoing if (r.barcode or "").strip() == value]
    direct_case = [r for r in outgoing if (r.case or "").strip() == value]
    direct_matter = [r for r in outgoing if (r.matter or "").strip() == value]

    if direct_bc:
        for r in direct_bc:
            items_to_add.append({
                "matter": r.matter or "",
                "case": r.case or "",
                "barcode": r.barcode or value
            })
    elif direct_case:
        for r in direct_case:
            items_to_add.append({
                "matter": r.matter or "",
                "case": r.case,
                "barcode": r.barcode or ""
            })
    elif direct_matter:
        for r in direct_matter:
            items_to_add.append({
                "matter": r.matter,
                "case": r.case or "",
                "barcode": r.barcode or ""
            })
    else:
        # 2. Fallback to global resolver
        info = get_scan_information(value)
        if not info or info.get("type") == "not_found":
            return {
                "status": "error",
                "message": f"Scanned value '<b>{value}</b>' does not match any existing Matter, Case, or Barcode."
            }

        if info["type"] == "matter":
            matter_val = info["matter"]
            matching_out = [r for r in outgoing if r.matter == matter_val]
            if not matching_out:
                return {
                    "status": "error",
                    "message": f"Matter '<b>{matter_val}</b>' is not part of Outgoing Files in this movement."
                }
            for out_r in matching_out:
                items_to_add.append({
                    "matter": out_r.matter,
                    "case": out_r.case or "",
                    "barcode": out_r.barcode or ""
                })

        elif info["type"] == "case":
            case_val = info["case_name"]
            matching_out = [r for r in outgoing if r.case == case_val]
            if not matching_out:
                return {
                    "status": "error",
                    "message": f"Case '<b>{case_val}</b>' is not part of Outgoing Files in this movement."
                }
            items_to_add.append({
                "matter": matching_out[0].matter,
                "case": case_val,
                "barcode": matching_out[0].barcode or info.get("barcode") or ""
            })

        elif info["type"] == "case_file":
            barcode_val = info["barcode"]
            matching_out = [r for r in outgoing if r.barcode == barcode_val]
            if not matching_out:
                return {
                    "status": "error",
                    "message": f"Barcode '<b>{barcode_val}</b>' is not part of Outgoing Files in this movement."
                }
            items_to_add.append({
                "matter": matching_out[0].matter,
                "case": matching_out[0].case or "",
                "barcode": barcode_val
            })

    # Filter out items already in incoming_files
    incoming = doc.get("incoming_files") or []
    new_items = []
    already_scanned = 0

    for item in items_to_add:
        if is_item_returned(item, incoming):
            already_scanned += 1
        else:
            new_items.append(item)

    if not new_items:
        return {
            "status": "warning",
            "message": f"All matching items for '<b>{value}</b>' are already scanned in Incoming Files."
        }

    # Insert new items into incoming_files
    for item in new_items:
        new_row = doc.append("incoming_files", item)
        new_row.parent = doc.name
        new_row.parenttype = "File Movement"
        new_row.parentfield = "incoming_files"
        new_row.db_insert()

    # Recalculate remaining missing
    remaining_missing = calculate_missing_files_from_doc(doc)
    doc.set_missing_file_table(remaining_missing)
    doc.status = "Received" if len(remaining_missing) == 0 else "Missing Files"
    doc.has_incoming = 1
    if not doc.incoming_date:
        doc.incoming_date = frappe.utils.now_datetime()

    frappe.db.set_value("File Movement", doc.name, {
        "status": doc.status,
        "has_incoming": 1,
        "incoming_date": doc.incoming_date
    })

    # Update missing file items in DB
    frappe.db.delete("Missing File Items", {"parent": doc.name})
    for row in doc.missing_file_items:
        row.parent = doc.name
        row.parenttype = "File Movement"
        row.parentfield = "missing_file_items"
        row.db_insert()

    # Update matter statuses
    doc.update_outgoing_linked_statuses()

    return {
        "status": "success",
        "movement_status": doc.status,
        "added_count": len(new_items),
        "missing_count": len(remaining_missing),
        "message": f"Scanned & received {len(new_items)} file(s). Status: <b>{doc.status}</b>."
    }


@frappe.whitelist()
def get_missing_files(movement_name):
    movement_name = str(movement_name or "").strip()
    if not movement_name:
        return []

    doc = frappe.get_doc("File Movement", movement_name)
    return calculate_missing_files_from_doc(doc)


@frappe.whitelist()
def return_missing_files(
    movement_name,
    files=None,
    selected_barcodes=None,
    selected_matters=None,
    selected_cases=None
):
    """
    Returns missing files directly into incoming_files of this single document.
    """
    movement_name = str(movement_name or "").strip()
    if not movement_name:
        frappe.throw("Movement name is required.")

    doc = frappe.get_doc("File Movement", movement_name)
    if doc.docstatus != 1:
        frappe.throw("Movement must be submitted first.")

    items_to_return = []
    if isinstance(files, str):
        try:
            files = json.loads(files)
        except Exception:
            files = [files]
    if isinstance(files, list):
        for f in files:
            if isinstance(f, dict):
                items_to_return.append(f)
            elif str(f).strip():
                items_to_return.append({"case": str(f).strip()})

    for b in selected_barcodes or []:
        if str(b).strip():
            items_to_return.append({"barcode": str(b).strip()})
    for m in selected_matters or []:
        if str(m).strip():
            items_to_return.append({"matter": str(m).strip()})
    for c in selected_cases or []:
        if str(c).strip():
            items_to_return.append({"case": str(c).strip()})

    if not items_to_return:
        frappe.throw("Please select or scan at least one file to return.")

    incoming = doc.get("incoming_files") or []
    outgoing = doc.get("outgoing_files") or []
    added_count = 0

    for item in items_to_return:
        t_case = item.get("case") or ""
        t_barcode = item.get("barcode") or ""
        t_matter = item.get("matter") or ""

        # Match against outgoing files to get full record
        matched_out = None
        for out_r in outgoing:
            if (t_case and out_r.case == t_case) or \
               (t_barcode and out_r.barcode == t_barcode) or \
               (t_matter and out_r.matter == t_matter and not t_case and not out_r.case):
                matched_out = out_r
                break

        if matched_out:
            if not is_item_returned(matched_out, incoming):
                new_row = doc.append("incoming_files", {
                    "barcode": matched_out.barcode or "",
                    "matter": matched_out.matter or "",
                    "case": matched_out.case or ""
                })
                new_row.parent = doc.name
                new_row.parenttype = "File Movement"
                new_row.parentfield = "incoming_files"
                new_row.db_insert()
                added_count += 1
        else:
            # Direct insert if not strictly matched
            if not t_matter and t_case:
                t_matter = frappe.db.get_value("Case", t_case, "matter") or ""
            if not t_case and t_barcode:
                t_case = find_case_by_barcode(t_barcode) or ""
                if t_case and not t_matter:
                    t_matter = frappe.db.get_value("Case", t_case, "matter") or ""

            entry = {"barcode": t_barcode, "matter": t_matter, "case": t_case}
            if not is_item_returned(entry, incoming):
                new_row = doc.append("incoming_files", entry)
                new_row.parent = doc.name
                new_row.parenttype = "File Movement"
                new_row.parentfield = "incoming_files"
                new_row.db_insert()
                added_count += 1

    remaining_missing = calculate_missing_files_from_doc(doc)
    doc.set_missing_file_table(remaining_missing)
    doc.status = "Received" if len(remaining_missing) == 0 else "Missing Files"
    doc.has_incoming = 1

    frappe.db.set_value("File Movement", doc.name, {
        "status": doc.status,
        "has_incoming": 1
    })

    frappe.db.delete("Missing File Items", {"parent": doc.name})
    for row in doc.missing_file_items:
        row.parent = doc.name
        row.parenttype = "File Movement"
        row.parentfield = "missing_file_items"
        row.db_insert()

    doc.update_outgoing_linked_statuses()

    return {
        "status": doc.status,
        "missing": remaining_missing,
        "remaining_barcodes": [item["barcode"] for item in remaining_missing if item.get("barcode")],
        "remaining_matters": [item["matter"] for item in remaining_missing if item.get("matter")],
        "remaining_cases": [item["case"] for item in remaining_missing if item.get("case")]
    }