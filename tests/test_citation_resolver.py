import unittest

from mariner_genai_dbx.citation_resolver import (
    DatabricksCitationResolver,
    extract_source_labels,
    remove_source_lines,
)
from mariner_genai_dbx.config import CITATION_TABLES
from mariner_genai_dbx.errors import CitationResolutionError


class FakeStatementExecution:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def execute_statement(self, **kwargs):
        self.calls.append(kwargs)
        return self.response

    def get_statement(self, statement_id):
        raise AssertionError(f"Unexpected polling for {statement_id}")


class FakeWorkspaceClient:
    def __init__(self, response):
        self.statement_execution = FakeStatementExecution(response)


def response(rows, state="SUCCEEDED"):
    return {
        "statement_id": "statement-id",
        "status": {"state": state},
        "result": {"data_array": rows},
    }


class CitationResolverTests(unittest.TestCase):
    def test_removes_plain_and_markdown_source_lines_from_display_answer(self):
        answer = (
            "Managers meet quarterly.\n\n"
            "**Source:** INSTRUCTIONS_PERFORMANCE.pdf\n\n"
            "Additional guidance."
        )

        self.assertEqual(
            remove_source_lines(answer),
            "Managers meet quarterly.\n\nAdditional guidance.",
        )

    def test_extracts_plain_and_markdown_source_labels(self):
        self.assertEqual(
            extract_source_labels(
                "Answer one.\n\nSource: Record Retention\n"
                "Answer two.\n\n**Source:** Employee Handbook\n"
                "Answer three.\n\n**Source**: Record Retention Policy\n"
                "Answer four.\n\nSource: **Benefits Guide**"
            ),
            (
                "Record Retention",
                "Employee Handbook",
                "Record Retention Policy",
                "Benefits Guide",
            ),
        )

    def test_resolves_label_with_parameterized_union_query(self):
        client = FakeWorkspaceClient(
            response(
                [
                    [
                        "Branch Operations",
                        "Record Retention.pdf",
                        "/Volumes/main/branch/Record Retention.pdf",
                        "4",
                        "Paid loan files must be retained for five years.",
                        "1",
                    ]
                ]
            )
        )
        resolver = DatabricksCitationResolver(
            workspace_client=client,
            warehouse_id="55cdb78d4d2a62d0",
            tables=CITATION_TABLES,
        )

        sources = resolver.resolve_labels(("Record Retention",))

        self.assertEqual(sources[0].label, "Record Retention.pdf")
        self.assertEqual(sources[0].domain, "Branch Operations")
        self.assertEqual(sources[0].page, 4)
        call = client.statement_execution.calls[0]
        self.assertEqual(call["warehouse_id"], "55cdb78d4d2a62d0")
        self.assertNotIn("Record Retention", call["statement"])
        self.assertIn(":source_label", call["statement"])
        self.assertIn("CONCAT", call["statement"])
        self.assertIn("' %'", call["statement"])
        self.assertIn("'% '", call["statement"])
        self.assertIn("',%'", call["statement"])
        self.assertIn("' - %'", call["statement"])
        self.assertIn("' – %'", call["statement"])
        self.assertIn("' — %'", call["statement"])
        self.assertIn("' (%'", call["statement"])
        self.assertIn("'%, '", call["statement"])
        self.assertIn("'% - '", call["statement"])
        self.assertIn("'[0-9]{4}", call["statement"])
        self.assertIn("'\\\\s+v[0-9]+'", call["statement"])
        self.assertIn("'[_()-]+'", call["statement"])
        self.assertIn("policy$", call["statement"])
        self.assertIn("LOWER(TRIM(:source_label)), '\\\\.pdf', ''", call["statement"])
        self.assertIn("workspace`.`default`.`branch_operations_chunks", call["statement"])
        self.assertIn(
            "workspace`.`performance_test`.`app_policy_chunks", call["statement"]
        )
        self.assertIn("`document_name` AS document_title", call["statement"])
        self.assertIn("`source_volume_path` AS volume_path", call["statement"])
        self.assertIn("TRY_CAST(`page_start` AS INT) AS page_number", call["statement"])
        parameter = call["parameters"][0]
        value = parameter.get("value") if isinstance(parameter, dict) else parameter.value
        self.assertEqual(value, "BRANCH_OPERATIONS_RECORD_RETENTION")

    def test_normalizes_filename_separators_for_human_readable_source_labels(self):
        client = FakeWorkspaceClient(
            response(
                [
                    [
                        "Branch Operations",
                        "EMPLOYEE_REIMBURSEMENT_AND_BUSINESS_TRAVEL_EXPENSES",
                        "/Volumes/main/branch/EMPLOYEE_REIMBURSEMENT_AND_BUSINESS_TRAVEL_EXPENSES.pdf",
                        "2",
                        "To create your Navan account, send an email request.",
                        "1",
                    ]
                ]
            )
        )
        resolver = DatabricksCitationResolver(
            workspace_client=client,
            warehouse_id="warehouse",
            tables=CITATION_TABLES,
        )

        source = resolver.resolve_labels(
            ("Employee Reimbursement and Business Travel Expenses",),
            "To create a Navan account, send an email request.",
        )[0]

        self.assertEqual(
            source.label,
            "EMPLOYEE_REIMBURSEMENT_AND_BUSINESS_TRAVEL_EXPENSES",
        )
        self.assertEqual(source.domain, "Branch Operations")
        self.assertEqual(source.page, 2)
        statement = client.statement_execution.calls[0]["statement"]
        self.assertIn("REGEXP_REPLACE", statement)
        self.assertIn("'[_()-]+'", statement)

    def test_omits_page_when_title_matches_chunks_on_multiple_pages(self):
        client = FakeWorkspaceClient(
            response(
                [
                    [
                        "Employee Handbook",
                        "Handbook.pdf",
                        "/Volumes/main/handbook/Handbook.pdf",
                        "2",
                        "Attendance and workplace conduct.",
                        "1",
                    ],
                    [
                        "Employee Handbook",
                        "Handbook.pdf",
                        "/Volumes/main/handbook/Handbook.pdf",
                        "19",
                        "Benefits and enrollment information.",
                        "1",
                    ]
                ]
            )
        )
        resolver = DatabricksCitationResolver(
            workspace_client=client,
            warehouse_id="warehouse",
            tables=CITATION_TABLES,
        )

        self.assertIsNone(resolver.resolve_labels(("Handbook",))[0].page)

    def test_selects_page_whose_chunk_supports_the_answer(self):
        client = FakeWorkspaceClient(
            response(
                [
                    [
                        "Branch Operations",
                        "Record Retention",
                        "/Volumes/main/branch/Record Retention.pdf",
                        "1",
                        "Policy overview and definitions.",
                        "1",
                    ],
                    [
                        "Branch Operations",
                        "Record Retention",
                        "/Volumes/main/branch/Record Retention.pdf",
                        "3",
                        "Paid loan files must be retained for five years after payoff.",
                        "1",
                    ],
                ]
            )
        )
        resolver = DatabricksCitationResolver(
            workspace_client=client,
            warehouse_id="warehouse",
            tables=CITATION_TABLES,
        )

        source = resolver.resolve_labels(
            ("Record Retention",),
            "Paid loan files are retained for five years after payoff.",
        )[0]

        self.assertEqual(source.page, 3)

    def test_breaks_page_tie_with_distinctive_answer_term(self):
        client = FakeWorkspaceClient(
            response(
                [
                    [
                        "Employee Benefits",
                        "Benefits _ Mariner Finance",
                        "/Volumes/main/benefits/Benefits.pdf",
                        "1",
                        "Mariner employees receive benefits.",
                        "1",
                    ],
                    [
                        "Employee Benefits",
                        "Benefits _ Mariner Finance",
                        "/Volumes/main/benefits/Benefits.pdf",
                        "2",
                        "PPO plan option details.",
                        "1",
                    ],
                    [
                        "Employee Benefits",
                        "Benefits _ Mariner Finance",
                        "/Volumes/main/benefits/Benefits.pdf",
                        "3",
                        "Mariner plan option details.",
                        "1",
                    ],
                    [
                        "Employee Benefits",
                        "Benefits _ Mariner Finance",
                        "/Volumes/main/benefits/Benefits.pdf",
                        "4",
                        "Mariner workplace information.",
                        "1",
                    ],
                ]
            )
        )
        resolver = DatabricksCitationResolver(
            workspace_client=client,
            warehouse_id="warehouse",
            tables=CITATION_TABLES,
        )

        source = resolver.resolve_labels(
            ("Mariner Benefits Knowledge Base",),
            "Yes, Mariner offers a PPO plan option.",
        )[0]

        self.assertEqual(source.page, 2)

    def test_omits_page_when_distinctive_answer_terms_still_tie(self):
        client = FakeWorkspaceClient(
            response(
                [
                    [
                        "Employee Benefits",
                        "Benefits _ Mariner Finance",
                        "/Volumes/main/benefits/Benefits.pdf",
                        "2",
                        "PPO plan details.",
                        "1",
                    ],
                    [
                        "Employee Benefits",
                        "Benefits _ Mariner Finance",
                        "/Volumes/main/benefits/Benefits.pdf",
                        "3",
                        "HMO plan details.",
                        "1",
                    ],
                ]
            )
        )
        resolver = DatabricksCitationResolver(
            workspace_client=client,
            warehouse_id="warehouse",
            tables=CITATION_TABLES,
        )

        source = resolver.resolve_labels(
            ("Mariner Benefits Knowledge Base",),
            "Compare the PPO and HMO plan details.",
        )[0]

        self.assertIsNone(source.page)

    def test_resolves_new_performance_agent_source_alias(self):
        client = FakeWorkspaceClient(
            response(
                [
                    [
                        "Employee Performance Policy",
                        "INSTRUCTIONS_PERFORMANCE.pdf",
                        "/Volumes/workspace/performance_test/data/INSTRUCTIONS_PERFORMANCE.pdf",
                        "2",
                        "The performance rating scale runs from one to five.",
                        "1",
                    ]
                ]
            )
        )
        resolver = DatabricksCitationResolver(
            workspace_client=client,
            warehouse_id="warehouse",
            tables=CITATION_TABLES,
        )

        source = resolver.resolve_labels(
            ("Employee Performance Management Policy",)
        )[0]

        self.assertEqual(source.label, "INSTRUCTIONS_PERFORMANCE.pdf")
        self.assertEqual(source.domain, "Employee Performance Policy")
        self.assertEqual(source.page, 2)
        statement = client.statement_execution.calls[0]["statement"]
        self.assertIn("`chunk_text`", statement)
        parameter = client.statement_execution.calls[0]["parameters"][0]
        value = parameter.get("value") if isinstance(parameter, dict) else parameter.value
        self.assertEqual(value, "INSTRUCTIONS_PERFORMANCE.pdf")

    def test_resolves_benefits_agent_medical_plan_source_alias(self):
        client = FakeWorkspaceClient(
            response(
                [
                    [
                        "Employee Benefits",
                        "Benefits _ Mariner Finance",
                        "/Volumes/workspace/default/benefits_docs/Benefits _ Mariner Finance.pdf",
                        "4",
                        "The PPO provides in-network and out-of-network coverage.",
                        "1",
                    ]
                ]
            )
        )
        resolver = DatabricksCitationResolver(
            workspace_client=client,
            warehouse_id="warehouse",
            tables=CITATION_TABLES,
        )

        for label in (
            "Mariner Benefits Knowledge Base",
            "Mariner Benefits Knowledge Base - Medical Plans Overview",
            "Mariner Benefits Knowledge Base - Medical Plans section",
        ):
            source = resolver.resolve_labels((label,))[0]

            self.assertEqual(source.label, "Benefits _ Mariner Finance")
            self.assertEqual(source.domain, "Employee Benefits")
            self.assertEqual(source.page, 4)

        for call in client.statement_execution.calls:
            parameter = call["parameters"][0]
            value = (
                parameter.get("value")
                if isinstance(parameter, dict)
                else parameter.value
            )
            self.assertEqual(value, "Benefits _ Mariner Finance")

    def test_canonicalizes_branch_record_retention_agent_alias(self):
        client = FakeWorkspaceClient(
            response(
                [
                    [
                        "Branch Operations",
                        "BRANCH_OPERATIONS_RECORD_RETENTION",
                        "/Volumes/main/branch/BRANCH_OPERATIONS_RECORD_RETENTION.pdf",
                        "3",
                        "Loan records must be retained after payoff.",
                        "1",
                    ]
                ]
            )
        )
        resolver = DatabricksCitationResolver(
            workspace_client=client,
            warehouse_id="warehouse",
            tables=CITATION_TABLES,
        )

        source = resolver.resolve_labels(("Branch Record Retention Policy",))[0]

        self.assertEqual(source.label, "BRANCH_OPERATIONS_RECORD_RETENTION")
        parameter = client.statement_execution.calls[0]["parameters"][0]
        value = parameter.get("value") if isinstance(parameter, dict) else parameter.value
        self.assertEqual(value, "BRANCH_OPERATIONS_RECORD_RETENTION")

    def test_failed_statement_is_sanitized(self):
        resolver = DatabricksCitationResolver(
            workspace_client=FakeWorkspaceClient(response([], state="FAILED")),
            warehouse_id="warehouse",
            tables=CITATION_TABLES,
        )

        with self.assertRaises(CitationResolutionError):
            resolver.resolve_labels(("Record Retention",))


if __name__ == "__main__":
    unittest.main()
