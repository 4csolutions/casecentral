# Copyright (c) 2026, 4C Solutions and Contributors
# See license.txt

import frappe
from frappe.tests.utils import FrappeTestCase
from casecentral.case_central.doctype.file_movement.file_movement import (
    create_incoming,
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
        """Must fail if barcode_files is empty."""
        fm = frappe.new_doc("File Movement")
        fm.movement_type = "Outgoing"
        fm.giver = self.giver
        fm.receiver = self.receiver
        self.assertRaises(frappe.ValidationError, fm.insert)

    def test_same_giver_receiver_validation(self):
        """Same giver and receiver must throw validation error."""
        fm = frappe.new_doc("File Movement")
        fm.movement_type = "Outgoing"
        fm.giver = self.giver
        fm.receiver = self.giver
        fm.append("barcode_files", {"barcode": "BC-001", "matter": self.matter_1, "case": self.case_1})
        self.assertRaises(frappe.ValidationError, fm.insert)

    def test_duplicate_barcode_validation(self):
        """Duplicate barcode in the same movement must throw validation error."""
        fm = frappe.new_doc("File Movement")
        fm.movement_type = "Outgoing"
        fm.giver = self.giver
        fm.receiver = self.receiver
        fm.append("barcode_files", {"barcode": "BC-DUP-01", "matter": self.matter_1, "case": self.case_1})
        fm.append("barcode_files", {"barcode": "BC-DUP-01", "matter": self.matter_2, "case": self.case_2})
        self.assertRaises(frappe.ValidationError, fm.insert)

    def test_nonexistent_matter_scan_rejection(self):
        """Scanning a non-existent Matter or barcode must return not_found."""
        res = get_scan_information("NON-EXISTENT-MATTER-999")
        self.assertIsNotNone(res)
        self.assertEqual(res["type"], "not_found")

    def test_outgoing_with_matter_files(self):
        """Outgoing movement with matter files in barcode_files table."""
        fm = frappe.new_doc("File Movement")
        fm.movement_type = "Outgoing"
        fm.giver = self.giver
        fm.receiver = self.receiver
        fm.append("barcode_files", {
            "barcode": "BC-001",
            "matter": self.matter_1,
            "case": self.case_1
        })
        fm.insert(ignore_permissions=True)
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

    def test_full_incoming_workflow_partial_and_full_returns(self):
        """
        Complete lifecycle test with single Matter Files table:
        1. Create Outgoing with 2 items -> Submit
        2. Create Incoming via create_incoming -> Check giver/receiver reversal & copy
        3. Partial return (1 returned, 1 unreturned) -> Submit -> Status "Missing Files" & missing table populated
        4. Late return of remaining missing file -> Status becomes "Received"
        """
        # Step 1: Outgoing
        outgoing = frappe.new_doc("File Movement")
        outgoing.movement_type = "Outgoing"
        outgoing.giver = self.giver
        outgoing.receiver = self.receiver
        outgoing.append("barcode_files", {
            "barcode": "TEST-BC-101",
            "matter": self.matter_1,
            "case": self.case_1,
            "returned": 0
        })
        outgoing.append("barcode_files", {
            "barcode": "TEST-BC-102",
            "matter": self.matter_2,
            "case": self.case_2,
            "returned": 0
        })
        outgoing.insert(ignore_permissions=True)
        outgoing.submit()

        # Step 2: Create Incoming
        incoming_name = create_incoming(outgoing.name)
        incoming = frappe.get_doc("File Movement", incoming_name)
        self.assertEqual(incoming.movement_type, "Incoming")
        self.assertTrue(outgoing.name.startswith("FMO-"), f"Outgoing name should start with FMO-, got {outgoing.name}")
        self.assertTrue(incoming.name.startswith("FMI-"), f"Incoming name should start with FMI-, got {incoming.name}")
        self.assertEqual(incoming.name[4:], outgoing.name[4:], f"FMI suffix {incoming.name} should match FMO suffix {outgoing.name}")
        self.assertEqual(incoming.giver, self.receiver)
        self.assertEqual(incoming.receiver, self.giver)
        self.assertEqual(incoming.original_outgoing_movement, outgoing.name)
        self.assertEqual(len(incoming.barcode_files), 2)
        self.assertEqual(incoming.barcode_files[0].returned, 0)
        self.assertEqual(incoming.barcode_files[1].returned, 0)

        # Step 3: Partial return - mark row 0 as returned, row 1 unreturned
        incoming.barcode_files[0].returned = 1
        incoming.barcode_files[1].returned = 0
        incoming.save(ignore_permissions=True)
        incoming.submit()

        self.assertEqual(incoming.status, "Missing Files")
        self.assertEqual(len(incoming.missing_file_items), 1)
        self.assertEqual(incoming.missing_file_items[0].case, self.case_2)

        # Step 4: Check get_missing_files
        missing = get_missing_files(incoming.name)
        self.assertEqual(len(missing), 1)
        self.assertEqual(missing[0]["case"], self.case_2)

        # Step 5: Late return of remaining missing file
        res = return_missing_files(incoming.name, files=[self.case_2])
        self.assertEqual(res["status"], "Received")
        self.assertEqual(len(res["missing"]), 0)

        # Verify incoming doc status updated in database
        incoming.reload()
        self.assertEqual(incoming.status, "Received")
        self.assertEqual(len(incoming.missing_file_items), 0)

    def test_fmo_and_fmi_matching_id_number(self):
        """Test that Outgoing movement creates FMO-##### and Incoming creates matching FMI-#####."""
        outgoing = frappe.new_doc("File Movement")
        outgoing.movement_type = "Outgoing"
        outgoing.giver = self.giver
        outgoing.receiver = self.receiver
        outgoing.append("barcode_files", {
            "barcode": "TEST-BC-FMO-01",
            "matter": self.matter_1,
            "case": self.case_1
        })
        outgoing.insert(ignore_permissions=True)
        outgoing.submit()

        self.assertTrue(outgoing.name.startswith("FMO-"), f"Expected FMO- prefix, got {outgoing.name}")

        # Extract number part
        num_part = outgoing.name.replace("FMO-", "")

        # Create incoming
        incoming_name = create_incoming(outgoing.name)
        self.assertEqual(incoming_name, f"FMI-{num_part}", f"Expected FMI-{num_part}, got {incoming_name}")



def run_test_suite():
    import unittest
    suite = unittest.TestLoader().loadTestsFromTestCase(TestFileMovement)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    if not result.wasSuccessful():
        raise Exception(f"Tests failed: {len(result.failures)} failures, {len(result.errors)} errors")
    print(f"\nAll {result.testsRun} tests passed successfully!")
