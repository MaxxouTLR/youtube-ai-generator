import os
import sys

import pytest

# Les modules du pipeline sont a la racine du depot (pas de package) : on la rend importable.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    """Les backoffs (2s, 4s, 8s...) ne doivent jamais ralentir les tests."""
    import net_retry
    sleeps = []
    monkeypatch.setattr(net_retry.time, "sleep", sleeps.append)
    return sleeps
