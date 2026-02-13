import unittest

import scanfile_rename as s


class TestPrettyTitleFromFilename(unittest.TestCase):
    def test_pretty_title_from_filename_basic(self):
        self.assertEqual(
            s.pretty_title_from_filename("2026-02-12 - acme inc - invoice - test doc.pdf"),
            "2026-02-12 - Acme Inc - Invoice - Test Doc",
        )

    def test_pretty_title_from_filename_strips_pdf_case_insensitive(self):
        self.assertEqual(s.pretty_title_from_filename("Test Doc.PDF"), "Test Doc")

    def test_pretty_title_from_filename_connectors_lowercased(self):
        self.assertEqual(
            s.pretty_title_from_filename("acme and sons - report.pdf"),
            "Acme and Sons - Report",
        )

    def test_pretty_title_from_filename_segment_initial_connector_titlecased(self):
        self.assertEqual(
            s.pretty_title_from_filename("2026-02-12 - the acme inc - invoice.pdf"),
            "2026-02-12 - The Acme Inc - Invoice",
        )

    def test_pretty_title_from_filename_keeps_all_caps_tokens(self):
        self.assertEqual(
            s.pretty_title_from_filename("2026-02-12 - ACME - USA report.pdf"),
            "2026-02-12 - ACME - USA Report",
        )

    def test_pretty_title_from_filename_preserves_unpadded_date_token(self):
        self.assertEqual(
            s.pretty_title_from_filename("2026-2-12 - acme inc.pdf"),
            "2026-2-12 - Acme Inc",
        )


class TestPdfCreationDateFromYmd(unittest.TestCase):
    def test_pdf_creation_date_from_ymd_valid(self):
        self.assertEqual(s.pdf_creation_date_from_ymd("2026-02-12"), "D:20260212000000Z")

    def test_pdf_creation_date_from_ymd_normalizes_non_padded(self):
        self.assertEqual(s.pdf_creation_date_from_ymd("2026-2-12"), "D:20260212000000Z")

    def test_pdf_creation_date_from_ymd_invalid_returns_none(self):
        self.assertIsNone(s.pdf_creation_date_from_ymd("not-a-date"))
        self.assertIsNone(s.pdf_creation_date_from_ymd("2026-02-30"))


class TestFormatKeywords(unittest.TestCase):
    def test_format_keywords_dedup_and_join(self):
        self.assertEqual(s.format_keywords(["alpha", "beta", "alpha"], 5), "alpha; beta")

    def test_format_keywords_truncates(self):
        self.assertEqual(s.format_keywords(["alpha", "beta", "gamma"], 2), "alpha; beta")

    def test_format_keywords_strips_and_skips_empty(self):
        self.assertEqual(s.format_keywords([" alpha ", "", "beta"], 5), "alpha; beta")

    def test_format_keywords_empty_returns_none(self):
        self.assertIsNone(s.format_keywords([], 5))
        self.assertIsNone(s.format_keywords([""], 5))

    def test_format_keywords_non_positive_count_returns_none(self):
        self.assertIsNone(s.format_keywords(["alpha"], 0))


if __name__ == "__main__":
    unittest.main()
