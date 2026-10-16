import csv
import json
import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import stress_Test.Scripts.build_stress_dashboard_FLASK as dashboard


class FlaskDashboardTests(unittest.TestCase):
    def make_run(self, root, name='STRESS-test', endpoint='http://127.0.0.1:5000/api/v1/chat', complete=False):
        folder = root / name
        folder.mkdir()
        config = dict(test_type='flask_http', endpoint=endpoint, base_url=endpoint.removesuffix('/api/v1/chat'),
                      concurrency=1, started_at='2026-10-15T18:00:00+00:00', auth='none',
                      backend_mode_declared='unknown', target_seconds=60, deadline_seconds=180,
                      min_reliability_percent=99, duration_seconds=300, warmup_seconds=60,
                      network_timeout_seconds=180, question_sha256='question', run_note='baseline')
        (folder / 'run.json').write_text(json.dumps(config))
        rows = [dict(workflow_id=name+'-measurement-000001', phase='measurement',
                     timestamp='2026-10-15T18:01:00+00:00', started_at='2026-10-15T18:00:40+00:00',
                     finished_at='2026-10-15T18:01:00+00:00', outcome='SUCCESS_WITHIN_TARGET',
                     elapsed_seconds='20', http_seconds='19', minute='0', http_status='200', request_id='req-1')]
        with (folder / 'workflows.csv').open('w', newline='') as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
        if complete:
            summary = dashboard.partial_summary(config, rows, [])
            summary.update(run_status='COMPLETE', measurement_complete=True, passed=True,
                           completed_workflows_per_second_including_drain=.05,
                           successful_workflows_per_second_including_drain=.05,
                           finished_at='2026-10-15T18:01:00+00:00')
            (folder / 'summary.json').write_text(json.dumps(summary))
        return folder

    def test_partial_run_cannot_pass_or_invent_throughput(self):
        with tempfile.TemporaryDirectory() as directory:
            self.make_run(Path(directory))
            run = dashboard.load_runs(Path(directory))['runs'][0]
        self.assertTrue(run['partial'])
        self.assertFalse(run['summary']['passed'])
        self.assertEqual(run['summary']['run_status'], 'NO_SUMMARY')
        self.assertIsNone(run['summary']['successful_workflows_per_second_including_drain'])
        self.assertEqual(run['http_status_counts'], {'200': 1})
        self.assertEqual(run['successful_http_latency_seconds']['mean'], 19)
        self.assertNotIn('summary.json', run['files'])
        self.assertNotIn('invocations.csv', run['files'])

    def test_completed_csv_reconciliation(self):
        with tempfile.TemporaryDirectory() as directory:
            self.make_run(Path(directory), complete=True)
            run = dashboard.load_runs(Path(directory))['runs'][0]
        self.assertFalse(run['partial'])
        self.assertEqual(run['checks'], [])
        self.assertTrue(run['summary']['passed'])
        self.assertIn('summary.json', run['files'])

    def test_local_and_deployed_targets_get_separate_groups(self):
        with tempfile.TemporaryDirectory() as directory:
            self.make_run(Path(directory), name='STRESS-local')
            self.make_run(Path(directory), name='STRESS-deployed', endpoint='https://example.test/api/v1/chat')
            runs = dashboard.load_runs(Path(directory))['runs']
        self.assertEqual(len({run['group_key'] for run in runs}), 2)

    def test_non_flask_run_is_excluded(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = self.make_run(Path(directory))
            (folder / 'run.json').write_text(json.dumps({'test_type': 'supervisor'}))
            data = dashboard.load_runs(Path(directory))
        self.assertEqual(data['runs'], [])
        self.assertEqual(len(data['skipped']), 1)

    def test_empty_output_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / 'new-results'
            with patch('sys.argv', ['builder', '--root', str(root)]), patch('builtins.print'):
                dashboard.main()
            output = (root / 'flask_stress_test_dashboard.html').read_text()
        self.assertIn('No Flask run metadata', output)
        self.assertIn('"runs": []', output)

    def test_embedded_data_escapes_html_and_preserves_text(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            folder = self.make_run(root)
            config = json.loads((folder / 'run.json').read_text())
            note = '</script><script>bad()</script>'
            config['run_note'] = note
            (folder / 'run.json').write_text(json.dumps(config))
            with patch('sys.argv', ['builder', '--root', str(root)]), patch('builtins.print'):
                dashboard.main()
            output = (root / 'flask_stress_test_dashboard.html').read_text()
            encoded = re.search(r'<script id="dashboard-data" type="application/json">(.*?)</script>', output, re.S).group(1)
        self.assertNotIn('<', encoded)
        self.assertEqual(json.loads(encoded)['runs'][0]['config']['run_note'], note)
        self.assertNotIn('invocations.csv', output)

    def test_truncated_csv_row_is_ignored(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = self.make_run(Path(directory))
            with (folder / 'workflows.csv').open('a') as handle:
                handle.write('STRESS-partial,measurement,')
            run = dashboard.load_runs(Path(directory))['runs'][0]
        self.assertEqual(run['csv_count'], 1)


if __name__ == '__main__':
    unittest.main()
