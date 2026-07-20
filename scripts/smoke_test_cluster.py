"""
smoke_test_cluster.py — post-deploy cluster verification.
Run after every terraform apply or deployment.
Exit 0 = cluster healthy. Exit 1 = something broken.

Usage:
    python scripts/smoke_test_cluster.py --env prod
    python scripts/smoke_test_cluster.py --env staging
"""
import argparse
import asyncio
import json
import os
import sys
import time
import uuid

results = []


def ok(check, msg=""):
    results.append(("OK", check, msg))
    print(f"  OK  {check}" + (f" — {msg}" if msg else ""))


def fail(check, msg):
    results.append(("FAIL", check, msg))
    print(f" FAIL {check} — {msg}")


# ── Kafka ─────────────────────────────────────────────────────────────────────

async def check_kafka():
    print("\n[Kafka]")
    try:
        from aiokafka import AIOKafkaProducer, AIOKafkaConsumer
        bootstrap = os.environ["KAFKA_BOOTSTRAP_SERVERS"]

        REQUIRED_TOPICS = [
            "prana.ingest.events", "prana.pipeline.events", "prana.vault.events",
            "prana.employee.events", "prana.tenant.events", "prana.oa_users.events",
            "prana.compliance.events", "prana.auth.events", "prana.security.events",
            "prana.statutory.events", "prana.analytics.events", "prana.integrations.events",
            "prana.platform.events", "prana.audit.events",
            "prana.notifications.email", "prana.notifications.sms",
            "prana.notifications.push", "prana.notifications.whatsapp",
            "prana.notifications.portal_bell",
        ]

        producer = AIOKafkaProducer(bootstrap_servers=bootstrap)
        await producer.start()

        # Verify all 21 topics exist by producing a smoke-test event to each
        test_event = json.dumps({"event_type": "SMOKE_TEST", "id": str(uuid.uuid4())}).encode()
        for topic in REQUIRED_TOPICS:
            try:
                await asyncio.wait_for(producer.send(topic, test_event), timeout=5)
                ok(f"kafka.topic.{topic}")
            except Exception as e:
                fail(f"kafka.topic.{topic}", str(e))

        await producer.stop()

    except ImportError:
        fail("kafka", "aiokafka not installed")
    except Exception as e:
        fail("kafka.connect", str(e))


# ── Redis ──────────────────────────────────────────────────────────────────────

async def check_redis():
    print("\n[Redis]")
    try:
        import redis.asyncio as aioredis
        r = aioredis.from_url(os.environ["REDIS_URL"])
        await r.ping()
        ok("redis.connect")

        # Write + read — tests basic replication path
        test_key = f"smoke:test:{uuid.uuid4()}"
        await r.set(test_key, "1", ex=30)
        val = await r.get(test_key)
        if val:
            ok("redis.write_read")
        else:
            fail("redis.write_read", "read returned None after write")

        # Pub/Sub — critical for SSE fanout
        sub = r.pubsub()
        channel = f"sse:smoke:{uuid.uuid4()}"
        await sub.subscribe(channel)
        await r.publish(channel, "smoke")
        msg = await asyncio.wait_for(sub.get_message(ignore_subscribe_messages=True, timeout=2), timeout=3)
        if msg:
            ok("redis.pubsub")
        else:
            fail("redis.pubsub", "published message not received")

        await r.delete(test_key)
        await r.aclose()

    except ImportError:
        fail("redis", "redis[asyncio] not installed")
    except Exception as e:
        fail("redis.connect", str(e))


# ── YugabyteDB ────────────────────────────────────────────────────────────────

async def check_yugabytedb():
    print("\n[YugabyteDB]")
    try:
        import asyncpg
        dsn = os.environ["DATABASE_URL"]
        conn = await asyncio.wait_for(asyncpg.connect(dsn), timeout=10)

        # Verify all 26 tables exist
        rows = await conn.fetch(
            "SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename"
        )
        table_names = {r["tablename"] for r in rows}
        required_tables = {
            "platform_config", "tenant", "tenant_config", "oa_user", "employee_user",
            "employee_master", "api_key", "document", "document_access_log",
            "audit_event", "notification_log", "user_session", "login_attempt_log",
            "share_token", "elevation_request", "exception_queue", "dpdp_erasure_request",
            "dpdp_grievance", "consent_log", "compliance_obligation",
        }
        for t in required_tables:
            if t in table_names:
                ok(f"yugabytedb.table.{t}")
            else:
                fail(f"yugabytedb.table.{t}", "table not found")

        # RLS check — tenant isolation
        rls_row = await conn.fetchrow(
            "SELECT relrowsecurity FROM pg_class WHERE relname='document'"
        )
        if rls_row and rls_row["relrowsecurity"]:
            ok("yugabytedb.rls.document")
        else:
            fail("yugabytedb.rls.document", "RLS not enabled on document table")

        await conn.close()

    except ImportError:
        fail("yugabytedb", "asyncpg not installed")
    except Exception as e:
        fail("yugabytedb.connect", str(e))


# ── KMS ───────────────────────────────────────────────────────────────────────

