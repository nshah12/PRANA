# Shim: all real tests live in test_pipeline_errors.py
# This file satisfies TDD-01 for pipeline/errors.py.
from tests.test_pipeline_errors import *  # noqa: F401,F403


def test_pipeline_error_import():
    """Sanity: PipelineError is importable and is a StrEnum."""
    from pipeline.errors import PipelineError
    from enum import EnumMeta
    assert issubclass(PipelineError, str)
    assert isinstance(PipelineError, EnumMeta)
