import unittest

from mariner_genai_dbx.coaching360 import Coaching360Service
from mariner_genai_dbx.config import Settings
from mariner_genai_dbx.models import AgentAnswer
from mariner_genai_dbx.web import create_app


class FakeStatements:
    def __init__(self, people=()):
        self.people = list(people)
        self.calls = []

    def execute_statement(self, **call):
        self.calls.append(call)
        # The directory lookup is the only query that returns people; data_status gives the latest month.
        if "data_status" in call["statement"]:
            rows = [["2026-09-01", "2026-10-20"]]
        else:
            rows = self.people if "org_hierarchy__eda_ref_t_ref_user u" in call["statement"] else []
        return {"statement_id": "s", "status": {"state": "SUCCEEDED"}, "result": {"data_array": rows}}


def service(people=()):
    statements = FakeStatements(people)
    client = type("Client", (), {"statement_execution": statements})()
    return Coaching360Service(workspace_client=client, warehouse_id="wh", run_in_background=lambda work: work()), statements


ANDRE = ["500210", "Andre Pemberton", "Branch Manager", "true", "branch", "Altamaha Landing", "District 5"]
ONE = [ANDRE]
MANY = [[str(500000 + i), f"Pat {i}", "Account Representative", "true", "employee", "Branch 80", "D1"] for i in range(3)]
ANALYST = [["500391", "Bea Holloway", "Business Analyst", "true", "none", None, None]]
INACTIVE = [["500016", "Old Timer", "Account Representative", "false", None, "Branch 1", "D1"]]


def merges(statements):
    return [c for c in statements.calls if "MERGE INTO" in c["statement"]]


