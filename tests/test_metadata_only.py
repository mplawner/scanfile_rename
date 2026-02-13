import unittest
import os, sys, io, json, tempfile, contextlib
from unittest.mock import patch

import scanfile_rename as s


def _touch_pdf(tmp_dir: str, name: str="input.pdf") -> str:
    path=os.path.join(tmp_dir, name)
    with open(path, "wb") as f:
        f.write(b"%PDF-1.4\n")
    return path


def _run_main(argv):
    buf=io.StringIO()
    with patch.object(sys, "argv", argv), \
         contextlib.redirect_stdout(buf), \
         contextlib.redirect_stderr(buf):
        try:
            rc=s.main()
        except SystemExit as e:
            rc=e.code
            if not isinstance(rc, int):
                rc=1
    return rc, buf.getvalue()


class TestMetadataOnlyCli(unittest.TestCase):
    def tearDown(self):
        s._PROGRESS_ENABLED=True

    def test_metadata_only_outdir_incompatible(self):
        with tempfile.TemporaryDirectory() as td:
            pdf_path=_touch_pdf(td)

            with patch.object(s, "extract_information") as extract, \
                 patch.object(s, "write_pdf_metadata_in_place") as writer, \
                 patch.object(s.shutil, "copy2") as copy2, \
                 patch.object(s.shutil, "move") as move, \
                 patch.object(s.os, "makedirs") as makedirs:
                rc, out=_run_main(["scanfile_rename.py", pdf_path, "--metadata-only", "--outdir", "X"])

            self.assertEqual(rc, 2)
            self.assertIn("incompatible", out.lower())
            self.assertIn("--outdir", out)
            extract.assert_not_called()
            writer.assert_not_called()
            copy2.assert_not_called()
            move.assert_not_called()
            makedirs.assert_not_called()

    def test_metadata_only_move_incompatible(self):
        with tempfile.TemporaryDirectory() as td:
            pdf_path=_touch_pdf(td)

            with patch.object(s, "extract_information") as extract, \
                 patch.object(s, "write_pdf_metadata_in_place") as writer, \
                 patch.object(s.shutil, "copy2") as copy2, \
                 patch.object(s.shutil, "move") as move, \
                 patch.object(s.os, "makedirs") as makedirs:
                rc, out=_run_main(["scanfile_rename.py", pdf_path, "--metadata-only", "--move"])

            self.assertEqual(rc, 2)
            self.assertIn("incompatible", out.lower())
            self.assertIn("--move", out)
            extract.assert_not_called()
            writer.assert_not_called()
            copy2.assert_not_called()
            move.assert_not_called()
            makedirs.assert_not_called()

    def test_metadata_only_dry_run_prints_docinfo_and_skips_writer(self):
        with tempfile.TemporaryDirectory() as td:
            pdf_path=_touch_pdf(td, name="2026-02-12 - acme inc - invoice - test doc.pdf")

            info={
                "date":"2026-02-12",
                "provider":"Acme Inc",
                "author":None,
                "subject":None,
                "keywords":["k1","k2"],
            }

            with patch.object(s, "extract_information", return_value=(info, "")) as extract, \
                 patch.object(s, "write_pdf_metadata_in_place") as writer, \
                 patch.object(s.shutil, "copy2") as copy2, \
                 patch.object(s.shutil, "move") as move, \
                 patch.object(s.os, "makedirs") as makedirs:
                rc, out=_run_main(["scanfile_rename.py", pdf_path, "--metadata-only", "--dry-run"])

            self.assertEqual(rc, 0)
            extract.assert_called_once()
            writer.assert_not_called()
            copy2.assert_not_called()
            move.assert_not_called()
            makedirs.assert_not_called()

            docinfo=json.loads(out)
            expected_title=s.pretty_title_from_filename(os.path.basename(pdf_path))
            self.assertEqual(docinfo.get("/Title"), expected_title)

    def test_metadata_only_writer_failure_is_strict(self):
        with tempfile.TemporaryDirectory() as td:
            pdf_path=_touch_pdf(td)

            info={
                "date":"2026-02-12",
                "provider":"Acme",
                "author":"Acme",
                "subject":"S",
                "keywords":[],
            }

            with patch.object(s, "extract_information", return_value=(info, "")), \
                 patch.object(s, "write_pdf_metadata_in_place", return_value=(False, "signed")) as writer, \
                 patch.object(s.shutil, "copy2") as copy2, \
                 patch.object(s.shutil, "move") as move, \
                 patch.object(s.os, "makedirs") as makedirs:
                rc, out=_run_main(["scanfile_rename.py", pdf_path, "--metadata-only"])

            self.assertEqual(rc, 1)
            self.assertIn("signed", out)
            writer.assert_called_once()
            copy2.assert_not_called()
            move.assert_not_called()
            makedirs.assert_not_called()

    def test_metadata_only_writer_success(self):
        with tempfile.TemporaryDirectory() as td:
            pdf_path=_touch_pdf(td)

            info={
                "date":"2026-02-12",
                "provider":"Acme",
                "author":"Acme",
                "subject":"S",
                "keywords":[],
            }

            with patch.object(s, "extract_information", return_value=(info, "")), \
                 patch.object(s, "write_pdf_metadata_in_place", return_value=(True, None)) as writer, \
                 patch.object(s.shutil, "copy2") as copy2, \
                 patch.object(s.shutil, "move") as move, \
                 patch.object(s.os, "makedirs") as makedirs:
                rc, out=_run_main(["scanfile_rename.py", pdf_path, "--metadata-only"])

            self.assertEqual(rc, 0)
            self.assertEqual(out.strip(), "")
            writer.assert_called_once()
            copy2.assert_not_called()
            move.assert_not_called()
            makedirs.assert_not_called()


if __name__ == "__main__":
    unittest.main()
