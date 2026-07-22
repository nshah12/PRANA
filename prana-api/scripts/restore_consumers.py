"""
Restore __init__ and run() methods in broken consumer files.
The _dispatch() and handler methods below those are still intact.

For each broken file:
- __init__ currently has: self._pool/etc attrs, THEN the run() body (await start, try/finally)
- run() method is missing entirely
- _dispatch() and helpers below are intact

Fix:
- Remove run() body from __init__
- Add AIOKafkaConsumer(...) to __init__
- Re-insert run() as a proper method before _dispatch
"""
import re
from pathlib import Path

CONSUMERS_DIR = Path(__file__).parent.parent / "kafka" / "consumers"

# Map: file stem -> (topic, group_id)
TOPIC_MAP = {
    "auth_consumer":               ("prana.auth.events",                "prana-auth-consumer"),
    "bell_consumer":               ("prana.notifications.portal_bell",  "prana-bell-consumer"),
    "cache_invalidation_consumer": ("prana.cache.events",               "prana-cache-invalidation-consumer"),
    "compliance_consumer":         ("prana.compliance.events",          "prana-compliance-consumer"),
    "email_consumer":              ("prana.notifications.email",        "prana-email-consumer"),
    "employee_consumer":           ("prana.employee.events",            "prana-employee-consumer"),
    "integration_consumer":        ("prana.integrations.events",        "prana-integration-consumer"),
    "oa_user_consumer":            ("prana.oa_users.events",            "prana-oa-user-consumer"),
    "platform_consumer":           ("prana.platform.events",            "prana-platform-consumer"),
    "push_consumer":               ("prana.notifications.push",         "prana-push-consumer"),
    "security_consumer":           ("prana.security.events",            "prana-security-consumer"),
    "sms_consumer":                ("prana.notifications.sms",          "prana-sms-consumer"),
    "statutory_consumer":          ("prana.statutory.events",           "prana-statutory-consumer"),
    "tenant_consumer":             ("prana.tenant.events",              "prana-tenant-consumer"),
    "whatsapp_consumer":           ("prana.notifications.whatsapp",     "prana-whatsapp-consumer"),
}

# The run() body block that got incorrectly placed in __init__
RUN_BODY_START = "        await self._consumer.start()"

for f in sorted(CONSUMERS_DIR.glob("*.py")):
    stem = f.stem
    if stem not in TOPIC_MAP:
        print(f"SKIP (not in map): {f.name}")
        continue

    src = f.read_text(encoding="utf-8")

    # Check if the run() body is inside __init__ (the breakage marker)
    # We look for the run() body starting inside the __init__ body
    if RUN_BODY_START not in src:
        print(f"SKIP (run body not in __init__): {f.name}")
        continue

    topic, group_id = TOPIC_MAP[stem]

    # Find what's stored in __init__ (self._pool, self._temporal, self._redis, etc.)
    # by reading everything between the def __init__ line and "await self._consumer.start()"
    init_match = re.search(
        r'(    def __init__\(self[^)]*\)[^:]*:\n)(.*?)(?=        await self\._consumer\.start\(\))',
        src, re.DOTALL
    )
    if not init_match:
        print(f"SKIP (init structure not found): {f.name}")
        continue

    init_sig = init_match.group(1)          # e.g. "    def __init__(self, settings: Settings, ...) -> None:\n"
    init_attrs = init_match.group(2)        # e.g. "        self._pool = db_pool\n        self._temporal = temporal_client\n"

    # Find the log message in run() to infer the consumer class name
    # Pattern: log.info("<ClassName> started")
    log_match = re.search(r'log\.info\("(\w+) started"\)', src)
    consumer_name = log_match.group(1) if log_match else f.stem.replace("_", " ").title().replace(" ", "")

    # Find the exception log message pattern
    exc_log_match = re.search(r'log\.exception\("(\w+) error event_type=%s"', src)
    exc_consumer_name = exc_log_match.group(1) if exc_log_match else consumer_name

    # Find what comes after the try/finally block (the _dispatch method and everything after)
    # The try/finally ends with "await self._consumer.stop()"
    stop_idx = src.find("        await self._consumer.stop()")
    if stop_idx == -1:
        print(f"SKIP (no consumer.stop found): {f.name}")
        continue

    # Everything after the stop line + newline + newline is the remaining methods
    after_stop = src[stop_idx + len("        await self._consumer.stop()"):]
    # Skip trailing newlines of the try/finally
    remaining_methods = after_stop.lstrip('\n')

    # Build the fixed file
    # 1. Keep everything up to the class body's __init__ signature
    pre_class_idx = src.find(init_sig)
    header = src[:pre_class_idx]

    # 2. Build proper __init__
    # Extract the GROUP_ID variable name from the source
    gid_varname = "GROUP_ID"  # always GROUP_ID in these files
    init_body = f"""{init_sig}{init_attrs}        self._consumer = AIOKafkaConsumer(
            "{topic}",
            bootstrap_servers=settings.kafka_bootstrap_servers,
            group_id={gid_varname},
            auto_offset_reset="earliest",
            enable_auto_commit=True,
            value_deserializer=lambda b: json.loads(b),
        )
"""

    # 3. Build proper run()
    run_body = f"""
    async def run(self) -> None:
        await self._consumer.start()
        log.info("{consumer_name} started")
        try:
            async for msg in self._consumer:
                event = msg.value
                etype = event.get("event_type")
                try:
                    await self._dispatch(etype, event)
                except Exception:
                    log.exception("{exc_consumer_name} error event_type=%s", etype)
        finally:
            await self._consumer.stop()

"""

    # 4. Assemble
    new_src = header + init_body + run_body + remaining_methods

    f.write_text(new_src, encoding="utf-8")
    print(f"FIXED: {f.name}")

print("Done.")
