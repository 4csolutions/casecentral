# Copyright (c) 2026, 4C Solutions and Contributors
# See license.txt

import json
import frappe
from frappe.model.document import Document


def ensure_status_options():
    try:
        current_options = frappe.db.get_value("DocField", {"parent": "File Movement", "fieldname": "status"}, "options") or ""
        needed = ["Taken Away / Incoming Created", "Incoming Created"]
        opts = [opt.strip() for opt in current_options.split("\n") if opt.strip()]
        changed = False
        for n in needed:
            if n not in opts:
                opts.append(n)
                changed = True
        if changed:
            new_options = "\n".join(opts)
            frappe.db.set_value("DocField", {"parent": "File Movement", "fieldname": "status"}, "options", new_options)
            frappe.clear_cache(doctype="File Movement")
    except Exception:
        pass


def publish_movement_realtime(movement_name):
    try:
        frappe.publish_realtime(
            "doc_update",
            {"doctype": "File Movement", "name": movement_name},
            doctype="File Movement",
            docname=movement_name,
            after_commit=True
        )
        frappe.publish_realtime(
            "list_update",
            {"doctype": "File Movement", "name": movement_name},
            after_commit=True
        )
        frappe.publish_realtime(
            "file_movement_updated",
            {"doctype": "File Movement", "name": movement_name},
            after_commit=True
        )
    except Exception:
        pass


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

    def before_update_after_submit(self):
        self.validate_duplicate_barcodes()
        self.update_missing_files_and_status()

    def on_update_after_submit(self):
        self.update_outgoing_linked_statuses()
        publish_movement_realtime(self.name)

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

        # Filter out completely blank rows in outgoing_files if any
        if self.get("outgoing_files"):
            self.set("outgoing_files", [
                r for r in self.outgoing_files
                if ((r.get("matter") or "").strip() or (r.get("case") or "").strip() or (r.get("barcode") or "").strip())
            ])

        if not self.get("outgoing_files"):
            frappe.throw("Please add at least one row in the Outgoing Files table.")

    def validate_rows(self):
        for idx, row in enumerate(self.get("outgoing_files") or [], start=1):
            row_matter = row.get("matter")
            row_case = row.get("case")
            row_barcode = row.get("barcode")

            if row_matter:
                if not frappe.db.exists("Matter", row_matter):
                    frappe.throw(f"Matter ID '{row_matter}' in row {idx} does not exist.")
                if not row_case:
                    case_name = frappe.db.get_value("Case", {"matter": row_matter}, "name")
                    if case_name:
                        row.case = case_name
                        row_case = case_name

            if row_case:
                if not frappe.db.exists("Case", row_case):
                    frappe.throw(f"Case '{row_case}' in row {idx} does not exist.")
                if not row_matter:
                    case_matter = frappe.db.get_value("Case", row_case, "matter")
                    if case_matter:
                        row.matter = case_matter
                        row_matter = case_matter

            if not row_matter and not row_case and not row_barcode:
                frappe.throw(f"Row {idx} in Outgoing Files must have a Matter ID, Case, or Barcode.")

            # Validate that the file is not currently taken away in another active movement
            if self.docstatus == 0 or self.is_new():
                taken_away_info = get_taken_away_info(
                    case=row_case,
                    barcode=row_barcode,
                    matter=row_matter if (not row_case and not row_barcode) else None,
                    current_docname=self.name
                )
                if taken_away_info:
                    m_name = taken_away_info.get("movement")
                    target = row_case or row_barcode or row_matter
                    frappe.throw(
                        f"Row {idx}: '{target}' has already been taken away in File Movement '{m_name}' and has not been returned."
                    )

    def validate_duplicate_barcodes(self):
        # Validate uniqueness inside outgoing_files
        seen_barcodes = set()
        seen_cases = set()
        for idx, row in enumerate(self.get("outgoing_files") or [], start=1):
            barcode = (row.get("barcode") or "").strip().lower()
            if barcode:
                if barcode in seen_barcodes:
                    frappe.throw(f"Duplicate barcode '{row.get('barcode')}' in Outgoing Files row {idx}.")
                seen_barcodes.add(barcode)

            case_name = (row.get("case") or "").strip().lower()
            if case_name:
                if case_name in seen_cases:
                    frappe.throw(f"Duplicate Case '{row.get('case')}' in Outgoing Files row {idx}.")
                seen_cases.add(case_name)

        # Validate uniqueness inside incoming_files
        seen_inc_barcodes = set()
        seen_inc_cases = set()
        for idx, row in enumerate(self.get("incoming_files") or [], start=1):
            barcode = (row.get("barcode") or "").strip().lower()
            if barcode:
                if barcode in seen_inc_barcodes:
                    frappe.throw(f"Duplicate barcode '{row.get('barcode')}' in Incoming Files row {idx}.")
                seen_inc_barcodes.add(barcode)

            case_name = (row.get("case") or "").strip().lower()
            if case_name:
                if case_name in seen_inc_cases:
                    frappe.throw(f"Duplicate Case '{row.get('case')}' in Incoming Files row {idx}.")
                seen_inc_cases.add(case_name)

    def update_missing_files_and_status(self):
        if self.status in ["Cancelled"]:
            return

        ensure_status_options()

        if self.status in ["Taken Away/Incoming Created", "taken away/incoming created"]:
            self.status = "Taken Away / Incoming Created"

        if not self.get("incoming_files"):
            if self.docstatus == 1:
                self.status = "Taken Away / Incoming Created" if self.has_incoming else "Taken Away"
            else:
                self.status = "Draft"
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
        self.status = "Taken Away"
        self.db_set("status", "Taken Away")
        self.update_outgoing_linked_statuses()
        publish_movement_realtime(self.name)

    def on_cancel(self):
        self.status = "Cancelled"
        self.db_set("status", "Cancelled")
        self.restore_outgoing_linked_statuses()
        publish_movement_realtime(self.name)

    def on_trash(self):
        if self.docstatus == 1:
            frappe.throw("Cannot delete submitted File Movement. Please cancel it first.")
        self.restore_outgoing_linked_statuses()

    def update_outgoing_linked_statuses(self):
        matters = set()
        for row in self.get("outgoing_files") or []:
            matter = row.get("matter")
            if matter:
                matters.add(matter)
        for matter_name in matters:
            recalculate_matter_status_from_movements(matter_name)

    def restore_outgoing_linked_statuses(self):
        matters = set()
        for row in self.get("outgoing_files") or []:
            matter = row.get("matter")
            if matter:
                matters.add(matter)
        for matter_name in matters:
            recalculate_matter_status_from_movements(matter_name)


