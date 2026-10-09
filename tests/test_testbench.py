"""The testbench runs the frontend's own client (frontend/src/api.js) against the real backend, through Vite's /api
proxy. Keep the three pieces in step."""
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
CLIENT = ROOT / "frontend" / "src" / "api.js"
SCRIPT = (ROOT / "scripts" / "testbench.py").read_text(encoding="utf-8")
CONFIG = (ROOT / "scripts" / "testbench" / "vite.config.mjs").read_text(encoding="utf-8")


@pytest.mark.skipif(not CLIENT.is_file(), reason="frontend not checked out")
def test_frontend_client_has_a_real_mode_and_a_base_url():
    text = CLIENT.read_text(encoding="utf-8")
    assert "VITE_USE_MOCK" in text and "VITE_API_BASE_URL" in text


def test_testbench_starts_the_frontend_in_real_mode_through_the_proxy():
    assert '"VITE_USE_MOCK": "false"' in SCRIPT
    assert "VITE_API_BASE_URL" in SCRIPT
    assert "proxy: { '/api': backend }" in CONFIG
    assert "alias" not in CONFIG                 # the frontend's mock module is no longer swapped
