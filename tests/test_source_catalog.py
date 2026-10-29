import io
import unittest
from types import SimpleNamespace

from mariner_genai_dbx.errors import InvalidSourcePathError, SourceDocumentNotFoundError
from mariner_genai_dbx.models import VolumeCatalog
from mariner_genai_dbx.source_catalog import DatabricksVolumeCatalogService


class FakeFiles:
    def __init__(self):
        self.directories = {
            "/Volumes/workspace/default/branch_operations_docs": [
                SimpleNamespace(
                    path="/Volumes/workspace/default/branch_operations_docs/archive",
                    is_directory=True,
                ),
                SimpleNamespace(
                    path="/Volumes/workspace/default/branch_operations_docs/policy.pdf",
                    is_directory=False,
                ),
                SimpleNamespace(
                    path="/Volumes/workspace/default/branch_operations_docs/notes.txt",
                    is_directory=False,
                ),
                SimpleNamespace(
                    path="/Volumes/workspace/default/branch_operations_docs/Lending.docx",
                    is_directory=False,
                ),
                SimpleNamespace(
                    path="/Volumes/workspace/default/branch_operations_docs/Attorneys.xlsx",
                    is_directory=False,
                ),
                SimpleNamespace(
                    path="/Volumes/workspace/default/branch_operations_docs/~$Lending.docx",
                    is_directory=False,
                ),
            ],
            "/Volumes/workspace/default/branch_operations_docs/archive": [
                SimpleNamespace(
                    path="/Volumes/workspace/default/branch_operations_docs/archive/retention.pdf",
                    is_directory=False,
                )
            ],
        }
        self.downloaded = None
        self.missing = set()

    def list_directory_contents(self, directory_path):
        return self.directories.get(directory_path, [])

    def download(self, file_path):
        self.downloaded = file_path
        if file_path in self.missing:
            raise NotFound("not found")
        return SimpleNamespace(
            contents=io.BytesIO(b"%PDF-test"),
            content_length=9,
            last_modified=None,
        )


class NotFound(Exception):
    status_code = 404


class FakeWorkspaceClient:
    def __init__(self):
        self.files = FakeFiles()


class SourceCatalogTests(unittest.TestCase):
    def setUp(self):
        self.workspace = FakeWorkspaceClient()
        self.service = DatabricksVolumeCatalogService(
            (
                VolumeCatalog(
                    id="branch-operations",
                    label="Branch Operations",
                    volume_path="/Volumes/workspace/default/branch_operations_docs",
                    rendition_path="/Volumes/workspace/default/branch_operations_renditions",
                ),
            ),
            workspace_client=self.workspace,
        )

    def test_lists_folders_and_supported_documents_only(self):
        result = self.service.list_children("branch-operations", "", None)

        self.assertEqual(
            [(entry["type"], entry["name"], entry.get("kind")) for entry in result["entries"]],
            [
                ("folder", "archive", None),
                ("document", "Attorneys.xlsx", "excel"),
                ("document", "Lending.docx", "word"),
                ("document", "policy.pdf", "pdf"),
            ],
        )

    def test_open_document_reports_kind(self):
        for path, kind in (("a.pdf", "pdf"), ("b/c.docx", "word"), ("d.XLSX", "excel"), ("e.xls", "excel")):
            with self.subTest(path=path):
                self.assertEqual(
                    self.service.open_document("branch-operations", path)["kind"], kind
                )

    def test_rejects_unsupported_document_types(self):
        with self.assertRaises(InvalidSourcePathError):
            self.service.open_document("branch-operations", "notes.txt")

    def test_rendition_is_read_from_the_same_relative_path(self):
        self.service.download_rendition("branch-operations", "Collections/Legal/Policy.docx")

        self.assertEqual(
            self.workspace.files.downloaded,
            "/Volumes/workspace/default/branch_operations_renditions/Collections/Legal/Policy.docx.pdf",
        )

    def test_rendition_only_exists_for_word_documents(self):
        with self.assertRaises(InvalidSourcePathError):
            self.service.download_rendition("branch-operations", "policy.pdf")

    def test_missing_file_raises_not_found(self):
        self.workspace.files.missing.add(
            "/Volumes/workspace/default/branch_operations_renditions/Policy.docx.pdf"
        )

        with self.assertRaises(SourceDocumentNotFoundError):
            self.service.download_rendition("branch-operations", "Policy.docx")

    def test_searches_pdf_names_recursively(self):
        result = self.service.search("retention")

        self.assertEqual(result["results"][0]["path"], "archive/retention.pdf")

    def test_rejects_paths_outside_allowlisted_volume(self):
        for path in ("../secret.pdf", "/absolute.pdf", "folder\\secret.pdf"):
            with self.subTest(path=path):
                with self.assertRaises(InvalidSourcePathError):
                    self.service.open_document("branch-operations", path)

    def test_download_uses_validated_absolute_volume_path(self):
        download = self.service.download_document(
            "branch-operations", "archive/retention.pdf"
        )

        self.assertEqual(download.contents.read(), b"%PDF-test")
        self.assertEqual(
            self.workspace.files.downloaded,
            "/Volumes/workspace/default/branch_operations_docs/archive/retention.pdf",
        )


if __name__ == "__main__":
    unittest.main()
