import json
import unittest
from types import SimpleNamespace

from mariner_genai_dbx.performance_retrieval import (
    PerformanceAccessScope, PerformanceQuery, PerformanceRetriever, PerformanceRetrievalError,
    PerformanceScopeError, PerformanceSelectionError, build_performance_query, build_policy_query,
)
from mariner_genai_dbx.performance_tool import PerformanceDataTool


def record(kind, **data):
    return [kind, json.dumps(data)]


def metadata(employees=1, branches=0):
    return record("meta", selected_employee_count=employees, selected_branch_count=branches,
                  max_employees=50, max_branches=50)


class Statements:
    def __init__(self, rows=()):
        self.calls = []
        self.cancelled = []
        self.response = {"statement_id": "statement", "status": {"state": "SUCCEEDED"},
                         "result": {"data_array": rows}}

    def execute_statement(self, **kwargs):
        self.calls.append(kwargs)
        return self.response

    def get_statement(self, statement_id):
        return self.response

    def cancel_execution(self, statement_id):
        self.cancelled.append(statement_id)


class PerformanceRetrievalTests(unittest.TestCase):
    scope = PerformanceAccessScope(employee_ids=("e1", "e2", "e3"), branch_ids=("b1", "b2"))

    def retriever(self, rows=(), **kwargs):
        statements = Statements(rows)
        retriever = PerformanceRetriever(workspace_client=SimpleNamespace(statement_execution=statements),
                                          warehouse_id="warehouse", **kwargs)
        return retriever, statements

    def test_batch_sql_is_parameterized_and_selects_only_requested_datasets(self):
        query = PerformanceQuery(employee_names=("O'Brien'); DROP TABLE x; --", "Another Person"),
                                 datasets=("history", "goals", "competencies", "reviews", "branch_summary"))
        sql, params = build_performance_query(query, self.scope)
        self.assertNotIn("O'Brien", sql)
        self.assertNotIn("Another Person", sql)
        self.assertIn("d.employee_id = c.employee_id AND d.cycle_id = c.cycle_id", sql)
        self.assertIn("app_vw_branch_quarterly_summary", sql)
        self.assertIn("array_contains(a.authorized_employees, p.employee_id)", sql)
        self.assertIn("array_contains(a.authorized_branches, b.branch_id)", sql)
        self.assertNotIn("SUM(", sql)
        self.assertNotIn("email", sql)
        values = {p.name if hasattr(p, "name") else p["name"]:
                  p.value if hasattr(p, "value") else p["value"] for p in params}
        self.assertIn("O'Brien".lower(), values["employee_names"])
        simple, _ = build_performance_query(PerformanceQuery(employee_ids=("e1",)), self.scope)
        self.assertNotIn("app_vw_employee_goal_status", simple)

    def test_multiple_employees_and_datasets_need_one_statement(self):
        rows = [metadata(2), record("profiles", employee_id="e1", employee_name="Employee A"),
                record("profiles", employee_id="e2", employee_name="Employee B"),
                record("history", employee_id="e1", final_rating=None),
                record("goals", employee_id="e2", completion_percent=0)]
        retriever, statements = self.retriever(rows)
        result = retriever.retrieve(PerformanceQuery(employee_ids=("e1", "e2"), datasets=("history", "goals")), scope=self.scope)
        self.assertEqual(len(statements.calls), 1)
        self.assertIsNone(result["history"][0]["final_rating"])
        self.assertEqual(result["goals"][0]["completion_percent"], 0)

    def test_branch_only_query_does_not_require_employee_views_or_access(self):
        sql, _ = build_performance_query(PerformanceQuery(branch_ids=("b1",), datasets=("branch_summary",)),
                                         PerformanceAccessScope(branch_ids=("b1",)))
        self.assertNotIn("app_vw_employee", sql)
        self.assertIn("app_vw_branch_quarterly_summary", sql)

    def test_scope_escalations_are_rejected_before_sql(self):
        retriever, statements = self.retriever()
        cases = [
            (PerformanceQuery(employee_ids=("outside",)), self.scope),
            (PerformanceQuery(datasets=("branch_summary",)), PerformanceAccessScope(employee_ids=("e1",))),
            (PerformanceQuery(), PerformanceAccessScope()),
            (PerformanceQuery(branch_ids=("outside",), datasets=("branch_summary",)), self.scope),
        ]
        for query, scope in cases:
            with self.subTest(query=query):
                with self.assertRaises(PerformanceScopeError):
                    retriever.retrieve(query, scope=scope)
        self.assertEqual(statements.calls, [])

    def test_poc_catalog_scope_is_server_owned_and_does_not_accept_sql(self):
        sql, _ = build_performance_query(PerformanceQuery(employee_names=("Different Person",)),
            PerformanceAccessScope(use_catalog_visibility=True))
        self.assertIn("app_vw_employee_profile", sql)
        self.assertNotIn("Different Person", sql)
        tool = PerformanceDataTool(self.retriever()[0], scope_provider=lambda principal: self.scope)
        with self.assertRaises(ValueError):
            tool.execute({'use_catalog_visibility': True}, principal_id='app')

    def test_missing_quarter_is_explicit_and_latest_availability_is_preserved(self):
        retriever, _ = self.retriever([
            metadata(), record("profiles", employee_id="e1", employee_name="Employee A"),
            record("availability", employee_id="e1", cycle_id="CY2026Q3"),
        ])
        result = retriever.retrieve(PerformanceQuery(employee_ids=("e1",), cycle_ids=("CY2026Q4",)), scope=self.scope)
        self.assertEqual(result["history"], [])
        self.assertEqual(result["missing_cycles_by_employee"], {"e1": ["CY2026Q4"]})
        self.assertEqual(result["availability"][0]["cycle_id"], "CY2026Q3")

    def test_future_review_keeps_requested_period_and_marks_historical_context(self):
        query = PerformanceQuery(employee_ids=("e1",), cycle_ids=("CY2027Q1",), include_latest_history=True)
        sql, _ = build_performance_query(query, self.scope)
        self.assertIn("OR q.cycle_rank <= 5", sql)
        result = PerformanceRetriever._decode([metadata(),
            record("profiles", employee_id="e1", employee_name="Employee A"),
            record("cycles", employee_id="e1", cycle_id="CY2026Q3"),
            record("history", employee_id="e1", cycle_id="CY2026Q3", final_rating=2)], query)
        self.assertEqual(result['requested_cycle_ids'], ['CY2027Q1'])
        self.assertEqual(result['missing_cycles_by_employee'], {'e1': ['CY2027Q1']})
        self.assertTrue(result['includes_latest_history_context'])

    def test_missing_quarter_is_reported_for_each_branch(self):
        query = PerformanceQuery(branch_names=('Branch A', 'Branch B'), datasets=('branch_summary',), cycle_ids=('CY2026Q4',))
        result = PerformanceRetriever._decode([metadata(0, 2),
            record('branch_availability', branch_id='b1', branch_name='Branch A', cycle_id='CY2026Q4'),
            record('branch_availability', branch_id='b2', branch_name='Branch B', cycle_id='CY2026Q3'),
            record('branch_summary', branch_id='b1', cycle_id='CY2026Q4')], query)
        self.assertEqual(result['missing_cycles_by_branch'], {'b1': [], 'b2': ['CY2026Q4']})

    def test_missing_and_ambiguous_names_do_not_invent_a_match(self):
        retriever, _ = self.retriever([metadata(2),
            record("profiles", employee_id="e1", employee_name="Same Name", branch_name="A"),
            record("profiles", employee_id="e2", employee_name="Same Name", branch_name="B")])
        with self.assertRaises(PerformanceSelectionError) as caught:
            retriever.retrieve(PerformanceQuery(employee_names=("Same Name",)), scope=self.scope)
        self.assertEqual(len(caught.exception.candidates), 2)
        retriever, _ = self.retriever([metadata(0)])
        result = retriever.retrieve(PerformanceQuery(employee_names=("Missing Person",)), scope=self.scope)
        self.assertEqual(result["missing_employee_names"], ["Missing Person"])

    def test_rejects_partial_or_overflow_results(self):
        retriever, statements = self.retriever([metadata()])
        statements.response["manifest"] = {"truncated": True}
        with self.assertRaises(PerformanceSelectionError):
            retriever.retrieve(PerformanceQuery(), scope=self.scope)
        retriever, _ = self.retriever([metadata(51)])
        with self.assertRaises(PerformanceSelectionError):
            retriever.retrieve(PerformanceQuery(), scope=self.scope)

    def test_polling_deadline_cancels_the_statement(self):
        clock = [0.0]
        retriever, statements = self.retriever(clock=lambda: clock[0], sleep=lambda value: clock.__setitem__(0, clock[0] + value), timeout_seconds=0.2)
        statements.response["status"] = {"state": "RUNNING"}
        with self.assertRaises(PerformanceRetrievalError):
            retriever.retrieve(PerformanceQuery(), scope=self.scope)
        self.assertEqual(statements.cancelled, ["statement"])

    def test_invalid_filters_and_unsupported_analytics_are_rejected(self):
        for kwargs in ({"datasets": ("arbitrary_sql",)}, {"cycle_ids": ("Q5 2026",)},
                       {"latest_cycles": True}, {"employee_names": "Employee A"}, {"max_employees": 100000}):
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(ValueError):
                    PerformanceQuery(**kwargs)

    def test_policy_and_data_share_one_statement_and_registry_metadata(self):
        sql, _ = build_performance_query(PerformanceQuery(employee_ids=('e1',)), self.scope,
            include_policy=True, policy_registry_table='workspace.default.app_citation_registry')
        self.assertIn("p.domain = 'Employee Performance Policy'", sql)
        for field in ('document_id', 'document_version', 'chunk_id', 'document_title', 'page_start', 'chunk_text'):
            self.assertIn(field, sql)
        only_policy, _ = build_performance_query(PerformanceQuery(), PerformanceAccessScope(),
            include_policy=True, include_data=False, policy_registry_table='workspace.default.app_citation_registry')
        self.assertNotIn('app_vw_employee', only_policy)

    def policy_retriever(self, data_rows, policy_rows, **kwargs):
        class SplitStatements(Statements):
            def execute_statement(self, **call):
                self.calls.append(call)
                rows = policy_rows if "ORDER BY record_json" in call["statement"] and \
                    "app_vw_employee" not in call["statement"] else data_rows
                return {"statement_id": "s", "status": {"state": "SUCCEEDED"},
                        "result": {"data_array": rows}}
        statements = SplitStatements()
        retriever = PerformanceRetriever(
            workspace_client=SimpleNamespace(statement_execution=statements), warehouse_id="warehouse",
            policy_registry_table="workspace.default.app_citation_registry", **kwargs)
        return retriever, statements

    def passage(self, chunk="c1"):
        return record("policy", document_id="doc", document_version="v1", chunk_id=chunk,
                      document_title="Policy", page_start=2, page_end=2,
                      source_volume_path="/Volumes/main/p.pdf", chunk_text="Approved text")

    def test_policy_is_cached_and_kept_out_of_the_data_query(self):
        retriever, statements = self.policy_retriever(
            [metadata(), record("profiles", employee_id="e1", employee_name="A")], [self.passage()])
        query = PerformanceQuery(employee_ids=("e1",))
        first = retriever.retrieve(query, scope=self.scope, include_policy=True)
        second = retriever.retrieve(query, scope=self.scope, include_policy=True)
        policy_calls = [c for c in statements.calls if "app_vw_employee" not in c["statement"]]
        data_calls = [c for c in statements.calls if "app_vw_employee" in c["statement"]]
        self.assertEqual((len(policy_calls), len(data_calls)), (1, 2))
        for call in data_calls:
            self.assertNotIn("chunk_text", call["statement"])
        self.assertEqual(first["policy"][0]["page_start"], 2)
        self.assertEqual(first["policy"], second["policy"])
        first["policy"][0]["chunk_text"] = "changed"  # callers get copies
        self.assertEqual(retriever.policy_passages()[0]["chunk_text"], "Approved text")

    def test_policy_only_request_runs_no_data_sql(self):
        retriever, statements = self.policy_retriever([], [self.passage()])
        result = retriever.retrieve(PerformanceQuery(), scope=PerformanceAccessScope(),
                                    include_policy=True, include_data=False)
        self.assertEqual(len(statements.calls), 1)
        self.assertEqual(len(result["policy"]), 1)
        self.assertEqual(result["profiles"], [])

    def test_prefetch_loads_in_background_and_retrieve_reuses_it(self):
        retriever, statements = self.policy_retriever([metadata()], [self.passage()])
        retriever.prefetch_policy()
        retriever._policy_future.result(2)
        retriever.prefetch_policy()  # fresh: nothing new starts
        retriever.retrieve(PerformanceQuery(employee_ids=("e1",)), scope=self.scope, include_policy=True)
        self.assertEqual(sum("app_vw_employee" not in c["statement"] for c in statements.calls), 1)

    def test_stale_policy_is_served_within_limit_and_reloaded_past_it(self):
        now = [0.0]
        retriever, statements = self.policy_retriever(
            [], [self.passage()], clock=lambda: now[0], policy_ttl_seconds=60, policy_max_stale_seconds=600)
        retriever.policy_passages()
        now[0] = 120  # stale but allowed: served now, refreshed in the background
        self.assertEqual(len(retriever.policy_passages()), 1)
        retriever._policy_future.result(2)
        self.assertEqual(len(statements.calls), 2)
        now[0] = 900  # past the limit since the t=120 refresh
        retriever.policy_passages()
        self.assertEqual(len(statements.calls), 3)

    def test_policy_query_matches_the_batch_policy_records(self):
        table = 'workspace.default.app_citation_registry'
        batch, _ = build_performance_query(PerformanceQuery(), PerformanceAccessScope(),
                                           include_policy=True, include_data=False, policy_registry_table=table)
        policy = build_policy_query(table)
        self.assertIn(policy[:-len(" ORDER BY record_json")], batch)
        self.assertTrue(policy.endswith("ORDER BY record_json"))

    def test_fast_view_prefix_reads_only_the_materialized_copies(self):
        query = PerformanceQuery(employee_ids=("e1",), datasets=tuple(
            ("history", "goals", "competencies", "reviews", "branch_summary")))
        live, _ = build_performance_query(query, self.scope)
        fast, _ = build_performance_query(query, self.scope, view_prefix="app_fast_")
        self.assertEqual(fast.replace("app_fast_", "app_vw_"), live)
        self.assertNotIn("app_vw_", fast)
        with self.assertRaises(ValueError):
            build_performance_query(query, self.scope, view_prefix="other_; DROP")
        with self.assertRaises(ValueError):
            PerformanceRetriever(workspace_client=None, warehouse_id="w", view_prefix="x_")

    def test_percentage_units_are_consistent_and_zero_target_is_not_zero_attainment(self):
        result = PerformanceRetriever._decode([metadata(),
            record('history', employee_id='e1', target_amount=100, funded_amount=75, attainment_percent=.75),
            record('history', employee_id='e1', target_amount=0, funded_amount=0, attainment_percent=0),
            record('branch_summary', branch_id='b1', cycle_id='CY2026Q3', total_target=100, total_funded_amount=75, branch_attainment_pct=75)],
            PerformanceQuery(datasets=('history', 'branch_summary')))
        self.assertEqual(result['history'][0]['attainment_percent'], 75)
        self.assertEqual(result['history'][0]['attainment_source_value'], .75)
        self.assertIsNone(result['history'][1]['attainment_percent'])
        self.assertEqual(result['branch_summary'][0]['branch_attainment_pct'], 75)

    def test_tool_cannot_accept_model_supplied_scope_or_principal(self):
        retriever, statements = self.retriever([metadata(0)])
        tool = PerformanceDataTool(retriever, scope_provider=lambda principal: self.scope)
        for args in ({"authorized_employees": ["outside"]}, {"principal_id": "admin"}, {"sql": "SELECT *"}):
            with self.assertRaises(ValueError):
                tool.execute(args, principal_id="authenticated-manager")
        self.assertEqual(statements.calls, [])
        tool.execute({"employee_ids": ["e1"], "datasets": ["history"]}, principal_id="authenticated-manager")
        self.assertEqual(len(statements.calls), 1)


if __name__ == "__main__":
    unittest.main()
