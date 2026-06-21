"""
Generate 1000 realistic Indian HR documents for 100 employees across 10 organizations.
Outputs: PRANA/test_docs.zip + credentials_summary.txt
"""

import os, io, json, random, zipfile, textwrap
from datetime import date, timedelta
from pathlib import Path
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, KeepTogether
)
from reportlab.pdfgen import canvas

W, H = A4

# ── Master data ────────────────────────────────────────────────────────────────

ORGS = [
    {"id": "ORG01", "name": "TechNova Solutions Pvt Ltd",     "domain": "technova.in",     "city": "Bengaluru", "sector": "IT Services",       "pan_prefix": "AABCT"},
    {"id": "ORG02", "name": "Greenfield Infra Ltd",           "domain": "greenfield.co.in","city": "Mumbai",    "sector": "Infrastructure",    "pan_prefix": "AABCG"},
    {"id": "ORG03", "name": "Bharat FinServ Pvt Ltd",         "domain": "bharatfin.in",    "city": "Pune",      "sector": "Financial Services","pan_prefix": "AABCB"},
    {"id": "ORG04", "name": "Sunrise Pharmaceuticals Ltd",    "domain": "sunrisepharma.in","city": "Hyderabad", "sector": "Pharma",            "pan_prefix": "AABCS"},
    {"id": "ORG05", "name": "DigiSpark Technologies Pvt Ltd", "domain": "digispark.io",    "city": "Chennai",   "sector": "SaaS / Product",    "pan_prefix": "AABCD"},
    {"id": "ORG06", "name": "Indus Retail Chain Ltd",         "domain": "indusretail.in",  "city": "Delhi",     "sector": "Retail",            "pan_prefix": "AABCI"},
    {"id": "ORG07", "name": "KaleidoMedia Pvt Ltd",           "domain": "kaleidomedia.in", "city": "Mumbai",    "sector": "Media & AdTech",    "pan_prefix": "AABCK"},
    {"id": "ORG08", "name": "PrimeLogistics Solutions Ltd",   "domain": "primelogix.in",   "city": "Kolkata",   "sector": "Logistics",         "pan_prefix": "AABCP"},
    {"id": "ORG09", "name": "NovaCure Health Services Pvt Ltd","domain":"novacure.in",     "city": "Bengaluru", "sector": "Healthcare",        "pan_prefix": "AABCN"},
    {"id": "ORG10", "name": "AgroTech India Pvt Ltd",         "domain": "agrotech.in",     "city": "Nagpur",    "sector": "AgriTech",          "pan_prefix": "AABCA"},
]

FIRST_NAMES = [
    "Priya","Rahul","Anjali","Vikram","Sneha","Arjun","Pooja","Karan",
    "Divya","Rohan","Meera","Aakash","Neha","Suresh","Kavya","Amit",
    "Ritu","Varun","Shweta","Deepak","Ananya","Rajesh","Shruti","Nikhil",
    "Preeti","Saurabh","Isha","Vivek","Simran","Gaurav","Riya","Pranav",
    "Tanvi","Mohit","Jyoti","Sandeep","Pallavi","Ankur","Sonal","Tarun",
]
LAST_NAMES = [
    "Sharma","Verma","Patel","Singh","Mehta","Gupta","Nair","Joshi",
    "Iyer","Kapoor","Reddy","Desai","Shah","Chopra","Mishra","Agarwal",
    "Pandey","Kumar","Rao","Tiwari","Bose","Pillai","Menon","Sinha",
]
DESIGNATIONS = {
    "IT Services":       ["Software Engineer","Senior Software Engineer","Tech Lead","Engineering Manager","VP Engineering","Product Manager","QA Engineer","DevOps Engineer"],
    "Infrastructure":    ["Site Engineer","Project Engineer","Senior Engineer","Project Manager","GM Projects","Safety Officer","Civil Engineer","Estimator"],
    "Financial Services":["Analyst","Senior Analyst","Associate Manager","Manager","Senior Manager","AVP","VP","Chief Risk Officer"],
    "Pharma":            ["Research Associate","Scientist","Senior Scientist","Research Manager","Head of R&D","Regulatory Affairs Manager","QA Specialist"],
    "SaaS / Product":    ["Software Developer","Senior Developer","Staff Engineer","Principal Engineer","CTO","Product Designer","Data Scientist","ML Engineer"],
    "Retail":            ["Store Associate","Team Lead","Store Manager","Regional Manager","VP Operations","Category Manager","Supply Chain Analyst"],
    "Media & AdTech":    ["Content Writer","Content Lead","Creative Head","Campaign Manager","Product Manager","Data Analyst","Ad Operations Manager"],
    "Logistics":         ["Operations Associate","Fleet Coordinator","Operations Manager","Regional Head","VP Logistics","Warehouse Supervisor","Route Planner"],
    "Healthcare":        ["Staff Nurse","Senior Nurse","Clinical Coordinator","Medical Officer","HOD","Hospital Administrator","Biomedical Engineer"],
    "AgriTech":          ["Field Officer","Senior Field Officer","District Manager","Zone Head","VP Agri","Data Analyst","Product Manager"],
}
DEPARTMENTS = {
    "IT Services":       ["Engineering","Product","QA","DevOps","Operations"],
    "Infrastructure":    ["Civil","Projects","Safety","Estimation","Contracts"],
    "Financial Services":["Risk","Credit","Operations","Compliance","Treasury"],
    "Pharma":            ["R&D","Quality","Manufacturing","Regulatory","Sales"],
    "SaaS / Product":    ["Engineering","Product","Design","Data","Customer Success"],
    "Retail":            ["Operations","Merchandising","Supply Chain","HR","Finance"],
    "Media & AdTech":    ["Content","Creative","Sales","Product","Technology"],
    "Logistics":         ["Operations","Fleet","Warehouse","Technology","Finance"],
    "Healthcare":        ["Clinical","Administration","Finance","IT","Operations"],
    "AgriTech":          ["Field Operations","Product","Technology","Data","Sales"],
}

