# Copyright (c) 2026, 4C Solutions and Contributors
# See license.txt

import frappe
from frappe.tests.utils import FrappeTestCase
from casecentral.case_central.doctype.file_movement.file_movement import (
    create_incoming,
    cancel_incoming,
    scan_incoming_file,
    get_missing_files,
    return_missing_files,
    get_scan_information,
    get_cases_for_matter,
    recalculate_matter_status_from_movements,
)


class TestFileMovement(FrappeTestCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.ensure_prerequisite_doctypes()

    @classmethod
    def ensure_prerequisite_doctypes(cls):
        """
        Ensures prerequisite DocTypes exist when running in an isolated test environment
        where ERPNext is not installed on test_site.
        """
        if not frappe.db.exists("DocType", "Employee"):
            try:
                emp_doctype = frappe.get_doc({
                    "doctype": "DocType",
                    "name": "Employee",
                    "module": "Case Central",
                    "custom": 1,
                    "autoname": "Prompt",
                    "fields": [
                        {"fieldname": "employee_name", "fieldtype": "Data", "label": "Employee Name"},
                        {"fieldname": "first_name", "fieldtype": "Data", "label": "First Name"},
                        {"fieldname": "status", "fieldtype": "Data", "label": "Status"},
                    ],
                    "permissions": [{"role": "System Manager", "read": 1, "write": 1, "create": 1}]
                })
                emp_doctype.insert(ignore_permissions=True)
            except Exception:
                pass

        if not frappe.db.exists("DocType", "Customer"):
            try:
                cust_doctype = frappe.get_doc({
                    "doctype": "DocType",
                    "name": "Customer",
                    "module": "Case Central",
                    "custom": 1,
                    "autoname": "Prompt",
                    "fields": [
                        {"fieldname": "customer_name", "fieldtype": "Data", "label": "Customer Name"},
                        {"fieldname": "customer_type", "fieldtype": "Data", "label": "Customer Type"},
                        {"fieldname": "customer_group", "fieldtype": "Data", "label": "Customer Group"},
                        {"fieldname": "territory", "fieldtype": "Data", "label": "Territory"},
                    ],
                    "permissions": [{"role": "System Manager", "read": 1, "write": 1, "create": 1}]
                })
                cust_doctype.insert(ignore_permissions=True)
            except Exception:
                pass

        if not frappe.db.exists("DocType", "Company"):
            try:
                comp_doctype = frappe.get_doc({
                    "doctype": "DocType",
                    "name": "Company",
                    "module": "Case Central",
                    "custom": 1,
                    "autoname": "Prompt",
                    "fields": [
                        {"fieldname": "company_name", "fieldtype": "Data", "label": "Company Name"},
                        {"fieldname": "abbr", "fieldtype": "Data", "label": "Abbr"},
                        {"fieldname": "default_currency", "fieldtype": "Data", "label": "Default Currency"},
                        {"fieldname": "country", "fieldtype": "Data", "label": "Country"},
                    ],
                    "permissions": [{"role": "System Manager", "read": 1, "write": 1, "create": 1}]
                })
                comp_doctype.insert(ignore_permissions=True)
            except Exception:
                pass

    def setUp(self):
        super().setUp()
        frappe.set_user("Administrator")
        self.giver = self.get_or_create_employee("TEST-GIVER-01", "Test Giver")
        self.receiver = self.get_or_create_employee("TEST-RECEIVER-01", "Test Receiver")
        self.matter_1 = self.get_or_create_matter("TEST-MATTER-01")
        self.matter_2 = self.get_or_create_matter("TEST-MATTER-02")
        self.case_1 = self.get_or_create_case("CASE-TEST-001", self.matter_1, "Petitioner 1", "Respondent 1")
        self.case_2 = self.get_or_create_case("CASE-TEST-002", self.matter_2, "Petitioner 2", "Respondent 2")

    def tearDown(self):
        frappe.set_user("Administrator")
        super().tearDown()

    def get_or_create_employee(self, emp_id, emp_name):
        if not frappe.db.exists("Employee", emp_id):
            emp = frappe.get_doc({
                "doctype": "Employee",
                "name": emp_id,
                "first_name": emp_name,
                "employee_name": emp_name,
                "status": "Active"
            })
            emp.flags.ignore_mandatory = True
            emp.insert(ignore_permissions=True)
            return emp.name
        return emp_id

    def get_or_create_matter(self, matter_name):
        if not frappe.db.exists("Matter", matter_name):
            customer = self.get_or_create_customer("Test Customer")
            service = self.get_or_create_service("Test Service")
            company = self.get_or_create_company("Test Company")
            file_type = self.get_or_create_file_type("Test File Type")

            matter = frappe.get_doc({
                "doctype": "Matter",
                "name": matter_name,
                "customer": customer,
                "service": service,
                "company": company,
                "file_type": file_type,
                "status": "Open",
                "posting_date": frappe.utils.today()
            })
            matter.flags.ignore_mandatory = True
            matter.insert(ignore_permissions=True)
            return matter.name
        else:
            frappe.db.set_value("Matter", matter_name, "status", "Open")
            return matter_name

    def get_or_create_case(self, case_name, matter, petitioner, respondent):
        if not frappe.db.exists("Case", case_name):
            case = frappe.get_doc({
                "doctype": "Case",
                "name": case_name,
                "matter": matter,
                "petitioner": petitioner,
                "respondent": respondent,
                "status": "InProgress"
            })
            case.flags.ignore_mandatory = True
            case.insert(ignore_permissions=True)
            return case.name
        return case_name

    def get_or_create_customer(self, name):
        if not frappe.db.exists("Customer", name):
            cg = frappe.db.get_value("Customer Group", {"is_group": 0}, "name") or "Individual"
            territory = frappe.db.get_value("Territory", {"is_group": 0}, "name") or "India"
            doc = frappe.get_doc({
                "doctype": "Customer",
                "customer_name": name,
                "customer_type": "Individual",
                "customer_group": cg,
                "territory": territory
            })
            doc.flags.ignore_mandatory = True
            doc.insert(ignore_permissions=True)
            return doc.name
        return name

    def get_or_create_company(self, name):
        existing = frappe.db.get_value("Company", {}, "name")
        if existing:
            return existing
        if not frappe.db.exists("Company", name):
            doc = frappe.get_doc({
                "doctype": "Company",
                "company_name": name,
                "abbr": "TC",
                "default_currency": "INR",
                "country": "India"
            })
            doc.flags.ignore_mandatory = True
            doc.insert(ignore_permissions=True)
            return doc.name
        return name

    def get_or_create_service(self, name):
        if not frappe.db.exists("Service", name):
            doc = frappe.get_doc({
                "doctype": "Service",
                "service": name,
                "abbr": "TS"
            })
            doc.flags.ignore_mandatory = True
            doc.insert(ignore_permissions=True)
            return doc.name
        return name

    def get_or_create_file_type(self, name):
        if not frappe.db.exists("File Type", name):
            doc = frappe.get_doc({
                "doctype": "File Type",
                "file_type": name,
                "abbr": "TFT"
            })
            doc.flags.ignore_mandatory = True
            doc.insert(ignore_permissions=True)
            return doc.name
        return name

    # =========================================================
    # TESTS
    # =========================================================

    def test_empty_movement_validation(self):
        """Must fail if outgoing_files is empty."""
        fm = frappe.new_doc("File Movement")
        fm.giver = self.giver
        fm.receiver = self.receiver
        self.assertRaises(frappe.ValidationError, fm.insert)

    def test_same_giver_receiver_validation(self):
        """Same giver and receiver must throw validation error."""
        fm = frappe.new_doc("File Movement")
        fm.giver = self.giver
        fm.receiver = self.giver
        fm.append("outgoing_files", {"barcode": "BC-001", "matter": self.matter_1, "case": self.case_1})
        self.assertRaises(frappe.ValidationError, fm.insert)

    def test_duplicate_barcode_validation(self):
        """Duplicate barcode in the same movement outgoing files must throw validation error."""
        fm = frappe.new_doc("File Movement")
        fm.giver = self.giver
        fm.receiver = self.receiver
        fm.append("outgoing_files", {"barcode": "BC-DUP-01", "matter": self.matter_1, "case": self.case_1})
        fm.append("outgoing_files", {"barcode": "BC-DUP-01", "matter": self.matter_2, "case": self.case_2})
        self.assertRaises(frappe.ValidationError, fm.insert)

    def test_nonexistent_matter_scan_rejection(self):
        """Scanning a non-existent Matter or barcode must return not_found."""
        res = get_scan_information("NON-EXISTENT-MATTER-999")
        self.assertIsNotNone(res)
        self.assertEqual(res["type"], "not_found")
        self.assertIn("No such Matter ID or Case exists", res["message"])

    def test_outgoing_with_files_and_autoname(self):
        """Outgoing movement creates FM-.#####, sets status to Taken Away and Matter to Working."""
        fm = frappe.new_doc("File Movement")
        fm.giver = self.giver
        fm.receiver = self.receiver
        fm.append("outgoing_files", {
            "barcode": "BC-001",
            "matter": self.matter_1,
            "case": self.case_1
        })
        fm.insert(ignore_permissions=True)
        self.assertTrue(fm.name.startswith("FM-"), f"Expected FM- prefix, got {fm.name}")
        self.assertEqual(fm.status, "Draft")
        fm.submit()
        self.assertEqual(fm.status, "Taken Away")
        self.assertEqual(frappe.db.get_value("Matter", self.matter_1, "status"), "Working")

    def test_scan_and_query_apis(self):
        """Test get_scan_information and get_cases_for_matter APIs."""
        # 1. Matter Scan
        matter_info = get_scan_information(self.matter_1)
        self.assertIsNotNone(matter_info)
        self.assertEqual(matter_info["type"], "matter")
        self.assertEqual(matter_info["matter"], self.matter_1)
        self.assertTrue(len(matter_info["cases"]) >= 1)

        # 2. Case Scan
        case_info = get_scan_information(self.case_1)
        self.assertIsNotNone(case_info)
        self.assertEqual(case_info["type"], "case")
        self.assertEqual(case_info["case_name"], self.case_1)
        self.assertEqual(case_info["matter"], self.matter_1)

        # 3. Get cases for matter
        cases = get_cases_for_matter(self.matter_1)
        self.assertTrue(any(c["name"] == self.case_1 for c in cases))

    def test_single_doc_incoming_workflow_partial_and_full_returns(self):
        """
        Complete Single Document Lifecycle test:
        1. Create Outgoing with 2 items in outgoing_files -> Submit (status: Taken Away, Matter: Working)
        2. Call create_incoming on SAME doc -> has_incoming=1, incoming_files empty, status: Incoming Created
        3. Scan 1 item into incoming_files via scan_incoming_file -> Status 'Missing Files', 1 missing
        4. Late return of remaining missing file via return_missing_files -> Status becomes 'Received', Matter: Open
        """
        # Step 1: Create Outgoing
        doc = frappe.new_doc("File Movement")
        doc.giver = self.giver
        doc.receiver = self.receiver
        doc.append("outgoing_files", {
            "barcode": "TEST-BC-101",
            "matter": self.matter_1,
            "case": self.case_1
        })
        doc.append("outgoing_files", {
            "barcode": "TEST-BC-102",
            "matter": self.matter_2,
            "case": self.case_2
        })
        doc.insert(ignore_permissions=True)
        doc.submit()

        self.assertEqual(doc.status, "Taken Away")
        self.assertEqual(frappe.db.get_value("Matter", self.matter_1, "status"), "Working")
        self.assertEqual(frappe.db.get_value("Matter", self.matter_2, "status"), "Working")

        # Step 2: Initialize Incoming on the SAME document
        res_inc = create_incoming(doc.name)
        self.assertEqual(res_inc["name"], doc.name)
        self.assertEqual(res_inc["has_incoming"], 1)
        self.assertEqual(res_inc["status"], "Taken Away / Incoming Created")
        self.assertEqual(res_inc["missing_count"], 0)

        doc.reload()
        self.assertEqual(len(doc.incoming_files), 0, "Incoming files should start empty")
        self.assertEqual(doc.status, "Taken Away / Incoming Created")

        # Step 3: Scan 1 item into incoming_files
        scan_res = scan_incoming_file(doc.name, "TEST-BC-101")
        self.assertEqual(scan_res["status"], "success")
        self.assertEqual(scan_res["movement_status"], "Missing Files")
        self.assertEqual(scan_res["added_count"], 1)
        self.assertEqual(scan_res["missing_count"], 1)

        doc.reload()
        self.assertEqual(len(doc.incoming_files), 1)
        self.assertEqual(len(doc.missing_file_items), 1)
        self.assertEqual(doc.missing_file_items[0].case, self.case_2)

        # Step 4: Return remaining item
        ret_res = return_missing_files(doc.name, files=[self.case_2])
        self.assertEqual(ret_res["status"], "Received")
        self.assertEqual(len(ret_res["missing"]), 0)

        # Step 5: Verify document is now Received and Matters are Open
        doc.reload()
        self.assertEqual(doc.status, "Received")
        self.assertEqual(len(doc.missing_file_items), 0)
        self.assertEqual(len(doc.incoming_files), 2)
        self.assertEqual(frappe.db.get_value("Matter", self.matter_1, "status"), "Open")
        self.assertEqual(frappe.db.get_value("Matter", self.matter_2, "status"), "Open")

    def test_cancel_incoming_preserves_traces(self):
        """Cancelling incoming resets status to 'Taken Away', has_incoming to 0, and allows re-creating incoming."""
        doc = frappe.new_doc("File Movement")
        doc.giver = self.giver
        doc.receiver = self.receiver
        doc.append("outgoing_files", {
            "barcode": "TEST-BC-CAN-01",
            "matter": self.matter_1,
            "case": self.case_1
        })
        doc.insert(ignore_permissions=True)
        doc.submit()

        self.assertEqual(doc.status, "Taken Away")
        self.assertEqual(frappe.db.get_value("Matter", self.matter_1, "status"), "Working")

        # Create incoming
        create_incoming(doc.name)
        doc.reload()
        self.assertEqual(doc.status, "Taken Away / Incoming Created")
        self.assertEqual(doc.has_incoming, 1)

        # Cancel incoming (not the whole FM)
        res_can = cancel_incoming(doc.name)
        self.assertEqual(res_can["status"], "Taken Away")
        self.assertEqual(res_can["has_incoming"], 0)

        doc.reload()
        self.assertEqual(doc.docstatus, 1, "Docstatus must remain 1 (submitted), NOT cancelled/deleted")
        self.assertEqual(doc.status, "Taken Away")
        self.assertEqual(doc.has_incoming, 0)
        self.assertEqual(len(doc.outgoing_files), 1, "Outgoing files traces must be preserved")
        self.assertEqual(frappe.db.get_value("Matter", self.matter_1, "status"), "Working")

        # Reopen/Re-create incoming
        res_reopen = create_incoming(doc.name)
        self.assertEqual(res_reopen["status"], "Taken Away / Incoming Created")
        self.assertEqual(res_reopen["has_incoming"], 1)
        doc.reload()
        self.assertEqual(doc.status, "Taken Away / Incoming Created")

    def test_delete_incoming_file_resets_status_to_taken_away(self):
        """
        When user returns 1 file from multiple files, status is 'Missing Files'.
        When user deletes the returned file from incoming_files, status reverts to 'Taken Away / Incoming Created'.
        Cancelling incoming resets has_incoming=0 and allows creating incoming again.
        """
        doc = frappe.new_doc("File Movement")
        doc.giver = self.giver
        doc.receiver = self.receiver
        doc.append("outgoing_files", {
            "barcode": "TEST-BC-DEL-01",
            "matter": self.matter_1,
            "case": self.case_1
        })
        doc.append("outgoing_files", {
            "barcode": "TEST-BC-DEL-02",
            "matter": self.matter_2,
            "case": self.case_2
        })
        doc.insert(ignore_permissions=True)
        doc.submit()

        self.assertEqual(doc.status, "Taken Away")

        # 1. Create incoming
        create_incoming(doc.name)
        doc.reload()
        self.assertEqual(doc.has_incoming, 1)
        self.assertEqual(doc.status, "Taken Away / Incoming Created")

        # 2. Return 1 file -> status becomes 'Missing Files'
        scan_incoming_file(doc.name, "TEST-BC-DEL-01")
        doc.reload()
        self.assertEqual(doc.status, "Missing Files")
        self.assertEqual(len(doc.incoming_files), 1)
        self.assertEqual(len(doc.missing_file_items), 1)

        # 3. User deletes returned file from incoming_files and saves document (Update)
        doc.incoming_files = []
        doc.save(ignore_permissions=True)
        doc.reload()
        self.assertEqual(doc.status, "Taken Away / Incoming Created", "Status must be Taken Away / Incoming Created when incoming files is empty while has_incoming is active")
        self.assertEqual(len(doc.missing_file_items), 0)
        self.assertEqual(doc.has_incoming, 1)

        # 4. Mandatory step: cancel incoming
        res_can = cancel_incoming(doc.name)
        self.assertEqual(res_can["status"], "Taken Away")
        self.assertEqual(res_can["has_incoming"], 0)
        doc.reload()
        self.assertEqual(doc.status, "Taken Away")
        self.assertEqual(doc.has_incoming, 0)

        # 5. Re-create incoming
        res_inc = create_incoming(doc.name)
        self.assertEqual(res_inc["has_incoming"], 1)
        self.assertEqual(res_inc["status"], "Taken Away / Incoming Created")

    def test_on_cancel_whole_fm_and_delete_protection(self):
        """Cancelling the whole FM sets status to Cancelled, restores Matter, and blocks deletion."""
        doc = frappe.new_doc("File Movement")
        doc.giver = self.giver
        doc.receiver = self.receiver
        doc.append("outgoing_files", {
            "barcode": "TEST-BC-CAN-02",
            "matter": self.matter_2,
            "case": self.case_2
        })
        doc.insert(ignore_permissions=True)
        doc.submit()
        self.assertEqual(frappe.db.get_value("Matter", self.matter_2, "status"), "Working")

        # Attempt to delete submitted doc must fail
        self.assertRaises(frappe.ValidationError, doc.delete)

        # Cancel the FM
        doc.cancel()
        doc.reload()
        self.assertEqual(doc.docstatus, 2)
        self.assertEqual(doc.status, "Cancelled")
        self.assertEqual(frappe.db.get_value("Matter", self.matter_2, "status"), "Open")

        # Cancelled doc can be deleted if user desires
        fm_name = doc.name
        doc.delete()
        self.assertFalse(frappe.db.exists("File Movement", fm_name))

    def test_whitelisted_endpoint_permissions(self):
        """Mutating endpoints must enforce doc.check_permission('write') and read endpoints enforce 'read'."""
        doc = frappe.new_doc("File Movement")
        doc.giver = self.giver
        doc.receiver = self.receiver
        doc.append("outgoing_files", {
            "barcode": "TEST-PERM-BC-01",
            "matter": self.matter_1,
            "case": self.case_1
        })
        doc.insert(ignore_permissions=True)
        doc.submit()

        # Guest user has no read or write permissions on File Movement
        frappe.set_user("Guest")
        try:
            self.assertRaises(frappe.PermissionError, create_incoming, doc.name)
            self.assertRaises(frappe.PermissionError, cancel_incoming, doc.name)
            self.assertRaises(frappe.PermissionError, scan_incoming_file, doc.name, "TEST-PERM-BC-01")
            self.assertRaises(frappe.PermissionError, return_missing_files, doc.name, files=[self.case_1])
            self.assertRaises(frappe.PermissionError, get_missing_files, doc.name)
        finally:
            frappe.set_user("Administrator")

    def test_frappe_qb_matter_status_recalculation(self):
        """Verify frappe.qb recalculation of matter status across movements."""
        doc = frappe.new_doc("File Movement")
        doc.giver = self.giver
        doc.receiver = self.receiver
        doc.append("outgoing_files", {
            "barcode": "TEST-QB-BC-01",
            "matter": self.matter_1,
            "case": self.case_1
        })
        doc.insert(ignore_permissions=True)
        doc.submit()

        recalculate_matter_status_from_movements(self.matter_1)
        self.assertEqual(frappe.db.get_value("Matter", self.matter_1, "status"), "Working")

        # Cancel the movement
        doc.cancel()
        recalculate_matter_status_from_movements(self.matter_1)
        self.assertEqual(frappe.db.get_value("Matter", self.matter_1, "status"), "Open")

    def test_taken_away_file_cannot_be_re_dispatched(self):
        """
        Files that are currently taken away in an active File Movement
        cannot be added or dispatched in another File Movement until returned.
        """
        # 1. Create first movement and submit it
        fm1 = frappe.new_doc("File Movement")
        fm1.giver = self.giver
        fm1.receiver = self.receiver
        fm1.append("outgoing_files", {
            "barcode": "TEST-TAKEN-BC-01",
            "matter": self.matter_1,
            "case": self.case_1
        })
        fm1.insert(ignore_permissions=True)
        fm1.submit()
        self.assertEqual(fm1.status, "Taken Away")

        # 2. Check get_scan_information returns taken_away: True
        info_case = get_scan_information(self.case_1)
        self.assertTrue(info_case.get("taken_away"))
        self.assertEqual(info_case.get("taken_away_info", {}).get("movement"), fm1.name)

        info_bc = get_scan_information("TEST-TAKEN-BC-01")
        self.assertTrue(info_bc.get("taken_away"))
        self.assertEqual(info_bc.get("taken_away_info", {}).get("movement"), fm1.name)

        # 3. Create second movement attempting to dispatch the same case -> must raise ValidationError
        fm2 = frappe.new_doc("File Movement")
        fm2.giver = self.giver
        fm2.receiver = self.receiver
        fm2.append("outgoing_files", {
            "barcode": "TEST-TAKEN-BC-01",
            "matter": self.matter_1,
            "case": self.case_1
        })
        self.assertRaises(frappe.ValidationError, fm2.insert)

        # 4. Once fm1 receives the file, it can be re-dispatched
        create_incoming(fm1.name)
        scan_incoming_file(fm1.name, "TEST-TAKEN-BC-01")
        fm1.reload()
        self.assertEqual(fm1.status, "Received")

        # Now get_scan_information should report not taken away
        info_returned = get_scan_information(self.case_1)
        self.assertFalse(info_returned.get("taken_away"))

        # And inserting fm2 now succeeds
        fm2.insert(ignore_permissions=True)
        self.assertTrue(fm2.name.startswith("FM-"))

    def test_prevent_duplicate_incoming_files(self):
        """Prevent duplicate files in incoming_files via manual save, scan_incoming_file, and return_missing_files."""
        fm = frappe.new_doc("File Movement")
        fm.giver = self.giver
        fm.receiver = self.receiver
        fm.append("outgoing_files", {
            "barcode": "TEST-DUP-01",
            "matter": self.matter_1,
            "case": self.case_1
        })
        fm.append("outgoing_files", {
            "barcode": "TEST-DUP-02",
            "matter": self.matter_2,
            "case": self.case_2
        })
        fm.insert(ignore_permissions=True)
        fm.submit()

        create_incoming(fm.name)
        fm.reload()

        # 1. Manually adding duplicate barcode/case in incoming_files must raise ValidationError on save
        fm.append("incoming_files", {
            "barcode": "TEST-DUP-01",
            "matter": self.matter_1,
            "case": self.case_1
        })
        fm.append("incoming_files", {
            "barcode": "TEST-DUP-01",
            "matter": self.matter_1,
            "case": self.case_1
        })
        self.assertRaises(frappe.ValidationError, fm.save)

        # Reload clean state to test API deduplication
        fm.reload()
        self.assertEqual(len(fm.incoming_files), 0)

        # 2. scan_incoming_file: scan same file twice -> only 1 row added, second scan returns warning
        res1 = scan_incoming_file(fm.name, "TEST-DUP-01")
        self.assertEqual(res1.get("status"), "success")
        fm.reload()
        self.assertEqual(len(fm.incoming_files), 1)

        res2 = scan_incoming_file(fm.name, "TEST-DUP-01")
        self.assertEqual(res2.get("status"), "warning")
        self.assertIn("already scanned", res2.get("message", ""))
        fm.reload()
        self.assertEqual(len(fm.incoming_files), 1)

        # 3. return_missing_files with duplicate items or already returned file -> no duplicates created
        return_missing_files(fm.name, files=[{"case": self.case_2}, {"case": self.case_2}])
        fm.reload()
        # Should have 2 incoming files: case_1 and case_2 (no duplicate case_2)
        self.assertEqual(len(fm.incoming_files), 2)
        cases_in_incoming = [r.case for r in fm.incoming_files]
        self.assertEqual(sorted(cases_in_incoming), sorted([self.case_1, self.case_2]))
        self.assertEqual(fm.status, "Received")


def run_test_suite():
    import unittest
    suite = unittest.TestLoader().loadTestsFromTestCase(TestFileMovement)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    if not result.wasSuccessful():
        raise Exception(f"Tests failed: {len(result.failures)} failures, {len(result.errors)} errors")
    print(f"\nAll {result.testsRun} tests passed successfully!")
