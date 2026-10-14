"""Fixtures for the analysis tests: the labelled stub windows (engine.analysis.stub)."""

import pytest

from engine.analysis.statements import Window
from engine.analysis.stub import FY2025, FY2026


@pytest.fixture
def fy2025() -> Window:
    return FY2025


@pytest.fixture
def fy2026() -> Window:
    return FY2026
