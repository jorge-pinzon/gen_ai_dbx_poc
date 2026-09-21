import io
import unittest
from types import SimpleNamespace

from mariner_genai_dbx.errors import InvalidSourcePathError
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
            ],
            "/Volumes/workspace/default/branch_operations_docs/archive": [
                SimpleNamespace(
                    path="/Volumes/workspace/default/branch_operations_docs/archive/retention.pdf",
                    is_directory=False,
                )
            ],
        }
        self.downloaded = None

    def list_directory_contents(self, directory_path):
        return self.directories.get(directory_path, [])

    def download(self, file_path):
        self.downloaded = file_path
        return SimpleNamespace(
            contents=io.BytesIO(b"%PDF-test"),
            content_length=9,
            last_modified=None,
        )


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
                ),
            ),
            workspace_client=self.workspace,
        )

    def test_lists_only_folders_and_pdf_documents(self):
        result = self.service.list_children("branch-operations", "", None)

        self.assertEqual(
            [(entry["type"], entry["name"]) for entry in result["entries"]],
            [("folder", "archive"), ("document", "policy.pdf")],
        )

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
