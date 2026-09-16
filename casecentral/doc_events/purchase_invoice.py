import frappe
from casecentral.case_central.doctype.book.book import fetch_book_details 

def create_book_on_submit(doc, method):
    create_book_on_purchase_invoice_value = frappe.db.get_single_value('Case Central Settings', 'create_book_on_purchase_invoice')

    if (create_book_on_purchase_invoice_value):
        for item in doc.items:
            if item.item_group == 'Books':
                item_code = item.item_code
                quantity = int(item.qty)

                for _ in range(quantity):
                    book = frappe.new_doc('Book')
                    book.item_code = item_code
                    book.purchase_invoice = doc.name
                    book.isbn = frappe.db.get_value('Item', item_code, 'isbn')
                    book.book_type = frappe.db.get_value('Item', item_code, 'book_type')
                    book.book_price = item.rate
                    book.insert()

                    book_details = fetch_book_details(book.isbn)
                    if book_details:
                        book.update(book_details)
                    book.save()
              
                frappe.msgprint('Books created successfully!')
    
