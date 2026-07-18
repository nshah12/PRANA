"""
preprod_load_data.py — Generate dev-equivalent data VOLUME in pre-prod through
the real APIs, not through SQL.

Why this exists: prana-db/seeds/dev_seed*.sql gets dev's ~510 employees / 13
tenants / ~900 documents into a database by directly INSERT-ing rows. That
never touches KMS, Kafka, Temporal, or the AI pipeline — the ciphertext is a
literal placeholder string, there's no audit_event trail, no S3 object, no
real extraction. Running those files against pre-prod would give you numbers
that look like dev but prove nothing.

This script instead drives the REAL HTTP APIs, at realistic volume:
  PA login -> create + activate N tenants (real TenantProvisioningWorkflow
              path, real KMS KEK, real Kafka TENANT_ACTIVATED event)
  -> first OA-Admin per tenant completes the real password-reset + TOTP-setup
     dance (same flow a real customer's admin goes through)
  -> optionally creates the other 4 OA roles per tenant (chro/cfo/ciso/operator)
  -> uploads real, well-formed synthetic PDFs per document type via
     POST /v1/ingest/upload (real S3 put, real DOC_INGESTED Kafka event, real
     6-stage pipeline if prana-ai is deployed and reachable in this environment)

Every row this script creates got there the same way a real customer's data
would. If prana-ai isn't deployed in this environment yet, documents will sit
at pipeline_status=QUEUED indefinitely -- that's expected and correct; the
script's job is to prove the ingestion/onboarding APIs work, not to run the
GPU extraction pipeline itself.

Usage (against pre-prod, NEVER against a real customer's production instance):
    python scripts/preprod_load_data.py \\
        --base-url https://preprod-api.prana.in \\
        --pa-email admin@prana.in \\
        --tenants 13 \\
        --docs-per-tenant 60 \\
        --create-extra-oa-roles

Prompts for the PA password and, if the PA account needs TOTP, its 6-digit
code interactively -- never pass credentials as CLI args (shell history).

Idempotent-ish: tenant domains are suffixed with a run tag; re-running with a
new --run-tag adds more data without colliding with a prior run's tenants.
"""
from __future__ import annotations

import argparse
import asyncio
import getpass
import random
import re
import string
import sys
import time
from dataclasses import dataclass, field
from io import BytesIO
from urllib.parse import parse_qs, urlparse

import httpx
import pyotp
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

# ── Synthetic (never-real) content pools ────────────────────────────────────

FIRST_NAMES = ["Arjun", "Priya", "Rohan", "Ananya", "Vikram", "Deepika", "Karthik",
               "Meera", "Siddharth", "Kavya", "Aditya", "Sneha", "Rajesh", "Divya"]
LAST_NAMES = ["Sharma", "Iyer", "Nair", "Reddy", "Gupta", "Menon", "Verma",
              "Pillai", "Rao", "Kapoor", "Krishnan", "Joshi", "Patel", "Singh"]
DESIGNATIONS = ["Software Engineer", "Senior Analyst", "Product Manager",
                 "HR Executive", "Finance Manager", "Operations Lead"]
DEPARTMENTS = ["Engineering", "Finance", "Human Resources", "Operations", "Sales"]

# doc_type -> field renderer. Mirrors the required_fields each doc type's
# platform-default doc_type_field_manifest row expects (see schema.sql LAYER
# 15) so a real extraction pass has a realistic chance of matching them.
DOC_TYPE_TEMPLATES: dict[str, "callable"] = {}


def _synthetic_pan() -> str:
    # AAAAA9999A shape -- format-valid, never a real PAN.
    letters = "".join(random.choices(string.ascii_uppercase, k=5))
    digits = "".join(random.choices(string.digits, k=4))
    return f"{letters}{digits}{random.choice(string.ascii_uppercase)}"


def _render_pdf(lines: list[str]) -> bytes:
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    width, height = A4
    y = height - 60
    for line in lines:
        c.drawString(50, y, line)
        y -= 20
        if y < 60:
            c.showPage()
            y = height - 60
    c.save()
    return buf.getvalue()


def _salary_slip(name: str, employer: str) -> bytes:
    return _render_pdf([
        f"{employer}", "SALARY SLIP", "",
        f"Employee Name: {name}",
        f"Employer Name: {employer}",
        f"Pay Period: {random.choice(['January','February','March','April'])} 2026",
        f"Net Pay: Rs. {random.randint(30000, 200000)}",
        f"PF Number: PF{random.randint(100000,999999)}",
        f"UAN Number: {random.randint(10**11, 10**12 - 1)}",
    ])


def _offer_letter(name: str, employer: str) -> bytes:
    return _render_pdf([
        f"{employer}", "OFFER LETTER", "",
        f"Dear {name},",
        f"We are pleased to offer you the position of {random.choice(DESIGNATIONS)}",
        f"Employer Name: {employer}",
        f"Date of Joining: 2026-08-01",
        f"CTC: Rs. {random.randint(400000, 2500000)} per annum",
    ])