def recalculate_matter_status_from_movements(matter_name):
    """
    Checks whether all cases and files for a Matter have been returned.
    If there are active unreturned movements (docstatus=1, status!='Received' and status!='Cancelled'),
    Matter status is set to 'Working'. Once all files are returned, status is 'Open'.
    Uses Frappe Query Builder (frappe.qb) with batch querying to eliminate N+1 queries.
    """
    if not matter_name or not frappe.db.exists("Matter", matter_name):
        return

    bfi = frappe.qb.DocType("File Movement Item")
    fm = frappe.qb.DocType("File Movement")

    unreturned = (
        frappe.qb.from_(bfi)
        .inner_join(fm).on(fm.name == bfi.parent)
        .select(bfi.name, bfi["case"], bfi.barcode, fm.name.as_("movement_name"))
        .where(
            (fm.docstatus == 1)
            & (~fm.status.isin(["Received", "Cancelled"]))
            & (bfi.parentfield == "outgoing_files")
            & (bfi.matter == matter_name)
        )
    ).run(as_dict=True)

    if not unreturned:
        frappe.db.set_value("Matter", matter_name, "status", "Open")
        return

    movement_names = list({row.movement_name for row in unreturned if row.get("movement_name")})

    # Batch query all incoming_files items for these movements in a single frappe.qb call
    inc_bfi = frappe.qb.DocType("File Movement Item")
    incoming_items = (
        frappe.qb.from_(inc_bfi)
        .select(inc_bfi.parent, inc_bfi["case"], inc_bfi.barcode, inc_bfi.matter)
        .where(
            (inc_bfi.parent.isin(movement_names))
            & (inc_bfi.parentfield == "incoming_files")
        )
    ).run(as_dict=True)

    # In-memory matching to evaluate if any outgoing row remains unreturned
    has_unreturned = False
    for out_row in unreturned:
        m_name = out_row.movement_name
        o_case = (out_row.get("case") or "").strip()
        o_barcode = (out_row.get("barcode") or "").strip()

        matched = False
        for inc_row in incoming_items:
            if inc_row.get("parent") != m_name:
                continue
            i_case = (inc_row.get("case") or "").strip()
            i_barcode = (inc_row.get("barcode") or "").strip()
            i_matter = (inc_row.get("matter") or "").strip()

            if o_case and i_case == o_case:
                matched = True
                break
            if o_barcode and i_barcode == o_barcode:
                matched = True
                break
            if not o_case and not o_barcode and i_matter == matter_name:
                matched = True
                break

        if not matched:
            has_unreturned = True
            break

    if has_unreturned:
        frappe.db.set_value("Matter", matter_name, "status", "Working")
    else:
        frappe.db.set_value("Matter", matter_name, "status", "Open")


