import io
import unittest
from datetime import datetime

from openpyxl import Workbook

from mariner_genai_dbx import document_views
from mariner_genai_dbx.document_views import (
    SpreadsheetError,
    read_workbook,
    render_message,
    render_workbook,
)


def xlsx(build):
    workbook = Workbook()
    build(workbook)
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


class SpreadsheetViewTests(unittest.TestCase):
    def test_reads_visible_sheets_with_excel_row_numbers(self):
        def build(workbook):
            sheet = workbook.active
            sheet.title = "Fees"
            sheet.append(["Fee", "Amount", None])
            sheet.append([None, None])
            sheet.append(["Late", 15.0])
            sheet.append(["Filed", datetime(2026, 1, 5)])
            hidden = workbook.create_sheet("Internal")
            hidden.append(["secret"])
            hidden.sheet_state = "hidden"

        sheets = read_workbook(xlsx(build), ".xlsx")

        self.assertEqual([sheet.name for sheet in sheets], ["Fees"])
        self.assertEqual(
            sheets[0].rows,
            ((1, ("Fee", "Amount")), (3, ("Late", "15")), (4, ("Filed", "2026-01-05"))),
        )

    def test_formulas_are_not_shown_or_evaluated(self):
        def build(workbook):
            workbook.active.append(["Total", "=SUM(1,2)"])

        rows = read_workbook(xlsx(build), ".xlsx")[0].rows

        # A file never opened in Excel has no saved result, so the cell is blank.
        self.assertEqual(rows, ((1, ("Total",)),))

    def test_caps_rows(self):
        def build(workbook):
            for number in range(5):
                workbook.active.append([number])

        original = document_views.MAX_ROWS
        document_views.MAX_ROWS = 3
        try:
            sheet = read_workbook(xlsx(build), ".xlsx")[0]
        finally:
            document_views.MAX_ROWS = original

        self.assertEqual(len(sheet.rows), 3)
        self.assertTrue(sheet.truncated)

    def test_render_escapes_sheet_names_and_values(self):
        def build(workbook):
            workbook.active.title = "A&B"
            workbook.active.append(['<img src=x onerror="alert(1)">'])

        html = render_workbook("Book <1>.xlsx", read_workbook(xlsx(build), ".xlsx"), "/dl?a=1&b=2")

        self.assertIn("A&amp;B", html)
        self.assertIn("&lt;img src=x onerror=&quot;alert(1)&quot;&gt;", html)
        self.assertIn("Book &lt;1&gt;.xlsx", html)
        self.assertNotIn("<img", html)
        self.assertNotIn("/dl", html)  # the reader toolbar has the Download button

    def test_message_page_escapes_download_link(self):
        html = render_message("Book.xlsx", "Too <big>.", "/dl?a=1&b=2")

        self.assertIn("Too &lt;big&gt;.", html)
        self.assertIn('href="/dl?a=1&amp;b=2"', html)

    def test_empty_workbook_shows_message(self):
        html = render_workbook("Empty.xlsx", read_workbook(xlsx(lambda w: None), ".xlsx"), "/dl")

        self.assertIn("no visible data", html)

    def test_corrupt_workbook_raises(self):
        with self.assertRaises(SpreadsheetError):
            read_workbook(b"not a workbook", ".xlsx")


if __name__ == "__main__":
    unittest.main()
