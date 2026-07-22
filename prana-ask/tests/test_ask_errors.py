"""RED tests for prana-ask/errors.py — AskError taxonomy."""
import pytest
from enum import EnumMeta


def test_ask_error_exists():
    from errors import AskError
    assert AskError is not None


def test_ask_error_is_str_enum():
    from errors import AskError
    assert issubclass(AskError, str)
    assert isinstance(AskError, EnumMeta)


def test_ask_error_values_equal_names():
    from errors import AskError
    for member in AskError:
        assert member.value == member.name


@pytest.mark.parametrize("code", [
    "UNAUTHORIZED",
    "MISSING_EMPLOYEE_ID",
    "INVALID_EMPLOYEE_ID",
    "EMPTY_QUERY",
    "QUERY_TOO_LONG",
    "PRIVACY_BLOCK",
    "RAG_UNAVAILABLE",
])
def test_ask_codes_present(code):
    from errors import AskError
    assert hasattr(AskError, code), f"AskError.{code} missing"


def test_ask_error_usable_as_string():
    from errors import AskError
    assert str(AskError.UNAUTHORIZED) == "UNAUTHORIZED"
    assert AskError.EMPTY_QUERY == "EMPTY_QUERY"
