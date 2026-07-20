"""Tests for spoof-resistant client-IP resolution (finding H3).

X-Forwarded-For is client-controllable to the LEFT of our own proxies. Login attempt
logs and IP anomaly detection must use the value our trusted proxy actually observed,
i.e. `trusted_proxy_count` entries from the right — never the attacker-supplied leftmost.
"""
from types import SimpleNamespace

from lib.client_ip import get_client_ip


def _req(xff=None, peer="10.0.0.9"):
    headers = {}
    if xff is not None:
        headers["x-forwarded-for"] = xff
    return SimpleNamespace(headers=headers, client=SimpleNamespace(host=peer))


def test_no_xff_falls_back_to_socket_peer():
    assert get_client_ip(_req(xff=None, peer="10.0.0.5")) == "10.0.0.5"


def test_single_proxy_uses_rightmost_entry():
    # Kong appended the real client on the right; leftmost is what the client sent.
    assert get_client_ip(_req(xff="203.0.113.7"), trusted_proxy_count=1) == "203.0.113.7"


def test_spoofed_left_entries_are_ignored():
    # Attacker pre-seeds a fake IP; our proxy appends the real one on the right.
    ip = get_client_ip(_req(xff="1.2.3.4, 203.0.113.7"), trusted_proxy_count=1)
    assert ip == "203.0.113.7"
    assert ip != "1.2.3.4"


def test_two_trusted_hops_counts_from_right():
    # client, alb, kong  → with 2 trusted hops the real client is 2 from the right.
    ip = get_client_ip(_req(xff="9.9.9.9, 203.0.113.7, 10.0.0.2"), trusted_proxy_count=2)
    assert ip == "203.0.113.7"


def test_short_chain_falls_back_to_peer():
    # Fewer entries than trusted hops → don't trust a spoofed value; use socket peer.
    ip = get_client_ip(_req(xff="1.2.3.4", peer="10.0.0.9"), trusted_proxy_count=2)
    assert ip == "10.0.0.9"