SALARY_BANDS = {
    # (grade_index_0_based) → (min_ctc, max_ctc) in INR per annum
    0: (360000,  600000),
    1: (600000,  1000000),
    2: (1000000, 1600000),
    3: (1600000, 2500000),
    4: (2500000, 4000000),
    5: (4000000, 8000000),
    6: (8000000, 15000000),
    7: (15000000,25000000),
}

DOC_TYPES = ["SALARY_SLIP","APPOINTMENT_LETTER","OFFER_LETTER","INCREMENT_LETTER",
             "PROMOTION_LETTER","FORM_16","RELIEVING_LETTER","EXPERIENCE_LETTER"]

# ── Helpers ────────────────────────────────────────────────────────────────────

rng = random.Random(42)   # deterministic

def pan(prefix, idx):
    digits = str(1000 + idx).zfill(4)
    alpha = chr(ord('A') + (idx % 26))
    return f"{prefix}{digits}{alpha}"

def phone(org_idx, emp_idx):
    # +91 9XXXXXXXXX
    base = 9000000000 + org_idx * 1000 + emp_idx
    return f"+91 {base}"

def fmt_inr(amount):
    # Indian number formatting
    s = str(int(amount))
    if len(s) <= 3:
        return s
    last3 = s[-3:]
    rest = s[:-3]
    parts = []
    while rest:
        parts.append(rest[-2:] if len(rest) >= 2 else rest)
        rest = rest[:-2]
    return ",".join(reversed(parts)) + "," + last3

def add_month(d, months):
    m = d.month - 1 + months
    y = d.year + m // 12
    m = m % 12 + 1
    return date(y, m, 1)

def fy_label(d):
    if d.month >= 4:
        return f"FY {d.year}-{str(d.year+1)[2:]}"
    return f"FY {d.year-1}-{str(d.year)[2:]}"

# ── PDF generators ─────────────────────────────────────────────────────────────

def _header_canvas(c, doc, org, title, date_str):
    c.saveState()
    c.setFillColor(colors.HexColor("#1E3A5F"))
    c.rect(0, H - 60*mm, W, 60*mm, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 14)
    c.drawString(20*mm, H - 22*mm, org["name"])
    c.setFont("Helvetica", 9)
    c.drawString(20*mm, H - 32*mm, f"{org['city']}  |  {org['domain']}  |  CIN: U72200KA2015PTC12345{org['id'][-2:]}")
    c.setFillColor(colors.HexColor("#F0F4F8"))
    c.setFont("Helvetica-Bold", 13)
    c.drawString(20*mm, H - 48*mm, title)
    c.setFont("Helvetica", 9)
    c.drawRightString(W - 20*mm, H - 48*mm, date_str)
    c.restoreState()

def _footer(c, doc):
    c.saveState()
    c.setStrokeColor(colors.HexColor("#CBD5E1"))
    c.line(20*mm, 15*mm, W - 20*mm, 15*mm)
    c.setFont("Helvetica", 7)
    c.setFillColor(colors.HexColor("#64748B"))
    c.drawString(20*mm, 10*mm, "This is a system-generated document. No signature required.")
    c.drawRightString(W - 20*mm, 10*mm, f"PRANA Document Vault | {date.today().isoformat()}")
    c.restoreState()


