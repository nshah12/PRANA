"""
Tests for routers/pa_admin_comms.py — communications & policy config.
Split 2026-08-10 out of test_pa_admin.py (see that file's docstring). Covers:
contact inquiries/org applications, severity/SLA policy, Communication Hub
settings (channel policy/vendor chains/vendor credentials), platform
credentials, HMAC rotation approval.
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

AUTH_HEADER = {"Authorization": "Bearer test.mock.token"}


def _set_pa_auth(client, pa_id: str = "pa-uuid-001") -> None:
    jwt = client.app.state.jwt_service
    jwt.decode = MagicMock(return_value={
        "sub": pa_id,
        "user_type": "portal_admin",
        "role": "portal_admin",
        "tenant_id": None,     # PA has no tenant affiliation
        "jti": "pa-session-001",
    })
    jwt.is_revoked = AsyncMock(return_value=False)


def _set_oa_auth(client) -> None:
    jwt = client.app.state.jwt_service
    jwt.decode = MagicMock(return_value={
        "sub": "oa-uuid-001",
        "user_type": "oa_user",
        "role": "oa_admin",
        "tenant_id": "tenant-001",
        "jti": "oa-session-001",
    })
    jwt.is_revoked = AsyncMock(return_value=False)

# ── Contact inquiries / org applications (relocated from routers/public.py) ──

@pytest.mark.asyncio
async def test_list_contact_inquiries_requires_pa_auth(client):
    resp = await client.get("/admin/contact-inquiries")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_list_contact_inquiries_rejects_oa_admin(client):
    _set_oa_auth(client)
    resp = await client.get("/admin/contact-inquiries", headers=AUTH_HEADER)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_list_contact_inquiries_returns_items(client, mock_db):
    import datetime
    _set_pa_auth(client)
    mock_db.fetch.return_value = [{
        "id": "ci-1", "name": "Priya", "email": "priya@example.com", "org": "Acme",
        "enquiry_type": "General", "message": "Hi", "status": "NEW",
        "submitted_at": datetime.datetime(2026, 7, 1, tzinfo=datetime.timezone.utc),
    }]
    mock_db.fetchval.return_value = 1

    resp = await client.get("/admin/contact-inquiries", headers=AUTH_HEADER)

    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["email"] == "priya@example.com"


@pytest.mark.asyncio
async def test_list_org_applications_requires_pa_auth(client):
    resp = await client.get("/admin/org-applications")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_list_org_applications_returns_items(client, mock_db):
    import datetime
    _set_pa_auth(client)
    mock_db.fetch.return_value = [{
        "id": "app-1", "org_name": "Acme", "domain": "acme.in", "entity_type": "PVT_LTD",
        "industry": "IT", "headcount_band": "50-100", "contact_name": "Priya",
        "contact_email": "priya@acme.in", "contact_mobile": "+919000000001",
        "message": "", "how_heard": "Google", "agreed_to_dpa": True, "email_verified": True,
        "status": "PENDING", "review_notes": None,
        "submitted_at": datetime.datetime(2026, 7, 1, tzinfo=datetime.timezone.utc),
        "reviewed_at": None,
    }]
    mock_db.fetchval.return_value = 1

    resp = await client.get("/admin/org-applications", headers=AUTH_HEADER)

    assert resp.status_code == 200
    assert resp.json()["items"][0]["org_name"] == "Acme"


@pytest.mark.asyncio
async def test_review_application_requires_pa_auth(client):
    resp = await client.patch("/admin/org-applications/app-1", json={"status": "APPROVED"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_review_application_updates_status(client, mock_db):
    _set_pa_auth(client)
    mock_db.execute = AsyncMock(return_value=None)

    resp = await client.patch(
        "/admin/org-applications/app-1",
        headers=AUTH_HEADER,
        json={"status": "APPROVED", "review_notes": "Looks good"},
    )

    assert resp.status_code == 200
    assert resp.json()["status"] == "APPROVED"
    mock_db.execute.assert_awaited_once()
    args = mock_db.execute.call_args.args
    assert args[1] == "APPROVED"
    assert args[2] == "Looks good"
    assert args[3] == "app-1"


# ── Severity / SLA policy config ─────────────────────────────────────────────

SLA_SVC = "services.severity_policy_service.SeverityPolicyService"


@pytest.mark.asyncio
async def test_list_sla_policy_requires_portal_admin_role(client, mock_db):
    _set_oa_auth(client)
    resp = await client.get("/admin/sla-policy", headers=AUTH_HEADER)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_list_sla_policy_returns_items(client, mock_db):
    _set_pa_auth(client)
    with patch(f"{SLA_SVC}.get_all_sla_policies", new_callable=AsyncMock) as mock_list:
        mock_list.return_value = [{"severity": "P0", "sla_minutes": 30, "auto_create_incident": True,
                                    "description": None, "updated_by": None, "updated_at": None}]
        resp = await client.get("/admin/sla-policy", headers=AUTH_HEADER)

    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["severity"] == "P0"


@pytest.mark.asyncio
async def test_update_sla_policy_calls_service_with_current_user(client, mock_db):
    _set_pa_auth(client, pa_id="pa-uuid-777")
    with patch(f"{SLA_SVC}.update_sla_policy", new_callable=AsyncMock) as mock_update, \
         patch("kafka.producer.get_kafka_producer", new=AsyncMock(return_value=AsyncMock())):
        mock_update.return_value = {"severity": "P1", "sla_minutes": 90,
                                     "auto_create_incident": True, "description": "x",
                                     "updated_by": "pa-uuid-777", "updated_at": None}
        resp = await client.patch(
            "/admin/sla-policy/P1", headers=AUTH_HEADER,
            json={"sla_minutes": 90, "auto_create_incident": True},
        )

    assert resp.status_code == 200
    assert resp.json()["message"] == "SLA_POLICY_UPDATED"
    assert resp.json()["sla_policy"]["sla_minutes"] == 90
    mock_update.assert_awaited_once_with(
        severity="P1", sla_minutes=90, auto_create_incident=True,
        description=None, updated_by="pa-uuid-777",
    )


@pytest.mark.asyncio
async def test_update_sla_policy_publishes_immudb_audited_tenant_event(client, mock_db):
    """Retrofit: sla-policy previously wrote no audit event at all — only
    updated_by/updated_at columns, not tamper-evident. See
    prana-docs/COMMUNICATION_HUB_ARCHITECTURE.md §10.3."""
    _set_pa_auth(client, pa_id="pa-uuid-777")
    mock_kafka = AsyncMock()
    with patch(f"{SLA_SVC}.update_sla_policy", new_callable=AsyncMock) as mock_update, \
         patch("kafka.producer.get_kafka_producer", new=AsyncMock(return_value=mock_kafka)):
        mock_update.return_value = {"severity": "P1", "sla_minutes": 90,
                                     "auto_create_incident": True, "description": "x",
                                     "updated_by": "pa-uuid-777", "updated_at": None}
        await client.patch(
            "/admin/sla-policy/P1", headers=AUTH_HEADER,
            json={"sla_minutes": 90, "auto_create_incident": True},
        )

    mock_kafka.tenant_event.assert_awaited_once()
    event = mock_kafka.tenant_event.call_args.args[0]
    assert event["event_type"] == "SLA_POLICY_UPDATED"
    assert event["tenant_id"] is None
    assert event["severity"] == "P1"
    assert event["actor_id"] == "pa-uuid-777"


@pytest.mark.asyncio
async def test_update_sla_policy_unknown_severity_returns_404(client, mock_db):
    _set_pa_auth(client)
    with patch(f"{SLA_SVC}.update_sla_policy", new_callable=AsyncMock,
               side_effect=ValueError("No SLA policy for severity P9")):
        resp = await client.patch(
            "/admin/sla-policy/P9", headers=AUTH_HEADER, json={"sla_minutes": 10},
        )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_list_severity_rules_requires_portal_admin_role(client, mock_db):
    _set_oa_auth(client)
    resp = await client.get("/admin/severity-rules", headers=AUTH_HEADER)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_list_severity_rules_filters_by_domain_query_param(client, mock_db):
    _set_pa_auth(client)
    with patch(f"{SLA_SVC}.list_severity_rules", new_callable=AsyncMock) as mock_list:
        mock_list.return_value = []
        resp = await client.get("/admin/severity-rules?domain=ANOMALY_RULE", headers=AUTH_HEADER)

    assert resp.status_code == 200
    mock_list.assert_awaited_once_with(domain="ANOMALY_RULE")


@pytest.mark.asyncio
async def test_create_severity_rule_calls_service_with_current_user(client, mock_db):
    _set_pa_auth(client, pa_id="pa-uuid-777")
    with patch(f"{SLA_SVC}.create_severity_rule", new_callable=AsyncMock) as mock_create, \
         patch("kafka.producer.get_kafka_producer", new=AsyncMock(return_value=AsyncMock())):
        mock_create.return_value = {"rule_id": "r-1", "domain": "ANOMALY_RULE", "match_type": "EXACT",
                                     "match_value": "NEW_RULE", "occurrence_threshold": 5,
                                     "occurrence_threshold_max": None, "window_minutes": 15,
                                     "severity": "P2", "priority": 50, "is_active": True,
                                     "description": None, "updated_by": "pa-uuid-777", "updated_at": None}
        resp = await client.post(
            "/admin/severity-rules", headers=AUTH_HEADER,
            json={"domain": "ANOMALY_RULE", "match_type": "EXACT", "match_value": "NEW_RULE",
                  "occurrence_threshold": 5, "window_minutes": 15, "severity": "P2", "priority": 50},
        )

    assert resp.status_code == 201
    assert resp.json()["message"] == "SEVERITY_RULE_CREATED"
    mock_create.assert_awaited_once_with(
        domain="ANOMALY_RULE", match_type="EXACT", match_value="NEW_RULE",
        occurrence_threshold=5, occurrence_threshold_max=None, window_minutes=15,
        severity="P2", priority=50, description=None, updated_by="pa-uuid-777",
    )


@pytest.mark.asyncio
async def test_create_severity_rule_publishes_immudb_audited_tenant_event(client, mock_db):
    _set_pa_auth(client, pa_id="pa-uuid-777")
    mock_kafka = AsyncMock()
    with patch(f"{SLA_SVC}.create_severity_rule", new_callable=AsyncMock) as mock_create, \
         patch("kafka.producer.get_kafka_producer", new=AsyncMock(return_value=mock_kafka)):
        mock_create.return_value = {"rule_id": "r-1", "domain": "ANOMALY_RULE", "match_type": "EXACT",
                                     "match_value": "NEW_RULE", "occurrence_threshold": 5,
                                     "occurrence_threshold_max": None, "window_minutes": 15,
                                     "severity": "P2", "priority": 50, "is_active": True,
                                     "description": None, "updated_by": "pa-uuid-777", "updated_at": None}
        await client.post(
            "/admin/severity-rules", headers=AUTH_HEADER,
            json={"domain": "ANOMALY_RULE", "match_type": "EXACT", "match_value": "NEW_RULE",
                  "occurrence_threshold": 5, "window_minutes": 15, "severity": "P2", "priority": 50},
        )

    mock_kafka.tenant_event.assert_awaited_once()
    event = mock_kafka.tenant_event.call_args.args[0]
    assert event["event_type"] == "SEVERITY_RULE_CREATED"
    assert event["rule_id"] == "r-1"
    assert event["actor_id"] == "pa-uuid-777"


@pytest.mark.asyncio
async def test_create_severity_rule_invalid_match_type_returns_422(client, mock_db):
    _set_pa_auth(client)
    with patch(f"{SLA_SVC}.create_severity_rule", new_callable=AsyncMock,
               side_effect=ValueError("match_type must be PREFIX, EXACT, or DEFAULT")):
        resp = await client.post(
            "/admin/severity-rules", headers=AUTH_HEADER,
            json={"domain": "ANOMALY_RULE", "match_type": "FUZZY", "severity": "P2"},
        )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_update_severity_rule_calls_service_with_current_user(client, mock_db):
    _set_pa_auth(client, pa_id="pa-uuid-777")
    with patch(f"{SLA_SVC}.update_severity_rule", new_callable=AsyncMock) as mock_update, \
         patch("kafka.producer.get_kafka_producer", new=AsyncMock(return_value=AsyncMock())):
        mock_update.return_value = {"rule_id": "r-1", "domain": "ANOMALY_RULE", "match_type": "EXACT",
                                     "match_value": "BULK_DOC_ACCESS", "occurrence_threshold": 75,
                                     "occurrence_threshold_max": None, "window_minutes": 10,
                                     "severity": "P1", "priority": 10, "is_active": False,
                                     "description": None, "updated_by": "pa-uuid-777", "updated_at": None}
        resp = await client.patch(
            "/admin/severity-rules/r-1", headers=AUTH_HEADER,
            json={"occurrence_threshold": 75, "is_active": False},
        )

    assert resp.status_code == 200
    assert resp.json()["message"] == "SEVERITY_RULE_UPDATED"
    assert resp.json()["severity_rule"]["is_active"] is False
    mock_update.assert_awaited_once_with(
        rule_id="r-1", occurrence_threshold=75, occurrence_threshold_max=None,
        window_minutes=None, severity=None, priority=None, is_active=False,
        description=None, updated_by="pa-uuid-777",
    )


@pytest.mark.asyncio
async def test_update_severity_rule_publishes_immudb_audited_tenant_event(client, mock_db):
    _set_pa_auth(client, pa_id="pa-uuid-777")
    mock_kafka = AsyncMock()
    with patch(f"{SLA_SVC}.update_severity_rule", new_callable=AsyncMock) as mock_update, \
         patch("kafka.producer.get_kafka_producer", new=AsyncMock(return_value=mock_kafka)):
        mock_update.return_value = {"rule_id": "r-1", "domain": "ANOMALY_RULE", "match_type": "EXACT",
                                     "match_value": "BULK_DOC_ACCESS", "occurrence_threshold": 75,
                                     "occurrence_threshold_max": None, "window_minutes": 10,
                                     "severity": "P1", "priority": 10, "is_active": False,
                                     "description": None, "updated_by": "pa-uuid-777", "updated_at": None}
        await client.patch(
            "/admin/severity-rules/r-1", headers=AUTH_HEADER,
            json={"occurrence_threshold": 75, "is_active": False},
        )

    mock_kafka.tenant_event.assert_awaited_once()
    event = mock_kafka.tenant_event.call_args.args[0]
    assert event["event_type"] == "SEVERITY_RULE_UPDATED"
    assert event["rule_id"] == "r-1"
    assert event["actor_id"] == "pa-uuid-777"


@pytest.mark.asyncio
async def test_update_severity_rule_unknown_id_returns_404(client, mock_db):
    _set_pa_auth(client)
    with patch(f"{SLA_SVC}.update_severity_rule", new_callable=AsyncMock,
               side_effect=ValueError("Rule r-9 not found")):
        resp = await client.patch(
            "/admin/severity-rules/r-9", headers=AUTH_HEADER, json={"priority": 5},
        )
    assert resp.status_code == 404


# ── Communication Hub settings — Channel Policy / Vendor Chains / Credentials ─
# prana-docs/COMMUNICATION_HUB_ARCHITECTURE.md §8.1

COMM_SVC = "services.communication_settings_service.CommunicationSettingsService"


@pytest.mark.asyncio
async def test_get_channel_policy_requires_portal_admin_role(client, mock_db):
    _set_oa_auth(client)
    resp = await client.get("/admin/communications/channel-policy", headers=AUTH_HEADER)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_get_channel_policy_returns_items(client, mock_db):
    _set_pa_auth(client)
    with patch(f"{COMM_SVC}.get_channel_policy", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = [
            {"template_id": "OA_WELCOME", "channels": ["email"], "platform_channels": ["email"],
             "is_tenant_override": False},
        ]
        resp = await client.get("/admin/communications/channel-policy", headers=AUTH_HEADER)

    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["template_id"] == "OA_WELCOME"
    mock_get.assert_awaited_once_with(tenant_id=None)


@pytest.mark.asyncio
async def test_update_channel_policy_calls_service_with_current_user(client, mock_db):
    _set_pa_auth(client, pa_id="pa-uuid-777")
    with patch(f"{COMM_SVC}.update_channel_policy", new_callable=AsyncMock) as mock_update:
        mock_update.return_value = {"template_id": "OA_WELCOME", "channels": ["email"], "tenant_id": None}
        resp = await client.patch(
            "/admin/communications/channel-policy/OA_WELCOME", headers=AUTH_HEADER,
            json={"channels": ["email"]},
        )

    assert resp.status_code == 200
    assert resp.json()["message"] == "COMM_CHANNEL_POLICY_UPDATED"
    mock_update.assert_awaited_once_with(
        template_id="OA_WELCOME", channels=["email"], tenant_id=None, updated_by="pa-uuid-777",
    )


@pytest.mark.asyncio
async def test_update_channel_policy_invalid_channels_returns_422(client, mock_db):
    _set_pa_auth(client)
    with patch(f"{COMM_SVC}.update_channel_policy", new_callable=AsyncMock,
               side_effect=ValueError("INVALID_CHANNELS: ['carrier_pigeon']")):
        resp = await client.patch(
            "/admin/communications/channel-policy/OA_WELCOME", headers=AUTH_HEADER,
            json={"channels": ["carrier_pigeon"]},
        )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_get_vendor_chains_requires_portal_admin_role(client, mock_db):
    _set_oa_auth(client)
    resp = await client.get("/admin/communications/vendor-chains", headers=AUTH_HEADER)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_get_vendor_chains_returns_items(client, mock_db):
    _set_pa_auth(client)
    with patch(f"{COMM_SVC}.get_vendor_chains", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = {"email": {"chain": ["ses"], "available_vendors": ["ses", "smtp"]}}
        resp = await client.get("/admin/communications/vendor-chains", headers=AUTH_HEADER)

    assert resp.status_code == 200
    assert resp.json()["chains"]["email"]["chain"] == ["ses"]
    mock_get.assert_awaited_once_with(tenant_id=None)


@pytest.mark.asyncio
async def test_update_vendor_chain_calls_service_with_current_user(client, mock_db):
    _set_pa_auth(client, pa_id="pa-uuid-777")
    with patch(f"{COMM_SVC}.update_vendor_chain", new_callable=AsyncMock) as mock_update:
        mock_update.return_value = {"channel": "sms", "chain": ["msg91", "aws"], "tenant_id": None}
        resp = await client.patch(
            "/admin/communications/vendor-chains/sms", headers=AUTH_HEADER,
            json={"vendors": ["msg91", "aws"]},
        )

    assert resp.status_code == 200
    assert resp.json()["message"] == "COMM_VENDOR_CHAIN_UPDATED"
    mock_update.assert_awaited_once_with(
        channel="sms", vendors=["msg91", "aws"], tenant_id=None, updated_by="pa-uuid-777",
    )


@pytest.mark.asyncio
async def test_update_vendor_chain_unknown_channel_returns_422(client, mock_db):
    _set_pa_auth(client)
    with patch(f"{COMM_SVC}.update_vendor_chain", new_callable=AsyncMock,
               side_effect=ValueError("UNKNOWN_CHANNEL: carrier_pigeon")):
        resp = await client.patch(
            "/admin/communications/vendor-chains/carrier_pigeon", headers=AUTH_HEADER,
            json={"vendors": ["x"]},
        )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_get_vendor_credentials_requires_portal_admin_role(client, mock_db):
    _set_oa_auth(client)
    resp = await client.get("/admin/communications/vendor-credentials", headers=AUTH_HEADER)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_get_vendor_credentials_never_leaks_secrets(client, mock_db):
    """editable_fields lists field NAMES (safe — needed by the frontend to
    render inputs); the guarantee under test is that the response schema has
    no slot for a raw secret VALUE — vendors carries only booleans/enums,
    and the DB row's enc_value column is never selected by this query."""
    _set_pa_auth(client)
    mock_db.fetch.return_value = [{"vendor": "exotel", "field_name": "exotel_api_key"}]
    resp = await client.get("/admin/communications/vendor-credentials", headers=AUTH_HEADER)
    assert resp.status_code == 200
    data = resp.json()
    assert data["vendors"]["exotel"] == {"configured": True, "source": "db"}
    assert "exotel_api_key" in data["editable_fields"]["exotel"]
    fetch_sql = mock_db.fetch.call_args.args[0]
    assert "enc_value" not in fetch_sql


