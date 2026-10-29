"""Application dependency construction."""

from .analytics import (
    BackgroundAnalyticsService,
    DatabricksAnalyticsService,
    NullAnalyticsService,
)

from .config import Settings
from .citation_resolver import DatabricksCitationResolver, NullCitationResolver
from .citation_registry import CitationRegistry
from .conversation_store import ConversationPersistence, InMemoryConversationStore
from .source_catalog import DatabricksVolumeCatalogService
from .supervisor_service import (
    DatabricksSupervisorService,
    MockSupervisorService,
    create_workspace_client,
)


def shared_workspace_client(settings: Settings):
    """Return a factory that builds one WorkspaceClient on first use and reuses it.

    One client means one OAuth token and one connection pool for the supervisor,
    analytics and source catalog instead of three of each.
    """
    clients = []

    def factory():
        if not clients:
            clients.append(create_workspace_client(settings.supervisor_config()))
        return clients[0]

    return factory


def _client_factory(settings: Settings, workspace_client_factory):
    return workspace_client_factory or (
        lambda: create_workspace_client(settings.supervisor_config())
    )


def create_supervisor_service(settings: Settings, *, workspace_client_factory=None):
    if settings.supervisor_mode == "mock":
        return MockSupervisorService()
    supervisor_config = settings.supervisor_config()
    workspace_client = _client_factory(settings, workspace_client_factory)()
    citation_resolver = NullCitationResolver()
    if settings.databricks_warehouse_id:
        registry = None
        if settings.citation_registry_table:
            registry = CitationRegistry(
                workspace_client=workspace_client,
                warehouse_id=settings.databricks_warehouse_id,
                table_name=settings.citation_registry_table,
                volume_roots=[catalog.volume_path for catalog in settings.volume_catalogs],
                ttl_seconds=settings.citation_registry_ttl_seconds,
                timeout_seconds=settings.citation_registry_timeout_seconds,
            )
        citation_resolver = DatabricksCitationResolver(
            workspace_client=workspace_client,
            warehouse_id=settings.databricks_warehouse_id,
            tables=settings.citation_tables,
            timeout_seconds=settings.request_timeout_seconds,
            registry=registry,
            preload_chunks=True,
        )
    supervisor = DatabricksSupervisorService(
        supervisor_config,
        citation_resolver=citation_resolver,
    )
    if settings.performance_fast_path_enabled:
        from .performance_retrieval import PerformanceRetriever
        from .performance_fast_path import PerformanceFastPathService
        return PerformanceFastPathService(
            supervisor,
            retriever=PerformanceRetriever(workspace_client=workspace_client,
                warehouse_id=settings.databricks_warehouse_id, timeout_seconds=25,
                policy_registry_table=settings.citation_registry_table,
                view_prefix=settings.performance_view_prefix),
            model_endpoint=settings.performance_fast_model_endpoint,
            synthesis_model_endpoint=settings.performance_synthesis_model_endpoint,
        )
    return supervisor


def create_conversation_persistence(settings: Settings) -> ConversationPersistence:
    return ConversationPersistence(
        InMemoryConversationStore(
            history_limit=settings.chat_history_limit,
            ttl_seconds=settings.chat_session_ttl_seconds,
        )
    )


def create_analytics_service(settings: Settings, *, workspace_client_factory=None):
    if settings.supervisor_mode != "databricks" or not settings.databricks_warehouse_id:
        return NullAnalyticsService()
    return BackgroundAnalyticsService(
        DatabricksAnalyticsService(
            workspace_client=_client_factory(settings, workspace_client_factory)(),
            warehouse_id=settings.databricks_warehouse_id,
            table_name=settings.databricks_log_table,
            stage_timings=settings.analytics_stage_timings,
        )
    )


def create_coaching360_service(settings: Settings, *, workspace_client_factory=None):
    if not settings.coaching360_enabled:
        return None
    from .coaching360 import Coaching360Service
    return Coaching360Service(
        workspace_client=_client_factory(settings, workspace_client_factory)(),
        warehouse_id=settings.databricks_warehouse_id,
        ttl_seconds=settings.chat_session_ttl_seconds,
    )


def create_document_search_service(settings: Settings, *, workspace_client_factory=None):
    """Keyword search inside the approved chunk tables, for the document reader."""
    if not settings.volume_catalogs or not settings.databricks_warehouse_id:
        return None
    from .document_search import DocumentTextSearch
    return DocumentTextSearch(DatabricksCitationResolver(
        workspace_client=_client_factory(settings, workspace_client_factory)(),
        warehouse_id=settings.databricks_warehouse_id,
        tables=settings.citation_tables,
        timeout_seconds=settings.request_timeout_seconds,
        preload_chunks=True,
    ))


def create_source_catalog_service(settings: Settings, *, workspace_client_factory=None):
    if not settings.volume_catalogs:
        return None
    workspace_client = _client_factory(settings, workspace_client_factory)()
    return DatabricksVolumeCatalogService(
        settings.volume_catalogs,
        workspace_client=workspace_client,
    )
