import frappe
from frappe import _
from frappe.utils import (flt)
from erpnext.accounts.doctype.sales_invoice.sales_invoice import SalesInvoice

class CustomSalesInvoice(SalesInvoice):
	@frappe.whitelist()
	def set_legal_services(self, checked_values):
		self.set("items", [])
		from erpnext.stock.get_item_details import get_item_details

		price_list_data = frappe.db.get_value(
			"Price List", {"selling": 1}, ["name", "currency"], as_dict=True
		)
		price_list = price_list_data.get("name") if price_list_data else None
		price_list_currency = price_list_data.get("currency") if price_list_data else self.currency
		customer = frappe.db.get_value("Matter", self.matter, "customer")

		for checked_item in checked_values:
			item_line = self.append("items", {})
			args = {
				"doctype": "Sales Invoice",
				"item_code": checked_item["item"],
				"company": self.company,
				"customer": customer,
				"selling_price_list": price_list,
				"price_list_currency": price_list_currency,
				"plc_conversion_rate": 1.0,
				"conversion_rate": 1.0,
			}
			item_details = get_item_details(args)
			item_line.item_code = checked_item["item"]
			item_line.qty = 1
			if checked_item["qty"]:
				item_line.qty = checked_item["qty"]
			if checked_item["rate"]:
				item_line.rate = checked_item["rate"]
			else:
				item_line.rate = item_details.price_list_rate
			item_line.amount = float(item_line.rate) * float(item_line.qty)
			if checked_item["income_account"]:
				item_line.income_account = checked_item["income_account"]
			if checked_item["dt"]:
				item_line.reference_doctype = checked_item["dt"]
			if checked_item["dn"]:
				item_line.reference_name = checked_item["dn"]
			if checked_item["description"]:
				item_line.description = checked_item["description"]

		self.set_missing_values(for_validate=True)