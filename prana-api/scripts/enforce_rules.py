"""
PRANA Rule Enforcement Scanner
================================
Mechanically enforces every rule in .claude/rules/ that can be statically checked.
Run in CI on every PR: python scripts/enforce_rules.py

Exit 0 = clean. Exit 1 = violations found, block merge.

Rules enforced:
  [SEC-01]    No raw salary/PAN field names in API responses
  [SEC-02]    No plaintext PAN in cache keys (only pan_token allowed)
  [SEC-03]    tenant_id never from request body or URL param
  [SEC-04]    No hardcoded secrets or KMS ARNs in source (all services)
  [SEC-05]    No direct external HTTP calls from routers (must go via Kafka → consumer)
  [DB-01]     No f-string SQL (parameterized queries only)
  [DB-02]     No bare SELECT * in production queries
  [DB-03]     No bare except: (must catch specific exceptions — all Python services)
  [DB-04]     No DELETE FROM audit_event anywhere (7-year legal retention)
  [API-01]    No bare array return — collections must be wrapped
  [API-02]    asyncpg UUID/date/datetime must be serialized (no raw dict(row))
  [KAFKA-01]  No audit_event INSERT in HTTP handlers
  [KAFKA-02]  No temporal.start_workflow in HTTP handlers
  [DEPLOY-01] No cross-service imports (prana-ai/prana-ask importing prana-api or each other)
  [TEMPORAL-01] No business logic inside @workflow.run directly
  [FRONTEND-01] No nested Pressable/TouchableOpacity components
  [FRONTEND-02] No fetch calls without loading/error state handling
  [ASK-01]    Qdrant search must filter by employee_user_id (no cross-tenant leakage)
  [MOB-01]    AsyncStorage never used for auth tokens (must use SecureStore)
  [SHARE-01]  document_access_log INSERT must include ip_address
  [KAFKA-03]  No direct kafka.publish() in routers/services — use domain helpers
  [DB-05]     No datetime.utcnow() — deprecated, use datetime.now(datetime.timezone.utc)
  [TDD-01]    Every source file must have a corresponding test file (ERROR — blocks merge)
  [TDD-02]    Test files must contain at least one def test_*() function
"""
import re
import sys
from pathlib import Path
from dataclasses import dataclass, field

ROOT = Path(__file__).parent.parent.parent  # monorepo root
API_ROOT = ROOT / "prana-api"
PORTAL_ROOT = ROOT / "prana-portal" / "src"
MOBILE_ROOT = ROOT / "prana-mobile" / "src"
AI_ROOT = ROOT / "prana-ai"
ASK_ROOT = ROOT / "prana-ask"


@dataclass
class Violation:
    rule: str
    file: str
    line: int
    code: str
    message: str
    severity: str = "ERROR"  # ERROR = block merge | WARN = review required


violations: list[Violation] = []


def fail(rule: str, file: Path, line: int, code: str, message: str, severity="ERROR"):
    violations.append(Violation(
        rule=rule,
        file=str(file.relative_to(ROOT)),
        line=line,
        code=code.strip(),
        message=message,
        severity=severity,
    ))


