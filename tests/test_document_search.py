import unittest

from mariner_genai_dbx.document_search import DocumentTextSearch, search_chunks


def row(title, path, page, text):
    return ("Branch Operations", title, path, page, text, 1)


ROWS = [
    row("WI Section 128 Policy", "/Volumes/v/docs/WI.docx", 2,
        "<table><tr><td>Submit the General Interest Rate Change E-Form</td></tr></table> "
        "as a ticket through the IT Support Portal."),
    row("WI Section 128 Policy", "/Volumes/v/docs/WI.docx", 3,
        "The interest rate is reduced. A change form may be required."),
    row("Autopay", "/Volumes/v/docs/Autopay.pdf", 1, "Autopay enrollment form."),
]


class DocumentSearchTests(unittest.TestCase):
    def test_exact_phrase_ranks_first_and_html_is_removed(self):
        hits = search_chunks(ROWS, "interest rate change")

        self.assertEqual([(h["title"], h["page"]) for h in hits],
                         [("WI Section 128 Policy", 2), ("WI Section 128 Policy", 3)])
        self.assertIn("General Interest Rate Change E-Form", hits[0]["snippet"])
        self.assertNotIn("<td>", hits[0]["snippet"])

    def test_every_word_must_appear(self):
        self.assertEqual(search_chunks(ROWS, "autopay portal"), [])

    def test_single_letter_words_are_ignored(self):
        hits = search_chunks(ROWS, "E-Form")

        self.assertEqual(hits[0]["page"], 2)

    def test_snippet_is_trimmed_around_the_match(self):
        long_row = row("Long", "/Volumes/v/docs/L.pdf", 1, "word " * 200 + "needle " + "word " * 200)

        snippet = search_chunks([long_row], "needle")[0]["snippet"]

        self.assertTrue(snippet.startswith("…") and snippet.endswith("…"))
        self.assertIn("needle", snippet)
        self.assertLess(len(snippet), 300)

    def test_one_result_per_document_page(self):
        rows = ROWS + [row("WI Section 128 Policy", "/Volumes/v/docs/WI.docx", 2, "IT Support Portal")]

        hits = search_chunks(rows, "portal")

        self.assertEqual(len(hits), 1)

    def test_uses_resolver_rows(self):
        class Resolver:
            def chunk_rows(self):
                return ROWS

        self.assertEqual(len(DocumentTextSearch(Resolver()).search("autopay")), 1)


if __name__ == "__main__":
    unittest.main()
