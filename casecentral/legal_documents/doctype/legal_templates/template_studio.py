# Copyright (c) 2024, 4C Solutions and contributors
# For license information, please see license.txt

import os
import re
import io
import json
import requests
import mammoth
import tempfile
from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_COLOR_INDEX
from docx.enum.table import WD_TABLE_ALIGNMENT
from docxtpl import DocxTemplate
import frappe
from frappe.utils import get_files_path
from frappe.utils.file_manager import save_file
from bs4 import BeautifulSoup
from html4docx import HtmlToDocx


def _get_template_file_path(legal_template_name):
	"""Retrieves the absolute path of the template_file for a given Legal Template."""
	legal_template_doc = frappe.get_doc("Legal Templates", legal_template_name)
	template_file = legal_template_doc.template_file

	if not template_file:
		frappe.throw(frappe._("Please attach a Word document (.docx) first."))

	is_private = 1 if "private" in template_file else 0
	file_name = template_file.split("/")[-1]
	file_path = get_files_path(file_name, is_private=is_private)
	real_path = os.path.realpath(file_path)

	if not os.path.exists(real_path):
		frappe.throw(frappe._("Template file not found at {0}").format(real_path))

	return legal_template_doc, real_path


@frappe.whitelist()
def get_document_preview(legal_template_name):
	"""Converts the uploaded .docx file into clean HTML for Desk preview and returns raw text."""
	_, real_path = _get_template_file_path(legal_template_name)

	with open(real_path, "rb") as docx_file:
		result = mammoth.convert_to_html(docx_file)
		html = result.value

	# Also extract raw text for NLP/AI
	doc = Document(real_path)
	text_lines = []
	for p in doc.paragraphs:
		if p.text.strip():
			text_lines.append(p.text)
	for t in doc.tables:
		for row in t.rows:
			for cell in row.cells:
				if cell.text.strip():
					text_lines.append(cell.text)

	return {
		"html": html,
		"text": "\n".join(text_lines)
	}


@frappe.whitelist()
def get_available_ai_engines():
	"""Returns the status of AI integrations: Frappe Flow, Cloud API keys, or Local NLP."""
	flow_installed = "flow" in frappe.get_installed_apps()
	flow_models = []
	flow_providers = []
	has_flow_key = False

	if flow_installed and frappe.db.exists("DocType", "Flow Provider"):
		try:
			flow_models = frappe.get_all(
				"Flow Model",
				filters={"enabled": 1},
				fields=["name", "title", "model_id", "provider"]
			)
			flow_providers = frappe.get_all(
				"Flow Provider",
				filters={"enabled": 1},
				fields=["name", "provider"]
			)
			for prov in flow_providers:
				try:
					p_doc = frappe.get_doc("Flow Provider", prov["name"])
					if p_doc.get_password("api_key", raise_exception=False):
						has_flow_key = True
						break
				except Exception:
					pass
		except Exception:
			pass

	has_direct_key = bool(
		frappe.conf.get("gemini_api_key")
		or frappe.conf.get("groq_api_key")
		or frappe.db.get_default("gemini_api_key")
		or frappe.db.get_default("groq_api_key")
	)

	has_active_key = has_flow_key or has_direct_key

	return {
		"flow_installed": flow_installed,
		"flow_models": flow_models,
		"flow_providers": flow_providers,
		"has_direct_key": has_direct_key,
		"has_flow_key": has_flow_key,
		"has_active_key": has_active_key,
	}


def _clean_and_parse_json(content):
	"""Robust JSON parser that removes markdown blocks and extracts the valid JSON structure."""
	if not content:
		return {}
	txt = content.strip()
	if txt.startswith("```"):
		txt = re.sub(r'^```(?:json)?\s*', '', txt)
		txt = re.sub(r'\s*```$', '', txt)
	m = re.search(r'(\{[\s\S]*\}|\[[\s\S]*\])', txt)
	if m:
		txt = m.group(1)
	return json.loads(txt)


def _call_flow_ai(raw_text, custom_prompt=None, flow_model_name=None, api_key_override=None, expect_dict=False):
	"""
	Leverages Frappe Flow's native AI infrastructure (Flow Provider / Flow Model)
	to analyze documents, draft templates, extract variables, and track token usage.
	Flow AI is the mandatory generation engine.
	"""
	if not frappe.db.exists("DocType", "Flow Provider"):
		frappe.throw(frappe._("Frappe Flow Client AI is not installed. Please install the Flow app."))

	model_doc = None
	api_key = api_key_override
	model_id = None
	provider = None

	# 1. Resolve Flow Model
	if flow_model_name and frappe.db.exists("Flow Model", flow_model_name):
		model_doc = frappe.get_doc("Flow Model", flow_model_name)
	else:
		enabled_models = frappe.get_all("Flow Model", filters={"enabled": 1}, fields=["name", "model_id", "provider"], limit=1)
		if enabled_models:
			model_doc = frappe.get_doc("Flow Model", enabled_models[0]["name"])

	if model_doc:
		model_id = model_doc.model_id
		provider = model_doc.provider
		if not api_key:
			api_key = model_doc.get_password("api_key", raise_exception=False)

	# 2. Resolve from Flow Provider if model has no direct key
	if not api_key:
		if provider and frappe.db.exists("Flow Provider", provider):
			prov_doc = frappe.get_doc("Flow Provider", provider)
			if prov_doc.enabled:
				api_key = prov_doc.get_password("api_key", raise_exception=False)
		else:
			enabled_providers = frappe.get_all("Flow Provider", filters={"enabled": 1}, fields=["name", "provider"], limit=1)
			if enabled_providers:
				prov_doc = frappe.get_doc("Flow Provider", enabled_providers[0]["name"])
				api_key = prov_doc.get_password("api_key", raise_exception=False)
				provider = prov_doc.provider or prov_doc.name

	# 3. Resolve from site defaults if set
	if not api_key:
		site_key = frappe.db.get_default("gemini_api_key") or frappe.db.get_default("groq_api_key")
		if site_key:
			api_key = site_key
			provider = "groq" if site_key.startswith("gsk_") else "gemini"

	# If still no key, Flow AI cannot make the API call
	if not api_key:
		return None, None, None

	if not model_id:
		if provider == "groq" or (api_key and api_key.startswith("gsk_")):
			provider = "groq"
			model_id = "groq/llama-3.3-70b-versatile"
		elif provider == "openai" or (api_key and api_key.startswith("sk-")):
			provider = "openai"
			model_id = "openai/gpt-4o-mini"
		else:
			provider = "gemini"
			model_id = "gemini/gemini-3.5-flash"
	elif "1.5" in model_id or "2.5" in model_id:
		model_id = "gemini/gemini-3.5-flash"

	prompt = custom_prompt if custom_prompt else _get_legal_prompt(raw_text)

	# Try Flow Model class via LiteLLM if available
	try:
		from flow.lib.model import Model
		flow_m = Model(model_id=model_id, api_key=api_key)
		chat_res = flow_m.chat(prompt)
		if chat_res and chat_res.content:
			parsed = _clean_and_parse_json(chat_res.content)
			if not expect_dict and isinstance(parsed, dict):
				for k, v in parsed.items():
					if isinstance(v, list):
						parsed = v
						break
			usage = chat_res.usage or {
				"prompt_tokens": len(prompt) // 4,
				"completion_tokens": len(chat_res.content) // 4,
				"total_tokens": (len(prompt) + len(chat_res.content)) // 4
			}
			return parsed, usage, f"Flow AI ({model_id})"
	except Exception as err:
		frappe.log_error(f"Flow Model LiteLLM call: {str(err)}")

	# Execute Flow Provider direct API call
	ai_res, usage = _call_flow_provider_api(
		raw_text,
		api_key=api_key,
		provider=provider,
		model_id=model_id,
		custom_prompt=custom_prompt,
		expect_dict=expect_dict
	)
	return ai_res, usage, f"Flow AI ({model_id})"


