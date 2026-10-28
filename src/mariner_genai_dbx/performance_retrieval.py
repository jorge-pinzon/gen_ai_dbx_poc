"""General, read-only performance retrieval without question-to-SQL generation.

    Access scopes come from authenticated server-side authorization, never from
    model arguments. Existing Unity Catalog checks still apply to every query.
    This module does not change Flask routing or grant access to any resource.
"""

from __future__ import annotations

import json
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from decimal import Decimal

from .citation_resolver import _field, _nested_field, _statement_state, _string_parameter


class PerformanceRetrievalError(Exception):
    pass


class PerformanceScopeError(PerformanceRetrievalError):
    pass


class PerformanceSelectionError(PerformanceRetrievalError):
    """Clarification or a narrower supported selection is needed."""

    def __init__(self, message, *, candidates=()):
        super().__init__(message)
        self.candidates = tuple(candidates)


# Identifiers and projections are code-owned. No model-supplied SQL, identifiers,
# contact details, joins or aggregate expressions are accepted.
PROFILE_COLUMNS = (
    "employee_id", "employee_name", "job_role_name", "branch_id", "branch_name",
    "region_id", "region_name", "manager_employee_id", "manager_name", "employment_status",
)
DATASETS = {
    "history": ("app_vw_employee_performance_history", (
        "employee_id", "employee_name", "cycle_id", "cycle_name", "final_rating",
        "rating_rationale", "review_status", "target_amount", "funded_amount",
        "funded_loan_count", "attainment_percent", "loan_rating", "meeting_status",
        "acknowledgment_status", "avg_competency_rating", "active_goal_count", "avg_goal_completion",
    )),
    "loans": ("app_vw_employee_performance_history", (
        "employee_id", "employee_name", "cycle_id", "cycle_name", "target_amount",
        "funded_amount", "funded_loan_count", "attainment_percent", "loan_rating",
    )),
    "goals": ("app_vw_employee_goal_status", (
        "employee_id", "employee_name", "cycle_id", "cycle_name", "goal_id", "goal_type",
        "goal_title", "goal_description", "goal_status", "completion_percent",
        "goal_start_date", "goal_due_date", "progress_date", "progress_note",
    )),
    "competencies": ("app_vw_employee_competency_summary", (
        "employee_id", "employee_name", "cycle_id", "cycle_name", "competency_id",
        "competency_name", "competency_rating", "rating_label", "rating_date",
    )),
    "reviews": ("app_vw_review_compliance", (
        "employee_id", "employee_name", "cycle_id", "cycle_name", "review_status",
        "review_due_date", "is_overdue", "meeting_status", "meeting_date",
        "is_missing_meeting", "acknowledgment_status", "is_missing_acknowledgment",
    )),
    "branch_summary": ("app_vw_branch_quarterly_summary", (
        "branch_id", "branch_name", "region_id", "region_name", "cycle_id", "cycle_name",
        "employee_count", "total_target", "total_funded_amount", "branch_attainment_pct",
        "funded_loan_count", "avg_rating", "rating_1_count", "rating_2_count", "rating_3_count",
        "rating_4_count", "rating_5_count", "completed_review_count", "missing_review_count",
    )),
}
# app_vw_* are the live views; app_fast_* are their materialized copies
# (sql/create_performance_fast_views.sql). Only these code-owned prefixes are accepted.
VIEW_PREFIXES = ("app_vw_", "app_fast_")
LIST_FIELDS = ("employee_ids", "employee_names", "branch_ids", "branch_names", "region_ids", "region_names", "cycle_ids")


def _strings(values, field_name, maximum=100):
    if not isinstance(values, (list, tuple)) or len(values) > maximum:
        raise ValueError(f"Invalid {field_name}")
    if any(not isinstance(v, str) or not v.strip() or len(v) > 200 for v in values):
        raise ValueError(f"Invalid {field_name}")
    return tuple(dict.fromkeys(v.strip() for v in values))