def gen_salary_slip(emp, org, month_date, seq):
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    _header_canvas(c, None, org, "SALARY SLIP", month_date.strftime("%B %Y"))
    _footer(c, None)

    ctc = emp["ctc"]
    gross_monthly = int(ctc / 12)
    basic = int(gross_monthly * 0.40)
    hra   = int(gross_monthly * 0.20)
    ta    = int(gross_monthly * 0.10)
    special= gross_monthly - basic - hra - ta
    pf_emp = int(basic * 0.12)
    pf_er  = int(basic * 0.12)
    prof_tax = 200
    tds   = max(0, int((ctc - 500000) / 12 * 0.10)) if ctc > 500000 else 0
    total_ded = pf_emp + prof_tax + tds
    net_pay = gross_monthly - total_ded

    c.setFont("Helvetica-Bold", 10)
    c.setFillColor(colors.HexColor("#1E3A5F"))
    c.drawString(20*mm, H - 75*mm, "EMPLOYEE INFORMATION")
    c.setFont("Helvetica", 9)
    c.setFillColor(colors.black)

    info = [
        ("Employee Name", emp["name"]),      ("Employee ID", emp["emp_id"]),
        ("Designation",  emp["designation"]),("Department",   emp["department"]),
        ("PAN",          emp["pan"]),         ("PF Number",   f"KA/{org['id']}/{seq:04d}"),
        ("Bank Account", f"XXXX XXXX {emp['emp_idx']:04d}"),("Bank", "HDFC Bank"),
    ]
    y = H - 85*mm
    for i, (k, v) in enumerate(info):
        x = 20*mm if i % 2 == 0 else 110*mm
        if i % 2 == 0 and i > 0:
            y -= 7*mm
        c.setFont("Helvetica-Bold", 8)
        c.drawString(x, y, f"{k}:")
        c.setFont("Helvetica", 8)
        c.drawString(x + 35*mm, y, str(v))

    y -= 15*mm
    c.setFont("Helvetica-Bold", 10)
    c.setFillColor(colors.HexColor("#1E3A5F"))
    c.drawString(20*mm, y, "EARNINGS & DEDUCTIONS")

    y -= 5*mm
    # Table
    data = [
        ["EARNINGS", "Amount (INR)", "DEDUCTIONS", "Amount (INR)"],
        ["Basic Salary", f"INR {fmt_inr(basic)}", "PF (Employee)", f"INR {fmt_inr(pf_emp)}"],
        ["HRA", f"INR {fmt_inr(hra)}", "Professional Tax", f"INR {fmt_inr(prof_tax)}"],
        ["Travel Allowance", f"INR {fmt_inr(ta)}", "TDS", f"INR {fmt_inr(tds)}"],
        ["Special Allowance", f"INR {fmt_inr(special)}", "", ""],
        ["", "", "", ""],
        [f"Gross Earnings", f"INR {fmt_inr(gross_monthly)}", "Total Deductions", f"INR {fmt_inr(total_ded)}"],
    ]
    t = Table(data, colWidths=[55*mm, 40*mm, 55*mm, 40*mm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#1E3A5F")),
        ("TEXTCOLOR",  (0,0), (-1,0), colors.white),
        ("FONTNAME",   (0,0), (-1,0), "Helvetica-Bold"),
        ("FONTSIZE",   (0,0), (-1,-1), 8),
        ("FONTNAME",   (0,-1), (-1,-1), "Helvetica-Bold"),
        ("BACKGROUND", (0,-1), (-1,-1), colors.HexColor("#EFF6FF")),
        ("GRID",       (0,0),  (-1,-1), 0.5, colors.HexColor("#CBD5E1")),
        ("ROWBACKGROUNDS", (0,1), (-1,-2), [colors.white, colors.HexColor("#F8FAFC")]),
        ("ALIGN",      (1,0),  (1,-1), "RIGHT"),
        ("ALIGN",      (3,0),  (3,-1), "RIGHT"),
        ("TOPPADDING", (0,0),  (-1,-1), 4),
        ("BOTTOMPADDING",(0,0),(-1,-1), 4),
    ]))

    from reportlab.platypus import Frame
    frame = Frame(20*mm, y - 75*mm, W - 40*mm, 75*mm, showBoundary=0)

    class TableDrawer:
        def __init__(self, table): self._t = table
        def wrap(self, *a): return self._t.wrap(*a)
        def drawOn(self, c, x, y): self._t.drawOn(c, x, y)

    t.wrapOn(c, W - 40*mm, 75*mm)
    t.drawOn(c, 20*mm, y - 72*mm)

    ny = y - 78*mm
    c.setFillColor(colors.HexColor("#1E3A5F"))
    c.setFont("Helvetica-Bold", 11)
    c.drawString(20*mm, ny, f"NET PAY:  INR {fmt_inr(net_pay)}")
    c.setFont("Helvetica", 8)
    c.setFillColor(colors.HexColor("#64748B"))
    # Amount in words (simplified)
    c.drawString(20*mm, ny - 7*mm, f"(Rupees {net_pay:,} Only)")

    c.save()
    return buf.getvalue()


