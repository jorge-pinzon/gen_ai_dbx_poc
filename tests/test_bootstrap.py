import unittest
from unittest.mock import patch

from mariner_genai_dbx.bootstrap import (
    create_analytics_service, create_source_catalog_service, create_supervisor_service,
    shared_workspace_client,
)
from mariner_genai_dbx.analytics import BackgroundAnalyticsService, DatabricksAnalyticsService
from mariner_genai_dbx.config import Settings
from mariner_genai_dbx.models import VolumeCatalog
from mariner_genai_dbx.supervisor_service import DatabricksSupervisorService


class BootstrapTests(unittest.TestCase):
    @patch("mariner_genai_dbx.bootstrap.create_workspace_client")
    def test_poc_performance_fast_path_wraps_without_querying(self, make_client):
        from mariner_genai_dbx.performance_fast_path import PerformanceFastPathService
        service = create_supervisor_service(Settings(
            supervisor_mode="databricks", databricks_host="https://workspace.example.test",
            databricks_client_id="client", databricks_client_secret="secret",
            supervisor_endpoint="supervisor", databricks_warehouse_id="warehouse",
            performance_fast_path_enabled=True))
        self.assertIsInstance(service, PerformanceFastPathService)
        self.assertIsInstance(service.supervisor, DatabricksSupervisorService)
        make_client.return_value.statement_execution.execute_statement.assert_not_called()

    @patch("mariner_genai_dbx.bootstrap.create_workspace_client")
    def test_registry_wiring_is_opt_in_and_does_not_query_at_construction(self, make_client):
        service = create_supervisor_service(Settings(
            supervisor_mode="databricks", databricks_host="https://workspace.example.test",
            databricks_client_id="client", databricks_client_secret="secret",
            supervisor_endpoint="supervisor", databricks_warehouse_id="warehouse",
            citation_registry_table="main.docs.registry",
            volume_catalogs=(VolumeCatalog("docs", "Docs", "/Volumes/main/docs"),)))
        self.assertIsNotNone(service._citation_resolver._registry)
        self.assertIsNone(service._citation_resolver._registry._worker)
        make_client.return_value.statement_execution.execute_statement.assert_not_called()

    @patch("mariner_genai_dbx.bootstrap.create_workspace_client")
    def test_live_analytics_is_delivered_in_background(self, create_workspace_client):
        settings = Settings(
            supervisor_mode="databricks",
            databricks_host="https://workspace.example.test",
            databricks_client_id="client-id",
            databricks_client_secret="client-secret",
            supervisor_endpoint="supervisor",
            databricks_warehouse_id="warehouse",
        )
        service = create_analytics_service(settings)
        self.assertIsInstance(service, BackgroundAnalyticsService)
        self.assertIsInstance(service._service, DatabricksAnalyticsService)
        create_workspace_client.assert_called_once()

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

    @patch("mariner_genai_dbx.bootstrap.create_workspace_client")
    def test_services_share_one_workspace_client(self, create_workspace_client):
        settings = Settings(
            supervisor_mode="databricks", databricks_host="https://workspace.example.test",
            databricks_client_id="client", databricks_client_secret="secret",
            supervisor_endpoint="supervisor", databricks_warehouse_id="warehouse",
            performance_fast_path_enabled=True,
            volume_catalogs=(VolumeCatalog("docs", "Docs", "/Volumes/main/docs"),))
        factory = shared_workspace_client(settings)
        supervisor = create_supervisor_service(settings, workspace_client_factory=factory)
        create_analytics_service(settings, workspace_client_factory=factory)
        create_source_catalog_service(settings, workspace_client_factory=factory)
        create_workspace_client.assert_called_once()
        self.assertEqual(supervisor._post, supervisor.supervisor._http.post)

    @patch("mariner_genai_dbx.bootstrap.create_workspace_client")
    def test_mock_mode_never_builds_a_client(self, create_workspace_client):
        factory = shared_workspace_client(Settings())
        create_supervisor_service(Settings(), workspace_client_factory=factory)
        create_analytics_service(Settings(), workspace_client_factory=factory)
        create_workspace_client.assert_not_called()


if __name__ == "__main__":
    unittest.main()
