import frappe

def get_context(context):
    context.show_sidebar = True
    context.no_cache = True

    # Get paging and filter parameters
    page = int(frappe.form_dict.get("page", 1))
    page_size = int(frappe.form_dict.get("page_size", 20))
    case_number = frappe.form_dict.get("case_number")
    status = frappe.form_dict.get("status")
    next_hearing_date = frappe.form_dict.get("next_hearing_date")

    filters = {}
    if case_number:
        filters["name"] = ["like", f"%{case_number}%"]
    if status:
        filters["status"] = ["like", f"%{status}%"]
    if next_hearing_date:
        filters["next_hearing_date"] = next_hearing_date

    # Fetch all customers linked to the logged-in user
    customer_list = frappe.get_all("Portal User", filters={"user": frappe.session.user}, pluck="parent")

    case_list = []
    has_next = False
    if customer_list:
        filters["customer"] = ["in", customer_list]
        start = (page - 1) * page_size

        case_list = frappe.get_all(
            "Case",
            filters=filters,
            fields=[
                "name", "case_title", "status", "registration_number",
                "court_number_and_judge", "next_hearing_date"
            ],
            order_by="next_hearing_date desc",
            limit_start=start,
            limit_page_length=page_size + 1
        )

        has_next = len(case_list) > page_size
        if has_next:
            case_list = case_list[:-1]

    context.case_list = case_list
    context.page = page
    context.page_size = page_size
    context.has_next = has_next
    context.case_number = case_number
    context.status = status
    context.next_hearing_date = next_hearing_date
    return context
