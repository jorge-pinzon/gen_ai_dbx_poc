import unittest

from werkzeug.security import generate_password_hash

from mariner_genai_dbx.config import load_settings
from mariner_genai_dbx.errors import ConfigurationError


class ConfigurationTests(unittest.TestCase):
    def test_performance_fast_path_requires_explicit_valid_configuration(self):
        self.assertFalse(load_settings(environ={}).performance_fast_path_enabled)
        with self.assertRaisesRegex(ConfigurationError, 'must be true or false'):
            load_settings(environ={'PERFORMANCE_FAST_PATH_ENABLED': 'yes'})
        with self.assertRaisesRegex(ConfigurationError, 'requires Databricks'):
            load_settings(environ={'PERFORMANCE_FAST_PATH_ENABLED': 'true'})
        with self.assertRaisesRegex(ConfigurationError, 'POC fast path'):
            load_settings(environ={'PERFORMANCE_FAST_PATH_ENABLED': 'true', 'APP_ENV': 'production'})

    def test_performance_view_prefix_defaults_to_live_views_and_is_allowlisted(self):
        self.assertEqual(load_settings(environ={}).performance_view_prefix, 'app_vw_')
        self.assertEqual(load_settings(environ={'PERFORMANCE_VIEW_PREFIX': 'app_fast_'}).performance_view_prefix,
                         'app_fast_')
        with self.assertRaisesRegex(ConfigurationError, 'PERFORMANCE_VIEW_PREFIX'):
            load_settings(environ={'PERFORMANCE_VIEW_PREFIX': 'app_x_'})

    def test_direct_specialist_routes_are_parsed_and_validated(self):
        self.assertEqual(load_settings(environ={}).direct_specialist_routes, ())
        settings = load_settings(environ={'DIRECT_SPECIALIST_ROUTES_JSON':
            '{"/policy": {"endpoint": "ka-1-endpoint", "api": "responses", "agent": "mariner-policy-assistant"}}'})
        [(command, route)] = settings.direct_specialist_routes
        self.assertEqual((command, route.endpoint, route.api), ('/policy', 'ka-1-endpoint', 'responses'))
        for bad in ('[]', '{"/other": {"endpoint": "e", "api": "chat", "agent": "a"}}',
                    '{"/policy": {"endpoint": "e/../x", "api": "chat", "agent": "a"}}',
                    '{"/policy": {"endpoint": "e", "api": "rpc", "agent": "a"}}', 'not json'):
            with self.assertRaises(ConfigurationError):
                load_settings(environ={'DIRECT_SPECIALIST_ROUTES_JSON': bad})

    def test_registry_requires_warehouse_and_approved_catalogs(self):
        with self.assertRaisesRegex(ConfigurationError, "registry requires"):
            load_settings(environ={"DATABRICKS_CITATION_REGISTRY_TABLE": "main.docs.registry"})

    def test_registry_rejects_unsafe_table_identifier(self):
        with self.assertRaisesRegex(ConfigurationError, "fully qualified"):
            load_settings(environ={"DATABRICKS_CITATION_REGISTRY_TABLE": "main.docs.registry;DROP"})

    def test_development_defaults_to_safe_mock_mode(self):
        settings = load_settings(environ={})

        self.assertEqual(settings.auth_mode, "local")
        self.assertEqual(settings.supervisor_mode, "mock")
        self.assertEqual(settings.log_level, "INFO")

    def test_rejects_invalid_log_level(self):
        with self.assertRaisesRegex(ConfigurationError, "LOG_LEVEL"):
            load_settings(environ={"LOG_LEVEL": "verbose"})

    def test_databricks_mode_requires_workspace_and_endpoint(self):
        with self.assertRaisesRegex(ConfigurationError, "DATABRICKS_HOST"):
            load_settings(environ={"SUPERVISOR_MODE": "databricks"})

    def test_databricks_mode_requires_oauth_client_credentials(self):
        with self.assertRaisesRegex(ConfigurationError, "DATABRICKS_CLIENT_ID"):
            load_settings(
                environ={
                    "SUPERVISOR_MODE": "databricks",
                    "DATABRICKS_HOST": "https://workspace.example.test",
                    "DATABRICKS_SUPERVISOR_ENDPOINT": "supervisor",
                }
            )

    def test_reads_supervisor_m2m_configuration(self):
        settings = load_settings(
            environ={
                "SUPERVISOR_MODE": "databricks",
                "DATABRICKS_HOST": "https://workspace.example.test",
                "DATABRICKS_CLIENT_ID": "client-id",
                "DATABRICKS_CLIENT_SECRET": "client-secret",
                "DATABRICKS_SUPERVISOR_ENDPOINT": "supervisor",
            }
        )

        supervisor = settings.supervisor_config()
        self.assertEqual(supervisor.endpoint_name, "supervisor")
        self.assertEqual(supervisor.client_id, "client-id")

    def test_password_mode_requires_hashed_credentials_and_session_secret(self):
        with self.assertRaisesRegex(ConfigurationError, "LOGIN_USERNAME"):
            load_settings(environ={"AUTH_MODE": "password"})

        settings = load_settings(
            environ={
                "AUTH_MODE": "password",
                "LOGIN_USERNAME": "prototype-user",
                "LOGIN_PASSWORD_HASH": generate_password_hash("prototype-password"),
                "SESSION_SECRET_KEY": "test-session-secret-key-with-32-characters",
            }
        )

        self.assertEqual(settings.auth_mode, "password")

    def test_volume_catalogs_use_approved_volume_paths(self):
        settings = load_settings(
            environ={
                "VOLUME_CATALOGS_JSON": (
                    '[{"id":"handbook","label":"Employee handbook",'
                    '"volumePath":"/Volumes/main/hr/handbook"}]'
                )
            }
        )

        self.assertEqual(settings.volume_catalogs[0].id, "handbook")

    def test_target_chunk_tables_are_configured(self):
        settings = load_settings(
            environ={"DATABRICKS_WAREHOUSE_ID": "55cdb78d4d2a62d0"}
        )

        self.assertEqual(settings.databricks_warehouse_id, "55cdb78d4d2a62d0")
        self.assertEqual(
            [table.table_name for table in settings.citation_tables],
            [
                "workspace.default.branch_operations_chunks",
                "workspace.default.employee_handbook_chunks",
                "workspace.default.benefits_chunks",
                "workspace.performance_test.app_policy_chunks",
            ],
        )

        performance_policy = settings.citation_tables[-1]
        self.assertEqual(performance_policy.domain, "Employee Performance Policy")
        self.assertEqual(performance_policy.document_title_column, "document_name")
        self.assertEqual(performance_policy.volume_path_column, "source_volume_path")
        self.assertEqual(performance_policy.page_number_column, "page_start")
        self.assertEqual(performance_policy.chunk_text_column, "chunk_text")
        self.assertIsNone(performance_policy.page_number_pattern)
        self.assertIn(
            (
                "Employee Performance Management Policy",
                "INSTRUCTIONS_PERFORMANCE.pdf",
            ),
            performance_policy.source_label_aliases,
        )

    def test_reads_analytics_configuration(self):
        settings = load_settings(
            environ={
                "APP_VERSION": "2026.09.17",
                "DATABRICKS_LOG_TABLE": "workspace.default.flask_app_logs",
            }
        )

        self.assertEqual(settings.app_version, "2026.09.17")
        self.assertEqual(
            settings.databricks_log_table, "workspace.default.flask_app_logs"
        )

    def test_production_rejects_mock_mode_and_personal_token(self):
        with self.assertRaisesRegex(ConfigurationError, "AUTH_MODE"):
            load_settings(environ={"APP_ENV": "production"})

        with self.assertRaisesRegex(ConfigurationError, "workload identity"):
            load_settings(
                environ={
                    "APP_ENV": "production",
                    "AUTH_MODE": "databricks",
                    "SUPERVISOR_MODE": "databricks",
                    "DATABRICKS_HOST": "https://workspace.example.test",
                    "DATABRICKS_TOKEN": "not-allowed",
                    "SUPERVISOR_ENDPOINT": "supervisor",
                }
            )


if __name__ == "__main__":
    unittest.main()
