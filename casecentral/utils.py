import frappe

@frappe.whitelist()
def get_legal_services_to_invoice(matter, company):
    items_to_invoice = []
    if matter:
        # Build a list of billable legal services
        items_to_invoice += get_uninvoced_legal_services(matter, company)
        
        return items_to_invoice

def get_uninvoced_legal_services(matter, company):
    matter = frappe.get_doc('Matter', matter)
    services_to_invoice = []
    lse_list = frappe.db.sql("""
        SELECT name, legal_service
        FROM `tabLegal Service Entry`
        WHERE matter=%s and invoiced = 0
    """,(matter.name), as_dict=True)

    for lse in lse_list:
        for lsr in matter.legal_service_rates:
            if lse.legal_service == lsr.legal_service:
                rate = lsr.rate

        services_to_invoice.append({
            'reference_type': 'Legal Service Entry',
            'reference_name': lse.name,
            'service': lse.legal_service,
            'rate': rate or 0.0
        })
    
    return services_to_invoice