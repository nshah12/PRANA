"""
PRANA enforce_rules.py — pre-merge gate.
Run: python scripts/enforce_rules.py
Exit 0 = clean. Exit 1 = violations found (blocks merge).
"""
import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
PRANA_API = ROOT / "prana-api"
PRANA_AI = ROOT / "prana-ai"
PRANA_ASK = ROOT / "prana-ask"

errors = []
warnings = []


def err(rule, path, msg):
    errors.append(f"[ERROR] {rule} {path}: {msg}")


def warn(rule, path, msg):
    warnings.append(f"[WARN]  {rule} {path}: {msg}")


# ──────────────────────────────────────────────────────────────
# TDD-01: every source file must have a matching test file
# ──────────────────────────────────────────────────────────────
TDD_EXEMPT = {
    "__init__.py", "config.py", "main.py", "db.py", "versioning.py",
    "worker.py", "llm_client.py",
    "errors.py", "messages.py",   # pure constants/enum files — no logic to unit-test
}
TDD_EXEMPT_DIRS = {
    "middleware", "kafka", "scripts", "migrations", "seeds", "prompts", "schemas",
    "extraction",  # prana-ai extraction prompts/schemas are data files not logic
}

def check_tdd(service_root: Path):
    tests_dir = service_root / "tests"
    src_files = []
    for py in service_root.rglob("*.py"):
        rel = py.relative_to(service_root)
        parts = rel.parts
        if parts[0] in TDD_EXEMPT_DIRS:
            continue
        if parts[0] == "tests":
            continue
        if py.name in TDD_EXEMPT:
            continue
        src_files.append(py)

    for src in src_files:
        stem = src.stem
        pattern = f"test_{stem}*.py"
        matches = list(tests_dir.glob(pattern)) if tests_dir.exists() else []
        if not matches:
            err("TDD-01", src.relative_to(ROOT), f"no test file matching tests/test_{stem}*.py")
        else:
            # TDD-02: test file must have at least one test_ function
            for t in matches:
                content = t.read_text(encoding="utf-8")
                if not re.search(r"def test_\w+", content):
                    warn("TDD-02", t.relative_to(ROOT), "no def test_*() found")


# ──────────────────────────────────────────────────────────────
# DB-01: no f-string SQL
# ──────────────────────────────────────────────────────────────
SQL_KEYWORDS = re.compile(r"\b(SELECT|INSERT|UPDATE|DELETE|WHERE|FROM|JOIN)\b", re.I)

DB_EXEMPT_DIRS = {"tests", "scripts", "migrations", "seeds"}

