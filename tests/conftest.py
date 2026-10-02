"""Spend guard: tests marked `live` (paid API calls) are skipped unless --confirm-spend is given.

This holds even for a bare `pytest` run with provider keys present in the environment.
The full spend rules (cost estimate, MAX_RUN_COST_USD) are enforced in code from Phase 1.
"""

import pytest


def pytest_addoption(parser):
    parser.addoption(
        "--confirm-spend",
        action="store_true",
        default=False,
        help="allow tests marked `live` to call paid APIs",
    )


def pytest_collection_modifyitems(config, items):
    if config.getoption("--confirm-spend"):
        return
    skip = pytest.mark.skip(reason="live test: requires --confirm-spend")
    for item in items:
        if "live" in item.keywords:
            item.add_marker(skip)
