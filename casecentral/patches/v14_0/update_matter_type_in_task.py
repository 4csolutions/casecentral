import frappe

def execute():

    x = frappe.get_list('Task', fields = ['name','matter'], order_by="name asc")
    for record in x:
        matter_type = frappe.db.get_value("Matter", record.matter, "matter_type")
        if matter_type:
            frappe.db.set_value("Task", record.name, "custom_matter_type", matter_type) 
            frappe.db.commit()