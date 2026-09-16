// Firm White-Labeling and Custom Branding for Case Central
function apply_firm_branding(branding) {
	if (!branding) return;

	if (branding.app_title && branding.app_title !== "Case Central") {
		if (frappe.boot) {
			frappe.boot.app_name = branding.app_title;
		}
		if (document.title.includes("Case Central")) {
			document.title = document.title.replace("Case Central", branding.app_title);
		}
		$(".navbar-brand span.app-title").text(branding.app_title);
	}
	if (branding.app_logo) {
		$(".navbar-brand img.app-logo").attr("src", branding.app_logo);
	}
	if (branding.favicon) {
		$('link[rel="shortcut icon"]').attr("href", branding.favicon);
	}
}

$(document).on("app_ready", function () {
	if (frappe.boot && frappe.boot.casecentral_branding) {
		apply_firm_branding(frappe.boot.casecentral_branding);
	} else if (frappe.call) {
		frappe.call({
			method: "casecentral.utils.get_firm_branding",
			callback: function (r) {
				if (r && r.message) {
					apply_firm_branding(r.message);
				}
			}
		});
	}
});
