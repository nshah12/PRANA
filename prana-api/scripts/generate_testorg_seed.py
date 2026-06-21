"""
Generate prana-db/seeds/dev_seed_testorgs.sql

Creates:
  - 10 tenants (ORG01–ORG10) matching the generated test credentials
  - 10 OA Admins with real Argon2id hashes of their passwords
  - 100 employee_user rows (10 per org, phones +919000001001–+919000010010)
  - 100 employee_master rows with real names from the credentials sheet

Run from prana-api/:
    python scripts/generate_testorg_seed.py

Output: prana-db/seeds/dev_seed_testorgs.sql
        (run this file against your local DB after dev_seed.sql)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from services.encryption_service import hash_password

# ── Org definitions ──────────────────────────────────────────────────────────

ORGS = [
    {
        "n": 1, "name": "TechNova Solutions Pvt Ltd",
        "cin": "U72900KA2020PTC111001", "domain": "technova.in",
        "email": "admin@technova.in", "password": "Prana@Admin0124",
        "state": "Karnataka", "region": "ap-south-2", "city": "Bengaluru",
    },
    {
        "n": 2, "name": "Greenfield Infra Ltd",
        "cin": "L45200MH2015PLC111002", "domain": "greenfield.co.in",
        "email": "admin@greenfield.co.in", "password": "Prana@Admin0224",
        "state": "Maharashtra", "region": "ap-south-1", "city": "Mumbai",
    },
    {
        "n": 3, "name": "Bharat FinServ Pvt Ltd",
        "cin": "U65920MH2012PTC111003", "domain": "bharatfin.in",
        "email": "admin@bharatfin.in", "password": "Prana@Admin0324",
        "state": "Maharashtra", "region": "ap-south-1", "city": "Pune",
    },
    {
        "n": 4, "name": "Sunrise Pharmaceuticals Ltd",
        "cin": "L24210TG2001PLC111004", "domain": "sunrisepharma.in",
        "email": "admin@sunrisepharma.in", "password": "Prana@Admin0424",
        "state": "Telangana", "region": "ap-south-2", "city": "Hyderabad",
    },
    {
        "n": 5, "name": "DigiSpark Technologies Pvt Ltd",
        "cin": "U72900TN2018PTC111005", "domain": "digispark.io",
        "email": "admin@digispark.io", "password": "Prana@Admin0524",
        "state": "Tamil Nadu", "region": "ap-south-2", "city": "Chennai",
    },
    {
        "n": 6, "name": "Indus Retail Chain Ltd",
        "cin": "L52100DL2010PLC111006", "domain": "indusretail.in",
        "email": "admin@indusretail.in", "password": "Prana@Admin0624",
        "state": "Delhi", "region": "ap-south-1", "city": "Delhi",
    },
    {
        "n": 7, "name": "KaleidoMedia Pvt Ltd",
        "cin": "U74140MH2016PTC111007", "domain": "kaleidomedia.in",
        "email": "admin@kaleidomedia.in", "password": "Prana@Admin0724",
        "state": "Maharashtra", "region": "ap-south-1", "city": "Mumbai",
    },
    {
        "n": 8, "name": "PrimeLogistics Solutions Ltd",
        "cin": "L63090WB2008PLC111008", "domain": "primelogix.in",
        "email": "admin@primelogix.in", "password": "Prana@Admin0824",
        "state": "West Bengal", "region": "ap-south-1", "city": "Kolkata",
    },
    {
        "n": 9, "name": "NovaCure Health Services Pvt Ltd",
        "cin": "U85100KA2014PTC111009", "domain": "novacure.in",
        "email": "admin@novacure.in", "password": "Prana@Admin0924",
        "state": "Karnataka", "region": "ap-south-2", "city": "Bengaluru",
    },
    {
        "n": 10, "name": "AgroTech India Pvt Ltd",
        "cin": "U01100MH2019PTC111010", "domain": "agrotech.in",
        "email": "admin@agrotech.in", "password": "Prana@Admin1024",
        "state": "Maharashtra", "region": "ap-south-1", "city": "Nagpur",
    },
]

# ── Employee names per org (from credentials sheet) ──────────────────────────

EMP_NAMES = {
    1:  ["Suresh Verma", "Shweta Rao", "Amit Iyer", "Shruti Joshi", "Jyoti Joshi",
         "Saurabh Sinha", "Arjun Mehta", "Suresh Kumar", "Pooja Sharma", "Tanvi Kapoor"],
    2:  ["Saurabh Nair", "Pallavi Iyer", "Neha Iyer", "Suresh Reddy", "Neha Reddy",
         "Neha Sharma", "Kavya Sinha", "Amit Mishra", "Amit Kapoor", "Saurabh Gupta"],
    3:  ["Sneha Gupta", "Gaurav Joshi", "Tanvi Rao", "Anjali Gupta", "Sneha Verma",
         "Aakash Tiwari", "Varun Kapoor", "Varun Patel", "Sandeep Mehta", "Neha Desai"],
    4:  ["Tanvi Kumar", "Rohan Gupta", "Ananya Verma", "Suresh Nair", "Isha Rao",
         "Deepak Sinha", "Deepak Joshi", "Deepak Reddy", "Divya Sinha", "Aakash Gupta"],
    5:  ["Preeti Pillai", "Arjun Chopra", "Karan Rao", "Isha Sharma", "Ritu Reddy",
         "Saurabh Menon", "Varun Tiwari", "Jyoti Bose", "Sandeep Kapoor", "Preeti Bose"],
    6:  ["Sneha Nair", "Saurabh Joshi", "Ankur Sharma", "Rahul Tiwari", "Ritu Singh",
         "Neha Verma", "Vivek Shah", "Sonal Kapoor", "Isha Pillai", "Sandeep Mishra"],
    7:  ["Arjun Singh", "Arjun Kapoor", "Vikram Menon", "Jyoti Nair", "Simran Joshi",
         "Sandeep Iyer", "Rajesh Menon", "Vikram Kapoor", "Nikhil Bose", "Mohit Agarwal"],
    8:  ["Suresh Agarwal", "Kavya Shah", "Tanvi Desai", "Pooja Bose", "Riya Mishra",
         "Pranav Sharma", "Rahul Nair", "Tanvi Iyer", "Deepak Mehta", "Nikhil Rao"],
    9:  ["Ananya Kumar", "Vivek Reddy", "Shweta Iyer", "Sonal Verma", "Ananya Sharma",
         "Jyoti Tiwari", "Sneha Kapoor", "Tanvi Patel", "Ananya Joshi", "Isha Tiwari"],
    10: ["Karan Nair", "Sandeep Desai", "Arjun Menon", "Shweta Pillai", "Sneha Shah",
         "Divya Kumar", "Ritu Bose", "Suresh Rao", "Rajesh Sinha", "Jyoti Iyer"],
}

DESIGNATIONS = [
    "Software Engineer", "Senior Engineer", "Tech Lead", "Manager", "Senior Manager",
    "Director", "Analyst", "Senior Analyst", "Consultant", "Associate",
]
DEPARTMENTS = [
    "Engineering", "Product", "Finance", "HR", "Operations",
    "Sales", "Marketing", "Legal", "Design", "Data Science",
]
GRADES = ["L1", "L2", "L3", "L4", "L5", "L6"]


def tenant_uuid(n: int) -> str:
    return f"50000000-0000-0000-{n:04d}-000000000000"


def oa_uuid(n: int) -> str:
    return f"60000000-0000-0000-{n:04d}-000000000001"


def emp_user_uuid(org: int, emp: int) -> str:
    return f"70000000-{org:04d}-{emp:04d}-0000-000000000000"


def emp_master_uuid(org: int, emp: int) -> str:
    return f"80000000-{org:04d}-{emp:04d}-0000-000000000000"


def mobile(org: int, emp: int) -> str:
    # Credentials sheet: +91 9000001001 (org=1, emp=1) to +91 9000010010 (org=10, emp=10)
    # Format: +91 9000 00N NNN where N=org (1-9) or +91 9000 010 NNN for org=10
    number = 9000000000 + org * 1000 + emp
    return f"+91{number}"


def main():
    out_path = Path(__file__).parent.parent.parent / "prana-db" / "seeds" / "dev_seed_testorgs.sql"

    print("Hashing passwords (Argon2id — takes ~5 seconds)...")
    lines = []
    lines.append("-- dev_seed_testorgs.sql")
    lines.append("-- 10 test-doc orgs + 100 employees from generate_test_docs.py")
    lines.append("-- Run AFTER dev_seed.sql")
    lines.append("-- NEVER run against staging or production.")
    lines.append("")
    lines.append("BEGIN;")
    lines.append("")

    # ── TENANTS ──────────────────────────────────────────────────────────────
    lines.append("-- ============================================================")
    lines.append("-- TENANTS (10 test orgs)")
    lines.append("-- ============================================================")
    lines.append("INSERT INTO tenant (")
    lines.append("  tenant_id, tenant_name, cin, domain, nik_type, kek_arn,")
    lines.append("  primary_state, home_region, status, storage_quota_gb, self_upload_policy")
    lines.append(") VALUES")
    tenant_rows = []
    for o in ORGS:
        n = o["n"]
        tenant_rows.append(
            f"  ('{tenant_uuid(n)}',\n"
            f"   '{o['name']}', '{o['cin']}', '{o['domain']}',\n"
            f"   'PAN', 'arn:aws:kms:ap-south-1:123456789012:key/dev-testorg{n:02d}-kek',\n"
            f"   '{o['state']}', '{o['region']}', 'ACTIVE', 50, 'ALLOWED_WITH_WARNING')"
        )
    lines.append(",\n".join(tenant_rows) + ";")
    lines.append("")

    # ── OA ADMINS ─────────────────────────────────────────────────────────────
    lines.append("-- ============================================================")
    lines.append("-- OA ADMINS (1 per org, totp_secret_enc=NULL → QR setup on first login)")
    lines.append("-- ============================================================")
    lines.append("INSERT INTO oa_user (")
    lines.append("  oa_user_id, tenant_id, email, role,")
    lines.append("  password_hash, temp_password_hash, force_reset, status")
    lines.append(") VALUES")
    oa_rows = []
    for o in ORGS:
        n = o["n"]
        pw_hash = hash_password(o["password"])
        print(f"  ORG{n:02d}: {o['email']} — hashed")
        oa_rows.append(
            f"  ('{oa_uuid(n)}',\n"
            f"   '{tenant_uuid(n)}', '{o['email']}', 'oa_admin',\n"
            f"   '{pw_hash}',\n"
            f"   NULL, FALSE, 'ACTIVE')"
        )
    lines.append(",\n".join(oa_rows) + ";")
    lines.append("")

    # ── EMPLOYEE USERS ────────────────────────────────────────────────────────
    lines.append("-- ============================================================")
    lines.append("-- EMPLOYEE USERS (100 total, 10 per org)")
    lines.append("-- pan_token via pgcrypto hmac — no raw PAN stored")
    lines.append("-- ============================================================")
    lines.append("INSERT INTO employee_user (")
    lines.append("  employee_user_id, pan_token, enc_pan, enc_dek,")
    lines.append("  mobile, status, activated_at")
    lines.append(") VALUES")
    eu_rows = []
    for org in range(1, 11):
        for emp in range(1, 11):
            uid = emp_user_uuid(org, emp)
            pan_key = f"TESTPAN_ORG{org:02d}_EMP{emp:03d}"
            mob = mobile(org, emp)
            eu_rows.append(
                f"  ('{uid}',\n"
                f"   encode(hmac('{pan_key}', 'dev_secret', 'sha256'), 'hex'),\n"
                f"   'DEVPAN{org:02d}{emp:03d}',\n"
                f"   'DEV_ENC_DEK_ORG{org:02d}_EMP{emp:03d}',\n"
                f"   '{mob}', 'ACTIVE', NOW() - interval '180 days')"
            )
    lines.append(",\n".join(eu_rows) + ";")
    lines.append("")

    # ── EMPLOYEE MASTER ───────────────────────────────────────────────────────
    lines.append("-- ============================================================")
    lines.append("-- EMPLOYEE MASTER (100 rows, real names from credentials sheet)")
    lines.append("-- ============================================================")
    lines.append("INSERT INTO employee_master (")
    lines.append("  employee_uuid, employee_user_id, tenant_id,")
    lines.append("  pan_token, enc_pan, enc_dek,")
    lines.append("  emp_id_org, full_name, designation, department,")
    lines.append("  grade, location, employment_type, doj, status")
    lines.append(") VALUES")
    em_rows = []
    for org in range(1, 11):
        o = ORGS[org - 1]
        for emp in range(1, 11):
            name = EMP_NAMES[org][emp - 1]
            uid = emp_master_uuid(org, emp)
            euid = emp_user_uuid(org, emp)
            pan_key = f"TESTPAN_ORG{org:02d}_EMP{emp:03d}"
            desig = DESIGNATIONS[(emp - 1) % len(DESIGNATIONS)]
            dept = DEPARTMENTS[(emp - 1) % len(DEPARTMENTS)]
            grade = GRADES[(emp - 1) % len(GRADES)]
            doj_years_ago = 1 + (emp % 4)
            em_rows.append(
                f"  ('{uid}',\n"
                f"   '{euid}',\n"
                f"   '{tenant_uuid(org)}',\n"
                f"   encode(hmac('{pan_key}', 'dev_secret', 'sha256'), 'hex'),\n"
                f"   'DEVPAN{org:02d}{emp:03d}',\n"
                f"   'DEV_ENC_DEK_ORG{org:02d}_EMP{emp:03d}',\n"
                f"   'ORG{org:02d}-EMP{emp:03d}',\n"
                f"   '{name}', '{desig}', '{dept}',\n"
                f"   '{grade}', '{o['city']}', 'PERMANENT',\n"
                f"   NOW() - interval '{doj_years_ago} years', 'ACTIVE')"
            )
    lines.append(",\n".join(em_rows) + ";")
    lines.append("")
    lines.append("COMMIT;")
    lines.append("")
    lines.append("-- Verify:")
    lines.append(f"-- SELECT COUNT(*) FROM tenant WHERE cin LIKE 'U%111%';  -- expect 10")
    lines.append(f"-- SELECT COUNT(*) FROM oa_user WHERE email LIKE '%@technova.in' OR email LIKE '%@greenfield%';")
    lines.append(f"-- SELECT COUNT(*) FROM employee_user WHERE mobile LIKE '+919000001%' OR mobile LIKE '+919000002%';")

    sql = "\n".join(lines) + "\n"
    out_path.write_text(sql, encoding="utf-8")
    print(f"\nWritten: {out_path}")
    print(f"Lines: {len(lines)}")
    print()
    print("Run against your local DB:")
    print("  psql -U prana -d prana_dev -f prana-db/seeds/dev_seed_testorgs.sql")
    print()
    print("Then log in at http://localhost:3000/org/login with e.g.:")
    print("  admin@technova.in  /  Prana@Admin0124")
    print("  TOTP QR setup will appear on first login (totp_secret_enc=NULL)")


if __name__ == "__main__":
    main()
