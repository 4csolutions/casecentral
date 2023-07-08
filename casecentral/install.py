import frappe

def after_install():

    if frappe.db.exists('Item Group', 'Books'):
        return
    
    item_group = frappe.new_doc('Item Group')
    item_group.item_group_name = 'Books'
    item_group.parent_item_group = 'All Item Groups'
    item_group.insert()
    frappe.db.commit()