def gen_appointment_letter(emp, org):
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    _header_canvas(c, None, org, "APPOINTMENT LETTER", emp["doj"].strftime("%d %B %Y"))
    _footer(c, None)

    y = H - 70*mm
    c.setFont("Helvetica", 9)
    c.setFillColor(colors.black)
    c.drawString(20*mm, y, f"Date: {emp['doj'].strftime('%d %B %Y')}")
    y -= 8*mm
    c.drawString(20*mm, y, f"To,")
    y -= 6*mm
    c.setFont("Helvetica-Bold", 9)
    c.drawString(20*mm, y, emp["name"])
    y -= 5*mm
    c.setFont("Helvetica", 9)
    c.drawString(20*mm, y, emp["address"])
    y -= 12*mm
    c.setFont("Helvetica-Bold", 10)
    c.drawString(20*mm, y, "Dear Candidate,")
    y -= 8*mm
    c.setFont("Helvetica-Bold", 10)
    c.drawString(20*mm, y, "APPOINTMENT LETTER")
    y -= 8*mm
    c.setFont("Helvetica", 9)
    body = (
        f"We are pleased to appoint you as {emp['designation']} in the {emp['department']} department "
        f"at {org['name']}, effective {emp['doj'].strftime('%d %B %Y')}. "
        f"Your appointment is subject to the terms and conditions set forth herein."
    )
    _wrap_text(c, body, 20*mm, y, W - 40*mm, 5.5*mm)
    y -= 30*mm

    data = [
        ["Designation",       emp["designation"]],
        ["Department",        emp["department"]],
        ["Date of Joining",   emp["doj"].strftime("%d %B %Y")],
        ["Location",          org["city"]],
        ["CTC Per Annum",     f"INR {fmt_inr(emp['ctc'])} (Cost to Company)"],
        ["Employment Type",   "Permanent, Full-Time"],
        ["Probation Period",  "6 months"],
        ["Notice Period",     "90 days (post probation)"],
    ]
    _draw_kv_table(c, data, 20*mm, y)
    y -= len(data)*8*mm - 10*mm

    c.setFont("Helvetica", 9)
    c.drawString(20*mm, y, "Please sign and return a copy of this letter as confirmation of your acceptance.")
    y -= 20*mm
    c.setFont("Helvetica-Bold", 9)
    c.drawString(20*mm, y, "For " + org["name"])
    y -= 15*mm
    c.drawString(20*mm, y, "_________________________")
    y -= 6*mm
    c.setFont("Helvetica", 8)
    c.drawString(20*mm, y, "Authorised Signatory")
    c.drawString(20*mm, y - 5*mm, "Human Resources")

    c.save()
    return buf.getvalue()


def gen_offer_letter(emp, org):
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    offer_date = emp["doj"] - timedelta(days=rng.randint(14, 30))
    _header_canvas(c, None, org, "OFFER LETTER", offer_date.strftime("%d %B %Y"))
    _footer(c, None)

    y = H - 70*mm
    c.setFont("Helvetica", 9)
    c.drawString(20*mm, y, f"Ref: {org['id']}/HR/OL/{offer_date.year}/{emp['emp_idx']:03d}")
    y -= 6*mm
    c.drawString(20*mm, y, f"Date: {offer_date.strftime('%d %B %Y')}")
    y -= 12*mm
    c.setFont("Helvetica-Bold", 9)
    c.drawString(20*mm, y, emp["name"])
    y -= 10*mm
    c.setFont("Helvetica-Bold", 10)
    c.drawString(20*mm, y, "Subject: Offer of Employment")
    y -= 8*mm
    c.setFont("Helvetica", 9)
    body = (
        f"We are delighted to offer you the position of {emp['designation']} with {org['name']} "
        f"in our {org['city']} office. This offer is contingent upon successful verification of your credentials."
    )
    _wrap_text(c, body, 20*mm, y, W - 40*mm, 5.5*mm)
    y -= 25*mm

    data = [
        ["Position",          emp["designation"]],
        ["Department",        emp["department"]],
        ["Location",          org["city"]],
        ["Proposed DOJ",      emp["doj"].strftime("%d %B %Y")],
        ["Annual CTC",        f"INR {fmt_inr(emp['ctc'])}"],
        ["Offer Valid Until", (offer_date + timedelta(days=7)).strftime("%d %B %Y")],
    ]
    _draw_kv_table(c, data, 20*mm, y)

    c.save()
    return buf.getvalue()