@pytest.mark.asyncio
async def test_update_vendor_credential_requires_portal_admin_role(client, mock_db):
    _set_oa_auth(client)
    resp = await client.patch(
        "/admin/communications/vendor-credentials/exotel", headers=AUTH_HEADER,
        json={"field_name": "exotel_api_key", "value": "real-secret"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_update_vendor_credential_calls_service_with_current_user(client, mock_db):
    _set_pa_auth(client, pa_id="pa-uuid-777")
    with patch(f"{COMM_SVC}.set_vendor_credential", new_callable=AsyncMock) as mock_set:
        resp = await client.patch(
            "/admin/communications/vendor-credentials/exotel", headers=AUTH_HEADER,
            json={"field_name": "exotel_api_key", "value": "real-secret-value"},
        )

    assert resp.status_code == 200
    assert resp.json()["message"] == "COMM_VENDOR_CREDENTIAL_ROTATED"
    assert "real-secret-value" not in resp.text
    mock_set.assert_awaited_once()
    call_kwargs = mock_set.call_args.kwargs
    assert call_kwargs["vendor"] == "exotel"
    assert call_kwargs["field_name"] == "exotel_api_key"
    assert call_kwargs["value"] == "real-secret-value"
    assert call_kwargs["updated_by"] == "pa-uuid-777"


@pytest.mark.asyncio
async def test_update_vendor_credential_unknown_field_returns_422(client, mock_db):
    _set_pa_auth(client)
    with patch(f"{COMM_SVC}.set_vendor_credential", new_callable=AsyncMock,
               side_effect=ValueError("UNKNOWN_FIELD: not_a_real_field for vendor exotel")):
        resp = await client.patch(
            "/admin/communications/vendor-credentials/exotel", headers=AUTH_HEADER,
            json={"field_name": "not_a_real_field", "value": "x"},
        )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_no_vendor_credentials_route_for_oa_admin_patch(client, mock_db):
    """OA-Admin never edits vendor secrets — no such route exists on org_settings.py."""
    _set_oa_auth(client)
    resp = await client.patch(
        "/v1/org/communications/vendor-credentials/exotel", headers=AUTH_HEADER,
        json={"field_name": "exotel_api_key", "value": "x"},
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Platform credentials — non-communication paid services (Qdrant, etc.)
# ---------------------------------------------------------------------------

PLATFORM_CRED_SVC = "services.platform_credential_service.PlatformCredentialService"


@pytest.mark.asyncio
async def test_get_platform_credentials_requires_portal_admin_role(client, mock_db):
    _set_oa_auth(client)
    resp = await client.get("/admin/platform-credentials", headers=AUTH_HEADER)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_get_platform_credentials_never_leaks_secrets(client, mock_db):
    _set_pa_auth(client)
    mock_db.fetch.return_value = [{"vendor": "qdrant", "field_name": "qdrant_api_key"}]
    resp = await client.get("/admin/platform-credentials", headers=AUTH_HEADER)
    assert resp.status_code == 200
    data = resp.json()
    assert data["vendors"]["qdrant"] == {"configured": True, "source": "db"}
    assert "qdrant_api_key" in data["editable_fields"]["qdrant"]
    fetch_sql = mock_db.fetch.call_args.args[0]
    assert "enc_value" not in fetch_sql


@pytest.mark.asyncio
async def test_update_platform_credential_requires_portal_admin_role(client, mock_db):
    _set_oa_auth(client)
    resp = await client.patch(
        "/admin/platform-credentials/qdrant", headers=AUTH_HEADER,
        json={"field_name": "qdrant_api_key", "value": "real-secret"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_update_platform_credential_calls_service_with_current_user(client, mock_db):
    _set_pa_auth(client, pa_id="pa-uuid-777")
    with patch(f"{PLATFORM_CRED_SVC}.set_credential", new_callable=AsyncMock) as mock_set:
        resp = await client.patch(
            "/admin/platform-credentials/qdrant", headers=AUTH_HEADER,
            json={"field_name": "qdrant_api_key", "value": "real-secret-value"},
        )

    assert resp.status_code == 200
    assert resp.json()["message"] == "PLATFORM_CREDENTIAL_ROTATED"
    assert "real-secret-value" not in resp.text
    mock_set.assert_awaited_once()
    call_kwargs = mock_set.call_args.kwargs
    assert call_kwargs["vendor"] == "qdrant"
    assert call_kwargs["field_name"] == "qdrant_api_key"
    assert call_kwargs["value"] == "real-secret-value"
    assert call_kwargs["updated_by"] == "pa-uuid-777"


@pytest.mark.asyncio
async def test_update_platform_credential_unknown_field_returns_422(client, mock_db):
    _set_pa_auth(client)
    with patch(f"{PLATFORM_CRED_SVC}.set_credential", new_callable=AsyncMock,
               side_effect=ValueError("UNKNOWN_FIELD: not_a_real_field for vendor qdrant")):
        resp = await client.patch(
            "/admin/platform-credentials/qdrant", headers=AUTH_HEADER,
            json={"field_name": "not_a_real_field", "value": "x"},
        )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_no_platform_credentials_route_for_oa_admin():
    """OA-Admin never edits platform-wide credentials — PA-only, no org/ equivalent."""
    import importlib
    org_settings = importlib.import_module("routers.org_settings")
    paths = {getattr(r, "path", "") for r in org_settings.router.routes}
    assert not any("platform-credentials" in p for p in paths)


# ---------------------------------------------------------------------------
# HMAC rotation — 2-distinct-PA approval signal
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_hmac_rotation_approve_requires_portal_admin_role(client, mock_db):
    _set_oa_auth(client)
    resp = await client.post("/admin/security/hmac-rotation/approve", headers=AUTH_HEADER)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_hmac_rotation_approve_signals_workflow_with_current_pa_id(client, mock_db):
    """Approver identity always comes from the JWT (current.user_id), never
    from the request body — same rule as everywhere else in this codebase."""
    _set_pa_auth(client, pa_id="pa-uuid-42")

    wf_handle = MagicMock()
    wf_handle.signal = AsyncMock()
    temporal_mock = MagicMock()
    temporal_mock.get_workflow_handle = MagicMock(return_value=wf_handle)
    client.app.state.temporal_client = temporal_mock

    resp = await client.post("/admin/security/hmac-rotation/approve", headers=AUTH_HEADER)

    assert resp.status_code == 200
    assert resp.json()["message"] == "HMAC_ROTATION_APPROVAL_SIGNALED"
    temporal_mock.get_workflow_handle.assert_called_once_with("hmac-secret-rotation-perpetual")
    wf_handle.signal.assert_awaited_once_with("approve", "pa-uuid-42")


@pytest.mark.asyncio
async def test_hmac_rotation_approve_returns_503_when_workflow_unavailable(client, mock_db):
    _set_pa_auth(client)
    client.app.state.temporal_client = None
    resp = await client.post("/admin/security/hmac-rotation/approve", headers=AUTH_HEADER)
    assert resp.status_code == 503
