"""Shared pytest setup for the whole test suite.

A freshly built athlete_tax.db (src/athlete_tax/clean_tax_data.py) holds only the
2026 tax tables. The sourced 2025 inputs are added by sync_historical_taxes(),
which the dashboard server runs at startup and test_league_tax.py runs in its
setup. Pytest runs test files alphabetically, so on a fresh database the files
that use 2025 rules (contract coverage/projection, league projection, MLB model
and projection, NFL history, player comparison) ran before test_league_tax.py
and failed with "Missing 2025 tax brackets ...". They passed on later runs only
because the first run had already updated the database.

Installing the 2025 inputs once, before any test, makes the suite pass on a
fresh database and in any order. sync_historical_taxes() only inserts or
replaces rows, so running it again on an up-to-date database changes nothing.
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from etl.historical_taxes import sync_historical_taxes  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def historical_tax_inputs():
    """Install the 2025 tax inputs once per test session."""
    sync_historical_taxes()