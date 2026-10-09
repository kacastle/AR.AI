"""The testbench swaps frontend/src/mocks/api.js for scripts/testbench/api.js. Keep them in step."""
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
MOCK = ROOT / "frontend" / "src" / "mocks" / "api.js"
REAL = ROOT / "scripts" / "testbench" / "api.js"
EXPORT = re.compile(r"^export\s+(?:async\s+)?(?:function|const|let)\s+(\w+)", re.M)
IMPORT = re.compile(r"import\s*\{([^}]*)\}\s*from\s*['\"][./]*mocks/api\.js['\"]")


def exports(path: Path) -> set[str]:
    return set(EXPORT.findall(path.read_text(encoding="utf-8")))


def imported_from_mock() -> set[str]:
    names = set()
    for f in (ROOT / "frontend" / "src").rglob("*.js*"):
        for group in IMPORT.findall(f.read_text(encoding="utf-8")):
            names |= {n.split(" as ")[0].strip() for n in group.split(",") if n.strip()}
    return names


@pytest.mark.skipif(not MOCK.is_file(), reason="frontend not checked out")
def test_testbench_client_has_every_export_the_frontend_imports():
    used = imported_from_mock()
    assert used, "found no imports from mocks/api.js"
    missing = used - exports(REAL)
    assert not missing, f"scripts/testbench/api.js is missing {sorted(missing)}, which the frontend imports"


@pytest.mark.skipif(not MOCK.is_file(), reason="frontend not checked out")
def test_frontend_still_imports_the_mock_module_the_testbench_replaces():
    screens = (ROOT / "frontend" / "src").rglob("*.jsx")
    assert any("mocks/api.js" in p.read_text(encoding="utf-8") for p in screens)