# =========================================================
# SCAN & QUERY APIS
# =========================================================

def get_taken_away_info(case=None, barcode=None, matter=None, current_docname=None):
    """
    Checks if a case, barcode, or matter is currently taken away in an active File Movement
    (docstatus = 1 and status not in ('Received', 'Cancelled')).
    Returns dict with movement info if unreturned, else None.
    Uses Frappe Query Builder (frappe.qb).
    """
    case = str(case or "").strip()
    barcode = str(barcode or "").strip()
    matter = str(matter or "").strip()

    if not case and not barcode and not matter:
        return None

    bfi = frappe.qb.DocType("File Movement Item")
    fm = frappe.qb.DocType("File Movement")

    conditions = (
        (fm.docstatus == 1)
        & (~fm.status.isin(["Received", "Cancelled"]))
        & (bfi.parentfield == "outgoing_files")
    )
    if current_docname:
        conditions &= (fm.name != current_docname)

    query = (
        frappe.qb.from_(bfi)
        .inner_join(fm).on(fm.name == bfi.parent)
        .select(bfi.name, bfi["case"], bfi.barcode, bfi.matter, fm.name.as_("movement_name"), fm.status)
        .where(conditions)
    )

    match_conditions = []
    if case:
        match_conditions.append(bfi["case"] == case)
    if barcode:
        match_conditions.append(bfi.barcode == barcode)
    if matter and not case and not barcode:
        match_conditions.append(bfi.matter == matter)

    if match_conditions:
        combined = match_conditions[0]
        for c in match_conditions[1:]:
            combined = combined | c
        query = query.where(combined)
    else:
        return None

    unreturned_candidates = query.run(as_dict=True)
    if not unreturned_candidates:
        return None

    movement_names = list({row.movement_name for row in unreturned_candidates})
    inc_bfi = frappe.qb.DocType("File Movement Item")
    incoming_items = (
        frappe.qb.from_(inc_bfi)
        .select(inc_bfi.parent, inc_bfi["case"], inc_bfi.barcode, inc_bfi.matter)
        .where(
            (inc_bfi.parent.isin(movement_names))
            & (inc_bfi.parentfield == "incoming_files")
        )
    ).run(as_dict=True)

    for out_row in unreturned_candidates:
        m_name = out_row.movement_name
        o_case = (out_row.get("case") or "").strip()
        o_barcode = (out_row.get("barcode") or "").strip()
        o_matter = (out_row.get("matter") or "").strip()

        is_returned = False
        for inc_row in incoming_items:
            if inc_row.get("parent") != m_name:
                continue
            i_case = (inc_row.get("case") or "").strip()
            i_barcode = (inc_row.get("barcode") or "").strip()
            i_matter = (inc_row.get("matter") or "").strip()

            if o_case and i_case and o_case == i_case:
                is_returned = True
                break
            if o_barcode and i_barcode and o_barcode == i_barcode:
                is_returned = True
                break
            if not o_case and not o_barcode and i_matter and i_matter == o_matter:
                is_returned = True
                break

        if not is_returned:
            return {
                "taken_away": True,
                "movement": m_name,
                "case": o_case,
                "barcode": o_barcode,
                "matter": o_matter,
                "message": f"File '{o_case or o_barcode or o_matter}' has already been taken away in File Movement '{m_name}' and has not been returned."
            }

    return None


