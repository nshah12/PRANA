"""
Pre-production API compatibility check.
Run in CI before every deployment: python scripts/check_api_compat.py

Catches:
  1. Code calling deprecated endpoint paths
  2. Code calling sunset endpoint paths (will get 410 in prod)
  3. v1 router files that have breaking changes (field removals/renames)
  4. Deprecated endpoints where sunset_on has passed (must be removed)
  5. Missing migration_guide or notify_sent on deprecated endpoints

Exit code 0 = clean. Exit code 1 = issues found, block deployment.
"""
import ast
import sys
import re
from pathlib import Path
from datetime import date

# Add parent to path so we can import versioning
sys.path.insert(0, str(Path(__file__).parent.parent))
from versioning import VERSION_REGISTRY, DEPRECATED_ENDPOINTS, BREAKING_CHANGES

ROOT = Path(__file__).parent.parent
ISSUES: list[str] = []
WARNINGS: list[str] = []


def error(msg: str):
    ISSUES.append(f"  ERROR: {msg}")


def warn(msg: str):
    WARNINGS.append(f"  WARN:  {msg}")


# ── Check 1: sunset endpoints past their date ──────────────────────────────────
def check_sunset_dates():
    today = date.today()
    for path, info in DEPRECATED_ENDPOINTS.items():
        sunset = info.get("sunset_on")
        if sunset and today >= sunset:
            error(
                f"Endpoint {path} sunset date {sunset} has PASSED. "
                f"Remove from router and update VERSION_REGISTRY."
            )
    for version, info in VERSION_REGISTRY.items():
        sunset = info.get("sunset_on")
        if sunset and today >= sunset and info.get("status") != "sunset":
            error(
                f"Version {version} sunset date {sunset} has passed but status is still "
                f"'{info['status']}'. Update VERSION_REGISTRY status to 'sunset'."
            )


# ── Check 2: deprecated endpoints missing required fields ─────────────────────
def check_deprecation_completeness():
    for path, info in DEPRECATED_ENDPOINTS.items():
        if not info.get("successor"):
            error(f"Deprecated endpoint {path} has no 'successor' defined.")
        if not info.get("migration_guide"):
            warn(f"Deprecated endpoint {path} has no 'migration_guide' URL.")
        if not info.get("notify_sent"):
            error(
                f"Deprecated endpoint {path} has notify_sent=False. "
                f"Partner notification email must be sent before deprecation is active."
            )
        deprecated_on = info.get("deprecated_on")
        sunset_on = info.get("sunset_on")
        if deprecated_on and sunset_on:
            delta = (sunset_on - deprecated_on).days
            if delta < 90:
                error(
                    f"Endpoint {path}: sunset_on is only {delta} days after deprecated_on. "
                    f"Minimum 90 days required for HRMS partner migration."
                )


# ── Check 3: source code calling deprecated or sunset paths ───────────────────
def check_deprecated_calls_in_source():
    deprecated_paths = set(DEPRECATED_ENDPOINTS.keys())
    sunset_versions = {v for v, info in VERSION_REGISTRY.items() if info.get("status") == "sunset"}

    scan_dirs = [ROOT / "routers", ROOT / "services", ROOT / "kafka"]
    # Also scan portal frontend
    portal_src = ROOT.parent / "prana-portal" / "src"
    mobile_src = ROOT.parent / "prana-mobile" / "src"

    for scan_root in [*scan_dirs, portal_src, mobile_src]:
        if not scan_root.exists():
            continue
        extensions = ["*.py", "*.ts", "*.tsx"]
        for ext in extensions:
            for f in scan_root.rglob(ext):
                text = f.read_text(encoding="utf-8", errors="ignore")
                for dep_path in deprecated_paths:
                    if dep_path in text:
                        warn(
                            f"{f.relative_to(ROOT.parent)} references deprecated endpoint "
                            f"'{dep_path}'. Migrate to: {DEPRECATED_ENDPOINTS[dep_path].get('successor')}"
                        )
                for sv in sunset_versions:
                    pattern = f"/{sv}/"
                    if pattern in text:
                        error(
                            f"{f.relative_to(ROOT.parent)} references SUNSET version "
                            f"'{sv}'. These calls will return 410 in production."
                        )


# ── Check 4: v1 router files must not have field removals ─────────────────────
def check_v1_router_safety():
    """
    Heuristic: scan git diff for removals of response field names in v1 routers.
    Flags any line removed (-) from v1 router files that looks like a dict key.
    Run after `git diff HEAD~1` is available.
    """
    import subprocess
    try:
        result = subprocess.run(
            ["git", "diff", "HEAD~1", "--", "routers/*.py"],
            capture_output=True, cwd=ROOT
        )
        diff = result.stdout.decode("utf-8", errors="replace") if result.stdout else ""
    except Exception:
        warn("Could not run git diff — skipping v1 breaking change check.")
        return

    v1_router_pattern = re.compile(r'^\-.*"(\w+)"\s*:', re.MULTILINE)
    removed_fields = v1_router_pattern.findall(diff)

    known_safe_removals = {"debug", "temp", "internal"}
    for field in removed_fields:
        if field not in known_safe_removals:
            warn(
                f"Field '{field}' was removed from a v1 router response. "
                f"If this is a breaking change, it must go into v2, not v1. "
                f"Verify this is an additive-only change."
            )


# ── Check 5: breaking changes documented ─────────────────────────────────────
def check_breaking_changes_documented():
    changelog = ROOT.parent / "prana-docs" / "API_CHANGELOG.md"
    if not changelog.exists():
        error("prana-docs/API_CHANGELOG.md does not exist. Create it before shipping.")
        return
    content = changelog.read_text()
    for change in BREAKING_CHANGES:
        marker = change.get("endpoint", "")
        if marker and marker not in content:
            error(
                f"Breaking change for {marker} (version {change['version']}) "
                f"is in versioning.py but NOT documented in API_CHANGELOG.md."
            )


# ── Run all checks ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("PRANA API Compatibility Check")
    print("=" * 50)

    check_sunset_dates()
    check_deprecation_completeness()
    check_deprecated_calls_in_source()
    check_v1_router_safety()
    check_breaking_changes_documented()

    if WARNINGS:
        print("\nWARNINGS (review before shipping):")
        for w in WARNINGS:
            print(w)

    if ISSUES:
        print("\nERRORS (block deployment):")
        for issue in ISSUES:
            print(issue)
        print(f"\n{len(ISSUES)} error(s) found. Deployment blocked.")
        sys.exit(1)
    else:
        print(f"\n[OK] All checks passed. {len(WARNINGS)} warning(s).")
        sys.exit(0)
