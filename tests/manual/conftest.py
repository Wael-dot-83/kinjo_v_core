"""Mark everything under tests/manual as requiring a live, populated database.

These files use ``database.SessionLocal()`` directly rather than the ``test_db``
fixture, so they read whatever database ``DATABASE_URL`` points at instead of the
per-test in-memory schema. Against the default test database their tables do not
exist and they fail with ``OperationalError``.

They are therefore integration checks, not suite tests, and are deselected by
default via ``addopts = -m "not manual"`` in pytest.ini. See README.md here.
"""

import pytest


def pytest_collection_modifyitems(items):
    for item in items:
        item.add_marker(pytest.mark.manual)