@frappe.whitelist()
def check_item_taken_away(case=None, barcode=None, matter=None, current_docname=None):
    return get_taken_away_info(case=case, barcode=barcode, matter=matter, current_docname=current_docname)


@frappe.whitelist()
def get_scan_information(value):
    value = str(value or "").strip()
    if not value:
        return None

    # 1. Check if exact Matter ID
    if frappe.db.exists("Matter", value):
        cases = get_cases_for_matter(value)
        matter_taken = get_taken_away_info(matter=value)
        all_cases_taken = bool(cases and all(c.get("taken_away") for c in cases))
        taken_away = bool(matter_taken or all_cases_taken)
        first_m = matter_taken.get("movement") if matter_taken else (cases[0].get("taken_away_movement") if (all_cases_taken and cases) else "")
        return {
            "type": "matter",
            "matter": value,
            "cases": cases,
            "taken_away": taken_away,
            "taken_away_movement": first_m,
            "taken_away_info": matter_taken or (cases[0].get("taken_away_info") if (all_cases_taken and cases) else None)
        }

    # 2. Check if exact Case Name
    if frappe.db.exists("Case", value):
        case_doc = frappe.get_doc("Case", value)
        barcode = get_case_barcode(case_doc)
        taken_info = get_taken_away_info(case=case_doc.name, barcode=barcode, matter=case_doc.get("matter"))
        return {
            "type": "case",
            "case_name": case_doc.name,
            "matter": case_doc.get("matter") or "",
            "barcode": barcode,
            "taken_away": bool(taken_info),
            "taken_away_movement": taken_info.get("movement") if taken_info else "",
            "taken_away_info": taken_info
        }

    # 3. Check if Case Barcode
    case_name = find_case_by_barcode(value)
    if case_name:
        case_doc = frappe.get_doc("Case", case_name)
        taken_info = get_taken_away_info(case=case_doc.name, barcode=value, matter=case_doc.get("matter"))
        return {
            "type": "case",
            "case_name": case_doc.name,
            "matter": case_doc.get("matter") or "",
            "barcode": value,
            "taken_away": bool(taken_info),
            "taken_away_movement": taken_info.get("movement") if taken_info else "",
            "taken_away_info": taken_info
        }

    # 4. Check if raw barcode or value is taken away in any active File Movement
    taken_info = get_taken_away_info(case=value, barcode=value)
    if taken_info:
        return {
            "type": "barcode",
            "barcode": taken_info.get("barcode") or value,
            "case_name": taken_info.get("case") or "",
            "matter": taken_info.get("matter") or "",
            "taken_away": True,
            "taken_away_movement": taken_info.get("movement") or "",
            "taken_away_info": taken_info
        }

    # If it does not match anything in the system
    return {
        "type": "not_found",
        "value": value,
        "message": f"No such Matter ID or Case exists: '{value}'"
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
        fields=["name", "matter", "case_title", "status"],
        order_by="name asc"
    )

    result = []
    for c in cases:
        case_doc = frappe.get_doc("Case", c.name)
        barcode = get_case_barcode(case_doc)
        taken_info = get_taken_away_info(case=c.name, barcode=barcode, matter=c.matter or matter)
        result.append({
            "name": c.name,
            "matter": c.matter or matter,
            "case_title": c.get("case_title") or "",
            "status": c.get("status") or "",
            "barcode": barcode,
            "taken_away": bool(taken_info),
            "taken_away_movement": taken_info.get("movement") if taken_info else "",
            "taken_away_info": taken_info
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

    prev_case = frappe.db.get_value("File Movement Item", {"barcode": barcode}, "case")
    if prev_case:
        return prev_case

    return None


# =========================================================
# SINGLE DOCUMENT INCOMING & RETURN WORKFLOW
# =========================================================

def is_item_returned(out_row, incoming_rows):
    """
    Checks if an item from outgoing_files is present in incoming_rows.
    """
    out_case = (out_row.get("case") or "").strip().lower()
    out_barcode = (out_row.get("barcode") or "").strip().lower()
    out_matter = (out_row.get("matter") or "").strip().lower()

    for inc_row in incoming_rows:
        inc_case = (inc_row.get("case") or "").strip().lower()
        inc_barcode = (inc_row.get("barcode") or "").strip().lower()
        inc_matter = (inc_row.get("matter") or "").strip().lower()

        # 1. Match by case if both have case
        if out_case and inc_case and out_case == inc_case:
            return True

        # 2. Match by barcode if both have barcode
        if out_barcode and inc_barcode and out_barcode == inc_barcode:
            return True

        # 3. Cross match: case == barcode
        if out_case and inc_barcode and out_case == inc_barcode:
            return True
        if out_barcode and inc_case and out_barcode == inc_case:
            return True

        # 4. Match by matter if neither row has case or barcode
        if out_matter and inc_matter and out_matter == inc_matter:
            if not out_case and not inc_case and not out_barcode and not inc_barcode:
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
            case_title = ""
            case_status = ""
            out_case = out_row.get("case")
            if out_case:
                case_title = frappe.db.get_value("Case", out_case, "case_title") or ""
                case_status = frappe.db.get_value("Case", out_case, "status") or ""
            missing.append({
                "barcode": out_row.get("barcode") or "",
                "matter": out_row.get("matter") or "",
                "case": out_case or "",
                "case_title": case_title,
                "status": case_status
            })
    return missing


@frappe.whitelist()
def create_incoming(movement_name):
    """
    Activates incoming workflow on the SAME File Movement document:
    - Asserts write permission
    - Sets has_incoming = 1
    - Initializes incoming_date
    - Computes missing files (all outgoing items not in incoming_files)
    - Updates status and persists missing_file_items using standard Document Model save
    """
    movement_name = str(movement_name or "").strip()
    if not movement_name or not frappe.db.exists("File Movement", movement_name):
        frappe.throw("File Movement not found.")

    doc = frappe.get_doc("File Movement", movement_name)
    doc.check_permission("write")

    if doc.docstatus != 1:
        frappe.throw("File Movement must be submitted before creating incoming.")

    doc.has_incoming = 1
    if not doc.incoming_date:
        doc.incoming_date = frappe.utils.now_datetime()

    ensure_status_options()
    missing = calculate_missing_files_from_doc(doc)
    if doc.get("incoming_files"):
        doc.status = "Received" if len(missing) == 0 else "Missing Files"
        doc.set_missing_file_table(missing)
    else:
        doc.status = "Taken Away / Incoming Created"
        doc.set("missing_file_items", [])

    doc.flags.ignore_validate_update_after_submit = True
    doc.save(ignore_permissions=True)
    doc.update_outgoing_linked_statuses()
    publish_movement_realtime(doc.name)

    return {
        "name": doc.name,
        "has_incoming": 1,
        "status": doc.status,
        "missing_count": len(missing) if doc.get("incoming_files") else 0
    }


@frappe.whitelist()
def cancel_incoming(movement_name):
    """
    Cancels the incoming workflow on this File Movement and resets status to 'Taken Away':
    - Asserts write permission
    - Sets has_incoming = 0
    - Resets incoming_date = None
    - Clears incoming_files and missing_file_items
    - Sets status to 'Taken Away'
    - Updates DB and recalculates linked matter statuses using standard Document Model save
    """
    movement_name = str(movement_name or "").strip()
    if not movement_name or not frappe.db.exists("File Movement", movement_name):
        frappe.throw("File Movement not found.")

    doc = frappe.get_doc("File Movement", movement_name)
    doc.check_permission("write")

    if doc.docstatus != 1:
        frappe.throw("File Movement must be submitted before cancelling incoming.")

    if not doc.has_incoming and doc.status not in ["Missing Files", "Received", "Incoming Created", "Incoming Cancelled", "Taken Away"]:
        frappe.throw("Incoming workflow has not been created for this movement.")

    doc.has_incoming = 0
    doc.incoming_date = None
    doc.set("incoming_files", [])
    doc.set("missing_file_items", [])
    doc.status = "Taken Away"
    doc.flags.ignore_validate_update_after_submit = True
    doc.save(ignore_permissions=True)

    doc.update_outgoing_linked_statuses()
    publish_movement_realtime(doc.name)

    return {
        "name": doc.name,
        "has_incoming": 0,
        "status": "Taken Away",
        "message": "Incoming workflow has been cancelled. Status updated to 'Taken Away'."
    }


@frappe.whitelist()
def scan_incoming_file(movement_name, value):
    """
    Scans a barcode, Case ID, or Matter ID into incoming_files for this movement:
    - Asserts write permission
    - Verifies the item belongs to outgoing_files
    - Appends to incoming_files
    - Recalculates missing files and status (Received / Missing Files)
    - Updates DB and Matter status using standard Document Model save
    """
    movement_name = str(movement_name or "").strip()
    value = str(value or "").strip()

    if not movement_name or not frappe.db.exists("File Movement", movement_name):
        frappe.throw("File Movement not found.")

    if not value:
        frappe.throw("Barcode or ID is required.")

    doc = frappe.get_doc("File Movement", movement_name)
    doc.check_permission("write")

    if doc.docstatus != 1:
        frappe.throw("Movement must be submitted before receiving files.")

    if doc.status in ["Cancelled"]:
        frappe.throw(f"Cannot scan files into a movement with status '{doc.status}'.")

    outgoing = doc.get("outgoing_files") or []
    incoming = doc.get("incoming_files") or []
    items_to_add = []

    # 1. Check if value matches Matter (directly in outgoing_files or globally)
    matter_val = None
    if any((r.matter or "").strip() == value for r in outgoing):
        matter_val = value
    else:
        info = get_scan_information(value)
        if info and info.get("type") == "matter":
            if any((r.matter or "").strip() == info.get("matter") for r in outgoing):
                matter_val = info.get("matter")

    if matter_val:
        matching_out = [r for r in outgoing if (r.matter or "").strip() == matter_val]
        unreturned = [r for r in matching_out if not is_item_returned(r, incoming)]
        if not unreturned:
            return {
                "status": "warning",
                "message": f"All files for Matter <b>{matter_val}</b> have already been returned."
            }

        if len(unreturned) > 1:
            cases_payload = []
            for r in unreturned:
                case_title = ""
                case_status = ""
                r_case = r.get("case")
                if r_case:
                    case_title = frappe.db.get_value("Case", r_case, "case_title") or ""
                    case_status = frappe.db.get_value("Case", r_case, "status") or ""
                cases_payload.append({
                    "case": r_case or "",
                    "matter": r.get("matter") or matter_val,
                    "barcode": r.get("barcode") or "",
                    "case_title": case_title,
                    "status": case_status
                })
            return {
                "status": "multiple_cases",
                "matter": matter_val,
                "cases": cases_payload,
                "message": f"Matter <b>{matter_val}</b> has {len(unreturned)} unreturned files. Select which case file is being returned."
            }
        else:
            items_to_add.append({
                "matter": unreturned[0].get("matter"),
                "case": unreturned[0].get("case") or "",
                "barcode": unreturned[0].get("barcode") or ""
            })
    else:
        # 2. Check direct matches in outgoing_files by barcode or case
        direct_bc = [r for r in outgoing if (r.get("barcode") or "").strip() == value]
        direct_case = [r for r in outgoing if (r.get("case") or "").strip() == value]

        if direct_bc:
            for r in direct_bc:
                items_to_add.append({
                    "matter": r.get("matter") or "",
                    "case": r.get("case") or "",
                    "barcode": r.get("barcode") or value
                })
        elif direct_case:
            for r in direct_case:
                items_to_add.append({
                    "matter": r.get("matter") or "",
                    "case": r.get("case") or "",
                    "barcode": r.get("barcode") or ""
                })
        else:
            # 3. Fallback to global resolver
            info = get_scan_information(value)
            if not info or info.get("type") == "not_found":
                return {
                    "status": "error",
                    "message": f"No such Matter ID or Case exists: '{value}'"
                }

            if info["type"] == "case":
                case_val = info["case_name"]
                matching_out = [r for r in outgoing if r.get("case") == case_val]
                if not matching_out:
                    return {
                        "status": "error",
                        "message": f"Case '<b>{case_val}</b>' is not part of Outgoing Files in this movement."
                    }
                items_to_add.append({
                    "matter": matching_out[0].get("matter") or "",
                    "case": case_val,
                    "barcode": matching_out[0].get("barcode") or info.get("barcode") or ""
                })

    # Filter out items already in incoming_files
    new_items = []
    already_scanned = 0

    for item in items_to_add:
        if is_item_returned(item, doc.get("incoming_files") or []):
            already_scanned += 1
        else:
            new_items.append(item)
            doc.append("incoming_files", item)

    if not new_items:
        return {
            "status": "warning",
            "message": f"All matching items for '<b>{value}</b>' are already scanned in Incoming Files."
        }

    # Recalculate remaining missing
    remaining_missing = calculate_missing_files_from_doc(doc)
    doc.set_missing_file_table(remaining_missing)
    doc.status = "Received" if len(remaining_missing) == 0 else "Missing Files"
    doc.has_incoming = 1
    if not doc.incoming_date:
        doc.incoming_date = frappe.utils.now_datetime()

    doc.flags.ignore_validate_update_after_submit = True
    doc.save(ignore_permissions=True)
    doc.update_outgoing_linked_statuses()
    publish_movement_realtime(doc.name)

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
    doc.check_permission("read")
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
    Returns missing files directly into incoming_files of this single document:
    - Asserts write permission
    - Appends returned files to incoming_files
    - Updates status and persists child tables via Document Model save
    """
    movement_name = str(movement_name or "").strip()
    if not movement_name:
        frappe.throw("Movement name is required.")

    doc = frappe.get_doc("File Movement", movement_name)
    doc.check_permission("write")

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
            out_c = out_r.get("case") or ""
            out_b = out_r.get("barcode") or ""
            out_m = out_r.get("matter") or ""
            if (t_case and out_c == t_case) or \
               (t_barcode and out_b == t_barcode) or \
               (t_matter and out_m == t_matter and not t_case and not out_c):
                matched_out = out_r
                break

        if matched_out:
            if not is_item_returned(matched_out, doc.get("incoming_files") or []):
                doc.append("incoming_files", {
                    "barcode": matched_out.get("barcode") or "",
                    "matter": matched_out.get("matter") or "",
                    "case": matched_out.get("case") or ""
                })
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
            if not is_item_returned(entry, doc.get("incoming_files") or []):
                doc.append("incoming_files", entry)
                added_count += 1

    remaining_missing = calculate_missing_files_from_doc(doc)
    doc.set_missing_file_table(remaining_missing)
    doc.status = "Received" if len(remaining_missing) == 0 else "Missing Files"
    doc.has_incoming = 1

    doc.flags.ignore_validate_update_after_submit = True
    doc.save(ignore_permissions=True)
    doc.update_outgoing_linked_statuses()
    publish_movement_realtime(doc.name)

    return {
        "status": doc.status,
        "missing": remaining_missing,
        "remaining_barcodes": [item["barcode"] for item in remaining_missing if item.get("barcode")],
        "remaining_matters": [item["matter"] for item in remaining_missing if item.get("matter")],
        "remaining_cases": [item["case"] for item in remaining_missing if item.get("case")]
    }