def gen_increment_letter(emp, org, increment_date, old_ctc, new_ctc):
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    _header_canvas(c, None, org, "SALARY INCREMENT LETTER", increment_date.strftime("%d %B %Y"))
    _footer(c, None)

    hike_pct = round((new_ctc - old_ctc) / old_ctc * 100, 1)
    y = H - 70*mm
    c.setFont("Helvetica", 9)
    c.drawString(20*mm, y, f"Date: {increment_date.strftime('%d %B %Y')}")
    y -= 10*mm
    c.setFont("Helvetica-Bold", 9)
    c.drawString(20*mm, y, emp["name"])
    y -= 5*mm
    c.setFont("Helvetica", 9)
    c.drawString(20*mm, y, emp["designation"] + " | " + emp["department"])
    y -= 12*mm
    c.setFont("Helvetica-Bold", 10)
    c.drawString(20*mm, y, "Subject: Annual Salary Increment")
    y -= 8*mm
    c.setFont("Helvetica", 9)
    body = (
        f"We are pleased to inform you that based on your performance review and contribution to {org['name']}, "
        f"the management has approved a salary revision of {hike_pct}% effective "
        f"{increment_date.strftime('%d %B %Y')}."
    )
    _wrap_text(c, body, 20*mm, y, W - 40*mm, 5.5*mm)
    y -= 25*mm

    data = [
        ["Employee Name",   emp["name"]],
        ["Employee ID",     emp["emp_id"]],
        ["Effective Date",  increment_date.strftime("%d %B %Y")],
        ["Previous CTC",    f"INR {fmt_inr(old_ctc)} per annum"],
        ["Revised CTC",     f"INR {fmt_inr(new_ctc)} per annum"],
        ["Increment",       f"{hike_pct}%"],
    ]
    _draw_kv_table(c, data, 20*mm, y)

    c.save()
    return buf.getvalue()


def gen_promotion_letter(emp, org, promo_date, old_desig, new_desig, new_ctc):
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    _header_canvas(c, None, org, "PROMOTION LETTER", promo_date.strftime("%d %B %Y"))
    _footer(c, None)

    y = H - 70*mm
    c.setFont("Helvetica", 9)
    c.drawString(20*mm, y, f"Date: {promo_date.strftime('%d %B %Y')}")
    y -= 10*mm
    c.setFont("Helvetica-Bold", 9)
    c.drawString(20*mm, y, emp["name"])
    y -= 10*mm
    c.setFont("Helvetica-Bold", 10)
    c.drawString(20*mm, y, "Subject: Promotion")
    y -= 8*mm
    c.setFont("Helvetica", 9)
    body = (
        f"We are delighted to inform you of your promotion from {old_desig} to {new_desig} "
        f"effective {promo_date.strftime('%d %B %Y')}. This reflects our recognition of your "
        f"outstanding performance, dedication, and leadership qualities."
    )
    _wrap_text(c, body, 20*mm, y, W - 40*mm, 5.5*mm)
    y -= 30*mm

    data = [
        ["Current Designation", old_desig],
        ["New Designation",     new_desig],
        ["Department",          emp["department"]],
        ["Effective Date",      promo_date.strftime("%d %B %Y")],
        ["Revised CTC",         f"INR {fmt_inr(new_ctc)} per annum"],
    ]
    _draw_kv_table(c, data, 20*mm, y)

    c.save()
    return buf.getvalue()


def gen_form16(emp, org, fy_year):
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    fy = f"{fy_year}-{str(fy_year+1)[2:]}"
    _header_canvas(c, None, org, f"FORM 16 — TDS CERTIFICATE", f"FY {fy}")
    _footer(c, None)

    gross_annual = emp["ctc"]
    basic_annual = int(gross_annual * 0.40)
    hra_annual   = int(gross_annual * 0.20)
    other        = gross_annual - basic_annual - hra_annual
    std_ded      = 50000
    taxable      = max(0, gross_annual - std_ded - 150000)
    tds_total    = max(0, int(taxable * 0.10)) if taxable > 500000 else 0

    y = H - 68*mm
    c.setFont("Helvetica-Bold", 9)
    c.setFillColor(colors.HexColor("#1E3A5F"))
    c.drawString(20*mm, y, "PART A — DETAILS OF DEDUCTOR")
    y -= 5*mm
    c.setFillColor(colors.black)
    data = [
        ["Employer Name",    org["name"]],
        ["Employer PAN",     org["pan_prefix"] + "7890P"],
        ["Employer TAN",     f"BLR{org['id'][-2:]}12345A"],
        ["Period",           f"01 April {fy_year} to 31 March {fy_year+1}"],
    ]
    _draw_kv_table(c, data, 20*mm, y, small=True)
    y -= 40*mm

    c.setFont("Helvetica-Bold", 9)
    c.setFillColor(colors.HexColor("#1E3A5F"))
    c.drawString(20*mm, y, "PART B — DETAILS OF DEDUCTEE")
    y -= 5*mm
    c.setFillColor(colors.black)
    data2 = [
        ["Employee Name",    emp["name"]],
        ["Employee PAN",     emp["pan"]],
        ["Employee ID",      emp["emp_id"]],
        ["Designation",      emp["designation"]],
    ]
    _draw_kv_table(c, data2, 20*mm, y, small=True)
    y -= 40*mm

    c.setFont("Helvetica-Bold", 9)
    c.setFillColor(colors.HexColor("#1E3A5F"))
    c.drawString(20*mm, y, "PART C — SALARY PARTICULARS")
    y -= 5*mm
    c.setFillColor(colors.black)
    data3 = [
        ["Gross Salary",                    f"INR {fmt_inr(gross_annual)}"],
        ["  Basic Salary",                  f"INR {fmt_inr(basic_annual)}"],
        ["  HRA",                           f"INR {fmt_inr(hra_annual)}"],
        ["  Other Allowances",              f"INR {fmt_inr(other)}"],
        ["Less: Standard Deduction",        f"INR {fmt_inr(std_ded)}"],
        ["Less: Section 80C (PF + PPF)",    f"INR {fmt_inr(min(150000, int(basic_annual*0.12*12)))}"],
        ["Taxable Income",                  f"INR {fmt_inr(taxable)}"],
        ["Tax on Total Income",             f"INR {fmt_inr(tds_total)}"],
        ["Total TDS Deducted",              f"INR {fmt_inr(tds_total)}"],
    ]
    _draw_kv_table(c, data3, 20*mm, y, small=True)

    c.save()
    return buf.getvalue()


