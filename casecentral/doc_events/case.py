import frappe

def update_case_matter(self, method):
    if self.matter:
        frappe.get_cached_doc("Matter", self.matter).update_matter_status()