def _form_16(name: str, employer: str) -> bytes:
    return _render_pdf([
        f"{employer}", "FORM 16", "",
        f"Employee Name: {name}",
        f"Employer Name: {employer}",
        "Financial Year: 2025-2026",
        f"Gross Salary: Rs. {random.randint(500000, 3000000)}",
        f"TDS Deducted: Rs. {random.randint(20000, 400000)}",
    ])


DOC_TYPE_TEMPLATES = {
    "SALARY_SLIP": _salary_slip,
    "OFFER_LETTER": _offer_letter,
    "FORM_16": _form_16,
}


@dataclass
class RunStats:
    tenants_created: int = 0
    tenants_failed: int = 0
    oa_users_created: int = 0
    documents_uploaded: int = 0
    documents_failed: int = 0
    errors: list[str] = field(default_factory=list)


def _extract_totp_secret(provisioning_uri: str) -> str:
    query = parse_qs(urlparse(provisioning_uri).query)
    return query["secret"][0]


class PreprodLoader:
    def __init__(self, base_url: str, run_tag: str):
        self.base_url = base_url.rstrip("/")
        self.run_tag = run_tag
        self.client = httpx.Client(base_url=self.base_url, timeout=30.0)
        self.stats = RunStats()

    def close(self) -> None:
        self.client.close()

    # ── PA auth ──────────────────────────────────────────────────────────────

    def login_pa(self, email: str, password: str) -> str:
        r = self.client.post("/auth/admin/login", json={"email": email, "password": password})
        r.raise_for_status()
        body = r.json()
        step_token = body["step_token"]

        if body.get("requires_totp_setup"):
            # First-ever login for this PA account -- same automated dance as a
            # brand-new OA-Admin. Real production PAs would do this once via the
            # UI and keep the secret in their own authenticator app; this script
            # only auto-completes it so unattended load-generation runs work.
            r = self.client.post("/auth/admin/totp-setup/init", json={"step_token": step_token})
            r.raise_for_status()
            setup = r.json()
            secret = _extract_totp_secret(setup["provisioning_uri"])
            code = pyotp.TOTP(secret).now()
            r = self.client.post("/auth/admin/totp-setup/confirm",
                                  json={"setup_token": setup["setup_token"], "code": code})
            r.raise_for_status()
            print(f"  (PA TOTP was unconfigured -- auto-completed setup; secret: {secret})")
            return r.json()["access_token"]

        code = getpass.getpass("PA TOTP code (from your authenticator app): ")
        r = self.client.post("/auth/admin/totp", json={"step_token": step_token, "code": code})
        r.raise_for_status()
        return r.json()["access_token"]

    # ── Tenant creation + activation (real TenantProvisioningWorkflow path) ──

    def create_and_activate_tenant(self, pa_token: str, index: int) -> dict | None:
        suffix = f"{self.run_tag}{index:03d}"
        domain = f"loadtest-{suffix}.example.com"
        tenant_name = f"LoadTest Org {suffix}"
        first_admin_email = f"admin@{domain}"

        headers = {"Authorization": f"Bearer {pa_token}"}
        payload = {
            "tenant_name": tenant_name,
            "primary_state": random.choice(["Maharashtra", "Karnataka", "Telangana", "Delhi"]),
            "domain": domain,
            "first_oa_admin_email": first_admin_email,
            "home_region": "ap-south-1",
        }
        r = self.client.post("/admin/tenants", json=payload, headers=headers)
        if r.status_code >= 400:
            self.stats.tenants_failed += 1
            self.stats.errors.append(f"create tenant {domain}: {r.status_code} {r.text[:200]}")
            return None
        tenant_id = r.json().get("tenant_id")
        if not tenant_id:
            # Some deployments return {"tenant": {...}} -- handle both shapes.
            tenant_id = r.json().get("tenant", {}).get("tenant_id")

        r = self.client.post(
            f"/admin/tenants/{tenant_id}/activate",
            json={"first_oa_admin_email": first_admin_email},
            headers=headers,
        )
        if r.status_code >= 400:
            self.stats.tenants_failed += 1
            self.stats.errors.append(f"activate tenant {domain}: {r.status_code} {r.text[:200]}")
            return None
        activation = r.json()
        self.stats.tenants_created += 1
        return {
            "tenant_id": tenant_id,
            "domain": domain,
            "admin_email": first_admin_email,
            "admin_temp_password": activation["temp_password"],
        }

    # ── First-login dance: password reset -> TOTP setup -> real session ─────

    def complete_first_login(self, email: str, temp_password: str, new_password: str) -> str:
        r = self.client.post("/auth/org/login", json={"email": email, "password": temp_password})
        r.raise_for_status()
        body = r.json()

        step_token = body["step_token"]
        r = self.client.post("/auth/org/password-reset",
                              json={"step_token": step_token, "new_password": new_password})
        r.raise_for_status()
        step_token = r.json()["step_token"]

        r = self.client.post("/auth/org/totp-setup/init", json={"step_token": step_token})
        r.raise_for_status()
        setup = r.json()
        secret = _extract_totp_secret(setup["provisioning_uri"])
        setup_token = setup["setup_token"]

        code = pyotp.TOTP(secret).now()
        r = self.client.post("/auth/org/totp-setup/confirm",
                              json={"setup_token": setup_token, "code": code})
        r.raise_for_status()
        return r.json()["access_token"]

    # ── Extra OA roles ────────────────────────────────────────────────────────

    def create_extra_oa_users(self, admin_token: str, domain: str) -> None:
        headers = {"Authorization": f"Bearer {admin_token}"}
        for role in ("oa_operator", "chro", "cfo", "ciso"):
            email = f"{role.replace('_', '')}@{domain}"
            r = self.client.post("/v1/org/users", json={"email": email, "role": role}, headers=headers)
            if r.status_code >= 400:
                self.stats.errors.append(f"create {role} for {domain}: {r.status_code} {r.text[:200]}")
                continue
            self.stats.oa_users_created += 1

    # ── Document upload (real S3 put + real DOC_INGESTED Kafka event) ───────

    def upload_documents(self, oa_token: str, tenant_domain: str, count: int) -> None:
        headers = {"Authorization": f"Bearer {oa_token}"}
        doc_types = list(DOC_TYPE_TEMPLATES.keys())
        for i in range(count):
            name = f"{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}"
            employer = tenant_domain.split(".")[0]
            doc_type = doc_types[i % len(doc_types)]
            pdf_bytes = DOC_TYPE_TEMPLATES[doc_type](name, employer)

            files = {"files": (f"{doc_type.lower()}_{i}.pdf", pdf_bytes, "application/pdf")}
            data = {"doc_type": doc_type, "comment": f"preprod-load {self.run_tag}"}
            r = self.client.post("/v1/ingest/upload", files=files, data=data, headers=headers)
            if r.status_code >= 400:
                self.stats.documents_failed += 1
                self.stats.errors.append(f"upload {doc_type} for {tenant_domain}: {r.status_code} {r.text[:200]}")
                continue
            self.stats.documents_uploaded += 1


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base-url", required=True, help="e.g. https://preprod-api.prana.in")
    parser.add_argument("--pa-email", required=True)
    parser.add_argument("--tenants", type=int, default=13)
    parser.add_argument("--docs-per-tenant", type=int, default=60)
    parser.add_argument("--create-extra-oa-roles", action="store_true",
                         help="Also create oa_operator/chro/cfo/ciso per tenant (slower: full TOTP dance skipped for these -- temp password only, matching real welcome-email flow)")
    parser.add_argument("--run-tag", default=None,
                         help="Suffix for synthetic domains, e.g. 'a'. Default: timestamp-based, so re-runs never collide.")
    args = parser.parse_args()

    run_tag = args.run_tag or f"{int(time.time()) % 100000}"
    pa_password = getpass.getpass(f"Password for {args.pa_email}: ")

    loader = PreprodLoader(args.base_url, run_tag)
    try:
        print("Logging in as Portal Admin...")
        pa_token = loader.login_pa(args.pa_email, pa_password)

        for i in range(1, args.tenants + 1):
            print(f"[{i}/{args.tenants}] Creating + activating tenant...")
            result = loader.create_and_activate_tenant(pa_token, i)
            if not result:
                continue

            print(f"  -> {result['domain']}: completing first-OA-Admin login + TOTP setup...")
            admin_token = loader.complete_first_login(
                result["admin_email"], result["admin_temp_password"],
                new_password=f"LoadTest{run_tag}!Passw0rd",
            )

            if args.create_extra_oa_roles:
                loader.create_extra_oa_users(admin_token, result["domain"])

            print(f"  -> uploading {args.docs_per_tenant} documents...")
            loader.upload_documents(admin_token, result["domain"], args.docs_per_tenant)

        s = loader.stats
        print("\n" + "=" * 60)
        print("PRE-PROD LOAD DATA GENERATION COMPLETE")
        print("=" * 60)
        print(f"Tenants created:      {s.tenants_created} (failed: {s.tenants_failed})")
        print(f"Extra OA users:       {s.oa_users_created}")
        print(f"Documents uploaded:   {s.documents_uploaded} (failed: {s.documents_failed})")
        if s.errors:
            print(f"\n{len(s.errors)} error(s):")
            for e in s.errors[:20]:
                print(f"  - {e}")
        print(
            "\nNote: documents will progress past QUEUED only if prana-ai is "
            "deployed and reachable in this environment -- that's expected, "
            "this script drives ingestion, not GPU extraction."
        )
    finally:
        loader.close()


if __name__ == "__main__":
    main()