class Coaching360FlowTests(unittest.TestCase):
    def test_not_a_coaching_conversation_returns_none(self):
        svc, _ = service()
        self.assertIsNone(svc.handle("u", "c", "What is the dress code?"))

    def test_start_without_a_name_asks_for_it(self):
        svc, statements = service(ONE)
        self.assertIn("What's your name?", svc.handle("u", "c", "/coaching360").reply)
        confirm = svc.handle("u", "c", "Andre Pemberton").reply
        self.assertTrue(confirm.startswith("👋 Welcome to Coaching360, Andre."))
        self.assertIn("  Performance: your scorecard, KPIs, ACE goals, and rankings", confirm)
        self.assertIn("Try: \"Show me my scorecard for September\"", confirm)
        self.assertIn("/coaching360 exit to leave", confirm)
        self.assertEqual(len(merges(statements)), 1)

    def test_start_with_a_name_identifies_in_one_step(self):
        svc, _ = service(ONE)
        confirm = svc.handle("u", "c", "/coaching360 Andre Pemberton").reply
        self.assertIn("Welcome to Coaching360, Andre.", confirm)
        turn = svc.handle("u", "c", "Who are my employees?")
        self.assertIsNone(turn.reply)
        self.assertIn("Person level: branch", turn.supervisor_message)
        self.assertIn("coaching360_branch_data", turn.supervisor_message)
        self.assertIn("Question: Who are my employees?", turn.supervisor_message)

    def test_questions_reuse_the_persona_without_rewriting_it(self):
        svc, statements = service(ONE)
        svc.handle("u", "c", "/coaching360 Andre")
        svc.handle("u", "c", "Who are my employees?")
        svc.handle("u", "c", "And their DPR scorecard?")
        self.assertEqual(len(merges(statements)), 1)

    def test_persona_is_rechecked_after_trust_window_and_rewritten_only_if_changed(self):
        now = [0.0]
        statements = FakeStatements(ONE)
        client = type("Client", (), {"statement_execution": statements})()
        svc = Coaching360Service(workspace_client=client, warehouse_id="wh", clock=lambda: now[0])
        svc.handle("u", "c", "/coaching360 Andre")
        now[0] = 400  # past the trust window: a read, and a write because user_map looks empty
        svc.handle("u", "c", "Who are my employees?")
        reads = [c for c in statements.calls if c["statement"].startswith("SELECT max(user_dwid)")]
        self.assertEqual(len(reads), 1)
        self.assertEqual(len(merges(statements)), 2)

    def test_several_matches_list_names_with_positions(self):
        svc, _ = service(MANY)
        listing = svc.handle("u", "c", "/coaching360 pat").reply
        self.assertIn("3 employees match", listing)
        self.assertIn("1. Pat 0 (Account Representative, Branch 80)", listing)
        self.assertIn("Welcome to Coaching360, Pat.", svc.handle("u", "c", "2").reply)

    def test_no_match(self):
        svc, statements = service([])
        reply = svc.handle("u", "c", "/coaching360 Nobody Here").reply
        self.assertIn("couldn't find an employee", reply)
        self.assertEqual(merges(statements), [])

    def test_position_without_coaching360_level(self):
        svc, statements = service(ANALYST)
        reply = svc.handle("u", "c", "/coaching360 Bea Holloway").reply
        self.assertIn("position **Business Analyst**", reply)
        self.assertIn("does not cover this position", reply)
        self.assertEqual(merges(statements), [])

    def test_inactive_employee(self):
        svc, statements = service(INACTIVE)
        reply = svc.handle("u", "c", "/coaching360 Old Timer").reply
        self.assertIn("not an active employee", reply)
        self.assertEqual(merges(statements), [])

    def test_switch_other_name_exit_and_other_commands(self):
        svc, _ = service(ONE)
        svc.handle("u", "c", "/coaching360 Andre")
        self.assertIsNone(svc.handle("u", "c", "/policy What is record retention?"))
        self.assertIn("What's your name?", svc.handle("u", "c", "/coaching360 switch").reply)
        self.assertIn("Welcome to Coaching360, Andre.", svc.handle("u", "c", "/coaching360 Andre Pemberton").reply)
        self.assertIn("left Coaching360", svc.handle("u", "c", "/coaching360 exit").reply)
        self.assertIsNone(svc.handle("u", "c", "Who are my employees?"))

    def test_conversations_are_independent(self):
        svc, _ = service(ONE)
        svc.handle("u", "c1", "/coaching360 Andre")
        self.assertIsNone(svc.handle("u", "c2", "Who are my employees?"))

    def test_choosing_a_person_warms_their_level_views(self):
        svc, statements = service(ONE)
        svc.handle("u", "c", "/coaching360 Andre")
        warmed = [c["statement"] for c in statements.calls if c["statement"].startswith("SELECT COUNT(*) FROM")]
        self.assertEqual(warmed, ["SELECT COUNT(*) FROM workspace.c360_branch.team_overview",
                                  "SELECT COUNT(*) FROM workspace.c360_branch.employee_monthly_kpis"])

    def test_warm_up_failure_is_ignored(self):
        class Failing(FakeStatements):
            def execute_statement(self, **call):
                if call["statement"].startswith("SELECT COUNT(*)"):
                    raise RuntimeError("view missing")
                return super().execute_statement(**call)
        statements = Failing(ONE)
        client = type("Client", (), {"statement_execution": statements})()
        svc = Coaching360Service(workspace_client=client, warehouse_id="wh", run_in_background=lambda work: work())
        self.assertIn("Welcome to Coaching360, Andre.", svc.handle("u", "c", "/coaching360 Andre").reply)

    def test_no_month_named_uses_latest_complete_kpi_month(self):
        svc, _ = service(ONE)
        svc.handle("u", "c", "/coaching360 Andre")
        message = svc.handle("u", "c", "Show me my scorecard").supervisor_message
        self.assertNotIn("Month from this conversation", message)  # the tools default to the latest complete month
        self.assertIn("Pass the person's question to the data tool word for word.", message)
        self.assertIn("Report numbers, goals and statuses exactly as the tool returns them", message)

    def test_month_is_carried_forward_until_another_is_named(self):
        svc, _ = service(ONE)
        svc.handle("u", "c", "/coaching360 Andre")
        self.assertIn("Month from this conversation: August 2026", svc.handle("u", "c", "How did my team do in August?").supervisor_message)
        self.assertIn("Month from this conversation: August 2026", svc.handle("u", "c", "And their DACC loans?").supervisor_message)
        self.assertIn("never use it to filter coaching records", svc.handle("u", "c", "And their DACC loans?").supervisor_message)
        self.assertIn("October 2026", svc.handle("u", "c", "What's in my Success Plan for October?").supervisor_message)
        self.assertIn("November 2025", svc.handle("u", "c", "What about November?").supervisor_message)
        self.assertNotIn("Month from this conversation", svc.handle("u", "c", "Show me the latest month").supervisor_message)

    def test_question_month_parsing(self):
        from datetime import date
        from mariner_genai_dbx.coaching360 import question_month
        latest = date(2026, 10, 20)  # the as-of date
        self.assertEqual(question_month("my scorecard for Sept", latest), date(2026, 9, 1))
        self.assertEqual(question_month("my October 7 visit", latest), date(2026, 10, 1))
        self.assertEqual(question_month("2026-07 numbers", latest), date(2026, 7, 1))
        self.assertEqual(question_month("October 2025", latest), date(2025, 10, 1))
        self.assertEqual(question_month("results in May", latest), date(2026, 5, 1))
        self.assertIsNone(question_month("What may I improve?", latest))
        self.assertIsNone(question_month("Who are my employees?", latest))

    def test_search_is_parameterized(self):
        svc, statements = service(ONE)
        svc.handle("u", "c", "/coaching360 o'brien'; DROP TABLE x; --")
        search = [c for c in statements.calls if "user_level" in c["statement"]][-1]
        self.assertNotIn("o'brien", search["statement"])


