import frappe
from frappe import _


@frappe.whitelist()
def get_uninvoced_legal_services(matter, company=None):
	"""
	Returns un-invoiced Legal Service Entries for a given Matter.
	"""
	matter_doc = frappe.get_doc("Matter", matter)
	services_to_invoice = []

	lse_list = frappe.get_all(
		"Legal Service Entry",
		filters={"matter": matter_doc.name, "invoiced": 0},
		fields=["name", "legal_service", "qty"]
	)

	for lse in lse_list:
		rate = 0.0

		for lsr in matter_doc.get("legal_service_rates", []):
			if lse.legal_service == lsr.legal_service:
				rate = lsr.rate
				break

		service_details = {
			"reference_type": "Legal Service Entry",
			"reference_name": lse.name,
			"service": lse.legal_service,
			"qty": lse.qty,
		}

		if rate:
			service_details["rate"] = rate

		services_to_invoice.append(service_details)

	return services_to_invoice


@frappe.whitelist(allow_guest=True)
def get_firm_branding():
	"""
	Returns firm white-label branding configuration.
	Accessible to both authenticated users and guests for custom login/desk branding.
	"""
	try:
		settings = frappe.get_cached_doc("Case Central Settings")
		return {
			"app_title": settings.get("custom_app_title") or "Case Central",
			"app_logo": settings.get("app_logo"),
			"splash_image": settings.get("splash_image"),
			"favicon": settings.get("favicon"),
			"watermark_text": settings.get("watermark_text") or "Case Central",
			"hide_system_branding": bool(settings.get("hide_system_branding")),
		}
	except Exception:
		return {
			"app_title": "Case Central",
			"app_logo": None,
			"splash_image": None,
			"favicon": None,
			"watermark_text": "Case Central",
			"hide_system_branding": False,
		}


def extend_bootinfo(bootinfo):
	"""
	Inject firm white-label branding into desk bootinfo.
	"""
	bootinfo.casecentral_branding = get_firm_branding()
