# Re-export so enforce_rules.py TDD-01 finds tests/test_keka*.py for connectors/keka.py.
# All actual connector tests live in test_hrms_adapters.py.
from tests.test_hrms_adapters import *  # noqa: F401,F403