@dataclass(frozen=True)
class PerformanceAccessScope:
    """Trusted allowlists, resolved by server code from the authenticated identity.

    Branch-summary permission and employee-detail permission are independent.
    A model may not choose or enlarge either list.
    """

    employee_ids: tuple[str, ...] = field(default=(), repr=False)
    branch_ids: tuple[str, ...] = field(default=(), repr=False)
    use_catalog_visibility: bool = False

    def __post_init__(self):
        if type(self.use_catalog_visibility) is not bool:
            raise ValueError("Invalid catalog visibility scope")
        for name in ("employee_ids", "branch_ids"):
            object.__setattr__(self, name, _strings(getattr(self, name), name, 10000))


@dataclass(frozen=True)
class PerformanceQuery:
    employee_ids: tuple[str, ...] = ()
    employee_names: tuple[str, ...] = ()
    branch_ids: tuple[str, ...] = ()
    branch_names: tuple[str, ...] = ()
    region_ids: tuple[str, ...] = ()
    region_names: tuple[str, ...] = ()
    cycle_ids: tuple[str, ...] = ()
    datasets: tuple[str, ...] = ("history",)
    latest_cycles: int = 5
    max_employees: int = 50
    max_branches: int = 50
    include_latest_history: bool = False

    def __post_init__(self):
        if type(self.include_latest_history) is not bool:
            raise ValueError("Invalid history context flag")
        for name in LIST_FIELDS:
            object.__setattr__(self, name, _strings(getattr(self, name), name))
        datasets = _strings(self.datasets, "datasets", len(DATASETS))
        if not datasets or set(datasets).difference(DATASETS):
            raise ValueError("Unsupported datasets; use the existing analytical fallback")
        object.__setattr__(self, "datasets", datasets)
        for name, maximum in (("latest_cycles", 20), ("max_employees", 100), ("max_branches", 100)):
            value = getattr(self, name)
            if type(value) is not int or not 1 <= value <= maximum:
                raise ValueError(f"Invalid {name}")
        if any(not re.fullmatch(r"CY\d{4}Q[1-4]", value) for value in self.cycle_ids):
            raise ValueError("Cycle IDs must use CYyyyyQn")


def _json_record(alias, columns):
    fields = ", ".join(f"'{column}', {alias}.`{column}`" for column in columns)
    return f"TO_JSON(NAMED_STRUCT({fields}), MAP('ignoreNullFields', 'false'))"


def _filter(alias, field_name, parameter, *, casefold=False):
    column = f"{alias}.`{field_name}`"
    column = f"LOWER({column})" if casefold else column
    return f"(size({parameter}) = 0 OR array_contains({parameter}, {column}))"


def _view(name, prefix):
    if prefix not in VIEW_PREFIXES:
        raise ValueError("Unsupported performance view prefix")
    return "workspace.performance_test." + prefix + name.removeprefix("app_vw_")


