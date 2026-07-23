"""Tests for kafka/producer.py's new Communication Hub entrypoint —
communication_requested() (prana-docs/COMMUNICATION_HUB_ARCHITECTURE.md §2) —
and the new IVR channel topic helper.
"""
from unittest.mock import AsyncMock

import pytest

from kafka.producer import KafkaPub, TOPIC_COMM, TOPIC_NOTIF_IVR


def _make_pub():
    pub = KafkaPub.__new__(KafkaPub)
    pub.publish = AsyncMock()
    return pub


@pytest.mark.asyncio
async def test_communication_requested_publishes_to_comm_topic():
    pub = _make_pub()
    await pub.communication_requested({
        "template_id": "VAULT_WELCOME", "recipient_id": "emp-1",
        "recipient_type": "employee", "tenant_id": "t-1", "template_data": {},
    })
    pub.publish.assert_called_once()
    topic, event = pub.publish.call_args.args
    assert topic == TOPIC_COMM
    assert event["template_id"] == "VAULT_WELCOME"


@pytest.mark.asyncio
async def test_communication_requested_keyed_by_recipient_id():
    pub = _make_pub()
    await pub.communication_requested({"template_id": "X", "recipient_id": "emp-42", "tenant_id": "t-1"})
    assert pub.publish.call_args.kwargs["key"] == "emp-42"


@pytest.mark.asyncio
async def test_communication_requested_falls_back_to_tenant_id_key_when_no_recipient():
    pub = _make_pub()
    await pub.communication_requested({"template_id": "X", "tenant_id": "t-1"})
    assert pub.publish.call_args.kwargs["key"] == "t-1"


@pytest.mark.asyncio
async def test_notify_ivr_publishes_to_ivr_topic():
    pub = _make_pub()
    await pub.notify_ivr({"template_id": "X", "recipient_id": "emp-1"})
    topic, event = pub.publish.call_args.args
    assert topic == TOPIC_NOTIF_IVR
    assert pub.publish.call_args.kwargs["key"] == "emp-1"