def gen_experience_letter(emp, org, last_day):
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    _header_canvas(c, None, org, "EXPERIENCE LETTER", last_day.strftime("%d %B %Y"))
    _footer(c, None)

    years = round((last_day - emp["doj"]).days / 365, 1)
    y = H - 70*mm
    c.setFont("Helvetica", 9)
    c.drawString(20*mm, y, f"Date: {last_day.strftime('%d %B %Y')}")
    y -= 12*mm
    c.setFont("Helvetica-Bold", 10)
    c.drawString(20*mm, y, "TO WHOMSOEVER IT MAY CONCERN")
    y -= 10*mm
    c.setFont("Helvetica", 9)
    body = (
        f"This is to certify that {emp['name']} (PAN: {emp['pan']}) was employed with {org['name']} "
        f"as {emp['designation']} in the {emp['department']} department from "
        f"{emp['doj'].strftime('%d %B %Y')} to {last_day.strftime('%d %B %Y')} "
        f"— a period of {years} years. During this period, they demonstrated exemplary "
        f"professionalism and were a valued member of our team. We wish them success in their future endeavours."
    )
    _wrap_text(c, body, 20*mm, y, W - 40*mm, 5.5*mm)
    y -= 45*mm

    data = [
        ["Employee Name",   emp["name"]],
        ["Employee ID",     emp["emp_id"]],
        ["Designation",     emp["designation"]],
        ["Department",      emp["department"]],
        ["Date of Joining", emp["doj"].strftime("%d %B %Y")],
        ["Last Working Day",last_day.strftime("%d %B %Y")],
        ["Tenure",          f"{years} years"],
    ]
    _draw_kv_table(c, data, 20*mm, y)

    c.save()
    return buf.getvalue()


def gen_relieving_letter(emp, org, last_day):
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    _header_canvas(c, None, org, "RELIEVING LETTER", last_day.strftime("%d %B %Y"))
    _footer(c, None)

    y = H - 70*mm
    c.setFont("Helvetica", 9)
    c.drawString(20*mm, y, f"Date: {last_day.strftime('%d %B %Y')}")
    y -= 10*mm
    c.setFont("Helvetica-Bold", 9)
    c.drawString(20*mm, y, emp["name"])
    y -= 10*mm
    c.setFont("Helvetica-Bold", 10)
    c.drawString(20*mm, y, "Subject: Relieving Letter")
    y -= 8*mm
    c.setFont("Helvetica", 9)
    body = (
        f"This is to confirm that {emp['name']} has been relieved from the services of {org['name']} "
        f"effective close of business on {last_day.strftime('%d %B %Y')}. "
        f"All dues, clearances and handovers have been completed as per company policy. "
        f"We thank them for their contribution and wish them the very best."
    )
    _wrap_text(c, body, 20*mm, y, W - 40*mm, 5.5*mm)
    y -= 35*mm
    data = [
        ["Employee Name",   emp["name"]],
        ["Employee ID",     emp["emp_id"]],
        ["Last Working Day",last_day.strftime("%d %B %Y")],
        ["Full & Final",    "Cleared"],
    ]
    _draw_kv_table(c, data, 20*mm, y)

    c.save()
    return buf.getvalue()


def _wrap_text(c, text, x, y, max_width, line_height):
    from reportlab.pdfbase.pdfmetrics import stringWidth
    words = text.split()
    line = ""
    for word in words:
        test = (line + " " + word).strip()
        if stringWidth(test, "Helvetica", 9) <= max_width:
            line = test
        else:
            c.drawString(x, y, line)
            y -= line_height
            line = word
    if line:
        c.drawString(x, y, line)


def _draw_kv_table(c, data, x, y, small=False):
    fs = 8 if small else 9
    row_h = 6.5*mm if small else 7.5*mm
    for k, v in data:
        c.setFont("Helvetica-Bold", fs)
        c.setFillColor(colors.HexColor("#374151"))
        c.drawString(x, y, k + ":")
        c.setFont("Helvetica", fs)
        c.setFillColor(colors.black)
        c.drawString(x + 60*mm, y, str(v))
        c.setStrokeColor(colors.HexColor("#E5E7EB"))
        c.line(x, y - 1.5*mm, x + 150*mm, y - 1.5*mm)
        y -= row_h


