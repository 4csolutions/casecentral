from . import __version__ as app_version

app_name = "casecentral"
app_title = "Case Central"
app_publisher = "4C Solutions"
app_description = "Legal Practice Management Application"
app_email = "info@4csolutions.in"
app_license = "MIT"

fixtures = [
    {
		"doctype": "Custom Field",
		"filters" : [
            [
                "name",
                "in",
                [
                    "Task-matter",
                    "Task-case",
                    "Task Type-naming_series",
                    "Task Type-matter_type",
                    "Sales Invoice-matter",
                    "Customer-contact_no",
                    "Customer-contact_email",
                    "Sales Invoice Item-reference_doctype",
                    "Sales Invoice Item-reference_name",
                    "Quality Review-matter",
                    "Quality Review-service",
                    "Quality Goal-service",
                    "Item-isbn",
                    "Item-book_type"
                ]
            ]
        ]
    },
    {
        "doctype": "Property Setter",
        "filters": [
            [
                "name",
                "in",
                [
                    "Customer-main-quick_entry",
                    "Customer-main-search_fields",
                    "Customer-lead_name-hidden",
                    "Customer-opportunity_name-hidden",
                    "Customer-customer_type-default",
                    "Task-project-hidden",
                    "Task-issue-hidden",
                    "Task-task_weight-hidden",
                    "Task-sb_depends_on-hidden",
                    "Task-sb_costing-hidden",
                    "Task-project-in_list_view",
                    "Task-project-in_standard_filter",
                    "Task-is_group-in_list_view",
                    "Task-is_milestone-in_list_view",
                    "Task-main-quick_entry",
                    "Task-subject-allow_in_quick_entry",
                    "Task-status-allow_in_quick_entry",
                    "Task-is_group-bold",
                    "Task-parent_task-bold",
                    "Task-priority-allow_in_quick_entry",
                    "Task-type-allow_in_quick_entry",
                    "Task-type-in_standard_filter",
                    "Task Type-main-naming_rule",
                    "Task Type-main-autoname",
                    "Task Type-main-search_fields",
                    "Task Type-description-in_list_view",
                    "Task Type-description-in_standard_filter",
                    "Task Type-main-title_field",
                    "Task Type-main-show_title_field_in_link"
                ]
            ]
        ]
    },
    {
		"doctype": "Client Script",
		"filters" : [
            [
                "name",
                "in",
                [
                    "Duplicate Contact Check",
                    "Remove Referral from Client",
                    "Quality Review",
                    "Task"
                ]
            ]
        ]
    }
]
# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/casecentral/css/casecentral.css"
app_include_js = "casecentral.bundle.js"

# include js, css files in header of web template
# web_include_css = "/assets/casecentral/css/casecentral.css"
# web_include_js = "/assets/casecentral/js/casecentral.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "casecentral/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
# doctype_js = {"doctype" : "public/js/doctype.js"}
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}
doctype_js = {
    "Sales Invoice" : "public/js/sales_invoice.js"
}

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
#	"Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
#	"methods": "casecentral.utils.jinja_methods",
#	"filters": "casecentral.utils.jinja_filters"
# }

# Installation
# ------------

# before_install = "casecentral.install.before_install"
after_install = "casecentral.install.after_install"

# Uninstallation
# ------------

# before_uninstall = "casecentral.uninstall.before_uninstall"
# after_uninstall = "casecentral.uninstall.after_uninstall"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "casecentral.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways

# permission_query_conditions = {
#	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
#	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

# DocType Class
# ---------------
# Override standard doctype classes

# override_doctype_class = {
#	"ToDo": "custom_app.overrides.CustomToDo"
# }
override_doctype_class = {
	'Sales Invoice': 'casecentral.overrides.CustomSalesInvoice'
}

# Document Events
# ---------------
# Hook on document methods and events

# doc_events = {
#	"*": {
#		"on_update": "method",
#		"on_cancel": "method",
#		"on_trash": "method"
#	}
# }
doc_events = {
    "Task": {
        "after_insert": "casecentral.doc_events.task.after_insert",
        "on_update": "casecentral.doc_events.task.update_task_matter",
        "after_delete": "casecentral.doc_events.task.update_task_matter"
    },
    "Case": {
        "on_update": "casecentral.doc_events.case.update_case_matter",
        "after_delete": "casecentral.doc_events.case.update_case_matter"
    },
    "Sales Invoice": {
        "on_submit": "casecentral.doc_events.sales_invoice.manage_invoice_submit_cancel",
		"on_cancel": "casecentral.doc_events.sales_invoice.manage_invoice_submit_cancel"
    },
    "Purchase Invoice": {
        "on_submit": "casecentral.doc_events.purchase_invoice.create_book_on_submit"
    }
}

# Scheduled Tasks
# ---------------

# scheduler_events = {
#	"all": [
#		"casecentral.tasks.all"
#	],
#	"daily": [
#		"casecentral.tasks.daily"
#	],
#	"hourly": [
#		"casecentral.tasks.hourly"
#	],
#	"weekly": [
#		"casecentral.tasks.weekly"
#	],
#	"monthly": [
#		"casecentral.tasks.monthly"
#	],
# }
scheduler_events = {
	"daily": [
		"casecentral.case_central.doctype.caveat.caveat.set_expired_status"
	]
}
# Testing
# -------

# before_tests = "casecentral.install.before_tests"

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
#	"frappe.desk.doctype.event.event.get_events": "casecentral.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
#	"Task": "casecentral.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]


# User Data Protection
# --------------------

# user_data_fields = [
#	{
#		"doctype": "{doctype_1}",
#		"filter_by": "{filter_by}",
#		"redact_fields": ["{field_1}", "{field_2}"],
#		"partial": 1,
#	},
#	{
#		"doctype": "{doctype_2}",
#		"filter_by": "{filter_by}",
#		"partial": 1,
#	},
#	{
#		"doctype": "{doctype_3}",
#		"strict": False,
#	},
#	{
#		"doctype": "{doctype_4}"
#	}
# ]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
#	"casecentral.auth.validate"
# ]
