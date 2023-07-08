# Copyright (c) 2023, 4C Solutions and contributors
# For license information, please see license.txt

import frappe
import requests
from frappe.model.document import Document

class Book(Document):
	pass

@frappe.whitelist()
def fetch_book_details(isbn):
    book_doc = {}
    response = requests.get(f'https://www.googleapis.com/books/v1/volumes?q=isbn={isbn}')
    if response.ok:
        data = response.json()

        if 'items' in data and len(data['items']) > 0:
            book = data['items'][0]['volumeInfo']
            book_doc['isbn'] = isbn
            book_doc['book_title'] = book.get('title')
            book_doc['book_subtitle'] = book.get('subtitle')
            book_doc['author'] = ', '.join(book.get('authors', []))
            book_doc['category'] = ', '.join(book.get('categories', []))
            book_doc['publisher'] = book.get('publisher')
            book_doc['published_date'] = book.get('publishedDate')
            book_doc['page_count'] = book.get('pageCount')
            book_doc['preview_link'] = book.get('previewLink')
            book_doc['description'] = book.get('description')
            if book.get('imageLinks'):
                book_doc['book_image'] = book.get('imageLinks')['thumbnail']
            else:
                book_doc['book_image'] = '' 

            return book_doc
    else:
        status_code = response.status_code
        frappe.msgprint(f"Failed to fetch book details. Response code: {status_code}")

