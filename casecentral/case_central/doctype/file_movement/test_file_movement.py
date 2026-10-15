# Copyright (c) 2026, 4C Solutions and Contributors
# See license.txt

import frappe
from frappe.tests.utils import FrappeTestCase
from casecentral.case_central.doctype.file_movement.file_movement import (
    create_incoming,
    scan_incoming_file,
    get_missing_files,
    return_missing_files,
    get_scan_information,
    get_cases_for_matter,
)


class TestFileMovement(FrappeTestCase):

    def setUp(self):
        super().setUp()
        self.giver = self.get_or_create_employee("TEST-GIVER-01", "Test Giver")
        self.receiver = self.get_or_create_employee("TEST-RECEIVER-01", "Test Receiver")
        self.matter_1 = self.get_or_create_matter("TEST-MATTER-01")
        self.matter_2 = self.get_or_create_matter("TEST-MATTER-02")
        self.case_1 = self.get_or_create_case("CASE-TEST-001", self.matter_1, "Petitioner 1", "Respondent 1")
        self.case_2 = self.get_or_create_case("CASE-TEST-002", self.matter_2, "Petitioner 2", "Respondent 2")

    def tearDown(self):
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

    def test_outgoing_with_files_and_autoname(self):
        """Outgoing movement creates FM-.#####, sets status to Open and Matter to Working."""
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
        self.assertEqual(fm.status, "Open")
        fm.submit()
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
        1. Create Outgoing with 2 items in outgoing_files -> Submit (status: Open, Matter: Working)
        2. Call create_incoming on SAME doc -> has_incoming=1, incoming_files empty, 2 missing items
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

        self.assertEqual(doc.status, "Open")
        self.assertEqual(frappe.db.get_value("Matter", self.matter_1, "status"), "Working")
        self.assertEqual(frappe.db.get_value("Matter", self.matter_2, "status"), "Working")

        # Step 2: Initialize Incoming on the SAME document
        res_inc = create_incoming(doc.name)
        self.assertEqual(res_inc["name"], doc.name)
        self.assertEqual(res_inc["has_incoming"], 1)
        self.assertEqual(res_inc["status"], "Missing Files")
        self.assertEqual(res_inc["missing_count"], 2)

        doc.reload()
        self.assertEqual(len(doc.incoming_files), 0, "Incoming files should start empty")
        self.assertEqual(len(doc.missing_file_items), 2, "All 2 outgoing items should initially be missing")

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


def run_test_suite():
    import unittest
    suite = unittest.TestLoader().loadTestsFromTestCase(TestFileMovement)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    if not result.wasSuccessful():
        raise Exception(f"Tests failed: {len(result.failures)} failures, {len(result.errors)} errors")
    print(f"\nAll {result.testsRun} tests passed successfully!")
