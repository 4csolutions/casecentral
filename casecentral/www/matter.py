import frappe

def get_context(context):
    context.show_sidebar = True
    context.no_cache = True

    # Get paging and filter parameters
    page = int(frappe.form_dict.get("page", 1))
    page_size = int(frappe.form_dict.get("page_size", 20))
    name = frappe.form_dict.get("name")
    service_type = frappe.form_dict.get("service_type")
    service = frappe.form_dict.get("service")
    status = frappe.form_dict.get("status")
    
    # Fetch all customers linked to the logged-in user
    customer_list = frappe.get_all("Portal User", filters={"user": frappe.session.user}, pluck="parent")

    filters = {}
    if name:
        filters["name"] = ["like", f"%{name}%"]
    if service_type:
        filters["service_type"] = ["like", f"%{service_type}%"]
    if service:
        filters["service"] = ["like", f"%{service}%"]
    if status:
        filters["status"] = ["like", f"%{status}%"]

    matter_list = []
    has_next = False
    if customer_list:
        filters["customer"] = ["in", customer_list]
        start = (page - 1) * page_size

        matter_list = frappe.get_all(
            "Matter",
            filters=filters,
            fields=[
                "name", "customer_name", "service_type", "service", "status"
            ],
            order_by="modified desc",
            limit_start=start,
            limit_page_length=page_size + 1
        )

        has_next = len(matter_list) > page_size
        if has_next:
            matter_list = matter_list[:-1]

    context.matter_list = matter_list
    context.page = page
    context.page_size = page_size
    context.has_next = has_next
    context.name = name
    context.service_type = service_type
    context.service = service
    context.status = status
    return context