def scan_py(directory: Path, rule: str, pattern: str, message: str,
            exclude_pattern: str = None, severity="ERROR"):
    """Scan Python files for a regex pattern."""
    if not directory.exists():
        return
    regex = re.compile(pattern)
    exclude = re.compile(exclude_pattern) if exclude_pattern else None
    for f in directory.rglob("*.py"):
        if "test_" in f.name or "__pycache__" in str(f) or "scripts" in f.parts:
            continue
        for i, line in enumerate(f.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
            if regex.search(line):
                if exclude and exclude.search(line):
                    continue
                if f"noqa: {rule}" in line:
                    continue
                fail(rule, f, i, line, message, severity)


def scan_ts(directory: Path, rule: str, pattern: str, message: str,
            exclude_pattern: str = None, severity="ERROR"):
    """Scan TypeScript/TSX files for a regex pattern."""
    if not directory.exists():
        return
    regex = re.compile(pattern)
    exclude = re.compile(exclude_pattern) if exclude_pattern else None
    for ext in ["*.ts", "*.tsx"]:
        for f in directory.rglob(ext):
            for i, line in enumerate(f.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
                if regex.search(line):
                    if exclude and exclude.search(line):
                        continue
                    fail(rule, f, i, line, message, severity)


# ── [SEC-01] No raw salary/PAN field names in API responses ───────────────────
# Flag sensitive field names only when they appear as dict return keys (response output)
# Pattern: "field_name": value inside a return statement context
SENSITIVE_FIELD_NAMES = r'"(salary|pan|nik|gross_salary|net_salary|basic_salary|ctc|enc_dek|totp_secret_enc)"\s*:'
scan_py(
    API_ROOT / "routers", "SEC-01",
    SENSITIVE_FIELD_NAMES,
    "Sensitive field as response key. Raw salary/PAN/DEK must never be returned in API response.",
    exclude_pattern=r"(#|SELECT|WHERE|INSERT|=\s*r\[|row\[|verify|hash|dummy)",
)

# ── [SEC-02] No plaintext PAN as cache key ────────────────────────────────────
# Redis keys must use pan_token (HMAC), never raw PAN
scan_py(
    API_ROOT, "SEC-02",
    r'redis.*["\']pan["\']|cache.*["\']pan["\']|f["\']pan:',
    "Possible plaintext PAN used as Redis cache key. Use pan_token (HMAC output) instead.",
)

# ── [SEC-03] tenant_id from request body or URL ───────────────────────────────
# Exception: pa_admin routes are cross-tenant by design (Portal Admin manages all tenants)
# Exception: employee routes where tenant_id is a TARGET (which employer) not auth scope
# Flag all others — OA user routes must never take tenant_id from body
scan_py(
    API_ROOT / "routers", "SEC-03",
    r'tenant_id\s*=\s*(body|request\.path_params|params)\.',
    "tenant_id from request body/URL. For OA routes: use current.tenant_id from JWT. "
    "For PA/employee cross-tenant targeting: add # sec03-cross-tenant-ok comment to suppress.",
    exclude_pattern=r"(pa_admin|#\s*sec03-cross-tenant-ok)",
)

# ── [SEC-04] Hardcoded secrets ────────────────────────────────────────────────
HARDCODED_SECRET_PATTERN = r'(api_key|secret|password|token|arn:aws:kms)\s*=\s*["\'][A-Za-z0-9/+]{16,}'
scan_py(API_ROOT, "SEC-04", HARDCODED_SECRET_PATTERN,
        "Possible hardcoded secret. All secrets must come from environment variables.",
        exclude_pattern=r"(#|test_|mock_|example_|placeholder)")
scan_ts(PORTAL_ROOT, "SEC-04", r'apiKey\s*[:=]\s*["\'][A-Za-z0-9]{20,}',
        "Possible hardcoded API key in frontend. Use environment variables.")

# ── [DB-01] No f-string SQL ───────────────────────────────────────────────────
# Catches both single-quoted and triple-quoted f-strings passed to db methods
scan_py(
    API_ROOT, "DB-01",
    r'(db|conn|pool)\.(fetch|execute|fetchrow|fetchval)\s*\(\s*f["\']',
    "f-string SQL detected. Use parameterized queries with $1, $2 placeholders.",
)
# Also catch f""" triple-quote variant (separate pass — regex above misses triple-quote)
scan_py(
    API_ROOT, "DB-01",
    r'(db|conn|pool)\.(fetch|execute|fetchrow|fetchval)\s*\(\s*f"""',
    "f-string SQL (triple-quote) detected. Use parameterized queries with $1, $2 placeholders.",
)

# ── [DB-02] No SELECT * ───────────────────────────────────────────────────────
scan_py(
    API_ROOT, "DB-02",
    r'SELECT\s+\*\s+FROM',
    "SELECT * detected. Name every column explicitly — schema changes break silent SELECT *.",
    severity="WARN",
)

# ── [DB-03] No bare except ────────────────────────────────────────────────────
scan_py(
    API_ROOT, "DB-03",
    r'^\s*except\s*:',
    "Bare except: detected. Catch specific exceptions (e.g. asyncpg.PostgresError, ValueError).",
)

# ── [API-01] No bare list return from routers ────────────────────────────────
# Routers returning a bare list [] instead of {"items": [], "total": N}
scan_py(
    API_ROOT / "routers", "API-01",
    r'^\s*return\s+\[',
    "Router returning bare list []. Collections must be wrapped: {\"items\": [...], \"total\": N}.",
)

# ── [API-02] No raw dict(row) return ─────────────────────────────────────────
# Scoped to routers only — routers own the API serialization boundary.
# Service methods returning dict(row) internally are OK if the calling router serializes.
# Catches: return [dict(r)], return dict(row), [dict(r) for r in rows] assigned in response,
#          **dict(r) spread into response dicts.
scan_py(
    API_ROOT / "routers", "API-02",
    r'(return\s+\[dict\(r\)|return\s+dict\(row\)|\[dict\(r\)\s+for\s+r\s+in|\*\*dict\(r\))',
    "Raw dict(row/r) in router. UUID/date/datetime/JSONB fields need explicit serialization.",
    exclude_pattern=r"(_serialize|_format|ManifestRecord)",
)

# ── [KAFKA-01] No audit_event INSERT in HTTP handlers ─────────────────────────
scan_py(
    API_ROOT / "routers", "KAFKA-01",
    r'INSERT\s+INTO\s+audit_event',
    "audit_event INSERT in HTTP handler. AuditConsumer owns this — publish to Kafka instead.",
)

# ── [KAFKA-02] No temporal.start_workflow in HTTP handlers ────────────────────
scan_py(
    API_ROOT / "routers", "KAFKA-02",
    r'temporal.*start_workflow|start_workflow.*temporal',
    "Temporal workflow start in HTTP handler. WorkflowConsumer owns this — publish to Kafka instead. "
    "Exception: add # kafka02-correlated-start-ok comment when direct start is required for signal correlation.",
    exclude_pattern=r'(signal|kafka02-correlated-start-ok)',
)

# ── [DEPLOY-01] No cross-service imports ──────────────────────────────────────
scan_py(
    AI_ROOT, "DEPLOY-01",
    r'from prana_api\.|import prana_api',
    "Cross-service import: prana-ai importing from prana-api. These are separate deployables.",
)
scan_py(
    ASK_ROOT, "DEPLOY-01",
    r'from prana_api\.|import prana_api',
    "Cross-service import: prana-ask importing from prana-api. These are separate deployables.",
)

# ── [TEMPORAL-01] Business logic inside @workflow.run ────────────────────────
# Flag workflows that contain direct DB calls or HTTP calls — these belong in service classes.
# Line count alone is not the signal: Pattern 2/5 workflows legitimately have signal handlers
# and multiple execute_activity calls. The rule is: no direct db.execute/fetch or requests.get.
WORKFLOW_BIZ_LOGIC_PATTERNS = re.compile(
    r'(await\s+db\.(execute|fetch|fetchrow|fetchval)|'
    r'requests\.(get|post|put|delete)|'
    r'aiohttp\.ClientSession|'
    r'asyncpg\.connect)'
)

def check_workflow_thickness():
    wf_dir = API_ROOT / "workflows"
    if not wf_dir.exists():
        return
    for f in wf_dir.rglob("*.py"):
        text = f.read_text(encoding="utf-8", errors="ignore")
        lines = text.splitlines()
        in_run = False
        run_start = 0
        for i, line in enumerate(lines, 1):
            if "@workflow.run" in line:
                in_run = True
                run_start = i
            elif in_run:
                # Stop scanning when next method definition starts (not same def)
                if i > run_start + 1 and line.strip().startswith("async def ") and "run" not in line:
                    in_run = False
                elif WORKFLOW_BIZ_LOGIC_PATTERNS.search(line):
                    fail("TEMPORAL-01", f, i,
                         line.strip(),
                         "Direct DB/HTTP call inside @workflow.run. "
                         "Business logic (db.execute, requests.*) belongs in a service class called via execute_activity.",
                         severity="WARN")

check_workflow_thickness()

# ── [FRONTEND-01] Nested Pressable/TouchableOpacity ──────────────────────────
def check_nested_pressables():
    if not MOBILE_ROOT.exists():
        return
    for f in MOBILE_ROOT.rglob("*.tsx"):
        lines = f.read_text(encoding="utf-8", errors="ignore").splitlines()
        pressable_depth = 0
        for i, line in enumerate(lines, 1):
            opens = len(re.findall(r'<(Pressable|TouchableOpacity)[\s>]', line))
            # Self-closing <Pressable ... /> counts as open+close (net 0 depth change)
            self_closes = len(re.findall(r'<(Pressable|TouchableOpacity)[^>]*/>', line))
            closes = len(re.findall(r'</(Pressable|TouchableOpacity)>', line)) + self_closes
            pressable_depth += opens - closes
            # Skip modal panel pattern: stopPropagation on inner Pressable is intentional
            if pressable_depth > 1 and opens > 0 and "stopPropagation" not in line:
                fail("FRONTEND-01", f, i, line,
                     "Nested Pressable/TouchableOpacity detected. One touch target per component.",
                     severity="WARN")

check_nested_pressables()

# ── [FRONTEND-02] useQuery without error handling ────────────────────────────
# Check at file level — if file has useQuery but no isLoading/isError anywhere in file
def check_usequery_states():
    for src_root in [PORTAL_ROOT, MOBILE_ROOT]:
        if not src_root.exists():
            continue
        for ext in ["*.ts", "*.tsx"]:
            for f in src_root.rglob(ext):
                text = f.read_text(encoding="utf-8", errors="ignore")
                if "useQuery" not in text:
                    continue
                has_state_handling = any(kw in text for kw in [
                    "isLoading", "isPending", "isError", "isFetching",
                    "status ===", "Skeleton", "skeleton", "Spinner", "spinner",
                ])
                if not has_state_handling:
                    fail("FRONTEND-02", f, 1, "useQuery",
                         "File uses useQuery but has no loading/error state handling. "
                         "Add isLoading, isError checks or skeleton UI.",
                         severity="WARN")

check_usequery_states()

# ── [SEC-04] Expanded — hardcoded secrets in all Python services ──────────────
# Already covers prana-api; add prana-ai and prana-ask
scan_py(AI_ROOT, "SEC-04", HARDCODED_SECRET_PATTERN,
        "Possible hardcoded secret in prana-ai. All secrets must come from environment variables.",
        exclude_pattern=r"(#|test_|mock_|example_|placeholder)")
scan_py(ASK_ROOT, "SEC-04", HARDCODED_SECRET_PATTERN,
        "Possible hardcoded secret in prana-ask. All secrets must come from environment variables.",
        exclude_pattern=r"(#|test_|mock_|example_|placeholder)")
# Mobile: TypeScript secret patterns
scan_ts(MOBILE_ROOT, "SEC-04", r'(apiKey|secret|password|token)\s*[:=]\s*["\'][A-Za-z0-9/+]{20,}',
        "Possible hardcoded secret in prana-mobile. Use Expo config / environment variables.",
        exclude_pattern=r"(//|test|mock|example|placeholder)")

# ── [DB-03] Expanded — bare except in all Python services ─────────────────────
scan_py(AI_ROOT, "DB-03",
        r'^\s*except\s*:',
        "Bare except: in prana-ai. Catch specific exceptions.",
)
scan_py(ASK_ROOT, "DB-03",
        r'^\s*except\s*:',
        "Bare except: in prana-ask. Catch specific exceptions.",
)

# ── [DB-04] No DELETE FROM audit_event ───────────────────────────────────────
# audit_event rows are legally required for 7 years. Never delete them.
def check_no_audit_delete():
    for svc_root in [API_ROOT, AI_ROOT, ASK_ROOT]:
        if not svc_root.exists():
            continue
        for f in svc_root.rglob("*.py"):
            # Exclude this script itself, test files, and __pycache__
            if "scripts" in str(f) or "test_" in f.name or "__pycache__" in str(f):
                continue
            for i, line in enumerate(f.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
                if re.search(r'DELETE\s+FROM\s+audit_event', line, re.IGNORECASE):
                    fail("DB-04", f, i, line.strip(),
                         "DELETE FROM audit_event is FORBIDDEN. Audit rows are legally retained "
                         "for 7 years. Erasure requests do NOT apply to audit_event rows.",
                         severity="ERROR")

check_no_audit_delete()

# ── [SEC-05] No direct external HTTP calls from routers ──────────────────────
# External calls (SMS, email, WhatsApp, EPFO) must go via Kafka → NotifConsumer.
# Exception: KMS and S3 are synchronous and allowed in handlers.
scan_py(
    API_ROOT / "routers", "SEC-05",
    r'(requests\.(get|post|put|delete|patch)|aiohttp\.ClientSession|httpx\.(get|post|put|delete))',
    "Direct external HTTP call in router. Must go through Kafka → NotifConsumer. "
    "Exception: KMS and S3 (sync, required for document handling).",
    exclude_pattern=r"(#\s*sec05-direct-ok|kms|s3|boto)",
)

# ── [ASK-01] Qdrant search must filter by employee_user_id ───────────────────
# Missing filter = cross-employee data leak (highest-risk gap in prana-ask).
# Check at file level: any file that calls qdrant search must also reference employee_user_id.
def check_qdrant_filter():
    if not ASK_ROOT.exists():
        return
    for f in ASK_ROOT.rglob("*.py"):
        if "tests" in str(f) or "__pycache__" in str(f):
            continue
        text = f.read_text(encoding="utf-8", errors="ignore")
        if not re.search(r'\.(search|query)\s*\(', text):
            continue
        if "employee_user_id" not in text:
            fail("ASK-01", f, 1, f.name,
                 "File calls qdrant .search()/.query() but does not reference employee_user_id. "
                 "Every qdrant query MUST filter by employee_user_id to prevent cross-tenant data leakage.",
                 severity="ERROR")

check_qdrant_filter()

# ── [MOB-01] AsyncStorage never used for auth tokens ────────────────────────
# Auth tokens must use SecureStore (encrypted). AsyncStorage is plaintext.
# Non-sensitive UI flags (dismissed nudges, preferences, theme, locale) are OK in AsyncStorage.
scan_ts(
    MOBILE_ROOT, "MOB-01",
    r'AsyncStorage\.(set|get|remove)Item',
    "AsyncStorage used for data storage. Auth tokens (JWT, refresh) must use expo-secure-store. "
    "AsyncStorage is unencrypted — never store tokens, session IDs, or sensitive data here.",
    exclude_pattern=r"(#\s*mob01-non-sensitive-ok|preference|theme|language|locale|dismissed|nudge|onboarding|setting)",
    severity="WARN",
)

# ── [SHARE-01] document_access_log INSERT must include ip_address ─────────────
# ip_address is NOT NULL in schema and required for CISO audit trail.
# Flag any INSERT INTO document_access_log that does not have ip_address within 20 lines.
def check_access_log_ip():
    for svc_root in [API_ROOT, AI_ROOT]:
        if not svc_root.exists():
            continue
        for f in svc_root.rglob("*.py"):
            if "test_" in f.name or "__pycache__" in str(f):
                continue
            lines = f.read_text(encoding="utf-8", errors="ignore").splitlines()
            for i, line in enumerate(lines, 1):
                if re.search(r'INSERT\s+INTO\s+document_access_log', line, re.IGNORECASE):
                    window = "\n".join(lines[max(0, i-1):min(len(lines), i+20)])
                    if "ip_address" not in window:
                        fail("SHARE-01", f, i, line.strip(),
                             "INSERT INTO document_access_log missing ip_address. "
                             "ip_address is NOT NULL in schema and mandatory for CISO audit trail.",
                             severity="ERROR")

check_access_log_ip()

# ── [DEPLOY-01] Expanded — prana-ask must not import from prana-ai ────────────
scan_py(
    ASK_ROOT, "DEPLOY-01",
    r'from prana_ai\.|import prana_ai',
    "Cross-service import: prana-ask importing from prana-ai. These are separate GPU deployables.",
)

# ── [KAFKA-03] No direct kafka.publish() — use domain helpers ────────────────
# Every Kafka publish in prana-api must go through a domain helper (doc_ingested,
# compliance_event, auth_event, etc.) which fans out to the right topics atomically.
# Direct publish() bypasses the fan-out and misses secondary topics (audit, analytics).
# Exception: kafka/producer.py itself defines the helpers (it IS the publish layer).
# Exception: prana-ai calls publish() directly — it has no domain helpers (separate service).
scan_py(
    API_ROOT / "routers", "KAFKA-03",
    r'\bkafka\b.*\.publish\s*\(',
    "Direct kafka.publish() in router. Use domain helpers: kafka.doc_ingested(), "
    "kafka.compliance_event(), kafka.auth_event(), etc. — they fan-out to the correct topics.",
    exclude_pattern=r"(#\s*kafka03-direct-ok|producer\.py|kafka/)",
)
scan_py(
    API_ROOT / "services", "KAFKA-03",
    r'\bkafka\b.*\.publish\s*\(|\b_kafka\b.*\.publish\s*\(',
    "Direct kafka.publish() in service. Use domain helpers which fan-out to the correct topics.",
    exclude_pattern=r"(#\s*kafka03-direct-ok|producer\.py)",
)

# ── [DB-05] No datetime.utcnow() — timezone-naive, deprecated in Python 3.12 ──
scan_py(
    API_ROOT, "DB-05",
    r'datetime\.utcnow\(\)',
    "datetime.utcnow() is deprecated in Python 3.12+ and returns timezone-naive datetimes. "
    "Use datetime.now(datetime.timezone.utc) instead.",
)
scan_py(
    AI_ROOT, "DB-05",
    r'datetime\.utcnow\(\)',
    "datetime.utcnow() is deprecated. Use datetime.now(datetime.timezone.utc).",
)
scan_py(
    ASK_ROOT, "DB-05",
    r'datetime\.utcnow\(\)',
    "datetime.utcnow() is deprecated. Use datetime.now(datetime.timezone.utc).",
)

# ── [TDD-01] Every source file must have a test file ─────────────────────────
# Red-Green-Refactor: write the failing test FIRST. No test file = blocked.
SKIP_STEMS = {
    "__init__", "config", "main", "db", "versioning", "worker",
    "llm_client", "conftest", "settings",
}
SKIP_DIR_PARTS = {
    "middleware", "kafka", "scripts", "migrations", "seeds",
    "prompts", "schemas", "tests", "__pycache__", "node_modules",
}

def check_tdd_coverage():
    checks = [
        # (source_dirs_to_scan, tests_dir)
        (
            [API_ROOT / "routers", API_ROOT / "services", API_ROOT / "workflows"],
            API_ROOT / "tests",
        ),
        (
            [AI_ROOT / "pipeline", AI_ROOT / "extraction", AI_ROOT / "insights", AI_ROOT / "resolution"],
            AI_ROOT / "tests",
        ),
        (
            [ASK_ROOT],
            ASK_ROOT / "tests",
        ),
    ]
    for source_dirs, tests_dir in checks:
        for source_dir in source_dirs:
            if not source_dir.exists():
                continue
            # Skip schema/prompt subdirs (pure data, no logic)
            if any(p in SKIP_DIR_PARTS for p in source_dir.parts):
                continue
            for f in source_dir.glob("*.py"):
                if f.stem in SKIP_STEMS:
                    continue
                if any(p in SKIP_DIR_PARTS for p in f.parts):
                    continue
                # Accept test_{stem}.py OR test_{stem}_*.py (e.g. test_ingest_kafka_contract.py)
                matches = list(tests_dir.glob(f"test_{f.stem}*.py")) if tests_dir.exists() else []
                if not matches:
                    fail("TDD-01", f, 1, f.name,
                         f"No test file found matching tests/test_{f.stem}*.py. "
                         "TDD is mandatory: write a FAILING test first, then implement. "
                         "Create tests/test_{f.stem}.py with at least one @pytest.mark.xfail stub.",
                         severity="ERROR")

check_tdd_coverage()

# ── [TDD-02] Test files must contain actual test functions ────────────────────
def check_tdd_assertions():
    test_dirs = [API_ROOT / "tests", AI_ROOT / "tests", ASK_ROOT / "tests"]
    for tests_dir in test_dirs:
        if not tests_dir.exists():
            continue
        for f in tests_dir.glob("test_*.py"):
            text = f.read_text(encoding="utf-8", errors="ignore")
            if "def test_" not in text:
                fail("TDD-02", f, 1, f.name,
                     "Test file has no test functions (no def test_*). "
                     "Add at least one real or @pytest.mark.xfail stub test.",
                     severity="WARN")

check_tdd_assertions()


# ── Report ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("PRANA Rule Enforcement Scanner")
    print("=" * 60)

    errors = [v for v in violations if v.severity == "ERROR"]
    warns  = [v for v in violations if v.severity == "WARN"]

    def _safe(s: str, limit: int = 120) -> str:
        """Truncate and encode safely for any console encoding."""
        return s[:limit].encode(sys.stdout.encoding or "utf-8", errors="replace").decode(
            sys.stdout.encoding or "utf-8", errors="replace"
        )

    if warns:
        print(f"\nWARNINGS ({len(warns)}) - review before merging:")
        for v in warns:
            print(f"  [{v.rule}] {v.file}:{v.line}")
            print(f"    Rule: {_safe(v.message)}")
            print(f"    Code: {_safe(v.code)}")

    if errors:
        print(f"\nERRORS ({len(errors)}) - merge blocked:")
        for v in errors:
            print(f"  [{v.rule}] {v.file}:{v.line}")
            print(f"    Rule: {_safe(v.message)}")
            print(f"    Code: {_safe(v.code)}")
        print(f"\n{len(errors)} rule violation(s). Fix before merging.")
        sys.exit(1)
    else:
        print(f"\n[OK] All rules enforced. {len(warns)} warning(s) to review.")
        sys.exit(0)
