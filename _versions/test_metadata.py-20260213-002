import unittest
import os, tempfile
import typing
import importlib
from unittest.mock import patch

import scanfile_rename as s


def _write_minimal_pdf(path: str) -> None:
    from pypdf import PdfWriter

    w=PdfWriter()
    w.add_blank_page(width=72, height=72)
    with open(path, "wb") as f:
        w.write(f)


def _encrypt_pdf_in_place(path: str, user_password: str, owner_password: str) -> None:
    from pypdf import PdfReader, PdfWriter

    with open(path, "rb") as f:
        r=PdfReader(f)
        w=PdfWriter(clone_from=r)

        encrypt=typing.cast(typing.Any, w.encrypt)

        try:
            encrypt(user_password=user_password, owner_password=owner_password)
        except TypeError:
            try:
                encrypt(user_pwd=user_password, owner_pwd=owner_password)
            except TypeError:
                encrypt(user_password, owner_password)

        with open(path, "wb") as out:
            w.write(out)


class TestWritePdfMetadataInPlace(unittest.TestCase):
    def test_metadata_write_happy_path(self):
        with tempfile.TemporaryDirectory() as td:
            pdf_path=os.path.join(td, "doc.pdf")
            _write_minimal_pdf(pdf_path)

            with patch.object(s, "_progress", lambda *_a, **_k: None):
                ok, reason=s.write_pdf_metadata_in_place(pdf_path, {
                    "/Title":"T",
                    "/Author":"A",
                    "/Subject":"S",
                    "/Keywords":"k1; k2",
                    "/CreationDate":"D:20260212000000Z",
                })
            self.assertTrue(ok)
            self.assertIsNone(reason)

            from pypdf import PdfReader
            with open(pdf_path, "rb") as f:
                r=PdfReader(f)
                m=r.metadata or {}

            self.assertEqual(m.get("/Title"), "T")
            self.assertEqual(m.get("/Author"), "A")
            self.assertEqual(m.get("/Subject"), "S")
            self.assertEqual(m.get("/Keywords"), "k1; k2")
            self.assertEqual(m.get("/CreationDate"), "D:20260212000000Z")

    def test_encrypted_skip(self):
        with tempfile.TemporaryDirectory() as td:
            pdf_path=os.path.join(td, "enc.pdf")
            _write_minimal_pdf(pdf_path)
            _encrypt_pdf_in_place(pdf_path, user_password="u", owner_password="o")

            with patch.object(s, "_progress", lambda *_a, **_k: None):
                ok, reason=s.write_pdf_metadata_in_place(pdf_path, {"/Title":"T"})
            self.assertFalse(ok)
            self.assertIn("encrypted", str(reason or "").lower())

            from pypdf import PdfReader
            with open(pdf_path, "rb") as f:
                r=PdfReader(f)
                self.assertTrue(getattr(r, "is_encrypted", False))
                dec=r.decrypt("u")
                self.assertNotEqual(dec, 0)
                _=r.pages[0]

    def test_signed_skip_via_patch(self):
        with tempfile.TemporaryDirectory() as td:
            pdf_path=os.path.join(td, "signed.pdf")
            _write_minimal_pdf(pdf_path)

            with patch.object(s, "_progress", lambda *_a, **_k: None), \
                 patch.object(s, "_pdf_appears_signed", return_value=True):
                ok, reason=s.write_pdf_metadata_in_place(pdf_path, {"/Title":"T"})

            self.assertFalse(ok)
            self.assertIn("signed", str(reason or "").lower())


class TestExtractInformationKeywordTruncation(unittest.TestCase):
    def test_extract_information_truncates_keywords_list(self):
        big_text=("hello world\n" * 2000)

        def fake_pdftotext(_pdf_path):
            return big_text, 0, ""

        fake_json=(
            '{'
            '"date":"2026-02-12",'
            '"date_basis":"document",'
            '"provider":"Acme",'
            '"document_type":"Invoice",'
            '"title":"Test Doc",'
            '"confidence":0.9,'
            '"keywords":["k1","k2","k3","k4"]'
            '}'
        )

        def fake_call_llm(_messages, **_kwargs):
            return fake_json, None

        with patch.object(s, "_progress", lambda *_a, **_k: None), \
             patch.object(s, "_pdftotext", side_effect=fake_pdftotext), \
             patch.object(s, "_call_llm", side_effect=fake_call_llm):
            info, _raw=s.extract_information("/tmp/does-not-exist.pdf", keywords_count=2)

        self.assertIsInstance(info, dict)
        info=typing.cast(typing.Dict[str, typing.Any], info)
        self.assertIn("keywords", info)
        self.assertLessEqual(len(info.get("keywords") or []), 2)


class TestLlmConfig(unittest.TestCase):
    def test_normalize_llm_endpoint_v1_slash_appends_chat_completions(self):
        self.assertEqual(
            s._normalize_chat_completions_endpoint("http://localhost:11434/v1/"),
            "http://localhost:11434/v1/chat/completions",
        )

    def test_llm_env_vars_override_legacy_lm_studio_vars(self):
        with patch.dict(os.environ, {
            "LLM_ENDPOINT":"http://newhost:9999/v1/",
            "LM_STUDIO_ENDPOINT":"http://oldhost:1234/v1/chat/completions",
            "LLM_MODEL":"new-model",
            "LM_STUDIO_MODEL":"old-model",
            "LLM_TIMEOUT":"7",
            "LM_STUDIO_TIMEOUT":"120",
            "LLM_MAX_RETRIES":"2",
            "LM_STUDIO_MAX_RETRIES":"9",
        }, clear=False):
            m=importlib.reload(s)
            self.assertEqual(m.LLM_ENDPOINT, "http://newhost:9999/v1/chat/completions")
            self.assertEqual(m.LLM_MODEL, "new-model")
            self.assertEqual(m.LLM_TIMEOUT, 7)
            self.assertEqual(m.LLM_MAX_RETRIES, 2)

        importlib.reload(s)


if __name__ == "__main__":
    unittest.main()
