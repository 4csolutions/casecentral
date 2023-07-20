import frappe

def execute():

    x = frappe.get_list('Customer', fields = ['name','customer_name', 'contact_no','contact_email'])
    for record in x:
        contact_doc = frappe.new_doc('Contact')
        contact_doc.first_name = record.get('customer_name')
        contact_doc.append('email_ids', {'email_id' : record.get('contact_email'), 'is_primary' : 1})
        contact_doc.append('phone_nos', {'phone' : record.get('contact_no'), 'is_primary_mobile_no' : 1})
        contact_doc.append('links', {'link_doctype' : 'Customer', 'link_name' : record.get('name')})
        contact_doc.insert()
        customer_doc = frappe.get_doc('Customer', record.get('name'))
        customer_doc.customer_primary_contact = contact_doc.name
        customer_doc.save()
        frappe.db.commit()
