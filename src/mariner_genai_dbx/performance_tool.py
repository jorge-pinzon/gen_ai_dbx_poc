"""Framework-neutral agent tool adapter; authorization is not a model argument."""

from .performance_retrieval import (
    DATASETS, LIST_FIELDS, PerformanceAccessScope, PerformanceQuery, PerformanceScopeError,
)


PERFORMANCE_TOOL = {
    "type": "function",
    "name": "retrieve_performance_data",
    "description": (
        "Retrieve authorized employee ratings/history, loan production, goals, competencies, "
        "review compliance, and branch summaries in one batch. Use employee, branch, region, "
        "and quarter filters; request only the needed datasets. Batch all people in the request "
        "in one call. Returns observed data and missing-period indicators, not policy or ratings "
        "decisions. Ask for clarification on ambiguous names. Use the existing analytical "
        "fallback for unsupported arbitrary analytics; do not invent SQL."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            **{name: {"type": "array", "items": {"type": "string"}, "maxItems": 100}
               for name in LIST_FIELDS},
            "datasets": {"type": "array", "items": {"type": "string", "enum": list(DATASETS)},
                         "minItems": 1, "maxItems": len(DATASETS)},
            "latest_cycles": {"type": "integer", "minimum": 1, "maximum": 20},
            "max_employees": {"type": "integer", "minimum": 1, "maximum": 100},
            "max_branches": {"type": "integer", "minimum": 1, "maximum": 100},
        },
        "additionalProperties": False,
    },
}


class PerformanceDataTool:
    def __init__(self, retriever, *, scope_provider):
        """scope_provider resolves an authenticated principal's existing entitlements.

        Bind principal_id from server authentication/tool context, not from a tool
        argument, browser claim, generated SQL, employee name or branch filter.
        """
        self.retriever = retriever
        self.scope_provider = scope_provider

    def execute(self, arguments, *, principal_id):
        allowed = PERFORMANCE_TOOL["parameters"]["properties"]
        if not isinstance(arguments, dict) or set(arguments).difference(allowed):
            raise ValueError("Unsupported retrieval arguments")
        if not isinstance(principal_id, str) or not principal_id.strip():
            raise PerformanceScopeError("Authenticated principal required")
        query = PerformanceQuery(**arguments)
        scope = self.scope_provider(principal_id)
        if not isinstance(scope, PerformanceAccessScope):
            raise PerformanceScopeError("Trusted authorization scope is unavailable")
        return self.retriever.retrieve(query, scope=scope)