def check_db_rules(service_root: Path):
    for py in service_root.rglob("*.py"):
        rel_parts = py.relative_to(service_root).parts
        if rel_parts[0] in DB_EXEMPT_DIRS:
            continue
        if "test" in py.name:
            continue
        src = py.read_text(encoding="utf-8", errors="ignore")
        for i, line in enumerate(src.splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            # Only flag f-string SQL that interpolates VALUES (not column names or clause builders).
            # Safe: f"SET {clause}" / f"WHERE {col} = $1" — column names from code, values still parameterized.
            # Unsafe: f"WHERE x = '{val}'" or f"= {val}" without $ placeholder.
            if re.search(r'f["\'].*\b(SELECT|INSERT|UPDATE|DELETE|WHERE)\b', stripped, re.I):
                if re.search(r"\{[^}]+\}['\"]|= '\{|'\{[^}]+\}'", stripped):
                    err("DB-01", f"{py.relative_to(ROOT)}:{i}", "f-string SQL with value interpolation — use parameterized $1 placeholders")

        # DB-02: no SELECT *
        for i, line in enumerate(src.splitlines(), 1):
            if re.search(r'\bSELECT\s+\*', line, re.I) and "test" not in py.name and not line.strip().startswith("#") and "r'" not in line and 'r"' not in line:
                err("DB-02", f"{py.relative_to(ROOT)}:{i}", "SELECT * — name every column explicitly")


# ──────────────────────────────────────────────────────────────
# API-01: no bare list return from endpoints
# ──────────────────────────────────────────────────────────────
def check_api_rules(service_root: Path):
    routers_dir = service_root / "routers"
    if not routers_dir.exists():
        return
    for py in routers_dir.rglob("*.py"):
        src = py.read_text(encoding="utf-8", errors="ignore")
        # API-01: return [...] bare list
        for i, line in enumerate(src.splitlines(), 1):
            stripped = line.strip()
            if re.match(r'^return\s+\[', stripped):
                err("API-01", f"{py.relative_to(ROOT)}:{i}", "bare list return — wrap in {\"items\": [...], \"total\": N}")

        # API-02: return dict(row) — raw asyncpg Record
        for i, line in enumerate(src.splitlines(), 1):
            if re.search(r'\breturn\s+dict\(row\)', line):
                err("API-02", f"{py.relative_to(ROOT)}:{i}", "raw dict(row) — always explicit field comprehension")


# ──────────────────────────────────────────────────────────────
# KAFKA-01: raw kafka.publish() call in HTTP handlers
# ──────────────────────────────────────────────────────────────
def check_kafka_rules(service_root: Path):
    routers_dir = service_root / "routers"
    if not routers_dir.exists():
        return
    for py in routers_dir.rglob("*.py"):
        src = py.read_text(encoding="utf-8", errors="ignore")
        for i, line in enumerate(src.splitlines(), 1):
            if re.search(r'kafka\.publish\s*\(', line):
                err("KAFKA-01", f"{py.relative_to(ROOT)}:{i}", "raw kafka.publish() in router — use domain helper (e.g. kafka.employee_event())")

    # KAFKA-02: audit_event INSERT in HTTP handler
    for py in (service_root / "routers").rglob("*.py") if (service_root / "routers").exists() else []:
        src = py.read_text(encoding="utf-8", errors="ignore")
        for i, line in enumerate(src.splitlines(), 1):
            if re.search(r'INSERT\s+INTO\s+audit_event', line, re.I):
                err("KAFKA-02", f"{py.relative_to(ROOT)}:{i}", "INSERT INTO audit_event in HTTP handler — AuditConsumer owns this")


# ──────────────────────────────────────────────────────────────
# SEC-01: plaintext PAN in logs / responses
# ──────────────────────────────────────────────────────────────
SEC_EXEMPT_DIRS = {"tests", "scripts", "seeds", "migrations"}

def check_security_rules(service_root: Path):
    for py in service_root.rglob("*.py"):
        rel_parts = py.relative_to(service_root).parts
        if rel_parts[0] in SEC_EXEMPT_DIRS:
            continue
        src = py.read_text(encoding="utf-8", errors="ignore")
        for i, line in enumerate(src.splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            # SEC-01: logging PAN value
            if re.search(r'log(ger)?.*["\'].*pan["\']', stripped, re.I) and "pan_token" not in stripped:
                warn("SEC-01", f"{py.relative_to(ROOT)}:{i}", "possible PAN value in log — use pan_token instead")
            # SEC-02: hardcoded secret/password
            if re.search(r'(password|secret|api_key)\s*=\s*["\'][^"\']{8,}["\']', stripped, re.I):
                err("SEC-02", f"{py.relative_to(ROOT)}:{i}", "hardcoded secret — use env var")


# ──────────────────────────────────────────────────────────────
# TEMPORAL-01: workflow.run body > 20 lines
# ──────────────────────────────────────────────────────────────
def check_temporal_rules(service_root: Path):
    workflows_dir = service_root / "workflows"
    if not workflows_dir.exists():
        return
    for py in workflows_dir.rglob("*.py"):
        src = py.read_text(encoding="utf-8", errors="ignore")
        lines = src.splitlines()
        in_run = False
        run_start = 0
        indent_base = 0
        for i, line in enumerate(lines, 1):
            if re.search(r'async def run\s*\(', line) and not in_run:
                in_run = True
                run_start = i
                indent_base = len(line) - len(line.lstrip())
            elif in_run:
                stripped = line.strip()
                if stripped == "":
                    continue
                current_indent = len(line) - len(line.lstrip())
                if current_indent <= indent_base and stripped:
                    run_len = i - run_start
                    if run_len > 20:
                        err("TEMPORAL-01", f"{py.relative_to(ROOT)}:{run_start}", f"workflow.run is {run_len} lines — max 20. Move business logic to service class.")
                    in_run = False


# ──────────────────────────────────────────────────────────────
# DEPLOY-01: cross-service imports
# ──────────────────────────────────────────────────────────────
def check_deploy_rules():
    for service, forbidden in [
        (PRANA_AI, ["prana_api", "prana_ask"]),
        (PRANA_ASK, ["prana_api", "prana_ai"]),
    ]:
        if not service.exists():
            continue
        for py in service.rglob("*.py"):
            src = py.read_text(encoding="utf-8", errors="ignore")
            for i, line in enumerate(src.splitlines(), 1):
                for f in forbidden:
                    if re.search(rf'from\s+{f}|import\s+{f}', line):
                        err("DEPLOY-01", f"{py.relative_to(ROOT)}:{i}", f"cross-service import of '{f}' — deployment boundary violation")


# ──────────────────────────────────────────────────────────────
# INTERNAL-01: prana-ai must never call the external Kong/ALB URL
#
# prana-ai is the ONLY service authorised to call prana-api directly
# (VPC-internal, for pipeline stage callbacks). That path is codified in
# the networking SG rule `api_from_ai_internal`.
#
# What is forbidden: prana-ai code using the public domain (api.prana.in
# or any https://* URL) to call prana-api. That would route traffic out
# through the ALB and back in — wrong path, higher latency, unnecessary
# Kong auth overhead on internal traffic.
#
# What is required: prana-ai uses the internal service DNS name
# (e.g. prana-api.prod.internal:8000 or the env var PRANA_API_INTERNAL_URL).
# ──────────────────────────────────────────────────────────────
INTERNAL_URL_PATTERN = re.compile(
    r'https?://[a-zA-Z0-9._-]*prana[a-zA-Z0-9._-]*\.(in|com|io|dev)["\'/]',
    re.I,
)
INTERNAL_EXEMPT_PATTERNS = [
    # Allowed: internal service DNS (not a public domain)
    re.compile(r'\.internal["\'/:]'),
    re.compile(r'localhost'),
    re.compile(r'127\.0\.0\.1'),
]

def check_internal_call_rules():
    if not PRANA_AI.exists():
        return
    for py in PRANA_AI.rglob("*.py"):
        rel_parts = py.relative_to(PRANA_AI).parts
        if rel_parts[0] in {"tests", "scripts"}:
            continue
        src = py.read_text(encoding="utf-8", errors="ignore")
        for i, line in enumerate(src.splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if INTERNAL_URL_PATTERN.search(stripped):
                if not any(p.search(stripped) for p in INTERNAL_EXEMPT_PATTERNS):
                    err(
                        "INTERNAL-01",
                        f"{py.relative_to(ROOT)}:{i}",
                        "prana-ai must call prana-api via VPC-internal URL (PRANA_API_INTERNAL_URL), "
                        "not the public Kong/ALB domain. See .claude/rules/internal-service-calls.md",
                    )


# ──────────────────────────────────────────────────────────────
# MSG-01: hardcoded English sentence in HTTPException detail (backend)
#   Correct:  raise HTTPException(..., detail=PranaError.INVALID_TOTP)
#   Correct:  raise HTTPException(..., detail=PranaError.INVALID_TOTP.value)
#   Wrong:    raise HTTPException(..., detail="Incorrect authenticator code")
# MSG-02: hardcoded "message" string in return dict (backend)
#   Correct:  {"message": SuccessCode.DOC_UPLOADED}
#   Wrong:    {"message": "Document uploaded successfully"}
# ──────────────────────────────────────────────────────────────

# Patterns that are definitely taxonomy code references (not hardcoded strings)
MSG_OK_DETAIL = re.compile(
    r'detail\s*=\s*('
    r'PranaError\.|AskError\.|PipelineError\.|SuccessCode\.|InfoCode\.|ValidationCode\.|StatusCode\.'  # typed constant
    r'|[A-Z_]+\.[A-Z_]+\b'          # any enum.MEMBER pattern
    r'|request_id|error_detail'      # variable references
    r'|f["\']'                       # f-string (assume intentional for dynamic content)
    r'|[a-zA-Z_][a-zA-Z_0-9]*\)'    # variable name passed
    r')',
    re.I,
)
MSG_HARDCODED_DETAIL = re.compile(r'detail\s*=\s*["\']([^"\']{10,})["\']')
MSG_HARDCODED_MESSAGE = re.compile(r'["\']message["\']\s*:\s*["\']([a-zA-Z][a-zA-Z0-9 _-]{5,})["\']')

MSG_EXEMPT_DIRS = {"tests", "scripts", "migrations", "seeds", "prompts", "schemas"}
MSG_EXEMPT_FILES = {"errors.py", "messages.py"}


def _looks_like_english(s: str) -> bool:
    """Return True if string looks like a user-facing English sentence, not a code."""
    # Codes are: UPPER_SNAKE, short slugs, UUID patterns, URLs, JSON keys
    if re.match(r'^[A-Z][A-Z0-9_]+$', s):     # ALL_CAPS code
        return False
    if re.match(r'^[a-z][a-z0-9_]+$', s):     # snake_case code
        return False
    if len(s.split()) == 1:                    # single token
        return False
    if "://" in s or s.startswith("/"):        # URL / path
        return False
    return True                                 # multi-word mixed-case → English sentence


def check_message_taxonomy_rules(service_root: Path):
    """MSG-01 and MSG-02 — no hardcoded English in HTTPException detail or success message dicts."""
    for py in service_root.rglob("*.py"):
        rel_parts = py.relative_to(service_root).parts
        if rel_parts[0] in MSG_EXEMPT_DIRS:
            continue
        if py.name in MSG_EXEMPT_FILES:
            continue
        if "test" in py.name:
            continue

        src = py.read_text(encoding="utf-8", errors="ignore")
        lines = src.splitlines()

        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue

            # MSG-01: detail="English sentence" in HTTPException
            if "HTTPException" in stripped or "detail=" in stripped:
                m = MSG_HARDCODED_DETAIL.search(stripped)
                if m and _looks_like_english(m.group(1)) and not MSG_OK_DETAIL.search(stripped):
                    err(
                        "MSG-01",
                        f"{py.relative_to(ROOT)}:{i}",
                        f'hardcoded English in detail="{m.group(1)[:50]}" — use PranaError.CODE or AskError.CODE',
                    )

            # MSG-02: "message": "English string" in return dict
            if '"message"' in stripped or "'message'" in stripped:
                m = MSG_HARDCODED_MESSAGE.search(stripped)
                if m and _looks_like_english(m.group(1)):
                    # Exclude taxonomy value assignments themselves (errors.py / messages.py already exempt)
                    if "SuccessCode" not in stripped and "InfoCode" not in stripped and "StatusCode" not in stripped:
                        err(
                            "MSG-02",
                            f"{py.relative_to(ROOT)}:{i}",
                            f'hardcoded English in "message": "{m.group(1)[:50]}" — use SuccessCode.CODE or success_response()',
                        )


# ──────────────────────────────────────────────────────────────
# MSG-03: hardcoded English strings in TSX / portal components
#
# Correct (portal):  tError(error.detail)  tSuccess(res.message)  tStatus(doc.pipeline_status)
# Correct (mobile):  tError(code)  tSuccess(code)  tStatus(code)
# Wrong:             <Text>Something went wrong</Text>
#                    Alert.alert("Error", "Failed to load documents")
#                    setError("This field is required")
#                    toast("Document uploaded successfully")
#
# Rule fires as WARN (not ERROR) — TSX has more legitimate non-taxonomy strings
# (navigation labels, static page copy, accessibility strings) than Python.
# ──────────────────────────────────────────────────────────────

# Sentences in JSX text content: >English sentence< or {'English sentence'}
MSG03_JSX_TEXT  = re.compile(r'[>}]\s*([A-Z][a-z][a-zA-Z0-9 ,.\'-]{12,})\s*[<{]')
# Alert.alert("Title", "English message body")
MSG03_ALERT     = re.compile(r'Alert\.alert\s*\(\s*["\']([^"\']+)["\']', re.I)
# setError("...") / setMessage("...") / showToast("...") / toast("...") with long English
MSG03_SET_ERR   = re.compile(r'(?:setError|setMessage|showToast|toast|addToast)\s*\(\s*["\']([A-Z][a-z][a-zA-Z0-9 ,.\'-]{10,})["\']')
# placeholder="English sentence" on TextInput / Input
MSG03_PLACEHOLDER = re.compile(r'placeholder\s*=\s*["\']([A-Z][a-z][a-zA-Z0-9 ,.\'-]{10,})["\']')

MSG03_EXEMPT_FILES = {
    "index.ts", "index.tsx", "tokens.ts",          # i18n and theme files
    "_layout.tsx",                                  # navigation shells
    "Landing.tsx",                                  # brand/marketing copy — intentional static strings
    "stub.tsx",                                     # dev stub pages
    "OrgRegister.tsx",                              # brand/form copy — headings not taxonomy
}
MSG03_EXEMPT_DIRS = {"i18n", "__tests__", "test", "mocks", "node_modules"}

# Only flag strings that are clearly feedback/error messages (not marketing or heading copy).
_MSG03_FEEDBACK = re.compile(
    r'\b(fail|error|wrong|invalid|expir|required|not found|try again|'
    r'no .{1,20} found|no .{1,20} yet|no .{1,20} configured|'
    r'please try|could not|couldn\'t|unable to|something went wrong|'
    r'check your|contact support|upload fail|register fail)\b', re.I
)

def _tsx_looks_like_english(s: str, require_feedback: bool = False) -> bool:
    if not s or len(s.split()) < 3:
        return False
    if re.match(r'^[A-Z_]+$', s):          # ALL_CAPS constant
        return False
    if s.startswith("http") or "/" in s:    # URL / path
        return False
    if require_feedback and not _MSG03_FEEDBACK.search(s):
        return False                        # Not a feedback message — skip
    return True

def check_tsx_message_rules():
    for project_root in [ROOT / "prana-portal", ROOT / "prana-mobile"]:
        if not project_root.exists():
            continue
        for tsx in project_root.rglob("*.tsx"):
            rel_parts = tsx.relative_to(project_root).parts
            if any(p in MSG03_EXEMPT_DIRS for p in rel_parts):
                continue
            if tsx.name in MSG03_EXEMPT_FILES:
                continue

            src = tsx.read_text(encoding="utf-8", errors="ignore")
            lines = src.splitlines()
            for i, line in enumerate(lines, 1):
                stripped = line.strip()
                if stripped.startswith("//") or stripped.startswith("*"):
                    continue

                for pat, label, feedback_only in [
                    (MSG03_JSX_TEXT,    "JSX text",        True),   # only feedback sentences
                    (MSG03_ALERT,       "Alert.alert",     False),  # all Alert.alert calls
                    (MSG03_SET_ERR,     "setError/toast",  False),  # all setError/toast calls
                    (MSG03_PLACEHOLDER, "placeholder",     False),  # all long placeholders
                ]:
                    m = pat.search(stripped)
                    if m and _tsx_looks_like_english(m.group(1), require_feedback=feedback_only):
                        # Skip if already wrapped in t() call on same line
                        if "t(" not in stripped and "tError(" not in stripped \
                                and "tSuccess(" not in stripped and "tStatus(" not in stripped \
                                and "tValidation(" not in stripped and "tInfo(" not in stripped \
                                and "tUi(" not in stripped:
                            warn(
                                "MSG-03",
                                f"{tsx.relative_to(ROOT)}:{i}",
                                f'{label}: hardcoded "{m.group(1)[:55]}" — use t() from i18n',
                            )
                        break  # one warning per line


# ──────────────────────────────────────────────────────────────
# FRONTEND-01: nested Pressable
# ──────────────────────────────────────────────────────────────
def check_frontend_rules():
    mobile = ROOT / "prana-mobile"
    if not mobile.exists():
        return
    for tsx in mobile.rglob("*.tsx"):
        src = tsx.read_text(encoding="utf-8", errors="ignore")
        # crude check: Pressable inside Pressable in same file
        pressable_count = src.count("<Pressable")
        if pressable_count > 1:
            # deeper check: look for nested pattern
            if re.search(r'<Pressable[\s\S]{0,500}<Pressable', src):
                warn("FRONTEND-01", tsx.relative_to(ROOT), "possible nested Pressable — one touch target per card")


# ──────────────────────────────────────────────────────────────
# Run all checks
# ──────────────────────────────────────────────────────────────
print("Running PRANA enforce_rules.py ...\n")

for svc in [PRANA_API, PRANA_AI, PRANA_ASK]:
    if svc.exists():
        check_tdd(svc)
        check_db_rules(svc)
        check_security_rules(svc)
        check_message_taxonomy_rules(svc)

check_api_rules(PRANA_API)
check_kafka_rules(PRANA_API)
check_temporal_rules(PRANA_API)
check_deploy_rules()
check_internal_call_rules()
check_frontend_rules()
check_tsx_message_rules()

# ──────────────────────────────────────────────────────────────
# Report
# ──────────────────────────────────────────────────────────────
for w in warnings:
    print(w)

for e in errors:
    print(e)

total_errors = len(errors)
total_warns = len(warnings)
print(f"\n{'-'*60}")
print(f"Errors: {total_errors}  Warnings: {total_warns}")

if total_errors == 0:
    print("OK — All checks passed — safe to merge.")
    sys.exit(0)
else:
    print("FAIL — Fix errors before merging.")
    sys.exit(1)
