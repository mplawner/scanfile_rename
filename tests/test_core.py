import unittest
import os, sys, subprocess

import scanfile_rename as s


class TestJsonParsing(unittest.TestCase):
    def test_extract_json_loose_full(self):
        self.assertEqual(s._extract_json_loose('{"a": 1}'), {"a": 1})

    def test_extract_json_loose_embedded(self):
        self.assertEqual(s._extract_json_loose('noise {"a": 1} tail'), {"a": 1})


class TestFilenameHelpers(unittest.TestCase):
    def test_normalize_doc_type(self):
        self.assertEqual(s._normalize_doc_type("invoice"), "Invoice")
        self.assertEqual(s._normalize_doc_type("tax"), "Tax Document")

    def test_create_filename(self):
        info={
            "date":"2024-01-02",
            "provider":"Acme/Inc",
            "document_type":"invoice",
            "title":"Test Doc",
        }
        name=s.create_filename(info)
        self.assertTrue(name.endswith(".pdf"))
        self.assertIn("2024-01-02", name)
        self.assertIn("Acme-Inc", name)
        self.assertIn("Invoice", name)


class TestCliFlags(unittest.TestCase):
    def _run_cli(self, *args):
        repo_root=os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        script=os.path.join(repo_root, "scanfile_rename.py")
        return subprocess.run([sys.executable, script, *args], cwd=repo_root, capture_output=True, text=True)

    def test_help_includes_keywords_count(self):
        r=self._run_cli("--help")
        self.assertEqual(r.returncode, 0)
        self.assertIn("--keywords-count", r.stdout)

    def test_keywords_count_invalid_fails_at_parse_time(self):
        r=self._run_cli("--keywords-count", "0", "--version")
        self.assertNotEqual(r.returncode, 0)

    def test_keywords_count_valid_allows_version(self):
        r=self._run_cli("--keywords-count", "5", "--version")
        self.assertEqual(r.returncode, 0)


if __name__ == "__main__":
    unittest.main()
