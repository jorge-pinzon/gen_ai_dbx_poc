import unittest

from mariner_genai_dbx.live_preview import LivePreview, tidy_table
from mariner_genai_dbx.web import _apply_output_guardrails, _interim_result, _mask_personal_data


def preview(hold=40):
    return LivePreview(check=_apply_output_guardrails, mask=_mask_personal_data, hold=hold)


def shown(events):
    return "".join(payload["text"] for event, payload in events if event == "delta")


class InterimResultTests(unittest.TestCase):
    TABLE = "| Employee | Overdue |\n| - | - |\n| Isaac Zeller | 11 |"

    def test_interim_result_shows_until_answer_text_is_shown(self):
        p = preview(hold=10)
        self.assertEqual(p.interim(self.TABLE), [("delta", {"text": self.TABLE})])
        self.assertEqual(p.reset(), [])  # a Supervisor hand-off does not clear it
        self.assertEqual(p.feed("Isaac"), [])  # still held back: the table stays
        out = p.feed(" has the most overdue tasks.\nFollow up this week, starting today.\n")
        self.assertEqual(out[0], ("preview_reset", {}))
        self.assertEqual(shown(out), "Isaac has the most overdue tasks.\n")

    def test_interim_result_is_checked_and_masked(self):
        p = preview()
        self.assertEqual(p.interim("| Endpoint |\n| - |\n| mas-abc123-endpoint |"), [])
        self.assertIn("[REDACTED PHONE]", shown(p.interim("| Phone |\n| - |\n| 410-555-1234 |")))

    def test_blocked_answer_clears_the_interim_result(self):
        p = preview(hold=10)
        p.interim(self.TABLE)
        self.assertEqual(p.feed("This uses the mas-abc123-endpoint internally.\n"), [("preview_reset", {})])

    def test_tidy_table_drops_row_numbers_and_midnight_times(self):
        raw = "||employee|oldest_due|\n|-|-|-|\n|0|Isaac Zeller|2026-01-27 00:00:00|"
        self.assertEqual(tidy_table(raw), "| employee | oldest_due |\n| - | - |\n| Isaac Zeller | 2026-01-27 |")
        self.assertIsNone(tidy_table("No rows were found."))

    def test_only_coaching360_data_tables_are_shown_early(self):
        table = "||employee|\n|-|-|\n|0|Isaac|"
        self.assertTrue(_interim_result("coaching360_branch_data", table).endswith("| Isaac |"))
        self.assertIsNone(_interim_result("coaching360_guide", table))
        self.assertIsNone(_interim_result("ka-56b296c2-4004", table))
        self.assertIsNone(_interim_result("coaching360_branch_data", "No data was found."))


class LivePreviewTests(unittest.TestCase):
    def test_shows_whole_lines_only_after_the_hold_window(self):
        p = preview(hold=40)
        self.assertEqual(p.feed("First line of the answer.\nSecond li"), [])
        events = p.feed("ne continues here with enough text after it to pass the hold.\n")
        self.assertEqual(shown(events), "First line of the answer.\n")

    def test_masks_personal_data_split_across_chunks(self):
        p = preview(hold=40)
        out = p.feed("Call HR at 410-555-")
        out += p.feed("1234 for help.\n")
        out += p.feed("More guidance follows in this line, long enough to release.\n" * 2)
        text = shown(out)
        self.assertIn("[REDACTED PHONE]", text)
        self.assertNotIn("410-555", text)

    def test_blocked_content_clears_the_preview(self):
        p = preview(hold=10)
        out = p.feed("Managers meet quarterly with each employee.\nThe next line keeps going.\n")
        self.assertTrue(shown(out))
        self.assertEqual(p.feed("This uses the mas-abc123-endpoint internally.\n"), [("preview_reset", {})])
        self.assertEqual(p.feed("Anything else.\n" * 5), [])

    def test_source_lines_are_never_shown(self):
        p = preview(hold=5)
        text = shown(p.feed("Files are kept five years.\nSource: Record Retention\nMore text here.\nEnd.\n"))
        self.assertIn("Files are kept five years.", text)
        self.assertNotIn("Source:", text)

    def test_structured_json_answers_are_not_previewed(self):
        for start in ('{"answer": "Ratings run 1 to 5.\\n', '```json\n{"answer": "x\\n'):
            p = preview(hold=5)
            self.assertEqual(p.feed(start + "padding line\n" * 10), [])

    def test_reset_clears_text_that_was_not_final(self):
        p = preview(hold=5)
        self.assertTrue(shown(p.feed("I'll check that for you.\nOne moment please.\n")))
        self.assertEqual(p.reset(), [("preview_reset", {})])
        self.assertEqual(shown(p.feed("Final answer line.\nAnother final line.\n")), "Final answer line.\n")


if __name__ == "__main__":
    unittest.main()
