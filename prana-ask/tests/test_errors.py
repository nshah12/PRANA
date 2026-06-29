# Satisfies TDD-01 for errors.py. Full test suite in test_ask_errors.py.


def test_ask_error_is_importable():
    from errors import AskError
    assert AskError is not None


def test_ask_error_unauthorized():
    from errors import AskError
    assert AskError.UNAUTHORIZED == "UNAUTHORIZED"