def build_performance_query(query: PerformanceQuery, scope: PerformanceAccessScope, *, max_rows=2000,
                            policy_registry_table=None, include_policy=False, include_data=True,
                            view_prefix="app_vw_"):
    """Return one SQL statement and bound parameters for any supported selection."""
    if not isinstance(scope, PerformanceAccessScope):
        raise PerformanceScopeError("A trusted access scope is required")
    if not 1 <= max_rows <= 10000:
        raise ValueError("Invalid row limit")
    needs_employees = include_data and (any(d != "branch_summary" for d in query.datasets) or bool(query.employee_ids or query.employee_names))
    needs_branches = include_data and "branch_summary" in query.datasets
    if needs_employees and not scope.employee_ids and not scope.use_catalog_visibility:
        raise PerformanceScopeError("No authorized employee-detail scope")
    if needs_branches and not scope.branch_ids and not scope.use_catalog_visibility:
        raise PerformanceScopeError("No authorized branch-summary scope")
    if not scope.use_catalog_visibility and set(query.employee_ids).difference(scope.employee_ids):
        raise PerformanceScopeError("Employee selection outside authorized scope")
    if needs_branches and not scope.use_catalog_visibility and set(query.branch_ids).difference(scope.branch_ids):
        raise PerformanceScopeError("Branch selection outside authorized scope")

    values = {name: list(getattr(query, name)) for name in LIST_FIELDS}
    for name in ("employee_names", "branch_names", "region_names"):
        values[name] = [v.lower() for v in values[name]]
    values.update(authorized_employees=list(scope.employee_ids), authorized_branches=list(scope.branch_ids))
    fields = [f"from_json(:{name}, 'ARRAY<STRING>') AS {name}" for name in values]
    ctes = ["args AS (SELECT " + ", ".join(fields) + ")"]
    records = []
    employee_count = "0"
    branch_count = "0"

    if needs_employees:
        filters = [
            "TRUE" if scope.use_catalog_visibility else "array_contains(a.authorized_employees, p.employee_id)",
            "((size(a.employee_ids) = 0 AND size(a.employee_names) = 0) "
            "OR array_contains(a.employee_ids, p.employee_id) OR array_contains(a.employee_names, LOWER(p.employee_name)))",
        ]
        filters += [_filter("p", name, f"a.{name}s", casefold=name.endswith("name"))
                    for name in ("branch_id", "branch_name", "region_id", "region_name")]
        projection = ", ".join(f"p.`{column}`" for column in PROFILE_COLUMNS)
        ctes.append("selected_profiles AS (SELECT " + projection +
                    " FROM " + _view("employee_profile", view_prefix) + " p CROSS JOIN args a WHERE " +
                    " AND ".join(filters) + f" ORDER BY p.employee_id LIMIT {query.max_employees + 1})")
        employee_count = "(SELECT COUNT(*) FROM selected_profiles)"
        ctes.append(f"bounded_profiles AS (SELECT * FROM selected_profiles WHERE {employee_count} <= {query.max_employees})")
        ctes.append("ranked_cycles AS (SELECT q.employee_id, q.cycle_id, q.cycle_name, q.cycle_end_date, q.final_rating, "
                    "ROW_NUMBER() OVER (PARTITION BY q.employee_id ORDER BY q.cycle_end_date DESC, "
                    "q.completed_date DESC NULLS LAST, q.cycle_id DESC) AS cycle_rank "
                    "FROM " + _view("employee_quarterly_performance", view_prefix) + " q "
                    "JOIN bounded_profiles p ON q.employee_id = p.employee_id)")
        ctes.append("selected_cycles AS (SELECT q.* FROM ranked_cycles q CROSS JOIN args a WHERE "
                    f"(size(a.cycle_ids) = 0 AND q.cycle_rank <= {query.latest_cycles}) "
                    "OR (size(a.cycle_ids) > 0 AND array_contains(a.cycle_ids, q.cycle_id))" +
                    (f" OR q.cycle_rank <= {query.latest_cycles}" if query.include_latest_history else "") + ")")
        records.append("SELECT 'profiles' AS record_type, " + _json_record("p", PROFILE_COLUMNS) + " AS record_json FROM bounded_profiles p")
        records.append("SELECT 'cycles' AS record_type, " + _json_record("q", (
            "employee_id", "cycle_id", "cycle_name", "cycle_end_date", "final_rating")) + " AS record_json FROM selected_cycles q")
        records.append("SELECT 'availability' AS record_type, " + _json_record("q", (
            "employee_id", "cycle_id", "cycle_name", "cycle_end_date", "final_rating")) +
            " AS record_json FROM ranked_cycles q WHERE cycle_rank = 1")

    if needs_branches:
        filters = ["TRUE" if scope.use_catalog_visibility else "array_contains(a.authorized_branches, b.branch_id)"]
        filters += [_filter("b", name, f"a.{name}s", casefold=name.endswith("name"))
                    for name in ("branch_id", "branch_name", "region_id", "region_name")]
        if query.employee_ids or query.employee_names:
            filters.append("b.branch_id IN (SELECT branch_id FROM bounded_profiles)")
        ctes.append("selected_branches AS (SELECT DISTINCT b.branch_id FROM " +
                    _view("branch_quarterly_summary", view_prefix) + " b CROSS JOIN args a WHERE " +
                    " AND ".join(filters) + f" ORDER BY b.branch_id LIMIT {query.max_branches + 1})")
        branch_count = "(SELECT COUNT(*) FROM selected_branches)"
        ctes.append("ranked_branches AS (SELECT b.*, ROW_NUMBER() OVER (PARTITION BY b.branch_id "
                    "ORDER BY b.cycle_id DESC) AS cycle_rank FROM " +
                    _view("branch_quarterly_summary", view_prefix) + " b JOIN selected_branches s "
                    f"ON b.branch_id = s.branch_id WHERE {branch_count} <= {query.max_branches})")
        records.append("SELECT 'branch_availability' AS record_type, " + _json_record("b", (
            "branch_id", "branch_name", "region_id", "region_name", "cycle_id", "cycle_name")) +
            " AS record_json FROM ranked_branches b WHERE cycle_rank = 1")

    for dataset in query.datasets if include_data else ():
        view, columns = DATASETS[dataset]
        if dataset == "branch_summary":
            source = "ranked_branches d CROSS JOIN args a"
            condition = f" WHERE (size(a.cycle_ids) = 0 AND d.cycle_rank <= {query.latest_cycles}) "
            condition += "OR (size(a.cycle_ids) > 0 AND array_contains(a.cycle_ids, d.cycle_id))"
            if query.include_latest_history:
                condition += f" OR d.cycle_rank <= {query.latest_cycles}"
        else:
            source = (f"{_view(view, view_prefix)} d JOIN selected_cycles c "
                      "ON d.employee_id = c.employee_id AND d.cycle_id = c.cycle_id")
            condition = ""
        records.append(f"SELECT '{dataset}' AS record_type, " + _json_record("d", columns) +
                       " AS record_json FROM " + source + condition)
    if include_policy:
        records.append(_policy_records(policy_registry_table))
    meta = ("SELECT 'meta' AS record_type, TO_JSON(NAMED_STRUCT("
            f"'selected_employee_count', {employee_count}, 'selected_branch_count', {branch_count}, "
            f"'max_employees', {query.max_employees}, 'max_branches', {query.max_branches}" +
            ")) AS record_json")
    statement = "WITH " + ",\n".join(ctes) + "\nSELECT record_type, record_json FROM (\n" + \
        "\nUNION ALL\n".join([meta, *records]) + f"\n) results ORDER BY record_type, record_json LIMIT {max_rows + 1}"
    parameters = [_string_parameter(name, json.dumps(value)) for name, value in values.items()]
    return statement, parameters


