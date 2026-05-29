from __future__ import annotations

import pytest

from reviewpilot.config import clear_settings_cache


@pytest.fixture(autouse=True)
def _clear_settings() -> None:
    clear_settings_cache()