class Coaching360WebTests(unittest.TestCase):
    class Supervisor:
        def __init__(self):
            self.messages = []

        def answer(self, message, session_id, history):
            self.messages.append(message)
            return AgentAnswer(answer="Your team ranking.")

        def check_readiness(self):
            return type("R", (), {"ready": True})()

    def test_setup_replies_skip_the_supervisor_and_questions_use_the_directive(self):
        svc, _ = service(ONE)
        supervisor = self.Supervisor()
        client = create_app(Settings(app_env="test"), supervisor_service=supervisor, coaching360_service=svc).test_client()
        first = client.post("/api/v1/chat", json={"message": "/coaching360"}).get_json()
        conversation = first["conversationId"]
        self.assertIn("What's your name?", first["answer"])
        client.post("/api/v1/chat", json={"message": "Andre Pemberton", "conversationId": conversation})
        self.assertEqual(supervisor.messages, [])
        reply = client.post("/api/v1/chat", json={"message": "Who are my employees?", "conversationId": conversation}).get_json()
        self.assertEqual(reply["answer"], "Your team ranking.")
        self.assertIn("Person level: branch", supervisor.messages[-1])

    def test_slow_coaching360_answer_times_out_with_a_clear_message(self):
        import threading
        from mariner_genai_dbx.models import PendingAgentAnswer
        release = threading.Event()

        class SlowSupervisor(self.Supervisor):
            def prepare_answer(self, message, session_id, history, on_event=None):
                release.wait(5)
                return PendingAgentAnswer(answer="late")

            def resolve_answer(self, pending):
                return AgentAnswer(answer=pending.answer)

        svc, _ = service(ONE)
        settings = Settings(app_env="test", coaching360_timeout_seconds=0.2)
        client = create_app(settings, supervisor_service=SlowSupervisor(), coaching360_service=svc).test_client()
        conversation = client.post("/api/v1/chat", json={"message": "/coaching360 Andre"}).get_json()["conversationId"]
        body = client.post("/api/v1/chat/stream", json={"message": "Rank my team", "conversationId": conversation}).get_data(as_text=True)
        release.set()
        self.assertIn('"code": "TIMEOUT"', body)
        self.assertIn("taking longer than expected", body)

    def test_streaming_setup_reply(self):
        svc, _ = service(ONE)
        client = create_app(Settings(app_env="test"), supervisor_service=self.Supervisor(), coaching360_service=svc).test_client()
        body = client.post("/api/v1/chat/stream", json={"message": "/coaching360"}).get_data(as_text=True)
        self.assertIn("event: answer", body)
        self.assertIn("What's your name?", body)
        self.assertIn("event: done", body)


if __name__ == "__main__":
    unittest.main()
