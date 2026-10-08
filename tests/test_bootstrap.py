import unittest
from unittest.mock import patch

from mariner_genai_dbx.bootstrap import create_supervisor_service
from mariner_genai_dbx.config import Settings
from mariner_genai_dbx.supervisor_service import DatabricksSupervisorService


class BootstrapTests(unittest.TestCase):
    @patch("mariner_genai_dbx.bootstrap.create_workspace_client")
    def test_databricks_mode_uses_canonical_streaming_supervisor(
        self, create_workspace_client
    ):
        settings = Settings(
            supervisor_mode="databricks",
            databricks_host="https://workspace.example.test",
            databricks_client_id="client-id",
            databricks_client_secret="client-secret",
            supervisor_endpoint="supervisor",
        )

        service = create_supervisor_service(settings)

        self.assertIsInstance(service, DatabricksSupervisorService)
        create_workspace_client.assert_called_once()


if __name__ == "__main__":
    unittest.main()