# ── Employee builder ───────────────────────────────────────────────────────────

def build_employees():
    employees = []
    name_pool = list(set(
        f"{fn} {ln}" for fn in FIRST_NAMES for ln in LAST_NAMES
    ))
    rng.shuffle(name_pool)
    name_idx = 0

    for oi, org in enumerate(ORGS):
        sector = org["sector"]
        desig_list = DESIGNATIONS[sector]
        dept_list  = DEPARTMENTS[sector]

        for ei in range(10):
            global_idx = oi * 10 + ei
            grade = min(ei // 2, len(desig_list) - 1)
            ctc_min, ctc_max = SALARY_BANDS[min(grade, 7)]
            ctc = rng.randint(ctc_min, ctc_max)
            ctc = (ctc // 12000) * 12000   # round to nearest 12k

            doj_year = rng.randint(2018, 2023)
            doj = date(doj_year, rng.randint(1, 12), 1)

            name = name_pool[name_idx % len(name_pool)]
            name_idx += 1

            emp = {
                "name":        name,
                "emp_id":      f"{org['id']}-EMP{ei+1:03d}",
                "emp_idx":     ei + 1,
                "pan":         pan(org["pan_prefix"], global_idx),
                "phone":       phone(oi + 1, ei + 1),
                "email":       name.lower().replace(" ", ".") + f"@gmail.com",
                "address":     f"Flat {(ei+1)*10+2}, Sector {ei+3}, {org['city']}",
                "designation": desig_list[grade],
                "department":  dept_list[ei % len(dept_list)],
                "ctc":         ctc,
                "doj":         doj,
                "grade":       grade,
                "org":         org,
                "org_idx":     oi,
            }
            employees.append(emp)
    return employees


# ── Document plan ──────────────────────────────────────────────────────────────

def plan_documents(emp):
    """Return list of (doc_type, date, extra_data) tuples for one employee."""
    docs = []
    org = emp["org"]

    # Offer + Appointment on DOJ
    docs.append(("OFFER_LETTER", emp["doj"], {}))
    docs.append(("APPOINTMENT_LETTER", emp["doj"], {}))

    # Salary slips — 6 months spread across tenure
    today = date.today()
    months_tenure = max(1, (today - emp["doj"]).days // 30)
    slip_months = sorted(rng.sample(range(1, min(months_tenure, 48)), min(6, months_tenure - 1)))
    for m in slip_months:
        slip_date = add_month(emp["doj"], m)
        if slip_date <= today:
            docs.append(("SALARY_SLIP", slip_date, {"month": slip_date}))

    # Increment (1-2 after first year)
    if months_tenure > 14:
        inc_date = add_month(emp["doj"], 13)
        new_ctc = int(emp["ctc"] * rng.uniform(1.08, 1.18))
        docs.append(("INCREMENT_LETTER", inc_date, {"old_ctc": emp["ctc"], "new_ctc": new_ctc}))
        if months_tenure > 26:
            inc2 = add_month(emp["doj"], 25)
            new_ctc2 = int(new_ctc * rng.uniform(1.10, 1.20))
            docs.append(("INCREMENT_LETTER", inc2, {"old_ctc": new_ctc, "new_ctc": new_ctc2}))

    # Promotion for senior grades
    if emp["grade"] >= 2 and months_tenure > 20:
        promo_date = add_month(emp["doj"], 18)
        desig_list = DESIGNATIONS[org["sector"]]
        old_desig = emp["designation"]
        next_grade = min(emp["grade"] + 1, len(desig_list) - 1)
        new_desig = desig_list[next_grade]
        new_ctc = int(emp["ctc"] * 1.25)
        docs.append(("PROMOTION_LETTER", promo_date,
                      {"old_desig": old_desig, "new_desig": new_desig, "new_ctc": new_ctc}))

    # Form 16 for each FY in tenure
    fy_start = emp["doj"].year if emp["doj"].month >= 4 else emp["doj"].year - 1
    fy_end   = today.year if today.month < 4 else today.year
    for fy in range(fy_start, min(fy_end, fy_start + 3)):
        docs.append(("FORM_16", date(fy + 1, 3, 31), {"fy_year": fy}))

    # Pad to 10 docs minimum with extra salary slips
    extra_months = [2, 5, 8, 11, 14, 17]
    for m in extra_months:
        if len(docs) >= 10:
            break
        slip_date = add_month(emp["doj"], m)
        if slip_date <= today and ("SALARY_SLIP", slip_date, {"month": slip_date}) not in docs:
            docs.append(("SALARY_SLIP", slip_date, {"month": slip_date}))

    # Guarantee at least one of each available type before padding with salary slips
    seen_types = set()
    priority, rest = [], []
    for d in docs:
        if d[0] not in seen_types:
            priority.append(d)
            seen_types.add(d[0])
        else:
            rest.append(d)
    ordered = priority + rest
    return sorted(ordered[:14], key=lambda x: x[1])


# ── Credentials ────────────────────────────────────────────────────────────────

def oa_creds(org):
    return {
        "email":    f"admin@{org['domain']}",
        "password": f"Prana@Admin{org['id'][-2:]}24",
    }

def emp_creds(emp):
    return {
        "phone":    emp["phone"],
        "name":     emp["name"],
        "email":    emp["email"],
        "otp_note": "OTP sent to phone (dev: check server logs or use 123456)",
    }


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    out_dir = Path(__file__).parent.parent.parent / "PRANA"
    out_dir.mkdir(exist_ok=True)
    zip_path = out_dir / "test_docs.zip"
    creds_path = out_dir / "credentials.txt"

    employees = build_employees()
    all_creds = []
    total = 0

    print(f"Generating documents...")

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for emp in employees:
            org = emp["org"]
            safe_emp_name = emp["name"].replace(" ", "_")
            safe_org_name = org["name"].replace(" ", "_").replace("/", "_")[:25]
            base = f"{org['id']}_{safe_org_name}/{emp['emp_id']}_{safe_emp_name}"

            doc_plan = plan_documents(emp)

            for seq, (doc_type, doc_date, extra) in enumerate(doc_plan, 1):
                filename = f"{base}/{seq:02d}_{doc_type}_{doc_date.strftime('%Y-%m')}.pdf"
                try:
                    if doc_type == "SALARY_SLIP":
                        pdf = gen_salary_slip(emp, org, extra.get("month", doc_date), seq)
                    elif doc_type == "APPOINTMENT_LETTER":
                        pdf = gen_appointment_letter(emp, org)
                    elif doc_type == "OFFER_LETTER":
                        pdf = gen_offer_letter(emp, org)
                    elif doc_type == "INCREMENT_LETTER":
                        pdf = gen_increment_letter(emp, org, doc_date,
                                                   extra["old_ctc"], extra["new_ctc"])
                    elif doc_type == "PROMOTION_LETTER":
                        pdf = gen_promotion_letter(emp, org, doc_date,
                                                   extra["old_desig"], extra["new_desig"],
                                                   extra["new_ctc"])
                    elif doc_type == "FORM_16":
                        pdf = gen_form16(emp, org, extra["fy_year"])
                    elif doc_type == "RELIEVING_LETTER":
                        last_day = add_month(emp["doj"], 24)
                        pdf = gen_relieving_letter(emp, org, last_day)
                    elif doc_type == "EXPERIENCE_LETTER":
                        last_day = add_month(emp["doj"], 24)
                        pdf = gen_experience_letter(emp, org, last_day)
                    else:
                        continue

                    zf.writestr(filename, pdf)
                    total += 1
                except Exception as e:
                    print(f"  SKIP {filename}: {e}")

            if total % 100 == 0:
                print(f"  {total} docs generated...")

    # ── Credentials file ────────────────────────────────────────────────────────
    lines = []
    lines.append("=" * 80)
    lines.append("PRANA TEST CREDENTIALS — 10 ORGS × 10 EMPLOYEES")
    lines.append("=" * 80)
    lines.append("")

    for oi, org in enumerate(ORGS):
        creds = oa_creds(org)
        lines.append(f"{'─'*78}")
        lines.append(f"  ORG {oi+1:02d}: {org['name']}")
        lines.append(f"  Sector  : {org['sector']}  |  City: {org['city']}")
        lines.append(f"  OA Admin Login (portal: /org/login)")
        lines.append(f"    Email    : {creds['email']}")
        lines.append(f"    Password : {creds['password']}")
        lines.append("")
        lines.append(f"  EMPLOYEES (login via /emp/login with phone + OTP):")
        emps = [e for e in employees if e["org_idx"] == oi]
        for e in emps:
            lines.append(f"    {e['emp_id']:<18} {e['name']:<28} Phone: {e['phone']}")
        lines.append("")

    lines.append("=" * 80)
    lines.append("NOTES")
    lines.append("=" * 80)
    lines.append("• Employee login: phone number + OTP (dev OTP: 123456 or check server logs)")
    lines.append("• OA Admin login: email + password + TOTP (dev: seed sets TOTP secret)")
    lines.append("• Upload path in portal: Documents → Upload → drag the PDF folder per org")
    lines.append("• After upload, pipeline processes: QUEUED→ENCRYPTING→SCANNING→EXTRACTING→RESOLVING→ROUTED")
    lines.append("• Employee sees document in vault after pipeline_status = ROUTED")
    lines.append(f"• Total documents generated: {total}")
    lines.append("")

    creds_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nDone! {total} documents")
    print(f"  ZIP  : {zip_path}")
    print(f"  Creds: {creds_path}")
    print(f"  Size : {zip_path.stat().st_size // 1024} KB")


if __name__ == "__main__":
    main()
