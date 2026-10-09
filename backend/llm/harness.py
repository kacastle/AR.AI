"""The prompts, model call and checks from content/test_prompts.py (Person 3's harness), loaded as a module.

The backend uses that file directly so there is only one copy of every prompt and check. It is loaded
by path because content/ is not a package and belongs to Person 3. It reads content.json, rules.json
and prompts.md next to itself when it loads.
"""
import importlib.util

from backend.db import ROOT

PATH = ROOT / "content" / "test_prompts.py"


def _load():
    spec = importlib.util.spec_from_file_location("content_test_prompts", PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


tp = _load()
