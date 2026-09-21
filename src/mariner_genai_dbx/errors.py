"""Application-specific errors with no provider details in public responses."""


class ConfigurationError(ValueError):
    """Application configuration is missing or unsafe."""


class InvalidQuestionError(ValueError):
    """The submitted question is invalid."""


class DatabricksAuthenticationError(Exception):
    """Databricks rejected or could not load the configured identity."""


class SupervisorInvocationError(Exception):
    """The multi-agent Supervisor could not complete a request."""


class ReadinessCheckError(Exception):
    """The backend readiness check could not be completed."""


class ConversationPersistenceError(Exception):
    """Conversation history is unavailable."""


class CitationResolutionError(Exception):
    """An approved citation label could not be resolved safely."""


class SourceCatalogError(Exception):
    """The approved document catalog is unavailable."""


class InvalidSourcePathError(ValueError):
    """A document path is invalid or outside its approved root."""
