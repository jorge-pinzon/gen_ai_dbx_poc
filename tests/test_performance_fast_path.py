import json
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from mariner_genai_dbx.errors import SupervisorInvocationError
from mariner_genai_dbx.models import ConversationHistory, PendingAgentAnswer, TokenUsage
from mariner_genai_dbx.performance_fast_path import PerformanceFastPathService
from mariner_genai_dbx.performance_retrieval import PerformanceSelectionError

CITATION = dict(document_id='d', document_version='v', chunk_id='c', document_title='Approved Policy', page=2)


class FastPathTests(unittest.TestCase):
    def make_service(self, plan=None, synthesis=None):
        supervisor = Mock()
        supervisor.config = SimpleNamespace(workspace_host='https://example.test')
        supervisor._citation_resolver = Mock()
        supervisor.prepare_answer.return_value = PendingAgentAnswer(answer='Existing route')
        retriever = Mock()
        retriever.retrieve.return_value = {'history': [], 'availability': [],
            'profiles': [{'employee_id': 'e1', 'employee_name': 'Employee A'}],
            'policy': [{**CITATION, 'page_start': 2, 'page_end': 2, 'chunk_text': 'Approved policy passage'}]}
        service = PerformanceFastPathService(supervisor, retriever=retriever, model_endpoint='model')
        service._chat = Mock(side_effect=[(plan or {
            'supported': True, 'needs_data': True, 'needs_policy': True,
            'filters': {'employee_names': ['Employee A', 'Employee B'], 'datasets': ['history', 'goals']}}, TokenUsage()),
            (synthesis or {'answer': 'Advisory plan', 'citation_labels': ['P1']}, TokenUsage())])
        return service, supervisor, retriever

    def test_batches_all_employees_once_and_preserves_citations_in_code(self):
        service, supervisor, retriever = self.make_service()
        pending = service.prepare_answer('Performance goals for Employee A and Employee B', 's', ConversationHistory())
        self.assertEqual(pending.answer, 'Advisory plan')
        self.assertEqual(pending.citation_references, (CITATION,))
        self.assertEqual(retriever.retrieve.call_count, 1)
        query = retriever.retrieve.call_args.args[0]
        self.assertEqual(query.employee_names, ('Employee A', 'Employee B'))
        self.assertEqual(query.datasets, ('history', 'goals'))
        self.assertTrue(retriever.retrieve.call_args.kwargs['scope'].use_catalog_visibility)
        self.assertTrue(retriever.retrieve.call_args.kwargs['include_policy'])
        supervisor.prepare_answer.assert_not_called()

    def test_policy_prefetch_starts_before_the_planner(self):
        service, _, retriever = self.make_service()
        order = []
        retriever.prefetch_policy.side_effect = lambda: order.append('prefetch')
        model = service._chat
        service._chat = lambda *args: (order.append('model'), model(*args))[1]
        service.prepare_answer('Prepare coaching for Alex Smith performance', 's', ConversationHistory())
        self.assertEqual(order, ['prefetch', 'model', 'model'])  # before planner and synthesis

    def test_coaching_command_tries_fast_path_then_falls_back_to_direct_route(self):
        service, supervisor, _ = self.make_service(plan={'supported': False})
        supervisor.prepare_direct_answer.return_value = PendingAgentAnswer(answer='Direct')
        directive = ('Mandatory application routing directive: Call the Employee Performance Agent '
                     'subagent/tool now. Employee question: What do ratings mean?')
        pending = service.prepare_direct_answer('/performance', 'What do ratings mean?', directive, 's')
        self.assertEqual(pending.answer, 'Direct')
        service._chat.assert_called_once()  # the planner ran first
        supervisor.prepare_answer.assert_not_called()

    def test_other_commands_go_straight_to_the_direct_route(self):
        service, supervisor, _ = self.make_service()
        supervisor.prepare_direct_answer.return_value = PendingAgentAnswer(answer='Direct')
        directive = 'Mandatory application routing directive: Call the Branch Operations specialist now.'
        service.prepare_direct_answer('/policy', 'Retention?', directive, 's')
        service._chat.assert_not_called()
        supervisor.prepare_direct_answer.assert_called_once_with('/policy', 'Retention?', directive, 's',
                                                                 on_event=None)

    def test_company_name_is_not_a_branch_filter(self):
        service, supervisor, retriever = self.make_service(plan={
            'supported': True, 'needs_data': True, 'needs_policy': False,
            'filters': {'branch_names': ['Mariner'], 'datasets': ['history']}})
        pending = service.prepare_answer('What are the performance ratings at Mariner?', 's', ConversationHistory())
        self.assertEqual(pending.answer, 'Existing route')  # no real scope left: the Supervisor answers
        retriever.retrieve.assert_not_called()

    def test_company_name_is_dropped_but_real_scope_is_kept(self):
        service, _, retriever = self.make_service(plan={
            'supported': True, 'needs_data': True, 'needs_policy': False,
            'filters': {'branch_names': ['Mariner Finance', 'Dallas'], 'datasets': ['history']}})
        retriever.retrieve.return_value.update(branch_availability=[{'branch_name': 'Dallas'}], policy=[])
        service._chat = Mock(side_effect=[
            ({'supported': True, 'needs_data': True, 'needs_policy': False,
              'filters': {'branch_names': ['Mariner Finance', 'Dallas'], 'datasets': ['history']}}, TokenUsage()),
            ({'answer': 'Dallas ratings', 'citation_labels': []}, TokenUsage())])
        pending = service.prepare_answer('Performance ratings for Dallas at Mariner Finance', 's', ConversationHistory())
        self.assertEqual(retriever.retrieve.call_args.args[0].branch_names, ('Dallas',))
        self.assertEqual(pending.answer, 'Dallas ratings')

    def test_names_that_match_nothing_use_the_existing_route(self):
        service, supervisor, retriever = self.make_service(plan={
            'supported': True, 'needs_data': True, 'needs_policy': False,
            'filters': {'branch_names': ['Atlantis'], 'datasets': ['history']}})
        retriever.retrieve.return_value = {'history': [], 'profiles': [], 'branch_availability': [], 'policy': []}
        pending = service.prepare_answer('Performance at the Atlantis branch', 's', ConversationHistory())
        self.assertEqual(pending.answer, 'Existing route')
        self.assertEqual(service._chat.call_count, 1)  # no synthesis from empty results

    def test_partial_matches_stay_on_the_fast_path(self):
        service, _, retriever = self.make_service()  # Employee A found, Employee B missing
        retriever.retrieve.return_value['missing_employee_names'] = ['employee b']
        pending = service.prepare_answer('Coaching plan for Employee A and Employee B performance', 's',
                                         ConversationHistory())
        self.assertEqual(pending.answer, 'Advisory plan')

    def test_synthesis_never_names_internal_fields(self):
        from mariner_genai_dbx.performance_fast_path import SYNTHESIS
        self.assertIn('Never mention internal field, list or record names', SYNTHESIS)

    def test_other_application_domains_never_enter_planner_or_new_retrieval(self):
        service, supervisor, retriever = self.make_service()
        for domain in ('Branch Operations specialist named mariner-policy-assistant',
                       'Employee Handbook specialist named mariner-handbook-assistant', 'Benefits Agent'):
            message = 'Mandatory application routing directive: Call the ' + domain + ' subagent/tool now. Employee question: performance ratings'
            result = service.prepare_answer(message, 's', ConversationHistory())
            self.assertEqual(result.answer, 'Existing route')
        self.assertEqual(supervisor.prepare_answer.call_count, 3)
        service._chat.assert_not_called()
        retriever.retrieve.assert_not_called()

    def test_policy_only_does_not_query_employee_data(self):
        service, _, retriever = self.make_service(plan={
            'supported': True, 'needs_data': False, 'needs_policy': True, 'filters': {}})
        service.prepare_answer('Explain the performance rating scale', 's', ConversationHistory())
        self.assertFalse(retriever.retrieve.call_args.kwargs['include_data'])
        self.assertTrue(retriever.retrieve.call_args.kwargs['include_policy'])

    def test_planner_does_not_set_selection_limits_from_an_expected_team_size(self):
        service, _, retriever = self.make_service(plan={
            'supported': True, 'needs_data': True, 'needs_policy': True,
            'filters': {'branch_names': ['Different Branch'], 'max_employees': 1, 'max_branches': 1}})
        service.prepare_answer('Team performance at Different Branch', 's', ConversationHistory())
        query = retriever.retrieve.call_args.args[0]
        self.assertEqual(query.max_employees, 50)
        self.assertEqual(query.max_branches, 50)

    def test_data_only_does_not_call_policy(self):
        service, _, retriever = self.make_service(plan={'supported': True, 'needs_data': True, 'needs_policy': False,
            'filters': {'branch_names': ['Different Branch'], 'datasets': ['branch_summary'], 'cycle_ids': ['CY2027Q1']}},
            synthesis={'answer': 'Requested quarter is unavailable', 'citation_labels': []})
        retriever.retrieve.return_value['policy'] = []
        p = service.prepare_answer('Branch performance for Different Branch', 's', ConversationHistory())
        self.assertEqual(p.citation_references, ())

    def test_unsupported_or_unscoped_plans_fall_back_before_reads(self):
        plans = [{'supported': False}, {'supported': True, 'needs_data': True, 'needs_policy': True, 'filters': {}},
                 {'supported': True, 'needs_data': True, 'needs_policy': True, 'filters': {'sql': 'SELECT *'}}]
        for plan in plans:
            service, supervisor, retriever = self.make_service(plan=plan)
            service.prepare_answer('Performance question', 's', ConversationHistory())
            supervisor.prepare_answer.assert_called_once()
            retriever.retrieve.assert_not_called()

    def test_unknown_or_omitted_citation_label_fails_without_a_slow_retry(self):
        for selected in (['forged'], []):
            service, supervisor, _ = self.make_service(synthesis={'answer': 'Policy claim', 'citation_labels': selected})
            with self.assertRaises(SupervisorInvocationError):
                service.prepare_answer('Performance goals', 's', ConversationHistory())
            supervisor.prepare_answer.assert_not_called()

    def test_ambiguous_employee_requires_clarification(self):
        service, _, retriever = self.make_service()
        retriever.retrieve.side_effect = PerformanceSelectionError('Employee name is ambiguous')
        pending = service.prepare_answer('Performance goals', 's', ConversationHistory())
        self.assertIn('provide the employee ID', pending.answer)
        self.assertEqual(service._chat.call_count, 1)

    def test_policy_metadata_is_validated_before_synthesis(self):
        service, supervisor, _ = self.make_service()
        service.prepare_answer('Performance goals', 's', ConversationHistory())
        supervisor.resolve_answer.assert_called_once()
        self.assertEqual(supervisor.resolve_answer.call_args.args[0].citation_references, (CITATION,))

    def test_model_fenced_json_is_parsed_but_incomplete_blocks_are_rejected(self):
        service, _, _ = self.make_service()
        del service._chat
        service._invoke = Mock(return_value={'choices': [{'finish_reason': 'stop',
            'message': {'content': '```json\n{"supported":false}\n```\nExplanation'}}]})
        value, _ = service._chat('Planner', {}, 100)
        self.assertEqual(value, {'supported': False})
        service._invoke.return_value['choices'][0]['message']['content'] = '```json\n{"supported":false}'
        with self.assertRaises(ValueError):
            service._chat('Planner', {}, 100)


if __name__ == '__main__':
    unittest.main()