POLICY_COLUMNS = ('document_id', 'document_version', 'chunk_id', 'document_title', 'page_start',
                  'page_end', 'source_volume_path', 'chunk_text')


def _policy_records(policy_registry_table):
    if not policy_registry_table or not re.fullmatch(r'[A-Za-z0-9_]+\.[A-Za-z0-9_]+\.[A-Za-z0-9_]+', policy_registry_table):
        raise ValueError('Approved policy registry required')
    table = '`' + policy_registry_table.replace('.', '`.`') + '`'
    return ("SELECT 'policy' AS record_type, " + _json_record('p', POLICY_COLUMNS) +
            f" AS record_json FROM {table} p WHERE p.domain = 'Employee Performance Policy'")


def build_policy_query(policy_registry_table):
    """Approved policy passages only, in the same record shape and order as the batch query."""
    return _policy_records(policy_registry_table) + " ORDER BY record_json"


class PerformanceRetriever:
    def __init__(self, *, workspace_client, warehouse_id, timeout_seconds=15, max_rows=2000,
                 policy_registry_table=None, policy_ttl_seconds=60, policy_max_stale_seconds=600,
                 view_prefix="app_vw_", clock=time.monotonic, sleep=time.sleep):
        if (not warehouse_id or timeout_seconds <= 0 or not 1 <= max_rows <= 10000
                or view_prefix not in VIEW_PREFIXES):
            raise ValueError("Invalid retrieval configuration")
        self._view_prefix = view_prefix
        self._client = workspace_client
        self._warehouse = warehouse_id
        self._timeout = timeout_seconds
        self._max_rows = max_rows
        self._policy_registry_table = policy_registry_table
        self._clock = clock
        self._sleep = sleep
        # Approved policy passages are shared, rarely change and carry the long
        # chunk text, so they are cached per worker instead of re-read with
        # every data query. Stale passages are never served past the limit.
        self._policy_ttl = policy_ttl_seconds
        self._policy_max_stale = policy_max_stale_seconds
        self._policy = None
        self._policy_loaded_at = None
        self._policy_future = None
        self._policy_lock = threading.Lock()
        self._policy_executor = None

    def retrieve(self, query: PerformanceQuery, *, scope: PerformanceAccessScope, include_policy=False, include_data=True):
        started = self._clock()
        policy = self.policy_passages() if include_policy else []
        if include_data:
            statement, parameters = build_performance_query(query, scope, max_rows=self._max_rows,
                include_policy=False, include_data=True, view_prefix=self._view_prefix)
            rows = self._execute(statement, parameters)
        else:
            # No data SQL is needed: validate the scope as before, then use the
            # meta record the batch query returns when no data is selected.
            build_performance_query(query, scope, include_data=False)
            rows = [["meta", json.dumps({"selected_employee_count": 0, "selected_branch_count": 0,
                                         "max_employees": query.max_employees,
                                         "max_branches": query.max_branches})]]
        result = self._decode(rows, query)
        result["policy"] = policy
        result["retrieval_ms"] = round((self._clock() - started) * 1000, 3)
        return result

    def prefetch_policy(self):
        """Start loading policy passages in the background unless the cache is fresh."""
        if not self._policy_registry_table:
            return
        with self._policy_lock:
            if self._policy_is_fresh() or (self._policy_future and not self._policy_future.done()):
                return
            if self._policy_executor is None:
                # Created lazily so each Gunicorn worker owns its thread after fork.
                self._policy_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="policy")
            self._policy_future = self._policy_executor.submit(self._load_policy)

    def policy_passages(self):
        with self._policy_lock:
            if self._policy_is_fresh():
                return [dict(p) for p in self._policy]
            stale_ok = (self._policy is not None and
                        self._clock() - self._policy_loaded_at <= self._policy_max_stale)
            future = self._policy_future if self._policy_future and not self._policy_future.done() else None
        if stale_ok:
            self.prefetch_policy()
            with self._policy_lock:
                return [dict(p) for p in self._policy]
        if future is not None:
            try:
                future.result(timeout=self._timeout)
            except Exception:
                pass  # retried synchronously below so the error is raised here
            with self._policy_lock:
                if self._policy_is_fresh():
                    return [dict(p) for p in self._policy]
        return [dict(p) for p in self._load_policy()]

    def _policy_is_fresh(self):
        return self._policy is not None and self._clock() - self._policy_loaded_at < self._policy_ttl

    def _load_policy(self):
        rows = self._execute(build_policy_query(self._policy_registry_table), [])
        passages = []
        for row in rows:
            if not isinstance(row, (list, tuple)) or len(row) != 2 or row[0] != "policy":
                raise PerformanceRetrievalError("Invalid policy result")
            data = json.loads(row[1])
            if not isinstance(data, dict):
                raise PerformanceRetrievalError("Invalid policy record")
            passages.append(data)
        with self._policy_lock:
            self._policy = tuple(passages)
            self._policy_loaded_at = self._clock()
        return self._policy

    def _execute(self, statement, parameters):
        started = self._clock()
        statement_id = None
        try:
            response = self._client.statement_execution.execute_statement(
                warehouse_id=self._warehouse, statement=statement, parameters=parameters,
                wait_timeout="10s", row_limit=self._max_rows + 1, byte_limit=2_000_000,
            )
            statement_id = _field(response, "statement_id")
            while _statement_state(response) in {"PENDING", "RUNNING"}:
                remaining = self._timeout - (self._clock() - started)
                if remaining <= 0:
                    if statement_id:
                        self._client.statement_execution.cancel_execution(statement_id)
                    raise PerformanceRetrievalError("Performance query timed out")
                self._sleep(min(0.1, remaining))
                response = self._client.statement_execution.get_statement(statement_id)
            if _statement_state(response) != "SUCCEEDED":
                raise PerformanceRetrievalError("Performance query failed")
            if (_nested_field(response, "manifest", "truncated") or
                    _nested_field(response, "result", "next_chunk_index") is not None):
                raise PerformanceSelectionError("Result exceeds the retrieval limit; narrow the selection")
            rows = _nested_field(response, "result", "data_array") or []
            if len(rows) > self._max_rows:
                raise PerformanceSelectionError("Result exceeds the retrieval limit; narrow the selection")
            return rows
        except PerformanceRetrievalError:
            raise
        except Exception as error:
            raise PerformanceRetrievalError("Performance data is temporarily unavailable") from error

    @staticmethod
    def _decode(rows, query):
        result = {name: [] for name in ("profiles", "cycles", "availability", "branch_availability", "policy", *query.datasets)}
        metadata = None
        for row in rows:
            if not isinstance(row, (list, tuple)) or len(row) != 2:
                raise PerformanceRetrievalError("Invalid performance result")
            kind, raw = row
            data = json.loads(raw)
            if not isinstance(data, dict):
                raise PerformanceRetrievalError("Invalid performance record")
            if kind == "meta":
                if metadata is not None:
                    raise PerformanceRetrievalError("Duplicate performance metadata")
                metadata = data
            elif kind in result:
                result[kind].append(data)
            else:
                raise PerformanceRetrievalError("Unexpected performance dataset")
        if metadata is None:
            raise PerformanceRetrievalError("Missing performance metadata")
        for dataset, target, funded, percent in (
            ('history', 'target_amount', 'funded_amount', 'attainment_percent'),
            ('loans', 'target_amount', 'funded_amount', 'attainment_percent'),
            ('branch_summary', 'total_target', 'total_funded_amount', 'branch_attainment_pct'),
        ):
            for row in result.get(dataset, []):
                if target not in row or funded not in row:
                    continue
                row['attainment_source_value'] = row.get(percent)
                row[percent] = (float((Decimal(str(row[funded])) / Decimal(str(row[target])) * 100).quantize(Decimal('0.01')))
                    if row[target] is not None and row[funded] is not None and Decimal(str(row[target])) > 0 else None)
        if (metadata["selected_employee_count"] > query.max_employees or
                metadata["selected_branch_count"] > query.max_branches):
            raise PerformanceSelectionError("Too many results; narrow the employee or branch selection")
        profiles = result["profiles"]
        ambiguities = [p for name in query.employee_names for p in profiles
                       if p["employee_name"].lower() == name.lower() and
                       sum(v["employee_name"].lower() == name.lower() for v in profiles) > 1]
        if ambiguities:
            candidates = [{key: p.get(key) for key in ("employee_id", "employee_name", "branch_name", "region_name")}
                          for p in ambiguities]
            raise PerformanceSelectionError("Employee name is ambiguous; select an employee ID or branch", candidates=candidates)
        names = {p["employee_name"].lower() for p in profiles}
        ids = {p["employee_id"] for p in profiles}
        result["missing_employee_names"] = [name for name in query.employee_names if name.lower() not in names]
        result["missing_employee_ids"] = [employee_id for employee_id in query.employee_ids if employee_id not in ids]
        result["requested_cycle_ids"] = list(query.cycle_ids)
        result["includes_latest_history_context"] = query.include_latest_history
        result["missing_cycles_by_employee"] = {
            employee_id: [cycle for cycle in query.cycle_ids if not any(
                r["employee_id"] == employee_id and r["cycle_id"] == cycle for r in result["cycles"])]
            for employee_id in ids
        }
        observed_branch_cycles = {r["cycle_id"] for r in result.get("branch_summary", [])}
        result["missing_branch_cycles"] = [c for c in query.cycle_ids if c not in observed_branch_cycles] if "branch_summary" in query.datasets else []
        branches = result["branch_availability"]
        result["missing_branch_names"] = [name for name in query.branch_names if
            name.casefold() not in {b["branch_name"].casefold() for b in branches}] if "branch_summary" in query.datasets else []
        result["missing_cycles_by_branch"] = {
            b["branch_id"]: [cycle for cycle in query.cycle_ids if not any(
                r["branch_id"] == b["branch_id"] and r["cycle_id"] == cycle
                for r in result.get("branch_summary", []))]
            for b in branches
        }
        result["definitions"] = {
            "ratings": "1–5; 3 meets expectations. NULL means missing, never zero.",
            "attainment": "Attainment fields are percentages on a 0–100 scale, calculated as funded / target * 100 from the approved view amounts. Original source values are retained separately; NULL or zero target means unavailable.",
            "scope": "Records use the server-configured access scope and the querying identity's Unity Catalog permissions.",
            "policy": "This tool returns observed data only. Retrieve approved policy separately.",
        }
        return result
