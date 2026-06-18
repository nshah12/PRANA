"""Tests for routers/elevations.py — TDD stubs. (workflows/elevation.py covered by test_elevation.py)"""
import pytest


@pytest.mark.xfail(reason="TDD stub — write real failing test first", strict=True)
def test_create_elevation_requires_oa_admin_role():
    raise NotImplementedError


@pytest.mark.xfail(reason="TDD stub — write real failing test first", strict=True)
def test_approve_elevation_sends_signal_to_workflow():
    raise NotImplementedError


@pytest.mark.xfail(reason="TDD stub — write real failing test first", strict=True)
def test_elevation_tenant_isolated():
    raise NotImplementedError
