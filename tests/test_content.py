import json
import shutil
import tempfile
import unittest
from pathlib import Path

from backend.content import CONTENT_DIR, ContentError, load_content


class ContentTest(unittest.TestCase):
    def test_real_content_loads_without_problems(self):
        content = load_content()
        self.assertEqual(content.problems, [])
        self.assertIn("w_bahay", content.words_by_id)

    def _load_edited(self, edit):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp)
        for name in ("content.json", "rules.json"):
            shutil.copy(CONTENT_DIR / name, tmp / name)
        data = json.loads((tmp / "content.json").read_text(encoding="utf-8"))
        edit(data)
        (tmp / "content.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        return load_content(tmp)

    def test_missing_field_is_reported_with_item_id(self):
        def edit(d):
            del d["words"][0]["tiles"]
        with self.assertRaises(ContentError) as ctx:
            self._load_edited(edit)
        self.assertIn("words[0] (w_aso): field 'tiles' is missing", ctx.exception.problems[0])

    def test_split_ng_tile_is_reported(self):
        def edit(d):
            w = next(w for w in d["words"] if w["id"] == "w_ngipin")
            w["tiles"] = ["n", "g", "i", "p", "i", "n"]
        content = self._load_edited(edit)
        self.assertTrue(any("ng must be one tile" in p for p in content.problems))

    def test_unknown_skill_is_reported(self):
        def edit(d):
            d["words"][0]["skill_ids"] = ["sk_nope"]
        content = self._load_edited(edit)
        self.assertTrue(any("'sk_nope' is not a skill id" in p for p in content.problems))


if __name__ == "__main__":
    unittest.main()
