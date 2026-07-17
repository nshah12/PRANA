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
  [ACTIVITY-01] Duplicate-named Temporal activity must resolve to its real implementation,
                never to an orphaned bare-stub declaration in another workflows/*.py file
  [QUEUE-01]  Every start_workflow/start_child_workflow task_queue must be one of
              worker.py's real registered queue names — a wrong queue name means the
              workflow sits started-but-never-polled forever, with zero error raised
  [IMPORT-01] `from services.X import Y` / `from workflows.X import Y` (and local
              bare modules db/config/messages/errors/versioning) must import a name
              that actually exists in the target module — a real, imported-and-
              checked resolution, not a regex guess
  [IMPORT-02] `instance.method()` where `instance` was assigned directly from a
              locally-imported class must call a method that actually exists on
              that class
"""
import ast
import importlib
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

# ── [ACTIVITY-01] Duplicate-named Temporal activity must resolve to its real
# implementation in worker.py, never to an orphaned stub in another file ──────
#
# Root cause of a real incident (2026-06-18, commit 813339c): activities.py grew
# real implementations (calling ComplianceService etc.) for several activity
# names, but worker.py's import block for compliance-queue was never updated to
# pull from there — it kept importing the plain stub names straight from
# workflows/compliance.py. Every workflow using those activities
# (ErasureConfirmationWorkflow, GrievanceWorkflow, ...) ran on Temporal and
# looked healthy, but every activity silently did nothing — a DPDP erasure
# request would never actually erase data. Purely structural
# (inspect.getsource(Workflow.run)) tests never caught this because they only
# look at the workflow shell, never at which activity function object actually
# got registered with the Worker. This check parses worker.py's AST for real
# instead of trusting import statements to be correct.

def _is_stub_body(body: list) -> bool:
    """True if a function body is only `...` (bare Ellipsis) — this codebase's
    established convention for an unimplemented activity."""
    if len(body) != 1:
        return False
    stmt = body[0]
    return (
        isinstance(stmt, ast.Expr)
        and isinstance(stmt.value, ast.Constant)
        and stmt.value.value is Ellipsis
    )


def check_activity_wiring():
    workflows_dir = API_ROOT / "workflows"
    worker_file = workflows_dir / "worker.py"
    if not workflows_dir.exists() or not worker_file.exists():
        return

    # 1. Every @activity.defn(name="X") across workflows/*.py, and whether it's a stub.
    declared: dict[str, list[tuple[Path, bool]]] = {}
    for f in workflows_dir.glob("*.py"):
        if f.name == "worker.py":
            continue
        try:
            tree = ast.parse(f.read_text(encoding="utf-8", errors="ignore"), filename=str(f))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.AsyncFunctionDef):
                continue
            for dec in node.decorator_list:
                if not (isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute)
                        and dec.func.attr == "defn"
                        and isinstance(dec.func.value, ast.Name) and dec.func.value.id == "activity"):
                    continue
                name_kw = next((kw for kw in dec.keywords if kw.arg == "name"), None)
                if name_kw and isinstance(name_kw.value, ast.Constant):
                    declared.setdefault(name_kw.value.value, []).append((f, _is_stub_body(node.body)))

    duplicates = {n: v for n, v in declared.items() if len(v) > 1}
    if not duplicates:
        return

    # 2. worker.py: local import alias -> (source module stem, original name).
    worker_tree = ast.parse(worker_file.read_text(encoding="utf-8", errors="ignore"), filename=str(worker_file))
    alias_origin: dict[str, tuple[str, str]] = {}
    for node in ast.walk(worker_tree):
        if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("workflows."):
            module_stem = node.module.split(".")[-1]
            for alias in node.names:
                alias_origin[alias.asname or alias.name] = (module_stem, alias.name)

    # 3. Local names actually referenced inside any WORKERS[...]["activities"] list.
    wired_locals: set[str] = set()
    for node in ast.walk(worker_tree):
        if isinstance(node, ast.Dict):
            for key, value in zip(node.keys, node.values):
                if isinstance(key, ast.Constant) and key.value == "activities" and isinstance(value, ast.List):
                    wired_locals.update(elt.id for elt in value.elts if isinstance(elt, ast.Name))

    # 4. For every duplicate-named activity, find which declaration is actually
    #    wired, and fail if that one is a stub while a real one exists elsewhere.
    for act_name, occurrences in duplicates.items():
        wired_file = next(
            (workflows_dir / f"{module_stem}.py"
             for local, (module_stem, original_name) in alias_origin.items()
             if original_name == act_name and local in wired_locals),
            None,
        )
        if wired_file is None:
            continue  # not wired anywhere — TDD-01/dead-code territory, not this rule's job
        wired_is_stub = next((stub for f, stub in occurrences if f == wired_file), None)
        real_elsewhere = [f for f, stub in occurrences if f != wired_file and not stub]
        if wired_is_stub and real_elsewhere:
            fail("ACTIVITY-01", wired_file, 1, act_name,
                 f"Activity '{act_name}' is wired in worker.py to the STUB in {wired_file.name}, "
                 f"but a real implementation exists in {', '.join(p.name for p in real_elsewhere)}. "
                 f"Fix worker.py's import for '{act_name}' to pull from the real module.",
                 severity="ERROR")

check_activity_wiring()

# ── [QUEUE-01] task_queue must be a real worker.py-registered queue name ──────
#
# Root cause of a live incident found 2026-07-17: workflow_consumer.py's
# _handle_doc_ingested — triggered on EVERY document upload — starts
# DocumentPipelineWorkflow and BatchTimeoutMonitorWorkflow on
# task_queue=TASK_QUEUE, where TASK_QUEUE is workflows/document_pipeline.py's
# own module constant ("document-pipeline"). But worker.py registers those
# workflow classes under "ingestsvc-queue" — a different string. Temporal's
# start_workflow() does not validate that a worker is polling the given queue
# name — it just queues the start event. Nothing ever raises: the document
# simply never advances past pipeline_status=QUEUED, forever, silently. The
# same "prana-admin" / "prana-compliance" style stale queue names (leftover
# from before queue names were standardized to the "*-queue" suffix) appear
# in auth_consumer.py, compliance_consumer.py, oa_user_consumer.py, and
# security_consumer.py's CSAMReportingWorkflow start.
#
# This resolves each call site's task_queue value — literal string, or a
# module-level constant possibly imported from another workflows/*.py file —
# statically, without a live Temporal cluster, and fails the build if it
# isn't one of worker.py's real WORKERS dict keys.

def _real_queue_names(worker_tree: ast.AST) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(worker_tree):
        # WORKERS: dict[str, dict] = {...} parses as AnnAssign, not Assign.
        if isinstance(node, (ast.Assign, ast.AnnAssign)) and isinstance(node.value, ast.Dict):
            for key in node.value.keys:
                if isinstance(key, ast.Constant) and isinstance(key.value, str):
                    names.add(key.value)
    return names


def _workflow_queue_map(worker_tree: ast.AST) -> dict[str, set[str]]:
    """Workflow class name -> the set of real queue(s) worker.py actually
    registers it on (a workflow can legitimately appear on more than one, e.g.
    VaultCompletenessWorkflow on both vault-queue and resolution-queue-analytics).
    Lets QUEUE-01 check not just 'is this any real queue' but 'is this the
    right queue for the specific workflow being started here' — the weaker
    check would have missed PolicyLockWorkflow being started on auth-queue
    when it's actually registered on secops-queue."""
    mapping: dict[str, set[str]] = {}
    for node in ast.walk(worker_tree):
        if not (isinstance(node, (ast.Assign, ast.AnnAssign)) and isinstance(node.value, ast.Dict)):
            continue
        for queue_key, queue_val in zip(node.value.keys, node.value.values):
            if not (isinstance(queue_key, ast.Constant) and isinstance(queue_val, ast.Dict)):
                continue
            queue_name = queue_key.value
            for k2, v2 in zip(queue_val.keys, queue_val.values):
                if isinstance(k2, ast.Constant) and k2.value == "workflows" and isinstance(v2, ast.List):
                    for elt in v2.elts:
                        if isinstance(elt, ast.Name):
                            mapping.setdefault(elt.id, set()).add(queue_name)
    return mapping


def _module_const_table(py_files: list[Path], module_prefix: str) -> dict[str, dict[str, object]]:
    """module_stem -> {const_name: ('literal', str) | ('ref', local_name) |
    ('import', source_module_stem, original_name)}"""
    table: dict[str, dict[str, object]] = {}
    for f in py_files:
        try:
            tree = ast.parse(f.read_text(encoding="utf-8", errors="ignore"), filename=str(f))
        except SyntaxError:
            continue
        entries: dict[str, object] = {}
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith(module_prefix):
                src_stem = node.module.split(".")[-1]
                for alias in node.names:
                    entries[alias.asname or alias.name] = ("import", src_stem, alias.name)
            elif isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
                target = node.targets[0].id
                if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                    entries[target] = ("literal", node.value.value)
                elif isinstance(node.value, ast.Name):
                    entries[target] = ("ref", node.value.id)
        table[f.stem] = entries
    return table


def _resolve_const(table: dict[str, dict[str, object]], module_stem: str, name: str, depth: int = 0):
    if depth > 6 or module_stem not in table or name not in table[module_stem]:
        return None
    kind, *rest = table[module_stem][name]
    if kind == "literal":
        return rest[0]
    if kind == "ref":
        return _resolve_const(table, module_stem, rest[0], depth + 1)
    if kind == "import":
        src_stem, original_name = rest
        return _resolve_const(table, src_stem, original_name, depth + 1)
    return None


_START_WORKFLOW_METHODS = {"start_workflow", "start_child_workflow", "execute_child_workflow"}


def _resolve_tq_node(node, const_table: dict, module_stem: str):
    """A task_queue argument's AST node -> its string value, or None if it can't
    be resolved statically (e.g. an f-string or a runtime-computed expression —
    not this check's job to flag, only genuinely wrong literals/constants)."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.Name):
        return _resolve_const(const_table, module_stem, node.id)
    return None


def _resolve_wf_node(node):
    """A start_workflow call's first argument -> the workflow class/type name,
    handling both `"EmployeeExitWorkflow"` (string) and `SomeWorkflow.run`
    (attribute access on the class) call styles."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
        return node.value.id
    if isinstance(node, ast.Name):
        return node.id
    return None


def _find_forwarding_wrappers(tree) -> dict[str, dict[str, tuple[int, str]]]:
    """Local method name -> {'task_queue': (pos, param_name), 'workflow': (pos, param_name)}
    for whichever of the two a wrapper forwards positionally/by-keyword. Several
    consumers wrap the real Temporal call in their own private helper (_start,
    _start_workflow, ...) — a direct scan of only the outermost call site misses
    both the queue name and the workflow name these forward through a parameter."""
    wrappers: dict[str, dict[str, tuple[int, str]]] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.AsyncFunctionDef):
            continue
        # .args covers positional-or-keyword params; .kwonlyargs covers the
        # keyword-only params after a bare `*` (e.g. ComplianceConsumer._start's
        # `async def _start(self, *, workflow, wf_id, args, task_queue)`).
        params = [a.arg for a in node.args.args if a.arg != "self"]
        params += [a.arg for a in node.args.kwonlyargs]
        for inner in ast.walk(node):
            if not (isinstance(inner, ast.Call) and isinstance(inner.func, ast.Attribute)
                    and inner.func.attr in _START_WORKFLOW_METHODS):
                continue
            found: dict[str, tuple[int, str]] = {}
            tq_kw = next((kw for kw in inner.keywords if kw.arg == "task_queue"), None)
            if tq_kw and isinstance(tq_kw.value, ast.Name) and tq_kw.value.id in params:
                found["task_queue"] = (params.index(tq_kw.value.id), tq_kw.value.id)
            # Workflow name/type is always the first positional arg to
            # start_workflow/start_child_workflow/execute_child_workflow.
            if inner.args and isinstance(inner.args[0], ast.Name) and inner.args[0].id in params:
                found["workflow"] = (params.index(inner.args[0].id), inner.args[0].id)
            if found:
                wrappers[node.name] = found
                break
    return wrappers


def _call_arg_node(call: ast.Call, pos: int, param_name: str):
    if pos < len(call.args):
        return call.args[pos]
    kw = next((k for k in call.keywords if k.arg == param_name), None)
    return kw.value if kw else None


def check_task_queue_wiring():
    workflows_dir = API_ROOT / "workflows"
    consumers_dir = API_ROOT / "kafka" / "consumers"
    worker_file = workflows_dir / "worker.py"
    if not worker_file.exists():
        return

    worker_tree = ast.parse(worker_file.read_text(encoding="utf-8", errors="ignore"), filename=str(worker_file))
    real_queues = _real_queue_names(worker_tree)
    workflow_queues = _workflow_queue_map(worker_tree)
    if not real_queues:
        return

    workflow_files = [f for f in workflows_dir.glob("*.py")]
    consumer_files = [f for f in consumers_dir.glob("*.py")] if consumers_dir.exists() else []
    const_table = _module_const_table(workflow_files, "workflows.")
    # Consumers can reference workflows.* constants too — fold them into the same table
    # under their own stem so in-file ast.Name lookups resolve against local constants.
    const_table.update(_module_const_table(consumer_files, "workflows."))

    for f in workflow_files + consumer_files:
        try:
            tree = ast.parse(f.read_text(encoding="utf-8", errors="ignore"), filename=str(f))
        except SyntaxError:
            continue
        wrappers = _find_forwarding_wrappers(tree)

        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue

            if isinstance(node.func, ast.Attribute) and node.func.attr in _START_WORKFLOW_METHODS:
                tq_kw = next((kw for kw in node.keywords if kw.arg == "task_queue"), None)
                tq_node = tq_kw.value if tq_kw else None
                wf_node = node.args[0] if node.args else None
            elif isinstance(node.func, ast.Attribute) and node.func.attr in wrappers:
                spec = wrappers[node.func.attr]
                tq_node = _call_arg_node(node, *spec["task_queue"]) if "task_queue" in spec else None
                wf_node = _call_arg_node(node, *spec["workflow"]) if "workflow" in spec else None
            else:
                continue

            resolved_queue = _resolve_tq_node(tq_node, const_table, f.stem) if tq_node is not None else None
            resolved_wf = _resolve_wf_node(wf_node) if wf_node is not None else None
            if resolved_queue is None:
                continue

            # WORKFLOW-01: the workflow name itself must correspond to a real
            # @workflow.defn class registered in worker.py's WORKERS map. This is
            # the same failure mode as ACTIVITY-01 one level up — a Kafka consumer
            # can call start_workflow("SomeWorkflow", ...) where "SomeWorkflow" was
            # never defined anywhere (renamed, planned-but-never-built, or a typo).
            # Against a mocked Temporal client in tests this silently "passes";
            # against a real cluster it raises the first time the event fires, or
            # (if task_queue happens to be a real queue) just queues forever with
            # no error anywhere. Found via full-repo AST scan 2026-07-17:
            # "AccountLockWorkflow" (auth_consumer.py, oa_user_consumer.py — real
            # target is PolicyLockWorkflow), "IdentityResolutionWorkflow"
            # (employee_consumer.py — no per-employee equivalent; EMPLOYEE_REJOINED
            # maps to RejoiningWorkflow instead), "ObligationEscalationWorkflow"/
            # "GratuityCalculationWorkflow"/"BonusCalculationWorkflow"
            # (statutory_consumer.py), "TenantOnboardingWorkflow"/
            # "TenantSuspensionWorkflow"/"KekRotationWorkflow" (tenant_consumer.py).
            if resolved_wf and resolved_wf not in workflow_queues:
                fail("WORKFLOW-01", f, node.lineno, resolved_wf,
                     f"'{resolved_wf}' is started via start_workflow(), but no "
                     f"@workflow.defn(name='{resolved_wf}') class is registered in "
                     f"worker.py's WORKERS map. This workflow either doesn't exist, was "
                     f"renamed, or was never wired up — starting it is a silent no-op "
                     f"against a real Temporal cluster (or an immediate failure the "
                     f"first time the triggering event fires).",
                     severity="ERROR")

            expected = workflow_queues.get(resolved_wf) if resolved_wf else None
            if expected is not None:
                # We know exactly which workflow is being started — verify against
                # ITS real registration, not just "any known queue" (a workflow can
                # resolve to a real-sounding queue that isn't the one it's actually
                # registered on, e.g. PolicyLockWorkflow on auth-queue instead of
                # its actual secops-queue — a same-severity silent no-op bug that a
                # weaker "is this any real queue" check would miss).
                if resolved_queue not in expected:
                    fail("QUEUE-01", f, node.lineno, resolved_queue,
                         f"{resolved_wf} is started with task_queue='{resolved_queue}', but "
                         f"worker.py registers {resolved_wf} on "
                         f"{'/'.join(sorted(expected))} — not that queue. The workflow will "
                         f"start but never be picked up by any worker — no error, silent no-op.",
                         severity="ERROR")
            elif resolved_queue not in real_queues:
                fail("QUEUE-01", f, node.lineno, resolved_queue,
                     f"task_queue resolves to '{resolved_queue}', which is not one of worker.py's "
                     f"registered queues ({', '.join(sorted(real_queues))}). The workflow will "
                     f"start but never be picked up by any worker — no error, silent no-op.",
                     severity="ERROR")

check_task_queue_wiring()

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


# ── [IMPORT-01/IMPORT-02] Local imports and instance-method calls must resolve ──
#
# Two real bugs found 2026-07-17, neither caught by any existing rule:
#   - workflows/compliance.py's mark_overdue_obligations did
#     `from db import get_db_connection` — db.py only exports create_pool/get_db
#     (a FastAPI dependency, not usable from a Temporal activity). AttributeError
#     the instant it ran; the only test covering it checked registration by
#     name, never actually called it.
#   - workflows/activities.py's stage02_encrypt called `await kms.decrypt_dek(...)`
#     — KMSService has no such method (the real one is unwrap_dek, and it's
#     synchronous). Every PAN-bearing document upload would have crashed
#     against a real KMSService; no test exercised that branch.
#
# Both are "code that looks finished" bugs — not bare stubs, so ACTIVITY-01 and
# TDD-01 don't fire. This check actually imports the target module (this script
# already runs inside the project's own venv, same as pytest) and verifies with
# a real hasattr() that the referenced name/method truly exists, instead of
# trusting that an import or method call that reads correctly IS correct.
#
# Scoped deliberately to project-local modules only — services.*, workflows.*,
# kafka.*, routers.*, connectors.*, and the bare top-level modules (db, config,
# messages, errors, versioning). Never third-party libraries (boto3, redis,
# asyncpg, httpx, temporalio...): several of them generate attributes
# dynamically at runtime in ways a static hasattr() check can't see correctly,
# and a noisy false-positive-prone rule erodes trust in this whole file faster
# than the bugs it would occasionally catch.

_LOCAL_MODULE_PREFIXES = ("services.", "workflows.", "kafka.", "routers.", "connectors.")
_LOCAL_BARE_MODULES = {"db", "config", "messages", "errors", "versioning"}


def _is_local_module(module_name: str) -> bool:
    return module_name in _LOCAL_BARE_MODULES or module_name.startswith(_LOCAL_MODULE_PREFIXES)


def _try_import(module_name: str):
    try:
        return importlib.import_module(module_name)
    except Exception:
        # Import failure is a real problem, but a different one (syntax error,
        # missing dependency, circular import) — not this rule's job, and
        # raising here would turn every unrelated import bug into a confusing
        # IMPORT-01 false positive. Silently skip; other tooling (pytest
        # collection) already surfaces broken imports loudly.
        return None


def check_local_import_resolution():
    if str(API_ROOT) not in sys.path:
        sys.path.insert(0, str(API_ROOT))

    scan_dirs = [
        API_ROOT / "workflows", API_ROOT / "services", API_ROOT / "kafka" / "consumers",
        API_ROOT / "routers", API_ROOT / "connectors",
    ]
    module_cache: dict[str, object] = {}

    def resolve_module(name: str):
        if name not in module_cache:
            module_cache[name] = _try_import(name)
        return module_cache[name]

    for directory in scan_dirs:
        if not directory.exists():
            continue
        for f in directory.glob("*.py"):
            if f.name == "__init__.py" or "test_" in f.name:
                continue
            try:
                tree = ast.parse(f.read_text(encoding="utf-8", errors="ignore"), filename=str(f))
            except SyntaxError:
                continue

            for func in ast.walk(tree):
                if not isinstance(func, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue

                # import_bindings: local name -> (module_name, real_name_in_module | None for whole-module import)
                import_bindings: dict[str, tuple[str, str | None]] = {}
                # instance_bindings: variable name -> class import binding, for `var = ClassName(...)`
                instance_bindings: dict[str, str] = {}

                for node in ast.walk(func):
                    if isinstance(node, ast.ImportFrom) and node.module and _is_local_module(node.module):
                        for alias in node.names:
                            import_bindings[alias.asname or alias.name] = (node.module, alias.name)
                    elif isinstance(node, ast.Import):
                        for alias in node.names:
                            if _is_local_module(alias.name):
                                import_bindings[alias.asname or alias.name] = (alias.name, None)
                    elif isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
                        callee = node.value.func
                        if (isinstance(callee, ast.Name) and callee.id in import_bindings
                                and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name)):
                            instance_bindings[node.targets[0].id] = callee.id

                # IMPORT-01: `from local_module import name` — name must exist in module.
                for local_name, (module_name, real_name) in import_bindings.items():
                    if real_name is None:
                        continue
                    mod = resolve_module(module_name)
                    if mod is None:
                        continue
                    if not hasattr(mod, real_name):
                        fail("IMPORT-01", f, func.lineno, f"from {module_name} import {real_name}",
                             f"'{real_name}' does not exist in {module_name} — this import will raise "
                             f"ImportError/AttributeError the first time {func.name} actually runs.",
                             severity="ERROR")

                # IMPORT-02: `instance.method()` where instance = LocallyImportedClass(...).
                for node in ast.walk(func):
                    if not (isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name)):
                        continue
                    var_name = node.value.id
                    if var_name not in instance_bindings:
                        continue
                    class_local_name = instance_bindings[var_name]
                    module_name, real_class_name = import_bindings[class_local_name]
                    if real_class_name is None:
                        continue
                    mod = resolve_module(module_name)
                    if mod is None:
                        continue
                    cls = getattr(mod, real_class_name, None)
                    if cls is None or not isinstance(cls, type):
                        continue
                    if not hasattr(cls, node.attr):
                        fail("IMPORT-02", f, node.lineno, f"{var_name}.{node.attr}(...)",
                             f"{real_class_name} (from {module_name}) has no method '{node.attr}' — "
                             f"this call will raise AttributeError the first time {func.name} actually runs.",
                             severity="ERROR")

check_local_import_resolution()


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
