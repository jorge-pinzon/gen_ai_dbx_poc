"""Application dependency construction."""

from .analytics import DatabricksAnalyticsService, NullAnalyticsService

from .config import Settings
from .citation_resolver import DatabricksCitationResolver, NullCitationResolver
from .conversation_store import ConversationPersistence, InMemoryConversationStore
from .source_catalog import DatabricksVolumeCatalogService
from .supervisor_service import (
    DatabricksSupervisorService,
    MockSupervisorService,
    create_workspace_client,
)


def create_supervisor_service(settings: Settings):
    if settings.supervisor_mode == "mock":
        return MockSupervisorService()
    supervisor_config = settings.supervisor_config()
    workspace_client = create_workspace_client(supervisor_config)
    citation_resolver = NullCitationResolver()
    if settings.databricks_warehouse_id:
        citation_resolver = DatabricksCitationResolver(
            workspace_client=workspace_client,
            warehouse_id=settings.databricks_warehouse_id,
            tables=settings.citation_tables,
            timeout_seconds=settings.request_timeout_seconds,
        )
    return DatabricksSupervisorService(
        supervisor_config,
        citation_resolver=citation_resolver,
    )


def create_conversation_persistence(settings: Settings) -> ConversationPersistence:
    return ConversationPersistence(
        InMemoryConversationStore(
            history_limit=settings.chat_history_limit,
            ttl_seconds=settings.chat_session_ttl_seconds,
        )
    )


def create_analytics_service(settings: Settings):
    if settings.supervisor_mode != "databricks" or not settings.databricks_warehouse_id:
        return NullAnalyticsService()
    return DatabricksAnalyticsService(
        workspace_client=create_workspace_client(settings.supervisor_config()),
        warehouse_id=settings.databricks_warehouse_id,
        table_name=settings.databricks_log_table,
    )


def create_source_catalog_service(settings: Settings):
    if not settings.volume_catalogs:
        return None
    workspace_client = create_workspace_client(settings.supervisor_config())
    return DatabricksVolumeCatalogService(
        settings.volume_catalogs,
        workspace_client=workspace_client,
    )