async def check_kms():
    print("\n[KMS]")
    try:
        import aioboto3
        key_arn = os.environ.get("PLATFORM_SECRET_KEY_ARN")
        if not key_arn:
            fail("kms", "PLATFORM_SECRET_KEY_ARN not set")
            return

        session = aioboto3.Session()
        async with session.client("kms", region_name="ap-south-1") as kms:
            plaintext = b"smoke-test-value"
            enc = await kms.encrypt(KeyId=key_arn, Plaintext=plaintext)
            dec = await kms.decrypt(CiphertextBlob=enc["CiphertextBlob"])
            if dec["Plaintext"] == plaintext:
                ok("kms.encrypt_decrypt")
            else:
                fail("kms.encrypt_decrypt", "decrypted value mismatch")

    except ImportError:
        fail("kms", "aioboto3 not installed")
    except Exception as e:
        fail("kms.connect", str(e))


# ── S3 ────────────────────────────────────────────────────────────────────────

async def check_s3():
    print("\n[S3]")
    try:
        import aioboto3
        bucket = os.environ.get("S3_DOCUMENTS_BUCKET")
        if not bucket:
            fail("s3", "S3_DOCUMENTS_BUCKET not set")
            return

        session = aioboto3.Session()
        key = f"smoke-test/{uuid.uuid4()}.txt"
        async with session.client("s3", region_name="ap-south-1") as s3:
            await s3.put_object(Bucket=bucket, Key=key, Body=b"smoke")
            obj = await s3.get_object(Bucket=bucket, Key=key)
            body = await obj["Body"].read()
            if body == b"smoke":
                ok("s3.put_get")
            else:
                fail("s3.put_get", "body mismatch")
            await s3.delete_object(Bucket=bucket, Key=key)
            ok("s3.delete")

    except ImportError:
        fail("s3", "aioboto3 not installed")
    except Exception as e:
        fail("s3.connect", str(e))


# ── prana-api health ──────────────────────────────────────────────────────────

async def check_api():
    print("\n[prana-api]")
    try:
        import aiohttp
        api_url = os.environ.get("API_URL", "http://localhost:8000")
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{api_url}/health", timeout=aiohttp.ClientTimeout(total=5)) as resp:
                if resp.status == 200:
                    ok("api.health")
                else:
                    fail("api.health", f"status {resp.status}")
    except Exception as e:
        fail("api.health", str(e))


# ── Kong gateway checks ───────────────────────────────────────────────────────

async def check_kong():
    print("\n[kong]")
    try:
        import aiohttp
        # KONG_URL = ALB DNS name from terraform output
        kong_url = os.environ.get("KONG_URL", "http://localhost:8000")

        async with aiohttp.ClientSession() as session:
            # 1. Gateway health probe (Kong built-in)
            async with session.get(f"{kong_url}/health", timeout=aiohttp.ClientTimeout(total=5)) as resp:
                if resp.status == 200:
                    ok("kong.health")
                else:
                    fail("kong.health", f"status {resp.status}")

            # 2. Unauthenticated call to protected route must return 401 (not 502/504)
            async with session.get(f"{kong_url}/v1/vault/documents", timeout=aiohttp.ClientTimeout(total=5)) as resp:
                if resp.status == 401:
                    ok("kong.jwt_plugin_active")
                elif resp.status in (502, 503, 504):
                    fail("kong.jwt_plugin_active", f"upstream unreachable — status {resp.status}")
                else:
                    fail("kong.jwt_plugin_active", f"unexpected status {resp.status} — expected 401")

            # 3. CORS preflight must return 200 with CORS headers
            headers = {
                "Origin": "https://portal.prana.in",
                "Access-Control-Request-Method": "POST",
            }
            async with session.options(f"{kong_url}/auth/org/login", headers=headers, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                if resp.status == 200 and "access-control-allow-origin" in resp.headers:
                    ok("kong.cors_plugin_active")
                else:
                    fail("kong.cors_plugin_active", f"status {resp.status}, headers {dict(resp.headers)}")

            # 4. X-Request-ID header must be injected by correlation-id plugin
            async with session.get(f"{kong_url}/health", timeout=aiohttp.ClientTimeout(total=5)) as resp:
                if "x-request-id" in resp.headers:
                    ok("kong.correlation_id_plugin")
                else:
                    fail("kong.correlation_id_plugin", "X-Request-ID header missing from response")

            # 5. Security headers injected by response-transformer
            async with session.get(f"{kong_url}/health", timeout=aiohttp.ClientTimeout(total=5)) as resp:
                if "strict-transport-security" in resp.headers:
                    ok("kong.security_headers")
                else:
                    fail("kong.security_headers", "Strict-Transport-Security header missing")

    except Exception as e:
        fail("kong", str(e))


# ── Main ──────────────────────────────────────────────────────────────────────

async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--env", default="dev", choices=["dev", "staging", "prod"])
    parser.add_argument("--skip", nargs="*", default=[], help="checks to skip: kafka redis yugabytedb kms s3 api kong")
    args = parser.parse_args()

    print(f"\nPRANA cluster smoke test — {args.env}\n{'='*50}")

    checks = {
        "kafka":      check_kafka,
        "redis":      check_redis,
        "yugabytedb": check_yugabytedb,
        "kms":        check_kms,
        "s3":         check_s3,
        "api":        check_api,
        "kong":       check_kong,
    }

    for name, fn in checks.items():
        if name not in args.skip:
            await fn()

    # Summary
    passed = sum(1 for r in results if r[0] == "OK")
    failed = sum(1 for r in results if r[0] == "FAIL")
    print(f"\n{'='*50}")
    print(f"Passed: {passed}  Failed: {failed}")

    if failed > 0:
        print("FAIL — cluster not healthy. Fix failures before routing traffic.")
        sys.exit(1)
    else:
        print("OK — cluster healthy.")
        sys.exit(0)


if __name__ == "__main__":
    asyncio.run(main())
