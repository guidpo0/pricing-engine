"""
Shared pytest fixtures for the pricing engine test suite.
"""
from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, patch

import pytest


@pytest.fixture
def ref_date() -> date:
    """Fixed reference date for deterministic test calculations."""
    return date(2026, 3, 7)


@pytest.fixture
def mock_pre_rate():
    """Fixture providing a stable 13% nominal pre rate."""
    def _rate(tenor, curve_type="pre"):
        if curve_type == "pre":
            return 0.13
        if curve_type == "ipca":
            return 0.08
        return 0.1325
    return _rate


@pytest.fixture
def mock_vna():
    """Fixture providing a stable VNA value."""
    return 4782.22


@pytest.fixture
def mock_selic_rate():
    return 0.1325
