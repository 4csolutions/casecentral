import frappe
from frappe import _  
from frappe.desk.form import assign_to
from frappe.utils import nowdate

def update_task_matter(self, method):
    if self.matter:
        matter_doc = frappe.get_cached_doc("Matter", self.matter)
        matter_doc.update_matter_status()
    
    task_type_id = frappe.db.get_value('Task Type', {'description': 'Hearing'}, 'name')
    if self.type == task_type_id and self.status == 'Completed' and not self.legal_service_entry_created:
        auto_create_setting = frappe.db.get_single_value('Case Central Settings', 'auto_create_lse_on_hearing_task_complete')
        if auto_create_setting:
            create_legal_service_entry(self)
        
def after_insert(self, method):
   
    if self.get("assign_to"):
        assign_to.add(
            {
                "assign_to": self.assign_to,
                "doctype": self.doctype,
                "name": self.name,
            }
        )

def create_legal_service_entry(task):
    try:
        if not frappe.db.exists("Legal Service Entry", {"task": task.name}):
            lse = frappe.get_doc({
                'doctype': 'Legal Service Entry',
                'matter': task.matter,
                'case': task.case or '',
                'task': task.name,
                'legal_service': 'Hearing Fee',
                'qty': 1,
                'posting_date': nowdate(),
                'description': task.subject,
                'task': task.name
            })
            lse.insert()
            task.db_set('legal_service_entry_created', 1)
            frappe.db.commit()
    except Exception as e:
        frappe.throw(_('An error occurred while creating the Legal Service Entry: {0}').format(str(e)))

def on_task_update(doc, method):
    update_task_matter(doc, method)

def on_task_insert(doc, method):
    after_insert(doc, method)