def _call_flow_provider_api(raw_text, api_key, provider=None, model_id=None, custom_prompt=None, expect_dict=False):
	"""
	Executes the API call directly against the Flow Provider endpoint.
	Throws detailed errors if the provider returns failure so the user knows exactly what failed.
	"""
	prompt = custom_prompt if custom_prompt else _get_legal_prompt(raw_text)

	# 1. Groq Provider
	if (provider and provider.lower() == "groq") or api_key.startswith("gsk_"):
		url = "https://api.groq.com/openai/v1/chat/completions"
		headers = {
			"Authorization": f"Bearer {api_key}",
			"Content-Type": "application/json"
		}
		model_name = "llama-3.3-70b-versatile"
		if model_id and "/" in model_id:
			model_name = model_id.split("/")[-1]

		payload = {
			"model": model_name,
			"messages": [
				{"role": "system", "content": "You are an expert legal document automation AI. Return valid JSON only."},
				{"role": "user", "content": prompt}
			],
			"temperature": 0.1,
			"response_format": {"type": "json_object"}
		}
		try:
			res = requests.post(url, headers=headers, json=payload, timeout=60)
		except Exception as e:
			frappe.throw(frappe._("Flow AI (Groq) Connection Failed: {0}").format(str(e)))

		if res.status_code != 200:
			try:
				err_msg = res.json().get("error", {}).get("message") or res.text
			except Exception:
				err_msg = res.text
			frappe.throw(frappe._("Flow AI (Groq) API Call Failed (Status {0}): {1}").format(res.status_code, err_msg))

		data = res.json()
		content = data["choices"][0]["message"]["content"]
		parsed = _clean_and_parse_json(content)
		if not expect_dict and isinstance(parsed, dict):
			for k, v in parsed.items():
				if isinstance(v, list):
					parsed = v
					break
		usage = data.get("usage", {
			"prompt_tokens": len(prompt) // 4,
			"completion_tokens": len(content) // 4,
			"total_tokens": (len(prompt) + len(content)) // 4
		})
		return (parsed if isinstance(parsed, (list, dict)) else []), usage

	# 2. OpenAI Provider
	elif (provider and provider.lower() == "openai") or api_key.startswith("sk-"):
		url = "https://api.openai.com/v1/chat/completions"
		headers = {
			"Authorization": f"Bearer {api_key}",
			"Content-Type": "application/json"
		}
		model_name = "gpt-4o-mini"
		if model_id and "/" in model_id:
			model_name = model_id.split("/")[-1]

		payload = {
			"model": model_name,
			"messages": [
				{"role": "system", "content": "You are an expert legal document automation AI. Return valid JSON only."},
				{"role": "user", "content": prompt}
			],
			"temperature": 0.1,
			"response_format": {"type": "json_object"}
		}
		try:
			res = requests.post(url, headers=headers, json=payload, timeout=60)
		except Exception as e:
			frappe.throw(frappe._("Flow AI (OpenAI) Connection Failed: {0}").format(str(e)))

		if res.status_code != 200:
			try:
				err_msg = res.json().get("error", {}).get("message") or res.text
			except Exception:
				err_msg = res.text
			frappe.throw(frappe._("Flow AI (OpenAI) API Call Failed (Status {0}): {1}").format(res.status_code, err_msg))

		data = res.json()
		content = data["choices"][0]["message"]["content"]
		parsed = _clean_and_parse_json(content)
		if not expect_dict and isinstance(parsed, dict):
			for k, v in parsed.items():
				if isinstance(v, list):
					parsed = v
					break
		usage = data.get("usage", {
			"prompt_tokens": len(prompt) // 4,
			"completion_tokens": len(content) // 4,
			"total_tokens": (len(prompt) + len(content)) // 4
		})
		return (parsed if isinstance(parsed, (list, dict)) else []), usage

	# 3. Google Gemini Provider (Default)
	else:
		requested_model = "gemini-3.5-flash"
		if model_id and "/" in model_id:
			requested_model = model_id.split("/")[-1]
		elif model_id:
			requested_model = model_id

		if "1.5" in requested_model or "2.5" in requested_model:
			requested_model = "gemini-3.5-flash"

		candidates = [requested_model]
		for fallback_m in ["gemini-3.5-flash", "gemini-3.6-flash", "gemini-flash-latest", "gemini-3.8-flash"]:
			if fallback_m not in candidates:
				candidates.append(fallback_m)

		headers = {"Content-Type": "application/json"}
		payload = {
			"contents": [{"parts": [{"text": prompt}]}],
			"generationConfig": {
				"temperature": 0.1,
				"responseMimeType": "application/json"
			}
		}

		last_err = None
		last_status = None
		res = None

		for m_name in candidates:
			url = f"https://generativelanguage.googleapis.com/v1beta/models/{m_name}:generateContent?key={api_key}"
			try:
				res = requests.post(url, headers=headers, json=payload, timeout=45)
				if res.status_code == 200:
					break
				else:
					last_status = res.status_code
					try:
						last_err = res.json().get("error", {}).get("message") or res.text
					except Exception:
						last_err = res.text
			except Exception as e:
				last_err = str(e)

		if not res or res.status_code != 200:
			frappe.throw(frappe._("Flow AI (Gemini) API Call Failed (Status {0}): {1}").format(last_status or 500, last_err))

		data = res.json()
		text_res = data["candidates"][0]["content"]["parts"][0]["text"]
		parsed = _clean_and_parse_json(text_res)
		if not expect_dict and isinstance(parsed, dict):
			for k, v in parsed.items():
				if isinstance(v, list):
					parsed = v
					break

		usage_meta = data.get("usageMetadata", {})
		usage = {
			"prompt_tokens": usage_meta.get("promptTokenCount", len(prompt) // 4),
			"completion_tokens": usage_meta.get("candidatesTokenCount", len(text_res) // 4),
			"total_tokens": usage_meta.get("totalTokenCount", (len(prompt) + len(text_res)) // 4)
		}
		return (parsed if isinstance(parsed, (list, dict)) else []), usage


def _get_legal_prompt(raw_text):
	return f"""
You are an expert legal document automation AI.
Analyze this legal contract/document and identify ALL dynamic placeholder values that would change from client to client (e.g. party names, addresses, dates, currency amounts, phone numbers, email addresses, terms).

CRITICAL INSTRUCTIONS:
1. NEVER use generic names like "amount_1", "amount_2", "date_1", "var_1".
2. ALWAYS inspect the legal role, sentence context, and clause purpose:
   - Monthly rent -> variable_name: "monthly_rental_amount", label: "Monthly Rental Amount", fieldtype: "Currency"
   - Security deposit -> variable_name: "security_deposit", label: "Security Deposit", fieldtype: "Currency"
   - Agreement date -> variable_name: "agreement_date", label: "Agreement Date", fieldtype: "Date"
   - Lease commencement -> variable_name: "lease_commencement_date", label: "Lease Commencement Date", fieldtype: "Date"
   - Landlord / Lessor name -> variable_name: "landlord_name", label: "Landlord Name", fieldtype: "Data"
   - Tenant / Lessee name -> variable_name: "tenant_name", label: "Tenant Name", fieldtype: "Data"
   - Landlord address -> variable_name: "landlord_address", label: "Landlord Address", fieldtype: "Small Text"
   - Tenant address -> variable_name: "tenant_address", label: "Tenant Address", fieldtype: "Small Text"
   - Tenant phone/email -> variable_name: "tenant_phone" / "tenant_email", fieldtype: "Data"

Document Text:
\"\"\"{raw_text[:12000]}\"\"\"

Return ONLY a valid JSON array of objects with this schema:
[
  {{
    "original_text": "Exact text substring as it appears in document",
    "variable_name": "clean_snake_case_variable_name",
    "label": "Human Readable Label",
    "fieldtype": "Any valid Frappe Fieldtype (e.g. Data, Date, Currency, Small Text, Int, Float, Percent, Phone, Signature, Text, Select, Link)"
  }}
]
Do not include markdown blocks or any conversational text. Return pure JSON only.
"""


def _get_drafting_prompt(user_prompt):
	return f"""
You are an elite Senior Partner and Head of Commercial & Legal Drafting at a premier global corporate law firm.
Your drafting standard is Tier-1 law firm perfection (equivalent to premier corporate firms like Cyril Amarchand Mangaldas, Khaitan & Co, Clifford Chance, Latham & Watkins).

The user has provided this request:
"{user_prompt}"

CRITICAL DIRECTIVE ON DEPTH AND LAW-FIRM PROFESSIONALISM:
1. Regardless of how brief, concise, or general the user's prompt is (even if it is just a few words like "commercial lease" or "consulting agreement" or "employment contract"), YOU MUST AUTONOMOUSLY DRAFT AN EXHAUSTIVE, BULLETPROOF, PRODUCTION-GRADE LEGAL AGREEMENT that can be presented directly to corporate counsel, advocates, and law firm clients.
2. Under NO circumstances should you produce a brief summary, outline, high-level overview, or 3-4 clause stub. The output MUST be a comprehensive, fully drafted legal instrument containing 12 to 18 exhaustive numbered sections with deep, formal legal prose.
3. Every operative clause must be written in authoritative legal English ("shall", "covenants", "undertakes", "warrants", "indemnifies", "in consideration whereof").
4. ALL dynamic values that should vary per transaction must be strictly formatted as Jinja tags: {{{{ variable_name }}}}.
   Examples of dynamic fields that MUST be templated:
   - Parties: {{{{ party_1_name }}}}, {{{{ party_1_address }}}}, {{{{ party_1_cin_or_pan }}}}, {{{{ party_1_authorized_signatory }}}}, {{{{ party_1_signatory_designation }}}}, {{{{ party_1_email }}}}, {{{{ party_1_phone }}}}
   - Counterparty: {{{{ party_2_name }}}}, {{{{ party_2_address }}}}, {{{{ party_2_cin_or_pan }}}}, {{{{ party_2_authorized_signatory }}}}, {{{{ party_2_signatory_designation }}}}, {{{{ party_2_email }}}}, {{{{ party_2_phone }}}}
   - Dates & Term: {{{{ agreement_date }}}}, {{{{ execution_place }}}}, {{{{ commencement_date }}}}, {{{{ expiry_date }}}}, {{{{ lock_in_period_months }}}}, {{{{ renewal_notice_period_days }}}}
   - Commercials: {{{{ consideration_amount }}}}, {{{{ payment_due_day }}}}, {{{{ late_payment_interest_pct }}}}, {{{{ security_deposit }}}}, {{{{ annual_escalation_pct }}}}
   - Legal/Operational: {{{{ project_scope_description }}}}, {{{{ notice_period_days }}}}, {{{{ cure_period_days }}}}, {{{{ liquidated_damages_amount }}}}, {{{{ governing_law_country }}}}, {{{{ dispute_resolution_city }}}}, {{{{ arbitration_seat_city }}}}
   - Witnesses: {{{{ witness_1_name }}}}, {{{{ witness_1_address }}}}, {{{{ witness_2_name }}}}, {{{{ witness_2_address }}}}

MANDATORY SECTIONS TO INCLUDE IN THE AGREEMENT (at least 12-16 sections):
1. Title in ALL CAPS (e.g. "COMMERCIAL LEASE & TENANCY AGREEMENT", "EXECUTIVE EMPLOYMENT & CONFIDENTIALITY AGREEMENT", "INDEPENDENT CONTRACTOR & MASTER SERVICES AGREEMENT").
2. Formal Preamble specifying date ({{{{ agreement_date }}}}), place ({{{{ execution_place }}}}), and comprehensive legal descriptions of both parties.
3. Recitals: Minimum 2 to 4 detailed "WHEREAS" clauses establishing legal capacity, operational background, mutual intention, and valuable consideration.
4. Operative Transition: "NOW, THEREFORE, IN CONSIDERATION OF THE MUTUAL COVENANTS, TERMS, CONDITIONS AND CONSIDERATIONS SET FORTH HEREIN, AND OTHER GOOD AND VALUABLE CONSIDERATION, THE RECEIPT AND SUFFICIENCY OF WHICH ARE HEREBY MUTUALLY ACKNOWLEDGED, THE PARTIES HERETO AGREE AS FOLLOWS:"
5. Numbered Operative Sections (ALL numbered, formal, and comprehensive):
   - Section 1: Definitions and Interpretation (define key capitalized terms and statutory rules of construction).
   - Section 2: Scope of Engagement / Demise / Core Subject Matter / Permitted Use / Deliverables.
   - Section 3: Term, Duration, Lock-in Period & Renewal Mechanism.
   - Section 4: Commercial Consideration, Fees / Rent, Escalation, Invoicing & Payment Terms (including 18% p.a. default interest, banking terms, TDS/GST).
   - Section 5: Security Deposit / Performance Guarantee / Advances (holding terms, deduction conditions, interest-free refund).
   - Section 6: Obligations and Covenants of Party 1.
   - Section 7: Obligations and Covenants of Party 2.
   - Section 8: Representations and Warranties of Both Parties (corporate power, legal validity, no conflict with laws/decrees, valid licenses).
   - Section 9: Intellectual Property Rights, Work-for-Hire & Ownership (absolute assignment, waiver of moral rights, IP indemnification).
   - Section 10: Confidentiality, Trade Secrets & Non-Disclosure (broad definition, standard of care, permitted disclosures, 3-5 year survival).
   - Section 11: Restrictive Covenants (Non-Compete and Non-Solicitation of clients, staff, contractors).
   - Section 12: Indemnification and Defense (mutual/unilateral indemnification against third-party claims, breaches, gross negligence, attorney fees).
   - Section 13: Limitation of Liability (waiver of consequential damages, liability cap).
   - Section 14: Events of Default, Cure Periods & Termination (termination for convenience, termination for material breach with 15-30 days cure notice, insolvency, post-termination handover and survival).
   - Section 15: Force Majeure (standard unforeseen disruptions, notification, mitigation, exit upon extended stoppage).
   - Section 16: Dispute Resolution & Formal Institutional Arbitration (30-day amicable conciliation, sole arbitrator appointment, seat & venue, language, finality of award, cost allocation).
   - Section 17: Governing Law and Exclusive Court Jurisdiction (applicable substantive law, exclusive territorial jurisdiction).
   - Section 18: Miscellaneous Boilerplate (Notices & deemed delivery, Entire Agreement, Written Amendments only, Severability, No Waiver, Independent Contractors, Counterparts & Electronic Execution).
6. Key Terms & Commercial Particulars Table ("particulars_table"):
   - Exhaustive schedule containing 14 to 25 essential commercial and operational particulars with their Jinja tags.
7. Execution Clause ("IN WITNESS WHEREOF..."):
   - Dual-column signature blocks for both parties with Authorized Signatory Name, Designation, Entity, Date, and Place.
8. Attestation by Two Independent Witnesses:
   - Witness 1 and Witness 2 blocks with Signature line, Name, Address, and Phone.
9. Variables List ("variables"):
   - Complete list of all 15 to 30 dynamic variables with variable_name (snake_case), label, fieldtype (Any valid Frappe Fieldtype e.g. Data, Date, Currency, Small Text, Int, Float, Percent, Phone, Signature, Select, Link), and original_text.

Return ONLY a valid JSON object matching EXACTLY this JSON structure:
{{
  "document_title": "FULL CONTRACT TITLE IN ALL CAPS",
  "template_name": "Short clean title for template (e.g. Commercial Lease Agreement)",
  "preamble": "This [Agreement Name] (the \\"Agreement\\") is entered into on this {{{{ agreement_date }}}} at {{{{ execution_place }}}} by and between:",
  "parties": [
    {{
      "role": "FIRST PARTY / LANDLORD / EMPLOYER / CLIENT",
      "text": "{{{{ party_1_name }}}}, a company incorporated under the laws of [Jurisdiction] having its registered office at {{{{ party_1_address }}}}, Corporate Identity / Registration Number: {{{{ party_1_cin_or_pan }}}}, represented by its authorized signatory {{{{ party_1_authorized_signatory }}}}, {{{{ party_1_signatory_designation }}}} (hereinafter referred to as \\"Party 1\\", which expression shall unless repugnant to the context include its successors and permitted assigns); and"
    }},
    {{
      "role": "SECOND PARTY / TENANT / EMPLOYEE / CONSULTANT",
      "text": "{{{{ party_2_name }}}}, residing at / having registered office at {{{{ party_2_address }}}}, Identification / PAN / Registration No.: {{{{ party_2_cin_or_pan }}}}, represented by {{{{ party_2_authorized_signatory }}}} (hereinafter referred to as \\"Party 2\\", which expression shall unless repugnant to the context include its successors, legal heirs, and permitted assigns)."
    }}
  ],
  "recitals": [
    "WHEREAS, Party 1 is engaged in...",
    "WHEREAS, Party 2 possesses specialized expertise...",
    "WHEREAS, the Parties have agreed to enter into this Agreement upon the terms and mutual covenants hereinafter contained."
  ],
  "sections": [
    {{
      "title": "1. Definitions and Interpretation",
      "paragraphs": [
        "In this Agreement, unless the context otherwise requires, capitalized terms shall have the meanings assigned herein...",
        "Headings and subheadings are inserted for convenience of reference only and shall not affect the interpretation or construction of any clause."
      ]
    }},
    {{
      "title": "2. Scope of Engagement and Core Subject Matter",
      "paragraphs": [
        "Party 1 hereby engages Party 2, and Party 2 accepts such engagement to perform {{{{ project_scope_description }}}} in accordance with highest professional standards...",
        "..."
      ]
    }},
    {{
      "title": "3. Term, Duration and Lock-in Period",
      "paragraphs": [
        "This Agreement shall become effective on {{{{ commencement_date }}}} (the \\"Effective Date\\") and shall remain valid and binding until {{{{ expiry_date }}}}...",
        "The Parties agree to a mandatory lock-in period of {{{{ lock_in_period_months }}}} months from the Effective Date, during which neither party may terminate for convenience."
      ]
    }},
    {{
      "title": "4. Commercial Considerations, Fees and Payment Terms",
      "paragraphs": [
        "In consideration of the satisfactory covenants herein, Party 1 shall pay Party 2 the sum of {{{{ consideration_amount }}}} payable on or before the {{{{ payment_due_day }}}} of each calendar month...",
        "Any delayed payment shall accrue late interest at the rate of {{{{ late_payment_interest_pct }}}}% per annum from the due date until actual realization.",
        "All payments shall be subject to applicable statutory deductions including tax deducted at source (TDS) and goods and services tax (GST)."
      ]
    }},
    {{
      "title": "5. Security Deposit and Financial Guarantees",
      "paragraphs": [
        "Party 2 shall furnish an interest-free refundable security deposit of {{{{ security_deposit }}}} to Party 1 upon execution of this Agreement...",
        "The security deposit shall be refunded within {{{{ deposit_refund_days }}}} days following expiration or earlier termination, subject to deductions for unpaid dues or damages."
      ]
    }},
    {{
      "title": "6. Representations and Warranties",
      "paragraphs": [
        "Each Party represents and warrants to the other that: (a) it is duly organized, validly existing, and in good standing under the laws of its jurisdiction; (b) it possesses full corporate power, authority, and legal right to execute and deliver this Agreement; and (c) the execution and performance of this Agreement does not and will not conflict with or violate any applicable statute, decree, or prior contractual obligation."
      ]
    }},
    {{
      "title": "7. Intellectual Property Rights and Work-for-Hire",
      "paragraphs": [
        "All deliverables, materials, inventions, software, documentation, and work product developed or conceived under this Agreement shall constitute work made for hire and shall be the exclusive proprietary property of {{{{ ip_owner_name }}}} from inception.",
        "Party 2 hereby irrevocably assigns, transfers, and conveys all right, title, interest, and intellectual property rights in perpetuity on a worldwide basis."
      ]
    }},
    {{
      "title": "8. Confidentiality and Non-Disclosure",
      "paragraphs": [
        "Each Party agrees that all business, technical, commercial, financial, and operational information disclosed under this Agreement shall be kept strictly confidential.",
        "The receiving party shall not disclose Confidential Information to any third party without prior written authorization, and such confidentiality covenants shall survive the expiration or termination of this Agreement for a period of {{{{ confidentiality_survival_years }}}} years."
      ]
    }},
    {{
      "title": "9. Restrictive Covenants and Non-Solicitation",
      "paragraphs": [
        "During the subsistence of this Agreement and for a period of {{{{ non_compete_duration_months }}}} months following its termination, neither Party shall directly or indirectly solicit, induce, or hire any employee, consultant, or client of the other Party."
      ]
    }},
    {{
      "title": "10. Indemnification and Defense",
      "paragraphs": [
        "Each Party covenants to defend, indemnify, and hold harmless the other Party, its directors, officers, employees, and agents from and against all claims, liabilities, losses, damages, penalties, and legal expenses (including reasonable attorney fees) arising out of any material breach of warranty, negligence, statutory non-compliance, or third-party infringement."
      ]
    }},
    {{
      "title": "11. Limitation of Liability",
      "paragraphs": [
        "Neither Party shall be liable to the other for any indirect, incidental, punitive, special, or consequential damages, including loss of profits, data, or business goodwill.",
        "The aggregate liability of either Party arising out of or related to this Agreement shall be capped at the total consideration paid or payable under this Agreement in the preceding {{{{ liability_cap_months }}}} months."
      ]
    }},
    {{
      "title": "12. Events of Default, Cure Periods and Termination",
      "paragraphs": [
        "Either Party may terminate this Agreement for convenience by providing {{{{ notice_period_days }}}} days prior written notice following the expiry of the lock-in period.",
        "Either Party may terminate immediately upon written notice if the other Party commits a material breach and fails to remedy such breach within {{{{ cure_period_days }}}} days of receiving written notice specifying the breach."
      ]
    }},
    {{
      "title": "13. Force Majeure",
      "paragraphs": [
        "Neither Party shall be held liable for any failure or delay in performance caused by circumstances beyond its reasonable control, including acts of God, flood, earthquake, epidemic, war, civil commotion, or government embargo.",
        "If a Force Majeure event continues uninterrupted for more than {{{{ force_majeure_limit_days }}}} days, either Party may terminate this Agreement without penalty."
      ]
    }},
    {{
      "title": "14. Dispute Resolution and Institutional Arbitration",
      "paragraphs": [
        "Any dispute, controversy, or claim arising out of or in connection with this Agreement shall first be submitted to good-faith mutual conciliation for a period of 30 days.",
        "In the event conciliation fails, the dispute shall be finally referred to and resolved by binding arbitration conducted by a sole arbitrator mutually agreed upon by the Parties.",
        "The seat and legal venue of arbitration shall be {{{{ dispute_resolution_city }}}}, and the proceedings shall be conducted in the English language in accordance with statutory arbitration laws."
      ]
    }},
    {{
      "title": "15. Governing Law and Exclusive Court Jurisdiction",
      "paragraphs": [
        "This Agreement shall be governed by, construed, and enforced in accordance with the substantive laws of {{{{ governing_law_country }}}}.",
        "Subject to the arbitration clause, the competent courts at {{{{ dispute_resolution_city }}}} shall have sole and exclusive territorial jurisdiction over any judicial proceeding arising hereunder."
      ]
    }},
    {{
      "title": "16. Miscellaneous Boilerplate Provisions",
      "paragraphs": [
        "16.1 Notices: All formal notices shall be in writing and delivered by registered post or verified electronic mail to the addresses specified in the Preamble.",
        "16.2 Entire Agreement: This Agreement constitutes the entire and sole agreement between the Parties and supersedes all prior oral or written discussions, proposals, and understandings.",
        "16.3 Amendments: No modification or amendment of this Agreement shall be valid unless executed in writing and signed by authorized signatories of both Parties.",
        "16.4 Severability: If any provision is held invalid or unenforceable, such invalidity shall not affect the remaining provisions, which shall continue in full legal force.",
        "16.5 Counterparts: This Agreement may be executed in counterparts, each of which shall be deemed an original, and electronic or digital signatures shall be deemed legally binding."
      ]
    }}
  ],
  "particulars_table": [
    {{"particular": "Agreement Name", "value": "Full Title"}},
    {{"particular": "Execution Date", "value": "{{{{ agreement_date }}}}"}},
    {{"particular": "Place of Execution", "value": "{{{{ execution_place }}}}"}},
    {{"particular": "First Party / Entity", "value": "{{{{ party_1_name }}}}"}},
    {{"particular": "Party 1 Registered Address", "value": "{{{{ party_1_address }}}}"}},
    {{"particular": "Party 1 Identification / PAN", "value": "{{{{ party_1_cin_or_pan }}}}"}},
    {{"particular": "Party 1 Authorized Signatory", "value": "{{{{ party_1_authorized_signatory }}}}"}},
    {{"particular": "Second Party / Entity", "value": "{{{{ party_2_name }}}}"}},
    {{"particular": "Party 2 Registered Address", "value": "{{{{ party_2_address }}}}"}},
    {{"particular": "Party 2 Identification / PAN", "value": "{{{{ party_2_cin_or_pan }}}}"}},
    {{"particular": "Party 2 Authorized Signatory", "value": "{{{{ party_2_authorized_signatory }}}}"}},
    {{"particular": "Commencement Date", "value": "{{{{ commencement_date }}}}"}},
    {{"particular": "Expiration Date", "value": "{{{{ expiry_date }}}}"}},
    {{"particular": "Lock-in Period", "value": "{{{{ lock_in_period_months }}}} Months"}},
    {{"particular": "Commercial Consideration", "value": "{{{{ consideration_amount }}}}"}},
    {{"particular": "Payment Due Date", "value": "{{{{ payment_due_day }}}} of each month"}},
    {{"particular": "Security Deposit", "value": "{{{{ security_deposit }}}}"}},
    {{"particular": "Notice Period", "value": "{{{{ notice_period_days }}}} Days"}},
    {{"particular": "Cure Period", "value": "{{{{ cure_period_days }}}} Days"}},
    {{"particular": "Governing Jurisdiction", "value": "{{{{ dispute_resolution_city }}}}"}}
  ],
  "execution_clause": "IN WITNESS WHEREOF, the Parties hereto have caused this Agreement to be duly executed and delivered by their respective authorized signatories as of the date first above written.",
  "parties_sign": [
    {{"role": "For Party 1", "name": "{{{{ party_1_name }}}}", "signatory": "{{{{ party_1_authorized_signatory }}}}", "designation": "{{{{ party_1_signatory_designation }}}}"}},
    {{"role": "For Party 2", "name": "{{{{ party_2_name }}}}", "signatory": "{{{{ party_2_authorized_signatory }}}}", "designation": "{{{{ party_2_signatory_designation }}}}"}}
  ],
  "variables": [
    {{"variable_name": "party_1_name", "label": "Party 1 Name", "fieldtype": "Data", "original_text": "{{{{ party_1_name }}}}"}},
    {{"variable_name": "party_1_address", "label": "Party 1 Registered Address", "fieldtype": "Small Text", "original_text": "{{{{ party_1_address }}}}"}},
    {{"variable_name": "party_1_cin_or_pan", "label": "Party 1 CIN / PAN / Tax ID", "fieldtype": "Data", "original_text": "{{{{ party_1_cin_or_pan }}}}"}},
    {{"variable_name": "party_1_authorized_signatory", "label": "Party 1 Authorized Signatory", "fieldtype": "Data", "original_text": "{{{{ party_1_authorized_signatory }}}}"}},
    {{"variable_name": "party_1_signatory_designation", "label": "Party 1 Signatory Designation", "fieldtype": "Data", "original_text": "{{{{ party_1_signatory_designation }}}}"}},
    {{"variable_name": "party_2_name", "label": "Party 2 Name", "fieldtype": "Data", "original_text": "{{{{ party_2_name }}}}"}},
    {{"variable_name": "party_2_address", "label": "Party 2 Address", "fieldtype": "Small Text", "original_text": "{{{{ party_2_address }}}}"}},
    {{"variable_name": "party_2_cin_or_pan", "label": "Party 2 CIN / PAN / Tax ID", "fieldtype": "Data", "original_text": "{{{{ party_2_cin_or_pan }}}}"}},
    {{"variable_name": "party_2_authorized_signatory", "label": "Party 2 Authorized Signatory", "fieldtype": "Data", "original_text": "{{{{ party_2_authorized_signatory }}}}"}},
    {{"variable_name": "party_2_signatory_designation", "label": "Party 2 Signatory Designation", "fieldtype": "Data", "original_text": "{{{{ party_2_signatory_designation }}}}"}},
    {{"variable_name": "agreement_date", "label": "Agreement Execution Date", "fieldtype": "Date", "original_text": "{{{{ agreement_date }}}}"}},
    {{"variable_name": "execution_place", "label": "Execution Place", "fieldtype": "Data", "original_text": "{{{{ execution_place }}}}"}},
    {{"variable_name": "commencement_date", "label": "Commencement Date", "fieldtype": "Date", "original_text": "{{{{ commencement_date }}}}"}},
    {{"variable_name": "expiry_date", "label": "Expiry Date", "fieldtype": "Date", "original_text": "{{{{ expiry_date }}}}"}},
    {{"variable_name": "lock_in_period_months", "label": "Lock-in Period (Months)", "fieldtype": "Int", "original_text": "{{{{ lock_in_period_months }}}}"}},
    {{"variable_name": "consideration_amount", "label": "Consideration / Fee / Rent Amount", "fieldtype": "Currency", "original_text": "{{{{ consideration_amount }}}}"}},
    {{"variable_name": "payment_due_day", "label": "Payment Due Day", "fieldtype": "Int", "original_text": "{{{{ payment_due_day }}}}"}},
    {{"variable_name": "security_deposit", "label": "Security Deposit / Guarantee", "fieldtype": "Currency", "original_text": "{{{{ security_deposit }}}}"}},
    {{"variable_name": "notice_period_days", "label": "Termination Notice Period (Days)", "fieldtype": "Int", "original_text": "{{{{ notice_period_days }}}}"}},
    {{"variable_name": "cure_period_days", "label": "Default Cure Period (Days)", "fieldtype": "Int", "original_text": "{{{{ cure_period_days }}}}"}},
    {{"variable_name": "dispute_resolution_city", "label": "Jurisdiction / Arbitration City", "fieldtype": "Data", "original_text": "{{{{ dispute_resolution_city }}}}"}},
    {{"variable_name": "witness_1_name", "label": "Witness 1 Name", "fieldtype": "Data", "original_text": "{{{{ witness_1_name }}}}"}},
    {{"variable_name": "witness_1_address", "label": "Witness 1 Address", "fieldtype": "Small Text", "original_text": "{{{{ witness_1_address }}}}"}},
    {{"variable_name": "witness_2_name", "label": "Witness 2 Name", "fieldtype": "Data", "original_text": "{{{{ witness_2_name }}}}"}},
    {{"variable_name": "witness_2_address", "label": "Witness 2 Address", "fieldtype": "Small Text", "original_text": "{{{{ witness_2_address }}}}"}}
  ]
}}
Do not include conversational preamble or markdown code blocks outside of JSON. Output valid JSON only.
"""


def create_docx_from_ai_structure(doc_data, output_path):
	"""
	Takes structured legal document JSON from Flow AI and creates an executive-grade Word (.docx) document
	with professional legal styling, typography, particulars table, signature blocks, and witness attestation.
	"""
	doc = Document()

	for section in doc.sections:
		section.top_margin = Inches(1.0)
		section.bottom_margin = Inches(1.0)
		section.left_margin = Inches(1.0)
		section.right_margin = Inches(1.0)

	# 1. Document Title
	title_text = doc_data.get("document_title") or doc_data.get("template_name") or "LEGAL AGREEMENT"
	title_p = doc.add_paragraph()
	title_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
	title_p.paragraph_format.space_before = Pt(0)
	title_p.paragraph_format.space_after = Pt(18)
	title_run = title_p.add_run(title_text.upper())
	title_run.font.name = "Calibri"
	title_run.font.size = Pt(16)
	title_run.font.bold = True
	title_run.font.color.rgb = RGBColor(15, 23, 42)

	# 2. Preamble
	preamble = doc_data.get("preamble")
	if preamble:
		p = doc.add_paragraph()
		p.paragraph_format.space_after = Pt(8)
		p.paragraph_format.line_spacing = 1.15
		r = p.add_run(preamble)
		r.font.name = "Calibri"
		r.font.size = Pt(11)

	# 3. Parties
	parties = doc_data.get("parties", [])
	for idx, party in enumerate(parties, 1):
		party_text = party.get("text") if isinstance(party, dict) else str(party)
		p = doc.add_paragraph()
		p.paragraph_format.left_indent = Inches(0.25)
		p.paragraph_format.space_after = Pt(6)
		p.paragraph_format.line_spacing = 1.15
		
		r_num = p.add_run(f"{idx}. ")
		r_num.font.name = "Calibri"
		r_num.font.bold = True
		r_num.font.size = Pt(11)
		
		r_txt = p.add_run(party_text)
		r_txt.font.name = "Calibri"
		r_txt.font.size = Pt(11)

	# 4. Recitals (WHEREAS)
	recitals = doc_data.get("recitals", [])
	if recitals:
		rec_p = doc.add_paragraph()
		rec_p.paragraph_format.space_before = Pt(8)
		rec_p.paragraph_format.space_after = Pt(4)
		r_w = rec_p.add_run("RECITALS:")
		r_w.font.name = "Calibri"
		r_w.font.bold = True
		r_w.font.size = Pt(11)

		for rec in recitals:
			p = doc.add_paragraph()
			p.paragraph_format.left_indent = Inches(0.25)
			p.paragraph_format.space_after = Pt(5)
			p.paragraph_format.line_spacing = 1.15
			r = p.add_run(rec if isinstance(rec, str) else str(rec))
			r.font.name = "Calibri"
			r.font.size = Pt(11)

	# Operative transition
	op_p = doc.add_paragraph()
	op_p.paragraph_format.space_before = Pt(8)
	op_p.paragraph_format.space_after = Pt(10)
	r_op = op_p.add_run("NOW, THEREFORE, the Parties agree as follows:")
	r_op.font.name = "Calibri"
	r_op.font.bold = True
	r_op.font.size = Pt(11)

	# 5. Operative Sections / Clauses
	sections = doc_data.get("sections", [])
	for sec in sections:
		sec_title = sec.get("title") or sec.get("section_title") or "Clause"
		sp = doc.add_paragraph()
		sp.paragraph_format.space_before = Pt(12)
		sp.paragraph_format.space_after = Pt(4)
		s_run = sp.add_run(sec_title)
		s_run.font.name = "Calibri"
		s_run.font.bold = True
		s_run.font.size = Pt(12)
		s_run.font.color.rgb = RGBColor(30, 41, 59)

		for para in sec.get("paragraphs", []):
			pp = doc.add_paragraph()
			pp.paragraph_format.space_after = Pt(6)
			pp.paragraph_format.line_spacing = 1.15
			prun = pp.add_run(para)
			prun.font.name = "Calibri"
			prun.font.size = Pt(11)

	# 6. Key Terms & Particulars Table
	particulars = doc_data.get("particulars_table", [])
	if particulars:
		tp = doc.add_paragraph()
		tp.paragraph_format.space_before = Pt(16)
		tp.paragraph_format.space_after = Pt(8)
		t_run = tp.add_run("Key Terms & Particulars")
		t_run.font.name = "Calibri"
		t_run.font.bold = True
		t_run.font.size = Pt(13)
		t_run.font.color.rgb = RGBColor(15, 23, 42)

		table = doc.add_table(rows=1, cols=2)
		table.alignment = WD_TABLE_ALIGNMENT.CENTER
		table.autofit = False

		hdr_cells = table.rows[0].cells
		hdr_cells[0].width = Inches(2.5)
		hdr_cells[1].width = Inches(4.0)

		for idx, heading in enumerate(["Key Particular", "Agreed Terms / Details"]):
			cell = hdr_cells[idx]
			cell.paragraphs[0].paragraph_format.space_before = Pt(4)
			cell.paragraphs[0].paragraph_format.space_after = Pt(4)
			hrun = cell.paragraphs[0].add_run(heading)
			hrun.font.name = "Calibri"
			hrun.font.bold = True
			hrun.font.size = Pt(10.5)

		for item in particulars:
			row_cells = table.add_row().cells
			row_cells[0].width = Inches(2.5)
			row_cells[1].width = Inches(4.0)
			
			part_label = item.get("particular") or item.get("item") or ""
			part_val = item.get("value") or item.get("value_tag") or ""

			p0 = row_cells[0].paragraphs[0]
			p0.paragraph_format.space_before = Pt(3)
			p0.paragraph_format.space_after = Pt(3)
			r0 = p0.add_run(part_label)
			r0.font.name = "Calibri"
			r0.font.bold = True
			r0.font.size = Pt(10)

			p1 = row_cells[1].paragraphs[0]
			p1.paragraph_format.space_before = Pt(3)
			p1.paragraph_format.space_after = Pt(3)
			r1 = p1.add_run(part_val)
			r1.font.name = "Calibri"
			r1.font.size = Pt(10)

	# 7. Execution Clause & Signatures
	exec_clause = doc_data.get("execution_clause") or "IN WITNESS WHEREOF, the Parties have executed this Agreement on the day and year first above written."
	ep = doc.add_paragraph()
	ep.paragraph_format.space_before = Pt(18)
	ep.paragraph_format.space_after = Pt(14)
	ep.paragraph_format.line_spacing = 1.15
	e_run = ep.add_run(exec_clause)
	e_run.font.name = "Calibri"
	e_run.font.bold = True
	e_run.font.size = Pt(11)

	parties_sign = doc_data.get("parties_sign") or [
		{"role": "Party 1", "name": "{{ party_1_name }}"},
		{"role": "Party 2", "name": "{{ party_2_name }}"}
	]
	sig_table = doc.add_table(rows=1, cols=len(parties_sign))
	sig_table.alignment = WD_TABLE_ALIGNMENT.CENTER
	sig_cells = sig_table.rows[0].cells

	col_w = Inches(6.5 / len(parties_sign))
	for idx, sign in enumerate(parties_sign):
		cell = sig_cells[idx]
		cell.width = col_w
		p = cell.paragraphs[0]
		p.paragraph_format.space_before = Pt(6)
		p.paragraph_format.space_after = Pt(4)
		
		r_role = p.add_run(f"{sign.get('role', 'Party')}:\n\n")
		r_role.font.name = "Calibri"
		r_role.font.bold = True
		r_role.font.size = Pt(10.5)

		r_line = p.add_run("______________________________\n")
		r_line.font.name = "Calibri"
		r_line.font.size = Pt(10)

		r_name = p.add_run(f"Name: {sign.get('name', '')}\n")
		r_name.font.name = "Calibri"
		r_name.font.size = Pt(10)

		signatory = sign.get("signatory") or sign.get("authorized_signatory")
		if signatory:
			r_sig = p.add_run(f"Authorized Signatory: {signatory}\n")
			r_sig.font.name = "Calibri"
			r_sig.font.size = Pt(10)

		desig = sign.get("designation") or sign.get("signatory_designation")
		if desig:
			r_des = p.add_run(f"Designation: {desig}\n")
			r_des.font.name = "Calibri"
			r_des.font.size = Pt(10)

		r_date = p.add_run("Date: {{ execution_date }}\n")
		r_date.font.name = "Calibri"
		r_date.font.size = Pt(10)

	# 8. Witness Attestation
	wp = doc.add_paragraph()
	wp.paragraph_format.space_before = Pt(20)
	wp.paragraph_format.space_after = Pt(8)
	w_run = wp.add_run("IN THE PRESENCE OF WITNESSES:")
	w_run.font.name = "Calibri"
	w_run.font.bold = True
	w_run.font.size = Pt(11)

	witness_table = doc.add_table(rows=1, cols=2)
	witness_table.alignment = WD_TABLE_ALIGNMENT.CENTER
	w_cells = witness_table.rows[0].cells
	w_col_w = Inches(3.25)

	for w_idx, w_label in enumerate(["WITNESS 1", "WITNESS 2"], 1):
		w_cell = w_cells[w_idx - 1]
		w_cell.width = w_col_w
		wp_cell = w_cell.paragraphs[0]
		wp_cell.paragraph_format.space_before = Pt(4)
		wp_cell.paragraph_format.space_after = Pt(4)

		r_w_lbl = wp_cell.add_run(f"{w_label}:\n\n")
		r_w_lbl.font.name = "Calibri"
		r_w_lbl.font.bold = True
		r_w_lbl.font.size = Pt(10)

		r_w_sig = wp_cell.add_run("Signature: ___________________________\n")
		r_w_sig.font.name = "Calibri"
		r_w_sig.font.size = Pt(9.5)

		r_w_name = wp_cell.add_run(f"Name: {{{{ witness_{w_idx}_name }}}}\n")
		r_w_name.font.name = "Calibri"
		r_w_name.font.size = Pt(9.5)

		r_w_addr = wp_cell.add_run(f"Address: {{{{ witness_{w_idx}_address }}}}\n")
		r_w_addr.font.name = "Calibri"
		r_w_addr.font.size = Pt(9.5)

	highlight_all_jinja_tags_in_docx(doc)
	doc.save(output_path)
	return output_path


def extract_existing_jinja_variables(raw_text, related_doctype=None):
	"""
	Extracts any pre-existing Jinja placeholder tags in the document: {{ variable_name }}.
	If the template has a related DocType, matches exact field labels and types.
	"""
	jinja_pattern = re.compile(r'\{\{\s*([a-zA-Z0-9_]+)\s*\}\}')
	existing_vars = []
	seen = set()

	doctype_fields = {}
	if related_doctype and frappe.db.exists("DocType", related_doctype):
		try:
			dt_doc = frappe.get_doc("DocType", related_doctype)
			for f in dt_doc.fields:
				if f.fieldname not in ("naming_series", "matter", "amended_from", "sb_doc_info", "cb_doc_info"):
					doctype_fields[f.fieldname] = {
						"label": f.label or f.fieldname.replace("_", " ").title(),
						"fieldtype": f.fieldtype or "Data"
					}
		except Exception:
			pass

	for m in jinja_pattern.finditer(raw_text):
		full_tag = m.group(0)
		vname = m.group(1).strip()
		if not vname or vname in seen:
			continue
		seen.add(vname)

		meta = doctype_fields.get(vname, {})
		label = meta.get("label") or vname.replace("_", " ").title()
		ftype = meta.get("fieldtype")

		if not ftype:
			vlower = vname.lower()
			if any(t in vlower for t in ["amount", "rent", "deposit", "fee", "price", "charges"]):
				ftype = "Currency"
			elif any(t in vlower for t in ["date", "expiry", "commencement"]):
				ftype = "Date"
			elif "address" in vlower:
				ftype = "Small Text"
			else:
				ftype = "Data"

		existing_vars.append({
			"original_text": full_tag,
			"variable_name": vname,
			"label": label,
			"fieldtype": ftype
		})

	return existing_vars


def _smart_nlp_extract_variables(raw_text):
	"""
	Rule-based / regex legal NLP variable extraction fallback.
	Extracts parties, addresses, dates, currency amounts, phones, percentages, and signatures.
	"""
	variables = []
	seen_texts = set()

	def add_var(orig_text, var_name, label, fieldtype):
		clean_orig = orig_text.strip().rstrip(".,;:")
		if not clean_orig or clean_orig in seen_texts or len(clean_orig) < 2:
			return
		seen_texts.add(clean_orig)
		variables.append({
			"original_text": clean_orig,
			"variable_name": frappe.scrub(var_name),
			"label": label,
			"fieldtype": fieldtype
		})

	# 1. Currency amounts
	currency_pattern = re.compile(r'(?:Rs\.?|INR|USD|\$|₹|AED|EUR|£)\s*[\d,]+(?:\.\d{2})?')
	for m in currency_pattern.finditer(raw_text):
		val = m.group(0)
		start, end = m.start(), m.end()
		ctx = raw_text[max(0, start - 100):min(len(raw_text), end + 60)].lower()
		if any(k in ctx for k in ["monthly rent", "rental sum", "rent of", "rent per month"]):
			add_var(val, "monthly_rental_amount", "Monthly Rental Amount", "Currency")
		elif any(k in ctx for k in ["security deposit", "interest-free", "caution deposit"]):
			add_var(val, "security_deposit", "Security Deposit", "Currency")
		elif any(k in ctx for k in ["maintenance charges", "society maintenance"]):
			add_var(val, "maintenance_charges", "Maintenance Charges", "Currency")
		elif any(k in ctx for k in ["consideration", "purchase price", "fee", "compensation"]):
			add_var(val, "consideration_amount", "Consideration Amount", "Currency")
		else:
			add_var(val, f"amount_{len(variables)+1}", f"Amount {len(variables)+1}", "Currency")

	# 2. Dates
	date_patterns = [
		r'\b\d{1,2}(?:st|nd|rd|th)?\s+(?:January|February|March|April|May|June|July|August|September|October|November|December),?\s+\d{4}\b',
		r'\b(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2}(?:st|nd|rd|th)?,?\s+\d{4}\b',
		r'\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b'
	]
	for dp in date_patterns:
		for m in re.finditer(dp, raw_text, re.IGNORECASE):
			val = m.group(0)
			start, end = m.start(), m.end()
			ctx = raw_text[max(0, start - 100):min(len(raw_text), end + 60)].lower()
			if any(k in ctx for k in ["executed on", "agreement date", "entered into on", "dated this", "dated:"]):
				add_var(val, "agreement_date", "Agreement Date", "Date")
			elif any(k in ctx for k in ["commencing from", "commencement", "effective from", "starting from"]):
				add_var(val, "commencement_date", "Commencement Date", "Date")
			elif any(k in ctx for k in ["expiring on", "expiry date", "termination date", "valid till"]):
				add_var(val, "expiry_date", "Expiry Date", "Date")
			else:
				add_var(val, f"date_{len(variables)+1}", f"Date {len(variables)+1}", "Date")

	# 3. Phone numbers
	phone_pattern = re.compile(r'(?:\+?\d{1,3}[-.\s]?)?\(?\d{3,4}\)?[-.\s]?\d{3,4}[-.\s]?\d{3,4}\b')
	for m in phone_pattern.finditer(raw_text):
		val = m.group(0).strip()
		if len(re.sub(r'\D', '', val)) >= 10:
			add_var(val, f"phone_{len(variables)+1}", f"Phone Number {len(variables)+1}", "Phone")

	# 4. Percentages
	pct_pattern = re.compile(r'\b\d{1,2}(?:\.\d{1,2})?\s*%\b')
	for m in pct_pattern.finditer(raw_text):
		val = m.group(0).strip()
		add_var(val, f"percentage_{len(variables)+1}", f"Percentage {len(variables)+1}", "Percent")

	return variables


@frappe.whitelist()
def detect_variables(legal_template_name, api_key=None, provider="auto", flow_model=None):
	"""
	Analyzes the document text and structure using Frappe Flow AI.
	Mandatory Flow AI API call - does not silently fall back to offline NLP.
	Also extracts and preserves any pre-existing Jinja variables in already-generated templates.
	"""
	legal_template_doc, real_path = _get_template_file_path(legal_template_name)
	preview_data = get_document_preview(legal_template_name)
	raw_text = preview_data["text"]

	if not raw_text.strip():
		frappe.throw(frappe._("The uploaded template document contains no readable text."))

	def sort_by_appearance(var_list):
		def get_order(v):
			orig = v.get("original_text", "")
			pos = raw_text.find(orig)
			if pos == -1:
				pos = raw_text.lower().find(orig.lower())
			return pos if pos != -1 else 999999
		return sorted(var_list, key=get_order)

	# 1. Extract any existing Jinja variables already embedded in this template
	existing_jinja_vars = extract_existing_jinja_variables(
		raw_text=raw_text,
		related_doctype=legal_template_doc.related_doctype
	)

	# If user supplied a key in request, sync it to Flow Provider
	if api_key:
		save_ai_key(api_key, provider=provider)

	# 2. Execute via Flow AI if key exists or user passed key
	flow_vars, usage, flow_engine = None, None, None
	try:
		flow_vars, usage, flow_engine = _call_flow_ai(raw_text, flow_model_name=flow_model, api_key_override=api_key)
	except Exception as flow_err:
		frappe.log_error(title="Flow AI Variable Detection Fallback", message=str(flow_err))
		# If Flow AI encounters an issue (e.g. 503 high demand or API quota), fall back to Smart Legal NLP
		# so the user is never blocked from opening and working in AI Template Studio!
		flow_vars = _smart_nlp_extract_variables(raw_text)
		flow_engine = "Built-in Smart Legal NLP"
		usage = {
			"prompt_tokens": len(raw_text.split()),
			"completion_tokens": len(flow_vars) * 15,
			"total_tokens": len(raw_text.split()) + len(flow_vars) * 15
		}

	# If no Flow AI key is configured
	if not flow_vars and not flow_engine:
		if existing_jinja_vars:
			# The template was already generated! Return existing variables so user can view/edit
			return {
				"status": "success",
				"variables": sort_by_appearance(existing_jinja_vars),
				"engine_used": "Template Jinja Variables",
				"token_usage": None,
				"total_count": len(existing_jinja_vars),
				"flow_installed": True,
				"message": f"Loaded {len(existing_jinja_vars)} existing Jinja variables from template."
			}
		else:
			return {
				"status": "needs_key",
				"variables": [],
				"engine_used": "Flow AI (Awaiting API Key)",
				"token_usage": None,
				"total_count": 0,
				"flow_installed": True,
				"message": "Flow AI is the mandatory generation engine. Please configure your Flow Provider or enter an API Key in Flow AI Settings to generate the template."
			}

	# Merge existing Jinja tags with Flow AI extracted variables
	merged_vars = []
	seen_varnames = set()

	for v in (existing_jinja_vars or []):
		vname = v.get("variable_name")
		if vname and vname not in seen_varnames:
			seen_varnames.add(vname)
			merged_vars.append(v)

	for v in (flow_vars or []):
		vname = v.get("variable_name")
		if vname and vname not in seen_varnames:
			seen_varnames.add(vname)
			merged_vars.append(v)

	sorted_vars = sort_by_appearance(merged_vars)

	return {
		"status": "warning" if flow_engine == "Built-in Smart Legal NLP" else "success",
		"variables": sorted_vars,
		"engine_used": flow_engine or "Flow AI",
		"token_usage": usage,
		"total_count": len(sorted_vars),
		"flow_installed": True,
		"message": ("Flow AI was unavailable; loaded variables with Built-in Smart Legal NLP so you can continue editing." if flow_engine == "Built-in Smart Legal NLP" else "")
	}


def synthesize_legal_agreement_from_prompt(user_prompt):
	"""
	Built-in, Tier-1 Law Firm Legal Synthesis Engine.
	Analyzes user prompt, determines the contract archetype, extracts business terms,
	and synthesizes an exhaustive, production-grade legal document structure complete with
	numbered operative clauses, comprehensive covenants, particulars schedule, recitals,
	authorized signature blocks, and witness attestation.
	"""
	p_lower = user_prompt.lower()

	# Extract potential monetary amounts from prompt (e.g. ₹50,000 or $10,000 or 50,000 INR)
	extracted_amount = None
	m_amt = re.search(r'([₹\$€£]\s*[\d,]+(?:\.\d+)?|[\d,]+(?:\.\d+)?\s*(?:inr|usd|eur|rupees))', user_prompt, re.IGNORECASE)
	if m_amt:
		extracted_amount = m_amt.group(1).strip()

	# Extract potential duration (e.g., 12 months, 3 years, 30 days)
	extracted_duration = None
	m_dur = re.search(r'(\d+)\s*(months?|years?|days?|weeks?)', user_prompt, re.IGNORECASE)
	if m_dur:
		extracted_duration = m_dur.group(0).strip()

	# Extract potential city
	extracted_city = "Mumbai"
	for city in ["Mumbai", "Delhi", "Bangalore", "Bengaluru", "Hyderabad", "Chennai", "Kolkata", "Pune", "Ahmedabad", "Gurugram", "Noida", "New York", "London", "Singapore", "Dubai"]:
		if city.lower() in p_lower:
			extracted_city = city
			break

	# 1. Residential Rental & Tenancy Agreement
	if any(k in p_lower for k in ["residential", "apartment", "flat", "house", "tenancy", "pg", "room"]) and not any(k in p_lower for k in ["office", "commercial", "warehouse", "showroom"]):
		doc_title = "RESIDENTIAL RENTAL & APARTMENT LEASE AGREEMENT"
		tpl_name = "Residential Rental Agreement"
		prefix = "RNT"
		parties = [
			{"role": "LESSOR / LANDLORD", "text": "{{ landlord_name }}, residing at {{ landlord_permanent_address }}, holding National ID / PAN: {{ landlord_id_number }}, Contact Phone: {{ landlord_phone }}, Email: {{ landlord_email }} (hereinafter referred to as the \"LANDLORD\"); and"},
			{"role": "LESSEE / TENANT", "text": "{{ tenant_name }}, residing at {{ tenant_permanent_address }}, holding National ID / PAN: {{ tenant_id_number }}, Contact Phone: {{ tenant_phone }}, Email: {{ tenant_email }} (hereinafter referred to as the \"TENANT\")."}
		]
		recitals = [
			"WHEREAS, the Landlord is the sole, absolute, and lawful owner and in peaceful possession of the residential property situated at {{ residential_premises_address }} (hereinafter referred to as the \"Demised Premises\");",
			"WHEREAS, the Tenant has approached the Landlord to take on lease the Demised Premises strictly for private residential accommodation for self and immediate family members;",
			"WHEREAS, the Landlord, relying upon the Tenant's representations and covenants, has agreed to demise the property upon the terms and mutual considerations set forth herein."
		]
		sections = [
			{
				"title": "1. Demise and Description of Residential Premises",
				"paragraphs": [
					"The Landlord hereby demises to the Tenant, and the Tenant accepts on tenancy, the residential apartment situated at {{ residential_premises_address }}, comprising {{ number_of_bedrooms }} bedrooms, living room, kitchen, and bathrooms, together with the electrical, sanitary, and wood fixtures inventoried in Annexure A.",
					"The Demised Premises shall be used exclusively for peaceful residential purposes by the Tenant and immediate family, and under no circumstances shall the premises be used for commercial, business, professional, or unlawful purposes."
				]
			},
			{
				"title": "2. Lease Term, Lock-in Period and Renewal",
				"paragraphs": [
					f"This Agreement shall commence on {{{{ lease_commencement_date }}}} and shall remain valid and subsisting for a term of {{{{ lease_duration_months }}}} months (estimated at {extracted_duration or '11 months'}), expiring on {{{{ lease_expiry_date }}}}.",
					"The Parties agree to a mandatory lock-in period of {{ lock_in_period_months }} months from the Commencement Date, during which neither party may terminate this tenancy without incurring penalty.",
					"Any renewal or extension of this tenancy shall be executed in writing by mutual consent at least {{ renewal_notice_days }} days prior to expiration, subject to revised rental terms."
				]
			},
			{
				"title": "3. Monthly Rent, Due Date and Payment Terms",
				"paragraphs": [
					f"The Tenant shall pay to the Landlord a monthly rental sum of {{{{ monthly_rent_amount }}}} (estimated at {extracted_amount or '₹35,000 INR'}) on or before the {{{{ rent_due_day }}}} day of each calendar month.",
					"Rent shall be paid directly into the Landlord's designated bank account: {{ landlord_bank_account_details }}.",
					"Any delay in payment beyond the due date shall attract late payment interest at the rate of {{ late_rent_interest_pct }}% per month, calculated on a daily pro-rata basis until cleared."
				]
			},
			{
				"title": "4. Interest-Free Refundable Security Deposit",
				"paragraphs": [
					"The Tenant has deposited with the Landlord an interest-free refundable security deposit of {{ security_deposit }} upon execution of this Agreement.",
					"The Security Deposit shall be maintained with the Landlord throughout the tenancy and shall be refunded to the Tenant within {{ deposit_refund_days }} days following peaceful handover of vacant possession, subject to deduction of unpaid rent, utility dues, or costs of repairing damages beyond normal wear and tear."
				]
			},
			{
				"title": "5. Utilities, Electricity and Society Maintenance Charges",
				"paragraphs": [
					"The Tenant covenants to punctually pay all electricity, domestic water, cooking gas, internet, and recurring housing society maintenance charges amounting to {{ monthly_society_maintenance }} directly to the respective authorities or resident welfare association.",
					"The Landlord shall remain responsible for the discharge of statutory property taxes and municipal assessments."
				]
			},
			{
				"title": "6. Tenant Covenants, Care and Prohibitions",
				"paragraphs": [
					"The Tenant covenants to maintain the Demised Premises in a state of good repair, cleanliness, and tenantable condition.",
					"The Tenant shall not make any structural additions, alterations, or puncture load-bearing walls without the prior written consent of the Landlord.",
					"The Tenant shall not store any hazardous, inflammable, combustible, or illegal substances on the premises, nor commit any act causing public nuisance to neighbors or violating building bylaws."
				]
			},
			{
				"title": "7. Landlord Covenants and Quiet Enjoyment",
				"paragraphs": [
					"The Landlord covenants that upon the Tenant punctually paying the agreed rent and observing the covenants herein, the Tenant shall peacefully and quietly enjoy the Demised Premises without unlawful eviction, hindrance, or interference by the Landlord.",
					"The Landlord shall be responsible for all major structural repairs, dampness, and roof seepage not caused by the Tenant's negligence."
				]
			},
			{
				"title": "8. Inspection and Access Rights",
				"paragraphs": [
					"The Landlord or authorized agents shall have the right to inspect the condition of the Demised Premises during reasonable daylight hours by providing at least {{ inspection_notice_hours }} hours prior notice to the Tenant."
				]
			},
			{
				"title": "9. Prohibition Against Subletting and Assignment",
				"paragraphs": [
					"The Tenant shall not assign, sublet, transfer, or part with possession of the Demised Premises or any portion thereof to any third party, paying guest, or licensee under any arrangement whatsoever."
				]
			},
			{
				"title": "10. Routine Repairs and Maintenance",
				"paragraphs": [
					"Minor day-to-day repairs of electrical switches, bulbs, water tap washers, and sanitary fittings costing up to {{ minor_repair_limit_amount }} per incident shall be borne by the Tenant. All major structural repairs shall be executed by the Landlord."
				]
			},
			{
				"title": "11. Termination, Vacating Notice and Peaceful Surrender",
				"paragraphs": [
					"Following the expiry of the lock-in period, either party may terminate this Agreement by issuing {{ notice_period_days }} days prior written notice to the other.",
					"Upon termination or expiration, the Tenant shall peacefully vacate and hand over vacant, unencumbered possession of the premises and original keys to the Landlord in the same condition as received, reasonable wear and tear excepted."
				]
			},
			{
				"title": "12. Stamp Duty, Registration and Police Verification",
				"paragraphs": [
					"All stamp duty, statutory registration charges, and documentation expenses shall be shared between the Parties in accordance with {{ stamp_duty_sharing_terms }}.",
					"The Tenant covenants to submit all mandatory identity verification documents for local police tenant verification within 7 days of execution."
				]
			},
			{
				"title": "13. Dispute Resolution and Governing Law",
				"paragraphs": [
					f"This Agreement shall be governed by and interpreted under the applicable laws of India. Courts at {{{{ jurisdiction_city }}}} (exclusive jurisdiction: {extracted_city}) shall have sole and exclusive jurisdiction."
				]
			},
			{
				"title": "14. Entire Agreement and Severability",
				"paragraphs": [
					"This Agreement constitutes the entire understanding between the Parties and supersedes all prior oral or written negotiations. If any clause is deemed invalid, the remaining provisions shall continue in full legal force."
				]
			}
		]
		particulars = [
			{"particular": "Landlord Full Name", "value": "{{ landlord_name }}"},
			{"particular": "Landlord Contact Phone", "value": "{{ landlord_phone }}"},
			{"particular": "Tenant Full Name", "value": "{{ tenant_name }}"},
			{"particular": "Tenant Contact Phone", "value": "{{ tenant_phone }}"},
			{"particular": "Premises Address", "value": "{{ residential_premises_address }}"},
			{"particular": "Bedrooms / Layout", "value": "{{ number_of_bedrooms }} BHK"},
			{"particular": "Monthly Rental Amount", "value": "{{ monthly_rent_amount }}"},
			{"particular": "Rent Due Day", "value": "{{ rent_due_day }} of each month"},
			{"particular": "Refundable Security Deposit", "value": "{{ security_deposit }}"},
			{"particular": "Deposit Refund Timeline", "value": "{{ deposit_refund_days }} Days post-handover"},
			{"particular": "Lease Commencement Date", "value": "{{ lease_commencement_date }}"},
			{"particular": "Lease Expiration Date", "value": "{{ lease_expiry_date }}"},
			{"particular": "Lock-in Period", "value": "{{ lock_in_period_months }} Months"},
			{"particular": "Vacating Notice Period", "value": "{{ notice_period_days }} Days"},
			{"particular": "Society Maintenance Dues", "value": "{{ monthly_society_maintenance }}"},
			{"particular": "Minor Repair Cap", "value": "{{ minor_repair_limit_amount }}"},
			{"particular": "Governing Jurisdiction", "value": "{{ jurisdiction_city }}"},
			{"particular": "Witness 1 Name", "value": "{{ witness_1_name }}"},
			{"particular": "Witness 2 Name", "value": "{{ witness_2_name }}"}
		]
		vars_list = [
			{"variable_name": "landlord_name", "label": "Landlord Full Name", "fieldtype": "Data"},
			{"variable_name": "landlord_permanent_address", "label": "Landlord Permanent Address", "fieldtype": "Small Text"},
			{"variable_name": "landlord_id_number", "label": "Landlord ID / PAN", "fieldtype": "Data"},
			{"variable_name": "landlord_phone", "label": "Landlord Contact Phone", "fieldtype": "Data"},
			{"variable_name": "landlord_email", "label": "Landlord Contact Email", "fieldtype": "Data"},
			{"variable_name": "tenant_name", "label": "Tenant Full Name", "fieldtype": "Data"},
			{"variable_name": "tenant_permanent_address", "label": "Tenant Permanent Address", "fieldtype": "Small Text"},
			{"variable_name": "tenant_id_number", "label": "Tenant ID / PAN", "fieldtype": "Data"},
			{"variable_name": "tenant_phone", "label": "Tenant Contact Phone", "fieldtype": "Data"},
			{"variable_name": "tenant_email", "label": "Tenant Contact Email", "fieldtype": "Data"},
			{"variable_name": "residential_premises_address", "label": "Residential Premises Address", "fieldtype": "Small Text"},
			{"variable_name": "number_of_bedrooms", "label": "Number of Bedrooms (BHK)", "fieldtype": "Data"},
			{"variable_name": "monthly_rent_amount", "label": "Monthly Rental Amount", "fieldtype": "Currency"},
			{"variable_name": "rent_due_day", "label": "Rent Due Day", "fieldtype": "Int"},
			{"variable_name": "security_deposit", "label": "Refundable Security Deposit", "fieldtype": "Currency"},
			{"variable_name": "deposit_refund_days", "label": "Deposit Refund Timeline (Days)", "fieldtype": "Int"},
			{"variable_name": "lease_commencement_date", "label": "Lease Commencement Date", "fieldtype": "Date"},
			{"variable_name": "lease_expiry_date", "label": "Lease Expiry Date", "fieldtype": "Date"},
			{"variable_name": "lock_in_period_months", "label": "Lock-in Period (Months)", "fieldtype": "Int"},
			{"variable_name": "notice_period_days", "label": "Vacating Notice Period (Days)", "fieldtype": "Int"},
			{"variable_name": "monthly_society_maintenance", "label": "Monthly Society Maintenance", "fieldtype": "Currency"},
			{"variable_name": "jurisdiction_city", "label": "Jurisdiction City", "fieldtype": "Data"},
			{"variable_name": "witness_1_name", "label": "Witness 1 Full Name", "fieldtype": "Data"},
			{"variable_name": "witness_1_address", "label": "Witness 1 Address", "fieldtype": "Small Text"},
			{"variable_name": "witness_2_name", "label": "Witness 2 Full Name", "fieldtype": "Data"},
			{"variable_name": "witness_2_address", "label": "Witness 2 Address", "fieldtype": "Small Text"}
		]

	# 2. Commercial Lease & Premises Tenancy Agreement
	elif any(k in p_lower for k in ["lease", "rent", "rental", "tenant", "landlord", "premises", "property", "shop", "office", "commercial", "showroom", "warehouse", "factory"]):
		doc_title = "COMMERCIAL LEASE & PREMISES TENANCY AGREEMENT"
		tpl_name = "Commercial Lease Agreement"
		prefix = "COM"
		parties = [
			{"role": "LESSOR / LANDLORD", "text": "{{ landlord_company_name }}, a company incorporated under applicable law, having its registered office at {{ landlord_registered_address }}, CIN / Tax ID: {{ landlord_cin_or_pan }}, represented by its Authorized Signatory {{ landlord_signatory_name }}, {{ landlord_signatory_designation }} (hereinafter referred to as the \"LANDLORD\"); and"},
			{"role": "LESSEE / TENANT", "text": "{{ tenant_company_name }}, a company incorporated under applicable law, having its registered office at {{ tenant_registered_address }}, CIN / Tax ID: {{ tenant_cin_or_pan }}, represented by its Authorized Signatory {{ tenant_signatory_name }}, {{ tenant_signatory_designation }} (hereinafter referred to as the \"TENANT\")."}
		]
		recitals = [
			"WHEREAS, the Landlord is the sole and absolute owner of the commercial building and premises situated at {{ leased_premises_address }} (hereinafter the \"Commercial Premises\");",
			"WHEREAS, the Tenant has verified the Landlord's title and requested to take on commercial lease the said premises for its corporate commercial operations;",
			"WHEREAS, the Landlord has agreed to demise the Commercial Premises to the Tenant on the terms, covenants, and commercial considerations set forth herein."
		]
		sections = [
			{
				"title": "1. Demise and Description of Commercial Premises",
				"paragraphs": [
					"The Landlord hereby demises to the Tenant, and the Tenant takes on lease, all that commercial space measuring approximately {{ chargeable_carpet_area_sqft }} sq. ft. of chargeable carpet area situated at {{ leased_premises_address }}, City: {{ premises_city }}, State: {{ premises_state }}, together with dedicated parking bays {{ dedicated_car_parking_slots }} and access to common areas.",
					"The Tenant confirms that it has inspected the premises and accepts the same on an 'as-is-where-is' basis for conducting permitted commercial operations."
				]
			},
			{
				"title": "2. Permitted Commercial Use and Statutory Approvals",
				"paragraphs": [
					"The Commercial Premises shall be utilized exclusively for {{ permitted_commercial_use }} and ancillary administrative activities.",
					"The Tenant covenants to obtain and maintain at its own cost all trade licenses, municipal permissions, environmental clearances, and statutory registrations required to operate its commercial enterprise upon the premises."
				]
			},
			{
				"title": "3. Lease Term, Mandatory Lock-in and Renewal Mechanism",
				"paragraphs": [
					f"The lease term shall commence on {{{{ lease_commencement_date }}}} (the \"Commencement Date\") and shall expire on {{{{ lease_expiry_date }}}} (the \"Expiry Date\"), spanning a tenure of {{{{ lease_tenure_years }}}} years (estimated at {extracted_duration or '3 years'}).",
					"Both Parties unconditionally agree to a mandatory lock-in period of {{ lock_in_period_months }} months from the Commencement Date, during which neither party may terminate this lease without paying the balance rent for the remainder of the lock-in period as liquidated damages.",
					"The Tenant shall have the option to renew this Lease for a further term of {{ renewal_term_years }} years by issuing written notice at least {{ renewal_notice_days }} days prior to expiration, subject to mutual agreement on revised commercial rent."
				]
			},
			{
				"title": "4. Monthly Commercial Rent, Escalation and Payment Terms",
				"paragraphs": [
					f"The Tenant covenants to pay to the Landlord a monthly commercial rental fee of {{{{ monthly_rent_amount }}}} (estimated at {extracted_amount or '₹65,000 INR'}), payable in advance on or before the {{{{ rent_due_day }}}} day of each calendar month.",
					"The monthly rent shall automatically escalate by {{ annual_rent_escalation_pct }}% upon the completion of every 12 months from the Commencement Date.",
					"Any delay in payment shall attract late interest at the rate of {{ late_payment_interest_pct }}% per annum from the due date until full payment.",
					"All payments shall be made via electronic wire transfer to {{ landlord_bank_details }}, subject to deduction of statutory tax at source (TDS) against valid certificates, and applicable Goods and Services Tax (GST) shall be payable over and above the rent."
				]
			},
			{
				"title": "5. Interest-Free Refundable Security Deposit",
				"paragraphs": [
					"The Tenant shall maintain with the Landlord an interest-free refundable security deposit of {{ security_deposit }} throughout the lease tenure.",
					"The Security Deposit shall be refunded to the Tenant within {{ deposit_refund_days }} days of peaceful handover of vacant possession, subject to deduction of unpaid rent, utility dues, or damages to the premises beyond normal wear and tear."
				]
			},
			{
				"title": "6. Common Area Maintenance, Utilities and Property Taxes",
				"paragraphs": [
					"The Tenant shall pay all metered electricity, water, high-speed data, and recurring Common Area Maintenance (CAM) charges amounting to {{ monthly_cam_charges }} per month.",
					"The Landlord shall be responsible for punctually discharging municipal property taxes, non-agricultural cess, and ground rent applicable to the building."
				]
			},
			{
				"title": "7. Fit-outs, Signage and Interior Modifications",
				"paragraphs": [
					"The Tenant may, at its own expense, install demountable partitions, interior fit-outs, and IT cabling, provided that no structural beams, columns, or load-bearing elements are altered without the Landlord's prior written approval.",
					"The Tenant shall be entitled to install corporate branding and signage at designated facade locations in compliance with municipal regulations."
				]
			},
			{
				"title": "8. Inspection Rights and Landlord Covenants",
				"paragraphs": [
					"The Landlord warrants that it has clear, marketable title and full authority to lease the premises and covenants that the Tenant shall enjoy peaceful, quiet possession without interruption during the lease term.",
					"The Landlord may inspect the premises during business hours upon giving at least {{ inspection_notice_hours }} hours prior written notice."
				]
			},
			{
				"title": "9. Prohibition Against Subletting and Assignment",
				"paragraphs": [
					"The Tenant shall not assign, sublease, mortgage, pledge, or create any third-party interest in the Commercial Premises or any portion thereof without the prior written consent of the Landlord."
				]
			},
			{
				"title": "10. Insurance, Risk and Indemnification",
				"paragraphs": [
					"The Tenant covenants to maintain comprehensive commercial general liability insurance and property insurance covering its equipment, inventory, and staff.",
					"Each Party covenants to defend, indemnify, and hold harmless the other Party against all third-party claims, penalties, or losses resulting from its negligence or breach of covenants."
				]
			},
			{
				"title": "11. Damage, Destruction and Force Majeure",
				"paragraphs": [
					"If the Commercial Premises are damaged by earthquake, fire, flood, or act of God so as to render them unfit for commercial use, the rent shall abate pro-rata until restored.",
					"If restoration cannot be accomplished within {{ restoration_period_days }} days, either Party may terminate this Lease without penalty."
				]
			},
			{
				"title": "12. Events of Default, Cure Periods and Termination",
				"paragraphs": [
					"An Event of Default shall occur if: (a) the Tenant fails to pay rent for two consecutive months; or (b) either Party commits a material breach and fails to cure such breach within {{ cure_period_days }} days of receiving written notice.",
					"Following the expiry of the lock-in period, either Party may terminate this Agreement for convenience by giving {{ notice_period_days }} days prior written notice."
				]
			},
			{
				"title": "13. Peaceful Vacant Handover and Re-possession",
				"paragraphs": [
					"Upon expiry or earlier termination, the Tenant shall peacefully vacate and hand over unencumbered possession of the premises to the Landlord.",
					"If the Tenant fails to vacate upon termination, the Tenant shall be deemed an unauthorized trespasser and shall pay liquidated damages of {{ unauthorized_holding_daily_penalty }} per day until actual physical possession is surrendered."
				]
			},
			{
				"title": "14. Dispute Resolution and Institutional Arbitration",
				"paragraphs": [
					f"Any dispute arising out of or in connection with this Lease shall first be submitted to conciliation for 30 days. In the event conciliation fails, the dispute shall be resolved through binding arbitration by a sole arbitrator in accordance with the Arbitration and Conciliation Act, with the seat and venue at {{{{ dispute_resolution_city }}}} (exclusive city: {extracted_city})."
				]
			},
			{
				"title": "15. Governing Law, Jurisdiction and Boilerplate",
				"paragraphs": [
					"This Lease shall be governed by the laws of India, and courts at {{ jurisdiction_city }} shall possess exclusive jurisdiction.",
					"This Agreement represents the entire understanding between the Parties, and no modification shall be valid unless executed in writing by authorized signatories."
				]
			}
		]
		particulars = [
			{"particular": "Landlord Entity", "value": "{{ landlord_company_name }}"},
			{"particular": "Landlord Registered Address", "value": "{{ landlord_registered_address }}"},
			{"particular": "Tenant Entity", "value": "{{ tenant_company_name }}"},
			{"particular": "Tenant Registered Address", "value": "{{ tenant_registered_address }}"},
			{"particular": "Commercial Premises Address", "value": "{{ leased_premises_address }}"},
			{"particular": "Chargeable Carpet Area", "value": "{{ chargeable_carpet_area_sqft }} Sq. Ft."},
			{"particular": "Permitted Commercial Use", "value": "{{ permitted_commercial_use }}"},
			{"particular": "Monthly Commercial Rent", "value": "{{ monthly_rent_amount }}"},
			{"particular": "Annual Rent Escalation", "value": "{{ annual_rent_escalation_pct }}% Per Annum"},
			{"particular": "Rent Due Day", "value": "{{ rent_due_day }} of each month"},
			{"particular": "Refundable Security Deposit", "value": "{{ security_deposit }}"},
			{"particular": "Deposit Refund Timeline", "value": "{{ deposit_refund_days }} Days"},
			{"particular": "Lease Commencement Date", "value": "{{ lease_commencement_date }}"},
			{"particular": "Lease Expiration Date", "value": "{{ lease_expiry_date }}"},
			{"particular": "Lock-in Period", "value": "{{ lock_in_period_months }} Months"},
			{"particular": "Termination Notice Period", "value": "{{ notice_period_days }} Days"},
			{"particular": "Default Cure Period", "value": "{{ cure_period_days }} Days"},
			{"particular": "Monthly CAM Charges", "value": "{{ monthly_cam_charges }}"},
			{"particular": "Governing Jurisdiction", "value": "{{ jurisdiction_city }}"},
			{"particular": "Witness 1 Name", "value": "{{ witness_1_name }}"},
			{"particular": "Witness 2 Name", "value": "{{ witness_2_name }}"}
		]
		vars_list = [
			{"variable_name": "landlord_company_name", "label": "Landlord Company Name", "fieldtype": "Data"},
			{"variable_name": "landlord_registered_address", "label": "Landlord Registered Address", "fieldtype": "Small Text"},
			{"variable_name": "landlord_cin_or_pan", "label": "Landlord CIN / PAN", "fieldtype": "Data"},
			{"variable_name": "landlord_signatory_name", "label": "Landlord Authorized Signatory", "fieldtype": "Data"},
			{"variable_name": "landlord_signatory_designation", "label": "Landlord Signatory Designation", "fieldtype": "Data"},
			{"variable_name": "tenant_company_name", "label": "Tenant Company Name", "fieldtype": "Data"},
			{"variable_name": "tenant_registered_address", "label": "Tenant Registered Address", "fieldtype": "Small Text"},
			{"variable_name": "tenant_cin_or_pan", "label": "Tenant CIN / PAN", "fieldtype": "Data"},
			{"variable_name": "tenant_signatory_name", "label": "Tenant Authorized Signatory", "fieldtype": "Data"},
			{"variable_name": "tenant_signatory_designation", "label": "Tenant Signatory Designation", "fieldtype": "Data"},
			{"variable_name": "leased_premises_address", "label": "Leased Commercial Premises Address", "fieldtype": "Small Text"},
			{"variable_name": "premises_city", "label": "Premises City", "fieldtype": "Data"},
			{"variable_name": "premises_state", "label": "Premises State", "fieldtype": "Data"},
			{"variable_name": "chargeable_carpet_area_sqft", "label": "Chargeable Carpet Area (Sq. Ft.)", "fieldtype": "Int"},
			{"variable_name": "permitted_commercial_use", "label": "Permitted Commercial Use", "fieldtype": "Data"},
			{"variable_name": "monthly_rent_amount", "label": "Monthly Rent Amount", "fieldtype": "Currency"},
			{"variable_name": "annual_rent_escalation_pct", "label": "Annual Rent Escalation (%)", "fieldtype": "Percent"},
			{"variable_name": "rent_due_day", "label": "Rent Due Day", "fieldtype": "Int"},
			{"variable_name": "security_deposit", "label": "Refundable Security Deposit", "fieldtype": "Currency"},
			{"variable_name": "deposit_refund_days", "label": "Deposit Refund Timeline (Days)", "fieldtype": "Int"},
			{"variable_name": "lease_commencement_date", "label": "Lease Commencement Date", "fieldtype": "Date"},
			{"variable_name": "lease_expiry_date", "label": "Lease Expiry Date", "fieldtype": "Date"},
			{"variable_name": "lock_in_period_months", "label": "Lock-in Period (Months)", "fieldtype": "Int"},
			{"variable_name": "notice_period_days", "label": "Notice Period (Days)", "fieldtype": "Int"},
			{"variable_name": "cure_period_days", "label": "Default Cure Period (Days)", "fieldtype": "Int"},
			{"variable_name": "monthly_cam_charges", "label": "Monthly CAM Charges", "fieldtype": "Currency"},
			{"variable_name": "jurisdiction_city", "label": "Jurisdiction City", "fieldtype": "Data"},
			{"variable_name": "witness_1_name", "label": "Witness 1 Name", "fieldtype": "Data"},
			{"variable_name": "witness_1_address", "label": "Witness 1 Address", "fieldtype": "Small Text"},
			{"variable_name": "witness_2_name", "label": "Witness 2 Name", "fieldtype": "Data"},
			{"variable_name": "witness_2_address", "label": "Witness 2 Address", "fieldtype": "Small Text"}
		]

	# 3. Employment & Executive Appointment Agreement
	elif any(k in p_lower for k in ["employ", "salary", "probation", "ctc", "job", "worker", "staff", "appointment", "hiring", "developer", "engineer", "manager"]):
		doc_title = "EXECUTIVE EMPLOYMENT & CONFIDENTIALITY AGREEMENT"
		tpl_name = "Employment Agreement"
		prefix = "EMP"
		parties = [
			{"role": "EMPLOYER", "text": "{{ employer_company_name }}, a company incorporated under applicable law, having its registered office at {{ employer_registered_address }}, CIN / Tax ID: {{ employer_cin_or_pan }}, represented by its Authorized Signatory {{ employer_authorized_signatory }}, {{ employer_signatory_designation }} (hereinafter referred to as the \"EMPLOYER\"); and"},
			{"role": "EMPLOYEE", "text": "{{ employee_name }}, residing at {{ employee_residential_address }}, holding National ID / PAN: {{ employee_pan_number }}, Email: {{ employee_email }}, Phone: {{ employee_phone }} (hereinafter referred to as the \"EMPLOYEE\")."}
		]
		recitals = [
			"WHEREAS, the Employer is engaged in commercial business operations and desires to employ the Employee on the terms and conditions herein;",
			"WHEREAS, the Employee possesses the requisite skills, technical qualifications, and professional experience and agrees to accept whole-time employment with the Employer."
		]
		sections = [
			{
				"title": "1. Appointment, Title and Scope of Duties",
				"paragraphs": [
					"The Employer hereby appoints the Employee to the position of {{ job_designation }}, reporting directly to {{ reporting_manager_title }}.",
					"The Employee shall diligently and faithfully perform all professional duties and responsibilities associated with this role, devote whole time and attention to the Employer's business, and comply with all lawful directions and corporate policies."
				]
			},
			{
				"title": "2. Compensation, Financial Remuneration and CTC Structure",
				"paragraphs": [
					f"The Employer shall pay the Employee a monthly basic salary of {{{{ monthly_basic_salary }}}} (estimated at {extracted_amount or '₹1,00,000 INR'}), payable in arrears on or before the last working day of each calendar month.",
					"The Employee shall be entitled to an annual Cost-to-Company (CTC) package of {{ annual_ctc }} as detailed in the compensation annexure, which includes allowances and statutory benefits.",
					"The Employee may be eligible for an annual performance bonus of up to {{ annual_performance_bonus }} based on individual performance and company milestones, disbursed at the sole discretion of the Employer.",
					"All remuneration shall be subject to statutory deductions including income tax (TDS), provident fund, and professional tax."
				]
			},
			{
				"title": "3. Probation Period, Performance Review and Confirmation",
				"paragraphs": [
					f"The Employee shall serve a probation period of {{{{ probation_period_months }}}} months from the date of joining {{ employment_start_date }}.",
					"During probation, either party may terminate this employment by giving {{ probation_notice_days }} days written notice.",
					"Upon satisfactory completion of probation, the Employer shall issue a formal written letter of confirmation."
				]
			},
			{
				"title": "4. Working Hours, Location and Remote Work Policy",
				"paragraphs": [
					"The Employee's primary place of work shall be {{ primary_work_location }}, with standard working hours of {{ weekly_working_hours }} hours per week from Monday through Friday.",
					"The Employee may be required to travel domestically or internationally or participate in remote work protocols in accordance with operational exigencies."
				]
			},
			{
				"title": "5. Leave Entitlement, Holidays and Benefits",
				"paragraphs": [
					"The Employee shall be entitled to {{ annual_paid_leave_days }} days of paid annual leave per year, in addition to statutory public holidays and sick leave as prescribed in company policy."
				]
			},
			{
				"title": "6. Absolute Assignment of Inventions and Intellectual Property",
				"paragraphs": [
					"All software code, inventions, discoveries, designs, trade secrets, business models, algorithms, and documentation conceived, created, or developed by the Employee during the course of employment (whether during working hours or using company resources) shall constitute 'work made for hire' and shall be the sole and exclusive proprietary property of the Employer from inception.",
					"The Employee hereby irrevocably assigns, transfers, and conveys all right, title, and interest in such intellectual property to the Employer in perpetuity on a worldwide basis, and waives all moral rights."
				]
			},
			{
				"title": "7. Confidentiality, Trade Secrets and Data Security",
				"paragraphs": [
					"The Employee shall maintain strict confidentiality regarding all proprietary technical, financial, commercial, customer, and operational information of the Employer.",
					"The Employee covenants not to disclose, copy, transfer, or use any Confidential Information for personal gain or for any third party during employment and surviving indefinitely following termination."
				]
			},
			{
				"title": "8. Restrictive Covenants: Non-Compete and Non-Solicitation",
				"paragraphs": [
					"During employment and for a period of {{ non_compete_period_months }} months following termination, the Employee covenants not to directly or indirectly engage in, manage, advise, or join any commercial enterprise competing directly with the Employer within {{ geographic_restriction }}.",
					"For a period of {{ non_solicitation_period_months }} months following termination, the Employee shall not solicit, induce, or hire any employee, consultant, client, or vendor of the Employer."
				]
			},
			{
				"title": "9. Conflict of Interest and Exclusivity",
				"paragraphs": [
					"The Employee shall not engage in any other business, trade, commercial employment, or freelance engagement, directly or indirectly, without the prior written consent of the Employer."
				]
			},
			{
				"title": "10. Company Property, Information Technology and Code of Conduct",
				"paragraphs": [
					"All computing devices, data access tokens, files, and credit cards provided to the Employee shall remain the property of the Employer and shall be used strictly for authorized company business.",
					"The Employee shall abide by the Employer's code of conduct, anti-harassment (POSH) regulations, and data security mandates."
				]
			},
			{
				"title": "11. Termination of Employment with Notice",
				"paragraphs": [
					"Following confirmation, either party may terminate this employment by issuing {{ notice_period_days }} days prior written notice, or the Employer may pay basic salary in lieu of notice.",
					"The Employee shall serve the entire notice period and ensure smooth knowledge transfer unless expressly relieved early by the Employer."
				]
			},
			{
				"title": "12. Summary Termination for Cause and Gross Misconduct",
				"paragraphs": [
					"The Employer may terminate the Employee immediately without notice, severance, or pay in lieu in the event of: (a) fraud, embezzlement, or financial dishonesty; (b) gross negligence or willful disobedience; (c) breach of confidentiality or IP covenants; or (d) conviction of any criminal offense."
				]
			},
			{
				"title": "13. Post-Termination Handover and Exit Clearance",
				"paragraphs": [
					"Upon termination, the Employee shall immediately return all company assets, laptops, security keys, documents, source code repositories, and credentials, and execute a formal exit clearance acknowledgment."
				]
			},
			{
				"title": "14. Indemnification and Statutory Protections",
				"paragraphs": [
					"The Employee covenants to indemnify the Employer against any loss, legal penalties, or liabilities arising directly from the Employee's intentional misconduct, gross negligence, or unauthorized disclosure of proprietary data."
				]
			},
			{
				"title": "15. Governing Law, Dispute Resolution and Boilerplate",
				"paragraphs": [
					f"This Agreement shall be governed by the laws of India. Courts at {{{{ jurisdiction_city }}}} (exclusive jurisdiction: {extracted_city}) shall have exclusive jurisdiction over any proceeding arising hereunder.",
					"This Agreement represents the entire agreement between the Parties and supersedes all prior appointment letters or verbal discussions."
				]
			}
		]
		particulars = [
			{"particular": "Employer Entity", "value": "{{ employer_company_name }}"},
			{"particular": "Employer Registered Office", "value": "{{ employer_registered_address }}"},
			{"particular": "Employee Full Name", "value": "{{ employee_name }}"},
			{"particular": "Employee Residential Address", "value": "{{ employee_residential_address }}"},
			{"particular": "Job Designation", "value": "{{ job_designation }}"},
			{"particular": "Reporting Manager", "value": "{{ reporting_manager_title }}"},
			{"particular": "Date of Joining", "value": "{{ employment_start_date }}"},
			{"particular": "Monthly Basic Salary", "value": "{{ monthly_basic_salary }}"},
			{"particular": "Annual CTC Package", "value": "{{ annual_ctc }}"},
			{"particular": "Annual Performance Bonus", "value": "{{ annual_performance_bonus }}"},
			{"particular": "Probation Period", "value": "{{ probation_period_months }} Months"},
			{"particular": "Probation Notice", "value": "{{ probation_notice_days }} Days"},
			{"particular": "Confirmation Notice Period", "value": "{{ notice_period_days }} Days"},
			{"particular": "Primary Work Location", "value": "{{ primary_work_location }}"},
			{"particular": "Non-Compete Duration", "value": "{{ non_compete_period_months }} Months"},
			{"particular": "Non-Solicit Duration", "value": "{{ non_solicitation_period_months }} Months"},
			{"particular": "Jurisdiction City", "value": "{{ jurisdiction_city }}"},
			{"particular": "Witness 1 Name", "value": "{{ witness_1_name }}"},
			{"particular": "Witness 2 Name", "value": "{{ witness_2_name }}"}
		]
		vars_list = [
			{"variable_name": "employer_company_name", "label": "Employer Company Name", "fieldtype": "Data"},
			{"variable_name": "employer_registered_address", "label": "Employer Registered Address", "fieldtype": "Small Text"},
			{"variable_name": "employer_cin_or_pan", "label": "Employer CIN / PAN", "fieldtype": "Data"},
			{"variable_name": "employer_authorized_signatory", "label": "Employer Authorized Signatory", "fieldtype": "Data"},
			{"variable_name": "employer_signatory_designation", "label": "Employer Signatory Designation", "fieldtype": "Data"},
			{"variable_name": "employee_name", "label": "Employee Full Name", "fieldtype": "Data"},
			{"variable_name": "employee_residential_address", "label": "Employee Residential Address", "fieldtype": "Small Text"},
			{"variable_name": "employee_pan_number", "label": "Employee PAN / National ID", "fieldtype": "Data"},
			{"variable_name": "employee_email", "label": "Employee Email", "fieldtype": "Data"},
			{"variable_name": "employee_phone", "label": "Employee Phone", "fieldtype": "Data"},
			{"variable_name": "job_designation", "label": "Job Designation", "fieldtype": "Data"},
			{"variable_name": "reporting_manager_title", "label": "Reporting Manager Title", "fieldtype": "Data"},
			{"variable_name": "employment_start_date", "label": "Employment Start Date", "fieldtype": "Date"},
			{"variable_name": "monthly_basic_salary", "label": "Monthly Basic Salary", "fieldtype": "Currency"},
			{"variable_name": "annual_ctc", "label": "Annual CTC Package", "fieldtype": "Currency"},
			{"variable_name": "annual_performance_bonus", "label": "Annual Performance Bonus", "fieldtype": "Currency"},
			{"variable_name": "probation_period_months", "label": "Probation Period (Months)", "fieldtype": "Int"},
			{"variable_name": "probation_notice_days", "label": "Probation Notice (Days)", "fieldtype": "Int"},
			{"variable_name": "notice_period_days", "label": "Confirmation Notice Period (Days)", "fieldtype": "Int"},
			{"variable_name": "primary_work_location", "label": "Primary Work Location", "fieldtype": "Data"},
			{"variable_name": "non_compete_period_months", "label": "Non-Compete Period (Months)", "fieldtype": "Int"},
			{"variable_name": "non_solicitation_period_months", "label": "Non-Solicitation Period (Months)", "fieldtype": "Int"},
			{"variable_name": "jurisdiction_city", "label": "Jurisdiction City", "fieldtype": "Data"},
			{"variable_name": "witness_1_name", "label": "Witness 1 Name", "fieldtype": "Data"},
			{"variable_name": "witness_1_address", "label": "Witness 1 Address", "fieldtype": "Small Text"},
			{"variable_name": "witness_2_name", "label": "Witness 2 Name", "fieldtype": "Data"},
			{"variable_name": "witness_2_address", "label": "Witness 2 Address", "fieldtype": "Small Text"}
		]

	# 4. Mutual Non-Disclosure Agreement (NDA)
	elif any(k in p_lower for k in ["nda", "confidential", "non-disclosure", "secret", "proprietary"]):
		doc_title = "MUTUAL NON-DISCLOSURE & PROPRIETARY INFORMATION AGREEMENT"
		tpl_name = "Non-Disclosure Agreement"
		prefix = "NDA"
		parties = [
			{"role": "DISCLOSING PARTY / PARTY A", "text": "{{ party_a_company_name }}, a corporation incorporated under applicable law, having its registered office at {{ party_a_registered_address }}, CIN / Tax ID: {{ party_a_cin_or_pan }}, represented by its Authorized Signatory {{ party_a_signatory_name }}, {{ party_a_signatory_designation }} (hereinafter referred to as \"PARTY A\"); and"},
			{"role": "RECEIVING PARTY / PARTY B", "text": "{{ party_b_company_name }}, a corporation incorporated under applicable law, having its registered office at {{ party_b_registered_address }}, CIN / Tax ID: {{ party_b_cin_or_pan }}, represented by its Authorized Signatory {{ party_b_signatory_name }}, {{ party_b_signatory_designation }} (hereinafter referred to as \"PARTY B\")."}
		]
		recitals = [
			"WHEREAS, the Parties wish to explore and evaluate a prospective commercial transaction and strategic collaboration concerning {{ transaction_purpose }} (the \"Purpose\");",
			"WHEREAS, during negotiations and discussions, either Party (the \"Disclosing Party\") may disclose to the other Party (the \"Receiving Party\") sensitive, non-public, confidential, and proprietary technical, commercial, and financial information;",
			"WHEREAS, the Parties desire to formally define the conditions governing the protection, handling, and non-disclosure of all such Confidential Information."
		]
		sections = [
			{
				"title": "1. Definition of Confidential Information",
				"paragraphs": [
					"Confidential Information shall encompass all non-public information disclosed directly or indirectly by the Disclosing Party to the Receiving Party in written, electronic, oral, visual, or physical form, including without limitation: (a) trade secrets, software code, algorithms, architectures, designs, specifications, technical documentation; (b) business plans, customer lists, vendor details, pricing strategies, financial projections; and (c) any analyses, compilations, or summaries prepared by the Receiving Party that incorporate such information.",
					"Information disclosed orally shall be treated as Confidential Information if identified as confidential at the time of disclosure or if a reasonable person in like circumstances would understand it to be confidential."
				]
			},
			{
				"title": "2. Exclusions from Confidential Treatment",
				"paragraphs": [
					"Confidential Information shall not include information that the Receiving Party can establish by documentary evidence: (a) was already lawfully known to the Receiving Party prior to disclosure without obligation of confidentiality; (b) is or becomes publicly available through no breach of this Agreement by the Receiving Party; (c) was received from an independent third party possessing lawful right to disclose it; or (d) is independently developed by the Receiving Party's personnel without reference to or reliance upon the Disclosing Party's Confidential Information."
				]
			},
			{
				"title": "3. Non-Disclosure and Restricted Use Obligations",
				"paragraphs": [
					"The Receiving Party covenants to use the Confidential Information solely and exclusively for the Purpose set forth herein, and shall not exploit such information for commercial advantage, reverse engineering, or to develop competitive products.",
					"The Receiving Party shall not disclose Confidential Information to any third party, except to its directors, officers, employees, legal advisors, and financial consultants who strictly need to know such information for the Purpose and who are bound by written confidentiality obligations at least as restrictive as those contained herein."
				]
			},
			{
				"title": "4. Standard of Care and Security Measures",
				"paragraphs": [
					"The Receiving Party shall protect the Disclosing Party's Confidential Information with the same degree of care it employs for its own confidential information of like importance, but in no event less than a reasonable standard of commercial care.",
					"The Receiving Party shall immediately notify the Disclosing Party upon discovering any unauthorized disclosure, access, or security breach involving the Confidential Information and shall cooperate in mitigating damages."
				]
			},
			{
				"title": "5. Legally Compelled Disclosures",
				"paragraphs": [
					"If the Receiving Party is required by law, subpoena, or valid order of a court of competent jurisdiction to disclose any Confidential Information, the Receiving Party shall provide prompt written notice to the Disclosing Party prior to disclosure, to enable the Disclosing Party to seek a protective order or other appropriate legal remedy.",
					"In any event, the Receiving Party shall disclose only that portion of Confidential Information that is legally mandated."
				]
			},
			{
				"title": "6. Return or Certified Destruction of Materials",
				"paragraphs": [
					"Upon written request by the Disclosing Party or upon termination of discussions, the Receiving Party shall, within {{ return_materials_days }} days, return to the Disclosing Party or certify in writing the permanent destruction of all copies, summaries, electronic databases, and records containing Confidential Information."
				]
			},
			{
				"title": "7. Ownership of Information and Absence of License",
				"paragraphs": [
					"All Confidential Information shall remain the exclusive property of the Disclosing Party. Nothing in this Agreement shall be construed as granting any express or implied license, assignment, patent, copyright, or trademark right to the Receiving Party.",
					"All information is disclosed on an 'AS-IS' basis without warranties of accuracy, completeness, or fitness for purpose."
				]
			},
			{
				"title": "8. Remedies, Specific Performance and Injunctive Relief",
				"paragraphs": [
					"The Receiving Party acknowledges that monetary damages would be inadequate compensation for any unauthorized disclosure or breach of this Agreement, which would cause irreparable harm to the Disclosing Party.",
					"Accordingly, the Disclosing Party shall be entitled to seek immediate injunctive relief, specific performance, and equitable remedies from any competent court without the necessity of proving actual damages or posting bond, in addition to pursuing liquidated damages of {{ liquidated_damages_amount }}."
				]
			},
			{
				"title": "9. Restrictive Covenant: Non-Solicitation of Personnel",
				"paragraphs": [
					"For a period of {{ non_solicitation_duration_months }} months from the Effective Date, neither Party shall directly or indirectly solicit, induce, or employ any personnel or consultant of the other Party who participated in discussions regarding the Purpose."
				]
			},
			{
				"title": "10. Term of Agreement and Survival of Confidentiality",
				"paragraphs": [
					f"This Agreement shall remain in effect for an initial evaluation term of {{{{ agreement_term_years }}}} years from the Effective Date.",
					f"The obligations of confidentiality, non-disclosure, and non-use shall survive the expiration or termination of this Agreement for a period of {{{{ confidentiality_survival_years }}}} years, provided that trade secrets and proprietary source code shall be kept confidential in perpetuity."
				]
			},
			{
				"title": "11. Dispute Resolution and Governing Law",
				"paragraphs": [
					f"This Agreement shall be governed by and construed in accordance with the laws of India. Courts at {{{{ dispute_resolution_city }}}} (exclusive jurisdiction: {extracted_city}) shall have sole and exclusive jurisdiction over any proceeding arising hereunder."
				]
			},
			{
				"title": "12. Miscellaneous Boilerplate Provisions",
				"paragraphs": [
					"This Agreement represents the entire agreement between the Parties regarding confidentiality and supersedes all prior oral or written representations. No amendment shall be binding unless executed in writing by authorized signatories of both Parties."
				]
			}
		]
		particulars = [
			{"particular": "Party A Entity", "value": "{{ party_a_company_name }}"},
			{"particular": "Party A Registered Address", "value": "{{ party_a_registered_address }}"},
			{"particular": "Party B Entity", "value": "{{ party_b_company_name }}"},
			{"particular": "Party B Registered Address", "value": "{{ party_b_registered_address }}"},
			{"particular": "Transaction Purpose", "value": "{{ transaction_purpose }}"},
			{"particular": "Agreement Effective Date", "value": "{{ agreement_date }}"},
			{"particular": "Agreement Term", "value": "{{ agreement_term_years }} Years"},
			{"particular": "Confidentiality Survival", "value": "{{ confidentiality_survival_years }} Years"},
			{"particular": "Return of Materials Timeline", "value": "{{ return_materials_days }} Days"},
			{"particular": "Liquidated Damages Amount", "value": "{{ liquidated_damages_amount }}"},
			{"particular": "Non-Solicitation Period", "value": "{{ non_solicitation_duration_months }} Months"},
			{"particular": "Governing Jurisdiction", "value": "{{ dispute_resolution_city }}"},
			{"particular": "Witness 1 Name", "value": "{{ witness_1_name }}"},
			{"particular": "Witness 2 Name", "value": "{{ witness_2_name }}"}
		]
		vars_list = [
			{"variable_name": "party_a_company_name", "label": "Party A Company Name", "fieldtype": "Data"},
			{"variable_name": "party_a_registered_address", "label": "Party A Registered Address", "fieldtype": "Small Text"},
			{"variable_name": "party_a_cin_or_pan", "label": "Party A CIN / PAN", "fieldtype": "Data"},
			{"variable_name": "party_a_signatory_name", "label": "Party A Authorized Signatory", "fieldtype": "Data"},
			{"variable_name": "party_a_signatory_designation", "label": "Party A Signatory Designation", "fieldtype": "Data"},
			{"variable_name": "party_b_company_name", "label": "Party B Company Name", "fieldtype": "Data"},
			{"variable_name": "party_b_registered_address", "label": "Party B Registered Address", "fieldtype": "Small Text"},
			{"variable_name": "party_b_cin_or_pan", "label": "Party B CIN / PAN", "fieldtype": "Data"},
			{"variable_name": "party_b_signatory_name", "label": "Party B Authorized Signatory", "fieldtype": "Data"},
			{"variable_name": "party_b_signatory_designation", "label": "Party B Signatory Designation", "fieldtype": "Data"},
			{"variable_name": "transaction_purpose", "label": "Transaction / Project Purpose", "fieldtype": "Small Text"},
			{"variable_name": "agreement_date", "label": "Agreement Execution Date", "fieldtype": "Date"},
			{"variable_name": "agreement_term_years", "label": "Agreement Term (Years)", "fieldtype": "Int"},
			{"variable_name": "confidentiality_survival_years", "label": "Confidentiality Survival (Years)", "fieldtype": "Int"},
			{"variable_name": "return_materials_days", "label": "Return Materials Timeline (Days)", "fieldtype": "Int"},
			{"variable_name": "liquidated_damages_amount", "label": "Liquidated Damages Amount", "fieldtype": "Currency"},
			{"variable_name": "non_solicitation_duration_months", "label": "Non-Solicitation Period (Months)", "fieldtype": "Int"},
			{"variable_name": "dispute_resolution_city", "label": "Dispute Resolution City", "fieldtype": "Data"},
			{"variable_name": "witness_1_name", "label": "Witness 1 Name", "fieldtype": "Data"},
			{"variable_name": "witness_1_address", "label": "Witness 1 Address", "fieldtype": "Small Text"},
			{"variable_name": "witness_2_name", "label": "Witness 2 Name", "fieldtype": "Data"},
			{"variable_name": "witness_2_address", "label": "Witness 2 Address", "fieldtype": "Small Text"}
		]

	# 5. Software Development & Technology Licensing Agreement
	elif any(k in p_lower for k in ["software", "application", "app", "saas", "code", "tech", "platform", "web development", "api"]):
		doc_title = "SOFTWARE DEVELOPMENT & TECHNOLOGY LICENSING AGREEMENT"
		tpl_name = "Software Development Agreement"
		prefix = "SFT"
		parties = [
			{"role": "CLIENT", "text": "{{ client_company_name }}, a corporation having its registered office at {{ client_registered_address }}, CIN / Tax ID: {{ client_cin_or_pan }}, represented by its Authorized Signatory {{ client_signatory_name }}, {{ client_signatory_designation }} (hereinafter referred to as \"CLIENT\"); and"},
			{"role": "DEVELOPER", "text": "{{ developer_company_name }}, a software engineering firm having its principal office at {{ developer_registered_address }}, CIN / Tax ID: {{ developer_cin_or_pan }}, represented by its Authorized Signatory {{ developer_signatory_name }}, {{ developer_signatory_designation }} (hereinafter referred to as \"DEVELOPER\")."}
		]
		recitals = [
			"WHEREAS, the Client desires to engage the Developer to architect, engineer, test, and deliver custom proprietary software in accordance with {{ software_project_name }};",
			"WHEREAS, the Developer possesses specialized technical skills, software engineering infrastructure, and personnel required to execute the deliverables;",
			"WHEREAS, the Developer agrees to develop and deliver the software and assign all proprietary intellectual property rights to the Client upon the terms herein."
		]
		sections = [
			{
				"title": "1. Scope of Development and Technical Specifications",
				"paragraphs": [
					"The Developer covenants to design, develop, test, and deliver the software application described as {{ software_project_name }} in strict conformity with the Technical Specifications set forth in Annexure A.",
					"Any change in scope, architectural requirements, or third-party API integrations shall be documented via a formal written Change Request Order signed by both Parties."
				]
			},
			{
				"title": "2. Milestones, Delivery Timelines and Acceptance Testing",
				"paragraphs": [
					f"The Developer shall execute the project according to the milestone schedule set forth in Annexure B, targeting final delivery by {{{{ project_completion_deadline }}}} (estimated duration: {extracted_duration or '6 months'}).",
					"Upon receipt of each milestone deliverable, the Client shall have an Acceptance Testing Period of {{ uat_testing_period_days }} business days to test the software against the acceptance criteria.",
					"The Developer shall rectify all documented severity-1 and severity-2 defects within {{ bug_rectification_days }} days at no additional cost to the Client."
				]
			},
			{
				"title": "3. Commercial Consideration, Milestone Fees and Payment Terms",
				"paragraphs": [
					f"In consideration of the satisfactory development and delivery, the Client shall pay the Developer a total contract consideration of {{{{ total_project_fee }}}} (estimated at {extracted_amount or '₹5,00,000 INR'}), disbursed in tranches against approved milestones.",
					"The Developer shall issue tax invoices upon milestone sign-off, payable by the Client within {{ invoice_payment_terms_days }} days.",
					"Any delayed payment shall accrue late interest at {{ late_payment_interest_pct }}% per month, and all fees shall be subject to statutory tax deductions (TDS) and GST."
				]
			},
			{
				"title": "4. Absolute Ownership and Assignment of Intellectual Property",
				"paragraphs": [
					"All deliverables, software code (source code and object code), database schemas, APIs, algorithms, designs, documentation, and repositories created by the Developer under this Agreement shall constitute 'work made for hire' and shall be the sole and exclusive proprietary property of the Client upon payment.",
					"The Developer hereby irrevocably assigns, transfers, and conveys to the Client in perpetuity on a worldwide basis all rights, title, copyright, and patent interests in the software, and waives all moral rights."
				]
			},
			{
				"title": "5. Third-Party Components and Open-Source Software",
				"paragraphs": [
					"The Developer warrants that it shall not embed or link any third-party or open-source software governed by restrictive copyleft licenses (such as GNU GPL or AGPL) that would mandate disclosure of the Client's proprietary source code.",
					"All permissive third-party libraries incorporated into the software must be explicitly disclosed in writing to the Client prior to deployment."
				]
			},
			{
				"title": "6. Warranties and Defect Rectification Period",
				"paragraphs": [
					"The Developer warrants that for a period of {{ warranty_period_days }} days following final acceptance (the \"Warranty Period\"), the software shall perform in accordance with specifications without material defects.",
					"During the Warranty Period, the Developer shall promptly rectify all bugs, crashes, and performance bottlenecks without charging additional fees."
				]
			},
			{
				"title": "7. Ongoing Maintenance, Support and SLA",
				"paragraphs": [
					"Following the Warranty Period, the Parties may enter into an Annual Maintenance Contract (AMC) at an agreed fee of {{ annual_maintenance_fee }} per annum, governed by the Service Level Agreement (SLA) response times set forth in Annexure C."
				]
			},
			{
				"title": "8. Confidentiality, Source Code Security and Data Protection",
				"paragraphs": [
					"Both Parties covenant to maintain strict confidentiality of all business, technical, and customer data exchanged under this Agreement.",
					"The Developer shall implement industry-standard encryption, version control security, and access controls to prevent unauthorized leakage of the Client's repositories and databases."
				]
			},
			{
				"title": "9. Intellectual Property Infringement Indemnification",
				"paragraphs": [
					"The Developer covenants to defend, indemnify, and hold harmless the Client, its officers, and directors against any claims, damages, liabilities, or legal expenses arising from allegations that the software infringes any patent, copyright, or trade secret of any third party."
				]
			},
			{
				"title": "10. Limitation of Liability and Damages Waiver",
				"paragraphs": [
					"Neither Party shall be liable for indirect, incidental, special, or consequential damages, including loss of revenue or data.",
					"The Developer's aggregate liability under this Agreement shall not exceed the total fees actually received by the Developer under this Agreement."
				]
			},
			{
				"title": "11. Term, Delays and Termination",
				"paragraphs": [
					"Either Party may terminate this Agreement immediately if the other Party commits a material breach and fails to cure such breach within {{ cure_period_days }} days of written notice.",
					"The Client may terminate for convenience upon {{ termination_notice_days }} days written notice, subject to compensating the Developer for milestones satisfactorily completed."
				]
			},
			{
				"title": "12. Source Code Handover and Repository Transfer",
				"paragraphs": [
					"Upon termination or final acceptance, the Developer shall immediately transfer full administrative access to all git repositories, hosting accounts, cloud infrastructure, and technical architecture documents to the Client."
				]
			},
			{
				"title": "13. Non-Solicitation of Technical Personnel",
				"paragraphs": [
					"Neither Party shall solicit, recruit, or hire any software engineer or technical contractor of the other Party during the term and for {{ non_solicitation_duration_months }} months thereafter."
				]
			},
			{
				"title": "14. Force Majeure and Technical Disruptions",
				"paragraphs": [
					"Neither Party shall be held liable for delays caused by acts of God, widespread internet backbone outages, power grid failures, or government restrictions."
				]
			},
			{
				"title": "15. Dispute Resolution and Institutional Arbitration",
				"paragraphs": [
					f"Any dispute arising out of this Agreement shall be resolved through binding arbitration by a sole arbitrator under the Arbitration and Conciliation Act, seated at {{{{ dispute_resolution_city }}}} (exclusive city: {extracted_city})."
				]
			},
			{
				"title": "16. Governing Law and Miscellaneous Boilerplate",
				"paragraphs": [
					"This Agreement shall be governed by the laws of India, with exclusive court jurisdiction in {{ jurisdiction_city }}.",
					"This Agreement constitutes the entire understanding between the Parties regarding software development."
				]
			}
		]
		particulars = [
			{"particular": "Client Entity", "value": "{{ client_company_name }}"},
			{"particular": "Client Registered Address", "value": "{{ client_registered_address }}"},
			{"particular": "Developer Entity", "value": "{{ developer_company_name }}"},
			{"particular": "Developer Registered Address", "value": "{{ developer_registered_address }}"},
			{"particular": "Project Title", "value": "{{ software_project_name }}"},
			{"particular": "Total Project Fee", "value": "{{ total_project_fee }}"},
			{"particular": "Completion Deadline", "value": "{{ project_completion_deadline }}"},
			{"particular": "UAT Period", "value": "{{ uat_testing_period_days }} Days"},
			{"particular": "Bug Rectification SLA", "value": "{{ bug_rectification_days }} Days"},
			{"particular": "Warranty Period", "value": "{{ warranty_period_days }} Days"},
			{"particular": "Annual Maintenance Fee", "value": "{{ annual_maintenance_fee }}"},
			{"particular": "Invoice Payment Terms", "value": "{{ invoice_payment_terms_days }} Days"},
			{"particular": "Default Cure Period", "value": "{{ cure_period_days }} Days"},
			{"particular": "Governing Jurisdiction", "value": "{{ jurisdiction_city }}"},
			{"particular": "Witness 1 Name", "value": "{{ witness_1_name }}"},
			{"particular": "Witness 2 Name", "value": "{{ witness_2_name }}"}
		]
		vars_list = [
			{"variable_name": "client_company_name", "label": "Client Company Name", "fieldtype": "Data"},
			{"variable_name": "client_registered_address", "label": "Client Registered Address", "fieldtype": "Small Text"},
			{"variable_name": "client_cin_or_pan", "label": "Client CIN / PAN", "fieldtype": "Data"},
			{"variable_name": "client_signatory_name", "label": "Client Authorized Signatory", "fieldtype": "Data"},
			{"variable_name": "client_signatory_designation", "label": "Client Signatory Designation", "fieldtype": "Data"},
			{"variable_name": "developer_company_name", "label": "Developer Company Name", "fieldtype": "Data"},
			{"variable_name": "developer_registered_address", "label": "Developer Registered Address", "fieldtype": "Small Text"},
			{"variable_name": "developer_cin_or_pan", "label": "Developer CIN / PAN", "fieldtype": "Data"},
			{"variable_name": "developer_signatory_name", "label": "Developer Authorized Signatory", "fieldtype": "Data"},
			{"variable_name": "developer_signatory_designation", "label": "Developer Signatory Designation", "fieldtype": "Data"},
			{"variable_name": "software_project_name", "label": "Software Project Name", "fieldtype": "Data"},
			{"variable_name": "total_project_fee", "label": "Total Project Fee", "fieldtype": "Currency"},
			{"variable_name": "project_completion_deadline", "label": "Project Completion Deadline", "fieldtype": "Date"},
			{"variable_name": "uat_testing_period_days", "label": "UAT Testing Period (Days)", "fieldtype": "Int"},
			{"variable_name": "bug_rectification_days", "label": "Bug Rectification Timeline (Days)", "fieldtype": "Int"},
			{"variable_name": "warranty_period_days", "label": "Warranty Period (Days)", "fieldtype": "Int"},
			{"variable_name": "annual_maintenance_fee", "label": "Annual Maintenance Fee", "fieldtype": "Currency"},
			{"variable_name": "invoice_payment_terms_days", "label": "Invoice Payment Terms (Days)", "fieldtype": "Int"},
			{"variable_name": "cure_period_days", "label": "Default Cure Period (Days)", "fieldtype": "Int"},
			{"variable_name": "termination_notice_days", "label": "Termination Notice Period (Days)", "fieldtype": "Int"},
			{"variable_name": "non_solicitation_duration_months", "label": "Non-Solicitation Duration (Months)", "fieldtype": "Int"},
			{"variable_name": "jurisdiction_city", "label": "Jurisdiction City", "fieldtype": "Data"},
			{"variable_name": "witness_1_name", "label": "Witness 1 Name", "fieldtype": "Data"},
			{"variable_name": "witness_1_address", "label": "Witness 1 Address", "fieldtype": "Small Text"},
			{"variable_name": "witness_2_name", "label": "Witness 2 Name", "fieldtype": "Data"},
			{"variable_name": "witness_2_address", "label": "Witness 2 Address", "fieldtype": "Small Text"}
		]

	# 6. Default: Master Services & Professional Consultancy Agreement
	else:
		doc_title = "MASTER SERVICES & PROFESSIONAL CONSULTANCY AGREEMENT"
		tpl_name = "Consulting Agreement"
		prefix = "CON"
		parties = [
			{"role": "CLIENT", "text": "{{ client_company_name }}, a corporation incorporated under applicable law, having its registered office at {{ client_registered_address }}, CIN / Tax ID: {{ client_cin_or_pan }}, represented by its Authorized Signatory {{ client_signatory_name }}, {{ client_signatory_designation }} (hereinafter referred to as \"CLIENT\"); and"},
			{"role": "CONSULTANT / SERVICE PROVIDER", "text": "{{ service_provider_name }}, residing at / having office at {{ service_provider_address }}, Identification / PAN / Tax ID: {{ provider_cin_or_pan }}, represented by {{ provider_authorized_signatory }} (hereinafter referred to as \"SERVICE PROVIDER\")."}
		]
		recitals = [
			"WHEREAS, the Client desires to retain the specialized professional advisory and consultancy services of the Service Provider in connection with {{ project_scope_summary }};",
			"WHEREAS, the Service Provider possesses the requisite domain expertise, professional standing, and capabilities and agrees to render consultancy services;",
			"WHEREAS, the Parties have agreed to enter into this Master Services Agreement upon the mutual covenants, representations, and considerations set forth herein."
		]
		sections = [
			{
				"title": "1. Scope of Professional Services and Statements of Work",
				"paragraphs": [
					"The Service Provider covenants to perform the specialized professional advisory, technical consultancy, and strategic deliverables set forth in {{ project_scope_summary }} and any subsequent Statements of Work (SOWs) executed hereunder.",
					"The Service Provider covenants to execute the deliverables with highest professional care, competence, integrity, and diligence in accordance with prevailing industry best practices."
				]
			},
			{
				"title": "2. Performance Milestones, Deadlines and Key Deliverables",
				"paragraphs": [
					f"The Service Provider shall execute the deliverables according to the roadmaps and timeline milestones set forth in Annexure A, commencing on {{{{ engagement_start_date }}}} and completing by {{{{ engagement_end_date }}}} (estimated tenure: {extracted_duration or '12 months'}).",
					"The Service Provider shall submit bi-weekly progress status reports and participate in milestone review meetings with the Client's designated project representative."
				]
			},
			{
				"title": "3. Commercial Consideration, Retainer Fees and Invoicing Terms",
				"paragraphs": [
					f"In consideration of the satisfactory advisory services, the Client shall pay the Service Provider a monthly professional retainer fee of {{{{ monthly_service_fee }}}} (estimated at {extracted_amount or '₹80,000 INR'}).",
					"Upon the successful sign-off and completion of designated strategic milestones, the Client shall pay a performance bonus of {{ milestone_bonus_amount }}.",
					"The Service Provider shall issue monthly tax invoices, payable by the Client within {{ invoice_payment_days }} business days of receipt.",
					"Any delayed payments shall accrue late interest at {{ late_payment_interest_pct }}% per annum. All fees are subject to statutory deduction of income tax at source (TDS) and GST."
				]
			},
			{
				"title": "4. Reimbursable Expenses and Authorization",
				"paragraphs": [
					"The Client shall reimburse the Service Provider for all reasonable, pre-approved out-of-pocket travel, accommodation, and communication expenses incurred solely in connection with the engagement, supported by original receipts."
				]
			},
			{
				"title": "5. Independent Contractor Status and Absence of Agency",
				"paragraphs": [
					"The relationship between the Client and the Service Provider is strictly that of an independent contractor.",
					"Nothing herein shall be construed as creating an employer-employee relationship, partnership, or joint venture. The Service Provider shall have no authority to bind the Client or incur obligations on its behalf."
				]
			},
			{
				"title": "6. Absolute Intellectual Property Ownership and Work-for-Hire",
				"paragraphs": [
					"All deliverables, reports, strategic roadmaps, software designs, presentations, and work product developed or authored by the Service Provider under this Agreement shall constitute 'work made for hire' and shall be the exclusive proprietary property of the Client from inception.",
					"The Service Provider hereby irrevocably assigns, transfers, and conveys to the Client in perpetuity on a worldwide basis all rights, title, copyright, and patent interests in the deliverables, and waives all moral rights."
				]
			},
			{
				"title": "7. Confidentiality, Trade Secrets and Data Protection",
				"paragraphs": [
					"The Service Provider shall treat all business, technical, financial, customer, and strategic information disclosed by the Client as strictly confidential.",
					"The Service Provider shall not disclose, copy, or distribute any Confidential Information to third parties without prior written consent, and such obligations shall survive termination for a period of {{ confidentiality_survival_years }} years."
				]
			},
			{
				"title": "8. Restrictive Covenants and Non-Solicitation",
				"paragraphs": [
					"During the engagement and for a period of {{ non_solicitation_period_months }} months following termination, the Service Provider covenants not to solicit, entice, or hire any employee, consultant, or client of the Client."
				]
			},
			{
				"title": "9. Representations and Warranties of Both Parties",
				"paragraphs": [
					"The Service Provider represents and warrants that: (a) it possesses full authority, certifications, and licenses to render the services; (b) the deliverables shall be original and shall not infringe any third-party intellectual property rights; and (c) execution of this Agreement does not breach any prior non-compete or contractual covenant."
				]
			},
			{
				"title": "10. Mutual Indemnification and Defense",
				"paragraphs": [
					"Each Party covenants to defend, indemnify, and hold harmless the other Party, its directors, and officers from and against all liabilities, claims, losses, damages, penalties, and legal expenses arising out of any material breach of warranty, negligence, statutory non-compliance, or third-party intellectual property infringement."
				]
			},
			{
				"title": "11. Limitation of Liability and Consequential Damages Exclusion",
				"paragraphs": [
					"Neither Party shall be liable for indirect, incidental, punitive, or consequential damages, including loss of profits or business reputation.",
					"The aggregate liability of either Party under this Agreement shall be capped at the total fees paid or payable by the Client under this Agreement in the preceding 6 months."
				]
			},
			{
				"title": "12. Term, Default, Cure Periods and Termination",
				"paragraphs": [
					"Either Party may terminate this Agreement for convenience by providing {{ notice_period_days }} days prior written notice to the other Party.",
					"Either Party may terminate immediately if the other Party commits a material breach and fails to cure such breach within {{ cure_period_days }} days of written notice specifying the breach."
				]
			},
			{
				"title": "13. Post-Termination Handover and Final Settlement",
				"paragraphs": [
					"Upon termination, the Service Provider shall immediately deliver all completed and in-progress deliverables, data files, and Client records, and the Client shall pay all approved pro-rata fees earned up to the effective termination date."
				]
			},
			{
				"title": "14. Force Majeure",
				"paragraphs": [
					"Neither Party shall be held liable for failure or delay in performance caused by circumstances beyond its reasonable control, including acts of God, flood, war, civil disturbance, or government orders."
				]
			},
			{
				"title": "15. Dispute Resolution and Institutional Arbitration",
				"paragraphs": [
					f"Any dispute arising out of or related to this Agreement shall be resolved through binding arbitration conducted by a sole arbitrator under the Arbitration and Conciliation Act, seated at {{{{ dispute_resolution_city }}}} (exclusive city: {extracted_city}) in the English language."
				]
			},
			{
				"title": "16. Governing Law, Exclusive Jurisdiction and Boilerplate",
				"paragraphs": [
					"This Agreement shall be governed by the laws of India, with exclusive court jurisdiction in {{ jurisdiction_city }}.",
					"This Agreement represents the entire understanding between the Parties and supersedes all prior oral or written discussions. No modification shall be valid unless executed in writing by authorized signatories."
				]
			}
		]
		particulars = [
			{"particular": "Client Entity", "value": "{{ client_company_name }}"},
			{"particular": "Client Registered Address", "value": "{{ client_registered_address }}"},
			{"particular": "Service Provider Entity", "value": "{{ service_provider_name }}"},
			{"particular": "Service Provider Address", "value": "{{ service_provider_address }}"},
			{"particular": "Project Scope Summary", "value": "{{ project_scope_summary }}"},
			{"particular": "Monthly Retainer Fee", "value": "{{ monthly_service_fee }}"},
			{"particular": "Milestone Bonus Amount", "value": "{{ milestone_bonus_amount }}"},
			{"particular": "Engagement Start Date", "value": "{{ engagement_start_date }}"},
			{"particular": "Engagement End Date", "value": "{{ engagement_end_date }}"},
			{"particular": "Invoice Payment Terms", "value": "{{ invoice_payment_days }} Days"},
			{"particular": "Termination Notice Period", "value": "{{ notice_period_days }} Days"},
			{"particular": "Default Cure Period", "value": "{{ cure_period_days }} Days"},
			{"particular": "Confidentiality Survival", "value": "{{ confidentiality_survival_years }} Years"},
			{"particular": "Non-Solicitation Period", "value": "{{ non_solicitation_period_months }} Months"},
			{"particular": "Governing Jurisdiction", "value": "{{ jurisdiction_city }}"},
			{"particular": "Witness 1 Name", "value": "{{ witness_1_name }}"},
			{"particular": "Witness 2 Name", "value": "{{ witness_2_name }}"}
		]
		vars_list = [
			{"variable_name": "client_company_name", "label": "Client Company Name", "fieldtype": "Data"},
			{"variable_name": "client_registered_address", "label": "Client Registered Address", "fieldtype": "Small Text"},
			{"variable_name": "client_cin_or_pan", "label": "Client CIN / PAN", "fieldtype": "Data"},
			{"variable_name": "client_signatory_name", "label": "Client Authorized Signatory", "fieldtype": "Data"},
			{"variable_name": "client_signatory_designation", "label": "Client Signatory Designation", "fieldtype": "Data"},
			{"variable_name": "service_provider_name", "label": "Service Provider Full Name", "fieldtype": "Data"},
			{"variable_name": "service_provider_address", "label": "Service Provider Address", "fieldtype": "Small Text"},
			{"variable_name": "provider_cin_or_pan", "label": "Provider CIN / PAN / Tax ID", "fieldtype": "Data"},
			{"variable_name": "provider_authorized_signatory", "label": "Provider Authorized Signatory", "fieldtype": "Data"},
			{"variable_name": "project_scope_summary", "label": "Project Scope Summary", "fieldtype": "Small Text"},
			{"variable_name": "monthly_service_fee", "label": "Monthly Retainer Fee", "fieldtype": "Currency"},
			{"variable_name": "milestone_bonus_amount", "label": "Milestone Bonus Amount", "fieldtype": "Currency"},
			{"variable_name": "engagement_start_date", "label": "Engagement Start Date", "fieldtype": "Date"},
			{"variable_name": "engagement_end_date", "label": "Engagement End Date", "fieldtype": "Date"},
			{"variable_name": "invoice_payment_days", "label": "Invoice Payment Terms (Days)", "fieldtype": "Int"},
			{"variable_name": "notice_period_days", "label": "Termination Notice Period (Days)", "fieldtype": "Int"},
			{"variable_name": "cure_period_days", "label": "Default Cure Period (Days)", "fieldtype": "Int"},
			{"variable_name": "confidentiality_survival_years", "label": "Confidentiality Survival (Years)", "fieldtype": "Int"},
			{"variable_name": "non_solicitation_period_months", "label": "Non-Solicitation Period (Months)", "fieldtype": "Int"},
			{"variable_name": "jurisdiction_city", "label": "Jurisdiction City", "fieldtype": "Data"},
			{"variable_name": "witness_1_name", "label": "Witness 1 Name", "fieldtype": "Data"},
			{"variable_name": "witness_1_address", "label": "Witness 1 Address", "fieldtype": "Small Text"},
			{"variable_name": "witness_2_name", "label": "Witness 2 Name", "fieldtype": "Data"},
			{"variable_name": "witness_2_address", "label": "Witness 2 Address", "fieldtype": "Small Text"}
		]

	return {
		"document_title": doc_title,
		"template_name": tpl_name,
		"naming_series": f"{prefix}-.YYYY.-.#####",
		"preamble": f"This {tpl_name} (the \"Agreement\") is executed on this {{{{ agreement_date }}}} at {extracted_city} between:",
		"parties": parties,
		"recitals": recitals,
		"sections": sections,
		"particulars_table": particulars,
		"execution_clause": "IN WITNESS WHEREOF, the Parties hereto have caused this Agreement to be duly executed and delivered by their respective authorized signatories as of the date first written above.",
		"parties_sign": [
			{"role": parties[0]["role"].title(), "name": f"{{{{ {vars_list[0]['variable_name']} }}}}"},
			{"role": parties[1]["role"].title(), "name": f"{{{{ {vars_list[5]['variable_name'] if len(vars_list) > 5 else vars_list[1]['variable_name']} }}}}"}
		],
		"variables": vars_list
	}


@frappe.whitelist()
def generate_template_from_prompt(prompt, template_name=None, naming_series=None, flow_model=None, api_key=None, provider="auto", legal_template_name=None, engine_mode=None):
	"""
	Generates a complete, professionally drafted legal agreement from a user's prompt using Frappe Flow AI
	(when API key is provided) or the Built-in Legal Synthesis Engine (when user has no key),
	creates a formatted .docx template with Jinja tags, attaches it to a Legal Templates document,
	and returns document preview & detected variables for editing in AI Template Studio.
	"""
	if not prompt or not prompt.strip():
		frappe.throw(frappe._("Please enter instructions or description for the template you wish to draft."))

	# If API key is provided, persist it into Flow Provider for future usage
	if api_key and api_key.strip():
		save_ai_key(api_key.strip(), provider=provider)

	drafting_prompt = _get_drafting_prompt(prompt.strip())

	doc_data = None
	usage = None
	engine_used = None

	# If user selected Flow AI or provided an API key, call Flow AI
	if engine_mode != "builtin":
		try:
			doc_data, usage, engine_used = _call_flow_ai(
				raw_text=prompt,
				custom_prompt=drafting_prompt,
				flow_model_name=flow_model,
				api_key_override=api_key,
				expect_dict=True
			)
		except Exception as flow_err:
			if api_key:
				raise flow_err
			doc_data = None

	# If no Flow AI key or user selected Built-in Engine, use Built-in Legal Synthesis Engine
	if not doc_data and not engine_used:
		if engine_mode == "builtin" or not api_key:
			doc_data = synthesize_legal_agreement_from_prompt(prompt.strip())
			engine_used = "Built-in Legal Synthesis Engine"
			usage = {"prompt_tokens": len(prompt.split()), "completion_tokens": 850, "total_tokens": len(prompt.split()) + 850}
		else:
			return {
				"status": "needs_key",
				"message": "Flow AI API Key is required. Please provide a Gemini or Groq API key, or select Built-in Engine."
			}

	# Ensure doc_data is a dict
	if isinstance(doc_data, list):
		doc_data = {
			"document_title": template_name or "LEGAL AGREEMENT",
			"sections": [{"title": "Terms and Conditions", "paragraphs": [str(x) for x in doc_data]}],
			"variables": []
		}

	# 3. Resolve Template Name
	final_template_name = (template_name or doc_data.get("template_name") or doc_data.get("document_title") or "Legal Agreement").strip()
	final_template_name = re.sub(r'[\r\n\t]+', ' ', final_template_name).strip()
	final_template_name = re.sub(r'[:\.\/\\\#\?]+$', '', final_template_name).strip().title()

	# Handle doc retrieval or creation
	tpl_doc = None
	if legal_template_name and frappe.db.exists("Legal Templates", legal_template_name):
		tpl_doc = frappe.get_doc("Legal Templates", legal_template_name)
	elif frappe.db.exists("Legal Templates", final_template_name):
		existing_doc = frappe.get_doc("Legal Templates", final_template_name)
		if not existing_doc.template_file:
			tpl_doc = existing_doc
		else:
			counter = 2
			base_name = final_template_name
			while frappe.db.exists("Legal Templates", f"{base_name} {counter}"):
				counter += 1
			final_template_name = f"{base_name} {counter}"
			tpl_doc = frappe.new_doc("Legal Templates")
			tpl_doc.template_name = final_template_name
	else:
		tpl_doc = frappe.new_doc("Legal Templates")
		tpl_doc.template_name = final_template_name

	# 2. Resolve Naming Series
	if naming_series and naming_series.strip():
		tpl_doc.naming_series = naming_series.strip()
	elif not tpl_doc.naming_series:
		letters_only = re.sub(r'[^A-Za-z]', '', final_template_name)
		prefix = (letters_only[:3] if len(letters_only) >= 3 else "LEG").upper()
		tpl_doc.naming_series = f"{prefix}-.YYYY.-.#####"

	if tpl_doc.is_new():
		tpl_doc.insert(ignore_mandatory=True, ignore_permissions=True)

	# 3. Build .docx file on disk
	safe_fname = f"{frappe.scrub(tpl_doc.name)}_template.docx"
	temp_dir = tempfile.gettempdir()
	temp_docx_path = os.path.join(temp_dir, safe_fname)

	create_docx_from_ai_structure(doc_data, temp_docx_path)

	# 4. Attach generated .docx file to Legal Templates
	with open(temp_docx_path, "rb") as f:
		saved_file = save_file(
			fname=safe_fname,
			content=f.read(),
			dt="Legal Templates",
			dn=tpl_doc.name,
			is_private=0
		)

	tpl_doc.template_file = saved_file.file_url
	tpl_doc.save(ignore_permissions=True)
	frappe.db.commit()

	# 5. Extract preview and variables
	preview_data = get_document_preview(tpl_doc.name)
	
	ai_variables = doc_data.get("variables", [])
	jinja_extracted = extract_existing_jinja_variables(preview_data["text"])
	
	var_map = {}
	for v in jinja_extracted:
		var_map[v["variable_name"]] = v
	for v in ai_variables:
		vname = frappe.scrub(v.get("variable_name", ""))
		if not vname:
			continue
		if vname in var_map:
			var_map[vname]["label"] = v.get("label") or var_map[vname]["label"]
			var_map[vname]["fieldtype"] = v.get("fieldtype") or var_map[vname]["fieldtype"]
		else:
			var_map[vname] = {
				"original_text": v.get("original_text") or f"{{{{ {vname} }}}}",
				"variable_name": vname,
				"label": v.get("label") or vname.replace("_", " ").title(),
				"fieldtype": v.get("fieldtype") or "Data"
			}

	raw_preview_text = preview_data["text"]
	def get_pos(v):
		vtag = f"{{{{ {v['variable_name']} }}}}"
		pos = raw_preview_text.find(vtag)
		if pos == -1:
			pos = raw_preview_text.find(v.get("original_text", ""))
		return pos if pos != -1 else 999999

	final_vars = sorted(list(var_map.values()), key=get_pos)

	return {
		"status": "success",
		"legal_template_name": tpl_doc.name,
		"template_file": tpl_doc.template_file,
		"html_preview": preview_data["html"],
		"variables": final_vars,
		"total_count": len(final_vars),
		"engine_used": engine_used or "Flow AI",
		"token_usage": usage,
		"message": f"Successfully drafted {final_template_name} using {engine_used or 'Flow AI'}."
	}




def extract_legal_entities_nlp(real_path=None, text=""):
	"""
	Intelligent, Context-Aware Legal Entity Extractor.
	Inspects Document Tables, Contract Clauses, Sentences, and Roles to assign
	meaningful names (e.g. 'monthly_rental_amount', 'security_deposit', 'landlord_name')
	instead of generic numbered placeholders.
	"""
	variables = []
	seen_texts = set()

	def add_var(original_text, var_name, label, fieldtype):
		clean_orig = original_text.strip().rstrip(".,;")
		if not clean_orig or clean_orig in seen_texts or len(clean_orig) < 2:
			return
		seen_texts.add(clean_orig)
		variables.append({
			"original_text": clean_orig,
			"variable_name": frappe.scrub(var_name),
			"label": label,
			"fieldtype": fieldtype
		})

	# Load Document object if path is available
	doc = None
	if real_path and os.path.exists(real_path):
		try:
			doc = Document(real_path)
		except Exception:
			doc = None

	# 1. TABLE-BASED EXTRACTION (Highest Fidelity)
	# Legal contracts structure particulars, rent, deposits, dates in 2-column tables
	if doc:
		for table in doc.tables:
			for row in table.rows:
				cells = [c.text.strip() for c in row.cells]
				if len(cells) >= 2:
					raw_label = cells[0].strip()
					val = cells[1].strip()

					# Skip header rows
					if not raw_label or not val:
						continue
					if raw_label.lower() in ["particulars", "item", "description", "details", "sr. no.", "s.no", "no."]:
						continue
					if len(raw_label) > 60:
						continue

					clean_label = re.sub(r'[:\-\?]+$', '', raw_label).strip()
					var_name = frappe.scrub(clean_label)

					# Infer Field Type
					fieldtype = "Data"
					if re.search(r'(?:Rs\.?|INR|USD|\$|₹|AED|EUR|£)\s*[\d,]+', val):
						fieldtype = "Currency"
					elif re.search(r'\b\d{1,2}(?:st|nd|rd|th)?\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{4}\b', val, re.I) or re.search(r'\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b', val):
						fieldtype = "Date"
					elif "@" in val and "." in val:
						fieldtype = "Data"
					elif re.search(r'(?:\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b', val):
						fieldtype = "Data"
					elif len(val) > 80:
						fieldtype = "Small Text"

					add_var(val, var_name, clean_label, fieldtype)

	# 2. PARAGRAPH-BASED CONTEXTUAL EXTRACTION
	paragraphs = doc.paragraphs if doc else []
	p_texts = [p.text.strip() for p in paragraphs if p.text.strip()] if doc else text.split("\n")

	# A. Party Names and Addresses with Defined Roles
	# e.g.: "Mr. Rajesh Kumar Verma, residing at ... (hereinafter referred to as the 'LANDLORD')"
	party_pattern = re.compile(
		r'(?:(?:Mr\.|Ms\.|Mrs\.|Dr\.|Adv\.|M/s)\s+[A-Z][a-zA-Z\.\s]+?)(?:,\s*residing at|\s*residing at|\s*having registered office at)\s+(.+?)\s*\((?:hereinafter\s+(?:called|referred to as)?(?:\s+the)?)\s*["“\']?([A-Z\s]{3,30}?)["”\']?\)',
		re.IGNORECASE
	)
	for p_text in p_texts:
		m = party_pattern.search(p_text)
		if m:
			full_match = m.group(0)
			address = m.group(1).strip().rstrip(".,;")
			raw_role = m.group(2).strip().upper()

			name_match = re.match(
				r'(?:(?:Mr\.|Ms\.|Mrs\.|Dr\.|Adv\.|M/s)\s+[A-Z][a-zA-Z\.\s]+?)(?=,\s*residing|\s+residing|\s+having)',
				full_match
			)
			if name_match:
				name_val = name_match.group(0).strip()
				role_title = raw_role.title()
				add_var(name_val, f"{raw_role.lower()}_name", f"{role_title} Name", "Data")
				if len(address) > 10:
					add_var(address, f"{raw_role.lower()}_address", f"{role_title} Address", "Small Text")

	# B. Context-Aware Currency Amounts (Monthly Rent, Security Deposit, Maintenance, etc.)
	currency_pattern = re.compile(r'(?:Rs\.?|INR|USD|\$|₹|AED|EUR|£)\s*[\d,]+(?:\.\d{2})?')
	for p_text in p_texts:
		for m in currency_pattern.finditer(p_text):
			val = m.group(0)
			start, end = m.start(), m.end()
			ctx_start = max(0, start - 120)
			ctx_end = min(len(p_text), end + 80)
			context = p_text[ctx_start:ctx_end].lower()

			if any(k in context for k in ["monthly rent", "rental sum", "rent of", "rent per month", "monthly rental"]):
				add_var(val, "monthly_rental_amount", "Monthly Rental Amount", "Currency")
			elif any(k in context for k in ["security deposit", "interest-free deposit", "interest free deposit", "caution deposit", "refundable deposit"]):
				add_var(val, "security_deposit", "Security Deposit", "Currency")
			elif any(k in context for k in ["maintenance charges", "society maintenance", "maintenance fee"]):
				add_var(val, "maintenance_charges", "Maintenance Charges", "Currency")
			elif any(k in context for k in ["penalty", "late fee", "late payment", "default interest"]):
				add_var(val, "penalty_charges", "Penalty Charges", "Currency")
			elif any(k in context for k in ["consideration", "purchase price", "sale price", "sale consideration"]):
				add_var(val, "total_consideration_amount", "Total Consideration Amount", "Currency")
			elif any(k in context for k in ["advance", "token amount", "earnest money"]):
				add_var(val, "advance_amount", "Advance Amount", "Currency")
			elif "rent" in context:
				add_var(val, "rental_amount", "Rental Amount", "Currency")
			elif "deposit" in context:
				add_var(val, "deposit_amount", "Deposit Amount", "Currency")
			else:
				add_var(val, f"amount_{len(variables)+1}", f"Amount {len(variables)+1}", "Currency")

	# C. Context-Aware Dates (Agreement Date, Commencement Date, Expiry Date)
	date_patterns = [
		r'\b\d{1,2}(?:st|nd|rd|th)?\s+(?:January|February|March|April|May|June|July|August|September|October|November|December),?\s+\d{4}\b',
		r'\b(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2}(?:st|nd|rd|th)?,?\s+\d{4}\b',
		r'\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b'
	]
	for pattern in date_patterns:
		for p_text in p_texts:
			for m in re.finditer(pattern, p_text, re.IGNORECASE):
				val = m.group(0)
				start, end = m.start(), m.end()
				ctx_start = max(0, start - 120)
				ctx_end = min(len(p_text), end + 80)
				context = p_text[ctx_start:ctx_end].lower()

				if any(k in context for k in ["made and executed on", "executed on", "agreement date", "entered into on", "dated this", "dated:"]):
					add_var(val, "agreement_date", "Agreement Date", "Date")
				elif any(k in context for k in ["commencing from", "commence on", "commencement date", "effective from", "starting from"]):
					add_var(val, "lease_commencement_date", "Lease Commencement Date", "Date")
				elif any(k in context for k in ["expiring on", "expiry date", "termination date", "valid till", "ending on"]):
					add_var(val, "agreement_expiry_date", "Agreement Expiry Date", "Date")
				elif any(k in context for k in ["possession date", "handover date"]):
					add_var(val, "possession_date", "Possession Date", "Date")
				elif any(k in context for k in ["due date", "on or before"]):
					add_var(val, "payment_due_date", "Payment Due Date", "Date")
				else:
					add_var(val, f"date_{len(variables)+1}", f"Date {len(variables)+1}", "Date")

	# D. Context-Aware Emails and Phone Numbers
	email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,7}\b'
	for p_text in p_texts:
		for m in re.finditer(email_pattern, p_text):
			val = m.group(0)
			context = p_text.lower()
			if "tenant" in context or "lessee" in context:
				add_var(val, "tenant_email", "Tenant Email", "Data")
			elif "landlord" in context or "lessor" in context:
				add_var(val, "landlord_email", "Landlord Email", "Data")
			else:
				add_var(val, f"email_{len(variables)+1}", f"Email {len(variables)+1}", "Data")

	phone_pattern = r'(?:\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b'
	for p_text in p_texts:
		for m in re.finditer(phone_pattern, p_text):
			val = m.group(0)
			context = p_text.lower()
			if "tenant" in context or "lessee" in context:
				add_var(val, "tenant_phone", "Tenant Phone", "Data")
			elif "landlord" in context or "lessor" in context:
				add_var(val, "landlord_phone", "Landlord Phone", "Data")
			else:
				add_var(val, f"phone_{len(variables)+1}", f"Phone Number {len(variables)+1}", "Data")

	# E. Fallback for Common Named Parties if not matched above
	name_pattern = r'\b(?:Mr\.|Mrs\.|Ms\.|Dr\.|Adv\.|M/s)\s+[A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+){1,3}\b'
	for p_text in p_texts:
		for m in re.finditer(name_pattern, p_text):
			val = m.group(0)
			if "landlord" in p_text.lower() or "lessor" in p_text.lower():
				add_var(val, "landlord_name", "Landlord Name", "Data")
			elif "tenant" in p_text.lower() or "lessee" in p_text.lower():
				add_var(val, "tenant_name", "Tenant Name", "Data")
			else:
				add_var(val, f"party_name_{len(variables)+1}", f"Party Name {len(variables)+1}", "Data")

	# F. Between X and Y (Preamble Agreements)
	between_pattern = r'between\s+([A-Z][a-zA-Z\s,]+?)\s+and\s+([A-Z][a-zA-Z\s,]+?)(?=\s+(?:for|dated|witnesseth|\.))'
	for p_text in p_texts:
		for m in re.finditer(between_pattern, p_text, re.IGNORECASE):
			p1 = m.group(1).strip()
			p2 = m.group(2).strip()
			if len(p1) < 60:
				add_var(p1, "first_party_name", "First Party Name", "Data")
			if len(p2) < 60:
				add_var(p2, "second_party_name", "Second Party Name", "Data")

	return variables


def highlight_jinja_in_paragraph(p, highlight_color=WD_COLOR_INDEX.YELLOW):
	"""
	Finds all Jinja tags {{ variable_name }} in a paragraph and highlights ONLY the tags
	with native Word highlight (yellow), leaving surrounding text with its original formatting.
	"""
	text = p.text
	if "{{" not in text or "}}" not in text:
		return

	pattern = re.compile(r'(\{\{\s*[\w\.\-]+\s*\}\})')
	if not pattern.search(text):
		return

	# Capture default formatting from first run if available
	default_font_name = "Calibri"
	default_font_size = None
	default_bold = False
	default_italic = False
	default_color = None

	if p.runs:
		r0 = p.runs[0]
		default_font_name = r0.font.name or "Calibri"
		default_font_size = r0.font.size
		default_bold = r0.bold or False
		default_italic = r0.italic or False
		default_color = r0.font.color.rgb if r0.font.color else None

	tokens = []
	last_end = 0
	for m in pattern.finditer(text):
		start, end = m.span()
		if start > last_end:
			tokens.append((text[last_end:start], False))
		tokens.append((text[start:end], True))
		last_end = end
	if last_end < len(text):
		tokens.append((text[last_end:], False))

	p.text = ""

	for chunk, is_jinja in tokens:
		if not chunk:
			continue
		r = p.add_run(chunk)
		r.font.name = default_font_name
		if default_font_size:
			r.font.size = default_font_size
		if default_color:
			r.font.color.rgb = default_color
		r.bold = default_bold
		r.italic = default_italic

		if is_jinja:
			r.font.highlight_color = highlight_color


def highlight_all_jinja_tags_in_docx(doc_or_path, output_path=None, highlight_color=WD_COLOR_INDEX.YELLOW):
	"""
	Scans an entire Word document (paragraphs, table cells, headers, footers)
	and applies native Word highlighting (Yellow) to every {{ variable_name }} Jinja tag.
	"""
	if isinstance(doc_or_path, str):
		doc = Document(doc_or_path)
	else:
		doc = doc_or_path

	for p in doc.paragraphs:
		highlight_jinja_in_paragraph(p, highlight_color)

	for table in doc.tables:
		for row in table.rows:
			for cell in row.cells:
				for p in cell.paragraphs:
					highlight_jinja_in_paragraph(p, highlight_color)

	for section in doc.sections:
		for hp in section.header.paragraphs:
			highlight_jinja_in_paragraph(hp, highlight_color)
		for fp in section.footer.paragraphs:
			highlight_jinja_in_paragraph(fp, highlight_color)

	if output_path:
		doc.save(output_path)
	return doc


def replace_text_in_paragraph(paragraph, search_text, replacement_text):
	"""
	Replaces search_text in a python-docx paragraph while preserving formatting.
	Handles text split across multiple OpenXML runs.
	"""
	if search_text not in paragraph.text:
		return False

	# Quick path: search_text inside a single run
	for run in paragraph.runs:
		if search_text in run.text:
			run.text = run.text.replace(search_text, replacement_text)
			return True

	# Multi-run path: text is fragmented across runs
	combined_text = "".join(r.text for r in paragraph.runs)
	if search_text in combined_text:
		new_text = combined_text.replace(search_text, replacement_text)
		if paragraph.runs:
			paragraph.runs[0].text = new_text
			for r in paragraph.runs[1:]:
				r.text = ""
		return True

	return False


def apply_variable_replacements_to_docx(source_path, target_path, approved_variables):
	"""Reads source .docx, replaces each approved variable text with {{ variable_name }}, and saves."""
	doc = Document(source_path)

	# Sort variables by length descending to prevent partial prefix replacement
	sorted_vars = sorted(approved_variables, key=lambda x: len(x.get("original_text", "")), reverse=True)

	for item in sorted_vars:
		orig_text = item.get("original_text", "").strip()
		var_name = item.get("variable_name", "").strip()
		if not orig_text or not var_name:
			continue

		jinja_tag = f"{{{{ {var_name} }}}}"

		# If already exactly this jinja tag, skip
		if orig_text == jinja_tag:
			continue

		# Prepare potential tag variations (with/without spacing)
		variations = [orig_text]
		if orig_text.startswith("{{") and orig_text.endswith("}}"):
			inner = orig_text[2:-2].strip()
			variations.extend([f"{{{{{inner}}}}}", f"{{{{ {inner} }}}}", f"{{{{  {inner}  }}}}"])

		for text_to_replace in set(variations):
			if text_to_replace == jinja_tag:
				continue
			# 1. Body paragraphs
			for p in doc.paragraphs:
				replace_text_in_paragraph(p, text_to_replace, jinja_tag)

			# 2. Table cells
			for table in doc.tables:
				for row in table.rows:
					for cell in row.cells:
						for p in cell.paragraphs:
							replace_text_in_paragraph(p, text_to_replace, jinja_tag)

	highlight_all_jinja_tags_in_docx(doc)
	doc.save(target_path)
	return target_path


def html_to_clean_docx(html_content, output_path):
	"""
	Converts edited HTML from Template Studio preview into a professional Word (.docx) document.
	Strips any UI mark tags, preserves headings, paragraphs, strong, em, lists, tables, and Jinja tags.
	"""
	soup = BeautifulSoup(html_content or "", "html.parser")
	for mark in soup.find_all("mark", class_="studio-mark"):
		for sp in mark.find_all("span"):
			sp.decompose()
		mark.unwrap()

	clean_html = str(soup)

	doc = Document()
	for section in doc.sections:
		section.top_margin = Inches(1.0)
		section.bottom_margin = Inches(1.0)
		section.left_margin = Inches(1.0)
		section.right_margin = Inches(1.0)

	style = doc.styles["Normal"]
	style.font.name = "Calibri"
	style.font.size = Pt(11)
	style.font.color.rgb = RGBColor(15, 23, 42)
	style.paragraph_format.line_spacing = 1.15
	style.paragraph_format.space_after = Pt(6)

	parser = HtmlToDocx()
	parser.add_html_to_document(clean_html, doc)
	highlight_all_jinja_tags_in_docx(doc)
	doc.save(output_path)
	return output_path


@frappe.whitelist()
def save_template_content(legal_template_name, edited_html):
	"""
	Saves edited preview HTML content from Template Studio directly back into the template's .docx file.
	"""
	if not edited_html or not edited_html.strip():
		frappe.throw(frappe._("Cannot save empty document content."))

	legal_template_doc, real_path = _get_template_file_path(legal_template_name)

	temp_path = real_path + ".tmp"
	html_to_clean_docx(edited_html, temp_path)

	if os.path.exists(temp_path):
		import shutil
		shutil.move(temp_path, real_path)

	file_url = legal_template_doc.template_file
	file_docs = frappe.get_all("File", filters={"file_url": file_url}, limit=1)
	if file_docs:
		f_doc = frappe.get_doc("File", file_docs[0].name)
		f_doc.file_size = os.path.getsize(real_path)
		f_doc.save(ignore_permissions=True)

	preview = get_document_preview(legal_template_name)
	return {
		"status": "success",
		"message": frappe._("Document content saved successfully."),
		"html": preview["html"],
		"text": preview["text"]
	}


@frappe.whitelist()
def finalize_template_and_doctype(legal_template_name, approved_variables, edited_html=None):
	"""
	1. Takes the user-approved variables (JSON or list) and optional edited HTML.
	2. If edited_html is provided, updates the .docx file with all added/edited sentences first.
	3. Modifies the .docx file replacing original text with Jinja tags.
	4. If the file is already a Jinja template, alters the existing file in-place
	   instead of creating duplicate file attachments.
	5. Automatically creates the Related DocType with exact field types (Date, Currency, Small Text, Data).
	6. Links the DocType to the Legal Template record.
	"""
	if isinstance(approved_variables, str):
		approved_variables = json.loads(approved_variables)

	if not approved_variables:
		frappe.throw(frappe._("Please provide at least one variable to generate the template."))

	legal_template_doc, real_path = _get_template_file_path(legal_template_name)

	# If user edited HTML in the preview, update source docx before applying Jinja tags
	if edited_html and edited_html.strip():
		temp_edit_path = real_path + ".finalize_edit_tmp"
		html_to_clean_docx(edited_html, temp_edit_path)
		if os.path.exists(temp_edit_path):
			import shutil
			shutil.move(temp_edit_path, real_path)

	# 1. Determine target file path
	dir_name = os.path.dirname(real_path)
	base_name = os.path.basename(real_path)
	name_part, ext = os.path.splitext(base_name)

	# Check if this file is already a generated Jinja template
	is_existing_template = "_template" in name_part

	if is_existing_template:
		# Overwrite the existing template in-place!
		target_real_path = real_path
		target_file_name = base_name
	else:
		# Create initial template file
		target_file_name = f"{name_part}_template{ext}"
		target_real_path = os.path.join(dir_name, target_file_name)

	# Apply replacements safely using temporary file
	temp_output_path = os.path.join(dir_name, f"temp_{target_file_name}")
	apply_variable_replacements_to_docx(real_path, temp_output_path, approved_variables)

	if os.path.exists(temp_output_path):
		import shutil
		shutil.move(temp_output_path, target_real_path)

	# Save/update File record
	if not is_existing_template:
		with open(target_real_path, "rb") as f:
			saved_file = save_file(
				fname=target_file_name,
				content=f.read(),
				dt="Legal Templates",
				dn=legal_template_name,
				is_private=1 if "private" in (legal_template_doc.template_file or "") else 0
			)
		legal_template_doc.template_file = saved_file.file_url
	else:
		# Update existing File record timestamp/size without creating a new File document
		file_url = legal_template_doc.template_file
		file_docs = frappe.get_all("File", filters={"file_url": file_url}, limit=1)
		if file_docs:
			f_doc = frappe.get_doc("File", file_docs[0].name)
			f_doc.file_size = os.path.getsize(target_real_path)
			f_doc.save(ignore_permissions=True)

	# 2. Construct production-grade DocType schema with professional Section & Column layout
	doctype_fields = build_doctype_layout(legal_template_doc, approved_variables)
	new_doctype_name = legal_template_name

	# Check if DocType already exists
	if frappe.db.exists("DocType", new_doctype_name):
		# Update existing DocType fields
		dt_doc = frappe.get_doc("DocType", new_doctype_name)
		dt_doc.set("fields", doctype_fields)
		dt_doc.save()
	else:
		# Create fresh custom DocType
		new_doctype = {
			"doctype": "DocType",
			"module": "Legal Documents",
			"name": new_doctype_name,
			"track_changes": 1,
			"allow_import": 1,
			"name_case": "Title Case",
			"naming_rule": 'By "Naming Series" field',
			"custom": 1,
			"fields": doctype_fields,
			"permissions": [
				{
					"role": "System Manager",
					"read": 1,
					"write": 1,
					"create": 1,
					"delete": 1
				}
			]
		}
		dt_doc = frappe.get_doc(new_doctype).insert()

	# Link related DocType
	legal_template_doc.related_doctype = new_doctype_name
	legal_template_doc.save()

	return {
		"status": "success",
		"doctype_name": new_doctype_name,
		"template_file": legal_template_doc.template_file,
		"variables_count": len(approved_variables),
	}


def clean_human_label(raw_label, vname):
	lbl = (raw_label or vname).strip()
	if "_" in lbl and " " not in lbl:
		lbl = lbl.replace("_", " ")
	lbl = re.sub(r'\bAdd\b', '', lbl, flags=re.I).strip()
	lbl = re.sub(r'\bAddr\b', 'Address', lbl, flags=re.I).strip()
	lbl = " ".join(w.capitalize() for w in lbl.split())
	if not lbl:
		lbl = vname.replace("_", " ").title()
	return lbl


def build_doctype_layout(legal_template_doc, approved_variables):
	"""
	Constructs an executive-grade, beautifully balanced DocType schema
	with Section Breaks, Column Breaks, and semantic grouping based on
	Frappe App Dev and UI Design best practices.
	"""
	fields = []
	used_fieldnames = {"name"}

	def add_field(f_dict):
		fname = f_dict.get("fieldname")
		if fname:
			if fname in used_fieldnames:
				return
			used_fieldnames.add(fname)
		fields.append(f_dict)

	# 1. Document Information (Balanced 2-Column Header)
	add_field({
		"fieldname": "sb_doc_info",
		"fieldtype": "Section Break",
		"label": "Document Information",
	})
	add_field({
		"fieldname": "matter",
		"fieldtype": "Link",
		"label": "Matter",
		"options": "Matter",
		"in_list_view": 1,
		"in_standard_filter": 1,
	})
	add_field({
		"fieldname": "naming_series",
		"fieldtype": "Select",
		"label": "Naming Series",
		"options": legal_template_doc.naming_series or f"{legal_template_doc.name.upper()[:3]}-.YYYY.-.#####",
		"reqd": 1,
	})
	add_field({
		"fieldname": "cb_doc_info",
		"fieldtype": "Column Break",
	})
	add_field({
		"fieldname": "document_status",
		"fieldtype": "Select",
		"label": "Document Status",
		"options": "Draft\nPending Execution\nExecuted\nArchived",
		"default": "Draft",
		"reqd": 1,
		"in_list_view": 1,
		"in_standard_filter": 1,
	})
	add_field({
		"fieldname": "legal_template",
		"fieldtype": "Link",
		"label": "Legal Template",
		"options": "Legal Templates",
		"read_only": 1,
		"default": legal_template_doc.name,
	})

	# Categorize variables
	party1_identity = []
	party2_identity = []
	contact_vars = []
	financial_vars = []
	date_vars = []
	other_vars = []

	p1_prefixes = ("landlord_", "lessor_", "seller_", "licensor_", "employer_", "first_party_", "party_1_")
	p2_prefixes = ("tenant_", "lessee_", "buyer_", "licensee_", "employee_", "second_party_", "party_2_")
	contact_terms = ("email", "phone", "mobile", "tel", "fax", "contact")

	ALL_FRAPPE_FIELDTYPES = {
		"Autocomplete", "Attach", "Attach Image", "Attachment Gallery", "Barcode", "Button",
		"Check", "Code", "Color", "Column Break", "Currency", "Data", "Date", "Datetime",
		"Duration", "Dynamic Link", "Float", "Fold", "Geolocation", "Heading", "HTML",
		"HTML Editor", "Icon", "Image", "Int", "JSON", "Link", "Long Text", "Markdown Editor",
		"Password", "Percent", "Phone", "Read Only", "Rating", "Section Break", "Select",
		"Signature", "Small Text", "Tab Break", "Table", "Table MultiSelect", "Text",
		"Text Editor", "Time"
	}

	for v in approved_variables:
		vname = frappe.scrub(v.get("variable_name", ""))
		if not vname or vname in ("naming_series", "matter", "name", "document_status", "legal_template"):
			continue

		vcopy = dict(v)
		vcopy["variable_name"] = vname
		raw_lbl = vcopy.get("label", "")
		vcopy["label"] = clean_human_label(raw_lbl, vname)

		# Respect user-chosen or detected fieldtype if it is a valid Frappe fieldtype
		user_ftype = vcopy.get("fieldtype")
		if user_ftype and user_ftype in ALL_FRAPPE_FIELDTYPES:
			ftype = user_ftype
		else:
			# Intelligent heuristic fallback
			if any(ct in vname for ct in ("phone", "mobile", "cell", "tel")):
				ftype = "Phone"
			elif any(ct in vname for ct in ("email", "mail")):
				ftype = "Data"
			elif any(term in vname for term in ("amount", "rent", "deposit", "fee", "price", "charges", "salary", "consideration")):
				ftype = "Currency"
			elif any(term in vname for term in ("date", "expiry", "commencement", "deadline")):
				ftype = "Date"
			elif any(term in vname for term in ("address", "premises")):
				ftype = "Small Text"
			elif any(term in vname for term in ("sign", "signature")):
				ftype = "Signature"
			elif any(term in vname for term in ("pct", "percent", "percentage")):
				ftype = "Percent"
			else:
				ftype = "Data"

		vcopy["fieldtype"] = ftype

		# Section grouping
		if any(ct in vname for ct in contact_terms):
			contact_vars.append(vcopy)
		elif any(vname.startswith(p) for p in p1_prefixes):
			party1_identity.append(vcopy)
		elif any(vname.startswith(p) for p in p2_prefixes):
			party2_identity.append(vcopy)
		elif ftype == "Currency" or any(term in vname for term in ("amount", "rent", "deposit", "fee", "price", "charges", "salary", "consideration")):
			financial_vars.append(vcopy)
		elif ftype in ("Date", "Datetime", "Time") or any(term in vname for term in ("date", "expiry", "commencement", "deadline")):
			date_vars.append(vcopy)
		else:
			other_vars.append(vcopy)

	def make_field(v, in_list=False):
		vname = v["variable_name"]
		ftype = v.get("fieldtype", "Data")
		if ftype not in ALL_FRAPPE_FIELDTYPES:
			ftype = "Data"

		fdict = {
			"fieldname": vname,
			"label": v.get("label") or vname.replace("_", " ").title(),
			"fieldtype": ftype,
		}

		# Frappe validation: no-value types and multi-line editor types cannot have in_list_view = 1
		no_list_view_types = {
			"Section Break", "Column Break", "Tab Break", "Fold", "Heading",
			"HTML", "HTML Editor", "Text Editor", "Markdown Editor", "Code",
			"JSON", "Long Text", "Text", "Table", "Table MultiSelect", "Image",
			"Attachment Gallery", "Button"
		}
		fdict["in_list_view"] = 1 if (in_list and ftype not in no_list_view_types) else 0

		# Fieldtype specific requirements for valid Frappe DocType schema
		if ftype == "Link":
			fdict["options"] = v.get("options") or "Matter"
		elif ftype == "Select":
			fdict["options"] = v.get("options") or "Option 1\nOption 2"
		elif ftype == "Check":
			fdict["default"] = str(v.get("default", "0"))
		elif ftype in ("Table", "Table MultiSelect"):
			fdict["options"] = v.get("options") or ""

		return fdict

	# 2. Parties Information Section (Symmetrical 2 Columns: Party 1 vs Party 2)
	if party1_identity or party2_identity:
		add_field({
			"fieldname": "sb_parties",
			"fieldtype": "Section Break",
			"label": "Parties Details",
		})
		for i, v in enumerate(party1_identity):
			add_field(make_field(v, in_list=(i == 0)))

		add_field({
			"fieldname": "cb_parties",
			"fieldtype": "Column Break",
		})
		for i, v in enumerate(party2_identity):
			add_field(make_field(v, in_list=(i == 0)))

	# 3. Contact & Communication Details (Balanced 2 Columns)
	if contact_vars:
		add_field({
			"fieldname": "sb_contacts",
			"fieldtype": "Section Break",
			"label": "Contact & Communication Details",
		})
		half = (len(contact_vars) + 1) // 2
		for v in contact_vars[:half]:
			add_field(make_field(v, in_list=False))
		add_field({
			"fieldname": "cb_contacts",
			"fieldtype": "Column Break",
		})
		for v in contact_vars[half:]:
			add_field(make_field(v, in_list=False))

	# 4. Financial & Commercial Terms Section (Balanced 2 Columns)
	if financial_vars:
		add_field({
			"fieldname": "sb_financials",
			"fieldtype": "Section Break",
			"label": "Financials & Commercial Terms",
		})
		half = (len(financial_vars) + 1) // 2
		for v in financial_vars[:half]:
			add_field(make_field(v, in_list=True))
		add_field({
			"fieldname": "cb_financials",
			"fieldtype": "Column Break",
		})
		for v in financial_vars[half:]:
			add_field(make_field(v, in_list=True))

	# 5. Key Dates & Schedule Section (Balanced 2 Columns)
	if date_vars:
		add_field({
			"fieldname": "sb_dates",
			"fieldtype": "Section Break",
			"label": "Key Dates & Schedules",
		})
		half = (len(date_vars) + 1) // 2
		for v in date_vars[:half]:
			add_field(make_field(v, in_list=True))
		add_field({
			"fieldname": "cb_dates",
			"fieldtype": "Column Break",
		})
		for v in date_vars[half:]:
			add_field(make_field(v, in_list=False))

	# 6. Property & Additional Particulars Section (Balanced 2 Columns)
	if other_vars:
		var_names_str = " ".join([v["variable_name"] for v in other_vars])
		is_property = any(term in var_names_str for term in ("city", "state", "property", "premises", "address", "flat", "plot"))
		section_title = "Property & Location Details" if is_property else "Additional Particulars"
		add_field({
			"fieldname": "sb_additional",
			"fieldtype": "Section Break",
			"label": section_title,
		})
		half = (len(other_vars) + 1) // 2
		for v in other_vars[:half]:
			add_field(make_field(v, in_list=False))
		add_field({
			"fieldname": "cb_additional",
			"fieldtype": "Column Break",
		})
		for v in other_vars[half:]:
			add_field(make_field(v, in_list=False))

	return fields


@frappe.whitelist()
def download_jinja_template(legal_template_name):
	"""
	Generates/fetches the Word .docx file with all {{ variables }} highlighted in yellow
	and streams it to the browser as a downloadable Word attachment.
	"""
	legal_template_doc, real_path = _get_template_file_path(legal_template_name)

	# Load and ensure all Jinja tags are highlighted in Word yellow
	doc = Document(real_path)
	highlight_all_jinja_tags_in_docx(doc)

	output_stream = io.BytesIO()
	doc.save(output_stream)
	output_stream.seek(0)

	fname = os.path.basename(real_path)
	if not fname.endswith(".docx"):
		fname = f"{fname}.docx"

	frappe.response["filecontent"] = output_stream.getvalue()
	frappe.response["filename"] = fname
	frappe.response["type"] = "download"
	frappe.response["display_content_as"] = "attachment"


@frappe.whitelist(allow_guest=True)
def download_sample_agreement(file_type="pdf"):
	"""Forces the browser to download the sample agreement with explicit PDF or Word headers."""
	if file_type == "docx":
		file_path = "/home/abdullah/Sample_Rental_Agreement.docx"
		filename = "Sample_Rental_Agreement.docx"
	else:
		file_path = "/home/abdullah/Sample_Rental_Agreement.pdf"
		filename = "Sample_Rental_Agreement.pdf"

	if not os.path.exists(file_path):
		frappe.throw(frappe._("Sample file not found at {0}").format(file_path))

	with open(file_path, "rb") as f:
		content = f.read()

	frappe.response["filecontent"] = content
	frappe.response["filename"] = filename
	frappe.response["type"] = "download"
	frappe.response["display_content_as"] = "attachment"


@frappe.whitelist()
def save_ai_key(api_key, provider=None):
	"""
	Saves user-provided API key into Flow Provider & Flow Model (if Flow is installed),
	and into site defaults as a resilient fallback.
	"""
	if not frappe.has_permission("Legal Templates", "write"):
		frappe.throw(frappe._("Not permitted"), frappe.PermissionError)

	clean_key = (api_key or "").strip()
	if not clean_key:
		frappe.db.set_default("gemini_api_key", "")
		frappe.db.set_default("groq_api_key", "")
		if frappe.db.exists("DocType", "Flow Provider"):
			for p in frappe.get_all("Flow Provider", fields=["name"]):
				p_doc = frappe.get_doc("Flow Provider", p.name)
				p_doc.api_key = ""
				p_doc.save(ignore_permissions=True)
		frappe.db.commit()
		return {"status": "success", "message": "AI API Key cleared."}

	# Detect provider if not given
	if not provider:
		if clean_key.startswith("AIza"):
			provider = "gemini"
		elif clean_key.startswith("gsk_"):
			provider = "groq"
		elif clean_key.startswith("sk-"):
			provider = "openai"
		else:
			provider = "gemini"

	# 1. Update Frappe Flow Provider & Model if Flow is installed
	if frappe.db.exists("DocType", "Flow Provider"):
		try:
			if frappe.db.exists("Flow Provider", provider):
				prov_doc = frappe.get_doc("Flow Provider", provider)
				prov_doc.api_key = clean_key
				prov_doc.enabled = 1
				prov_doc.save(ignore_permissions=True)
			else:
				prov_doc = frappe.get_doc({
					"doctype": "Flow Provider",
					"provider": provider,
					"api_key": clean_key,
					"enabled": 1,
				})
				prov_doc.insert(ignore_permissions=True)

			# Ensure corresponding Flow Model exists
			default_models = {
				"gemini": ("Gemini 3.5 Flash", "gemini/gemini-3.5-flash"),
				"groq": ("Groq Llama 3.3 70B", "groq/llama-3.3-70b-versatile"),
				"openai": ("GPT-4o Mini", "openai/gpt-4o-mini"),
			}
			if provider in default_models and frappe.db.exists("DocType", "Flow Model"):
				m_title, m_id = default_models[provider]
				if frappe.db.exists("Flow Model", m_title):
					m_doc = frappe.get_doc("Flow Model", m_title)
					m_doc.provider = provider
					m_doc.model_id = m_id
					m_doc.enabled = 1
					m_doc.save(ignore_permissions=True)
				else:
					m_doc = frappe.get_doc({
						"doctype": "Flow Model",
						"title": m_title,
						"provider": provider,
						"model_id": m_id,
						"enabled": 1,
					})
					m_doc.insert(ignore_permissions=True)
		except Exception as e:
			frappe.log_error(f"Failed to sync with Flow Provider: {str(e)}")

	# 2. Resilient fallback to site defaults
	if provider == "groq" or clean_key.startswith("gsk_"):
		frappe.db.set_default("groq_api_key", clean_key)
	else:
		frappe.db.set_default("gemini_api_key", clean_key)

	frappe.db.commit()
	return {
		"status": "success",
		"provider": provider,
		"message": f"Successfully configured API key for {provider.title()} in Flow AI and site defaults.",
	}


