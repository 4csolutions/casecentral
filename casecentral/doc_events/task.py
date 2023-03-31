import frappe

def update_task_matter(self, method):
    if self.matter:
        frappe.get_cached_doc("Matter", self.matter).update_matter_status()

def after_insert(self, method):
    from frappe.desk.form import assign_to

    if self.get("assign_to"):
        assign_to.add(
            {
                "assign_to": self.assign_to,
                "doctype": self.doctype,
                "name": self.name,
            }
        )