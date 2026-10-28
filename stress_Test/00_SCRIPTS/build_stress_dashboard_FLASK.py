"""Build a standalone Flask HTTP dashboard from stress_Test/FLASK/STRESS-* runs.

Usage: python3 build_stress_dashboard_FLASK.py
Re-run after each completed experiment to refresh the snapshot. Uses stdlib only.
"""
import argparse
import csv
import json
import math
import statistics
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


def stats(values):
    values = sorted(float(value) for value in values if value not in (None, ''))
    if not values:
        return dict(count=0, mean=None, p50=None, p95=None, p99=None, max=None)
    return {'count': len(values), 'mean': statistics.mean(values), 'max': max(values),
            **{name: values[math.ceil(len(values) * quantile) - 1]
               for name, quantile in (('p50', .5), ('p95', .95), ('p99', .99))}}


def partial_summary(config, rows, attempts):
    """Provisional finalized-row statistics, never an inferred passing verdict."""
    counts = Counter(row['outcome'] for row in rows)
    buckets = {}
    for row in rows:
        buckets.setdefault(int(float(row.get('minute') or 0)), []).append(row)
    good = [row for row in rows if row['outcome'] in ('SUCCESS_WITHIN_TARGET', 'SUCCESS_LATE')]
    bad = [row for row in rows if row['outcome'] not in ('SUCCESS_WITHIN_TARGET', 'SUCCESS_LATE')]
    return {'test_type': 'flask_http', 'run_status': 'NO_SUMMARY', 'measurement_complete': False,
            'passed': False, 'workflows_started': len(rows), 'outcomes': dict(counts),
            'reliability_percent': 100 * counts['SUCCESS_WITHIN_TARGET'] / len(rows) if rows else None,
            'target_seconds': config.get('target_seconds'),
            'required_reliability_percent': config.get('min_reliability_percent'),
            'successful_latency_seconds': stats([r.get('elapsed_seconds') for r in good]),
            'failed_latency_seconds': stats([r.get('elapsed_seconds') for r in bad]),
            'completed_workflows_per_second_including_drain': None,
            'successful_workflows_per_second_including_drain': None,
            'http_attempt_outcomes': dict(Counter(r['outcome'] for r in attempts)),
            'per_minute_start_cohorts': [
                {'minute': minute, 'started': len(group),
                 'outcomes': dict(Counter(r['outcome'] for r in group))}
                for minute, group in sorted(buckets.items())], 'phases': []}


def read_csv(path):
    if not path.exists():
        return []
    with path.open(newline='', encoding='utf-8') as handle:
        # Ignore an incomplete final write in a snapshot of a running experiment.
        rows = []
        for row in csv.DictReader(handle):
            if row.get('outcome') not in {'SUCCESS_WITHIN_TARGET', 'SUCCESS_LATE', 'FAILED',
                                          'DEADLINE_EXCEEDED', 'INTERRUPTED'}:
                continue
            try:
                elapsed = float(row.get('elapsed_seconds') or '')
            except ValueError:
                continue
            if (math.isfinite(elapsed) and elapsed >= 0 and row.get('workflow_id')
                    and row.get('phase') and (row.get('finished_at') or row.get('timestamp'))):
                rows.append(row)
        return rows


def load_runs(root):
    runs, skipped = [], []
    for folder in sorted(root.glob('STRESS-*')):
        if not folder.is_dir():
            continue
        try:
            config = json.loads((folder / 'run.json').read_text())
        except (FileNotFoundError, json.JSONDecodeError) as error:
            skipped.append({'folder': folder.name, 'reason': 'Unreadable run.json: ' + type(error).__name__})
            continue
        if config.get('test_type') != 'flask_http':
            skipped.append({'folder': folder.name, 'reason': 'Not a Flask HTTP experiment'})
            continue
        all_rows = read_csv(folder / 'workflows.csv')
        rows = [row for row in all_rows if row.get('phase') == 'measurement']
        attempts = [row for row in read_csv(folder / 'attempts.csv') if row.get('phase') == 'measurement']
        checks = []
        try:
            summary = json.loads((folder / 'summary.json').read_text())
            partial = False
        except (FileNotFoundError, json.JSONDecodeError):
            summary, partial = partial_summary(config, rows, attempts), True
        counts = Counter(row['outcome'] for row in rows)
        if not partial:
            if len(rows) != summary.get('workflows_started'):
                checks.append('Workflow CSV count differs from summary.')
            if dict(counts) != summary.get('outcomes', {}):
                checks.append('Workflow CSV outcomes differ from summary.')
        failures = [row for row in rows if row['outcome'] not in ('SUCCESS_WITHIN_TARGET', 'SUCCESS_LATE')]
        signatures = Counter((row.get('stage') or 'Unknown', row.get('error_category') or 'Unknown',
                              row.get('exception_chain') or 'No exception chain recorded',
                              row.get('app_error_code') or '') for row in failures)
        sample_fields = ('workflow_id', 'started_at', 'outcome', 'stage', 'error_category',
                         'exception_chain', 'request_id', 'header_request_id', 'http_status', 'app_error_code')
        endpoint = config.get('endpoint', config.get('base_url', 'Unknown'))
        grouping = (endpoint, config.get('auth'), config.get('backend_mode_declared'),
                    config.get('question_sha256'), config.get('target_seconds'),
                    config.get('deadline_seconds'), config.get('min_reliability_percent'),
                    config.get('network_timeout_seconds'), config.get('connect_timeout_seconds'))
        label = (f"{endpoint} · auth={config.get('auth', 'unknown')} · backend={config.get('backend_mode_declared', 'unknown')}"
                 f" · target={config.get('target_seconds')}s / deadline={config.get('deadline_seconds')}s"
                 f" · required={config.get('min_reliability_percent')}%"
                 f" · question={str(config.get('question_sha256', 'unknown'))[:8]}"
                 f" · network={config.get('network_timeout_seconds')}s")
        http_counts = dict(Counter(row.get('http_status') or 'NO_RESPONSE' for row in rows))
        app_codes = dict(Counter(row['app_error_code'] for row in failures if row.get('app_error_code')))
        # app_error_message exists in runs from 2026-10-28 on; older runs only have the code.
        errors = Counter((' · '.join(x for x in (row.get('app_error_code'), row.get('app_error_message')) if x)
                          or ('Not recorded' if 'app_error_message' in row else 'Not recorded (run predates error details)'),
                          row.get('error_category') or 'Unknown') for row in failures)
        good = [row for row in rows if row['outcome'] in ('SUCCESS_WITHIN_TARGET', 'SUCCESS_LATE')]
        runs.append({'folder': folder.name, 'config': config, 'summary': summary, 'partial': partial,
                     'checks': checks, 'group_key': json.dumps(grouping), 'group_label': label,
                     'csv_count': len(rows), 'http_status_counts': http_counts,
                     'app_error_codes': app_codes,
                     'error_codes': [{'error': error, 'category': category, 'count': count}
                                     for (error, category), count in errors.most_common()],
                     'phase_outcomes': dict(Counter(f"{row.get('phase', 'unknown')}: {row['outcome']}" for row in all_rows)),
                     'successful_http_latency_seconds': stats([row.get('http_seconds') for row in good]),
                     'files': [name for name in ('run.json', 'summary.json', 'workflows.csv', 'attempts.csv', 'events.csv')
                               if (folder / name).exists()],
                     'failure_signatures': [
                         {'stage': stage, 'category': category, 'chain': chain, 'app_code': code, 'count': count}
                         for (stage, category, chain, code), count in signatures.most_common()],
                     'failure_samples': [{key: row.get(key, '') for key in sample_fields} for row in failures[:5]]})
    runs.sort(key=lambda run: (run['config'].get('concurrency', 0), run['config'].get('started_at', '')))
    return {'generated_at': datetime.now(timezone.utc).isoformat(), 'runs': runs, 'skipped': skipped}

TEMPLATE = r'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Flask stress test · HTTP reliability dashboard</title>
<style>
:root{--ink:#142834;--muted:#526571;--paper:#f3f5f4;--card:#fff;--line:#dbe3e2;--good:#087b68;--late:#ac7207;--bad:#bd4049;--timeout:#6954a5;--other:#72838b;--blue:#316aba;--track:#e9efed}
*{box-sizing:border-box}body{margin:0;background:var(--paper);color:var(--ink);font:15px/1.55 system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}header{background:var(--ink);color:#f5faf8;padding:38px max(24px,calc((100vw - 1280px)/2));border-bottom:5px solid #35ba9f}header .eyebrow{color:#8cdbc8;font-size:12px;font-weight:700;letter-spacing:.16em;text-transform:uppercase}h1{font-size:clamp(28px,4vw,42px);line-height:1.16;letter-spacing:-.035em;margin:10px 0 12px}header p{color:#cad8dc;max-width:860px;margin:0}main{max-width:1328px;margin:auto;padding:26px 24px 40px}h2{font-size:20px;letter-spacing:-.02em;margin:0 0 6px}h3{font-size:16px;margin:0 0 8px}p{margin:0 0 14px}.sub,.muted{overflow-wrap:anywhere;color:var(--muted);font-size:13px}.sub{margin-bottom:20px}.meta{display:flex;gap:8px 20px;flex-wrap:wrap;margin-top:22px;color:#c5d8dc;font-size:12px;font-variant-numeric:tabular-nums}.metrics{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:15px;margin-bottom:22px}.metric,.panel{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:22px}.metric .value{font-size:32px;letter-spacing:-.04em;line-height:1.25;margin:9px 0;font-weight:650}.metric .label{font-size:12px;text-transform:uppercase;letter-spacing:.07em;color:var(--muted)}.metric p{font-size:12px;margin:0;color:var(--muted)}.insight{border-left:4px solid var(--bad);background:#fff;padding:18px 22px;margin:0 0 22px;display:grid;grid-template-columns:1.1fr 2fr;gap:20px}.insight strong{font-size:18px}.insight p{margin:0;color:var(--muted);font-size:14px}.grid{display:grid;grid-template-columns:1fr 1fr;gap:20px;margin-bottom:20px}.wide{grid-column:1/-1}.panel{min-width:0}.legend{display:flex;flex-wrap:wrap;gap:8px 16px;font-size:12px;margin:8px 0 18px;color:var(--muted)}.legend span:before{content:"";display:inline-block;width:9px;height:9px;margin-right:6px;background:var(--swatch);border-radius:2px}.barrow{display:grid;grid-template-columns:72px 1fr 68px;align-items:center;gap:10px;margin:17px 0;font-size:12px;font-variant-numeric:tabular-nums}.track{display:flex;position:relative;height:23px;border-radius:3px;background:var(--track)}.segment{height:100%;min-width:0}.track .target{position:absolute;height:31px;top:-4px;border-left:2px dashed var(--ink);left:99%;z-index:1}.target-label{text-align:right;font-size:11px;color:var(--muted)}.throughputrow{display:grid;grid-template-columns:72px 1fr 82px;gap:10px;align-items:center;margin:14px 0;font-size:12px}.doubletrack{height:31px;position:relative}.doubletrack i{position:absolute;display:block;height:12px;border-radius:2px;left:0}.doubletrack .total{top:0;background:#aebbc0}.doubletrack .successful{bottom:0;background:var(--good)}.right{text-align:right;font-variant-numeric:tabular-nums}.scroll{overflow-x:auto}table{border-collapse:collapse;width:100%;font-size:13px}th{text-align:left;color:var(--muted);font-weight:550;font-size:11px;letter-spacing:.035em;text-transform:uppercase;white-space:nowrap}td,th{padding:12px 10px;border-bottom:1px solid var(--line)}tbody tr:last-child td{border-bottom:none}td.num,th.num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}.badge{display:inline-block;font-size:11px;font-weight:700;padding:3px 8px;border-radius:20px;white-space:nowrap}.pass{background:#e2f3ee;color:#096951}.fail{background:#fbecee;color:#a23440}.pending{background:#f0ebfa;color:#5c4891}a{color:var(--blue);text-decoration:underline;text-underline-offset:3px}button,select{font:inherit}button{background:transparent;border:0;color:var(--blue);text-decoration:underline;padding:0;cursor:pointer;text-align:left}button:focus-visible,a:focus-visible,select:focus-visible{outline:3px solid var(--blue);outline-offset:4px}select{padding:9px 12px;max-width:100%;border:1px solid #aabbbd;background:white;color:var(--ink);border-radius:5px}label{display:block;font-size:12px;margin-bottom:6px;color:var(--muted)}#detail-toggle>summary{cursor:pointer;list-style:none;display:flex;align-items:baseline;gap:12px;flex-wrap:wrap}#detail-toggle>summary::-webkit-details-marker{display:none}#detail-toggle>summary h2{margin:0}#detail-toggle>summary h2:before{content:"▸";display:inline-block;width:1.1em;color:var(--blue);transition:transform .15s}#detail-toggle[open]>summary h2:before{transform:rotate(90deg)}#detail-toggle[open]>summary{margin-bottom:16px}#detail-toggle>summary:focus-visible{outline:3px solid var(--blue);outline-offset:4px}.detail-head{display:flex;justify-content:space-between;gap:18px;flex-wrap:wrap;margin-bottom:20px}.detail-facts{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:14px;margin-bottom:24px}.detail-facts .number{font-size:23px;font-weight:650;font-variant-numeric:tabular-nums}.detail-facts small{display:block;color:var(--muted);font-size:12px}.links{display:flex;gap:10px 18px;flex-wrap:wrap;margin-top:18px;font-size:12px}.mono{font:12px/1.5 ui-monospace,SFMono-Regular,Consolas,monospace;overflow-wrap:anywhere}.notice{background:#faf4e5;color:#745414;padding:12px 15px;border-radius:5px;font-size:13px;margin-bottom:18px}.detailgrid{display:grid;grid-template-columns:1fr 1fr;gap:24px}.chart svg{display:block;width:100%}.chart text{font-family:inherit;fill:var(--muted);font-size:11px}.chart .axis{stroke:var(--line);stroke-width:1}.chart .series{fill:none;stroke-width:2.5}.chart .threshold{stroke:#7a8990;stroke-dasharray:4 4}.footnotes{margin-top:22px;display:grid;grid-template-columns:1fr 1fr;gap:24px;font-size:12px;color:var(--muted)}.footnotes p{margin-bottom:10px}footer{margin-top:24px;padding-top:16px;border-top:1px solid var(--line);font-size:12px;color:var(--muted)}.empty{padding:30px;text-align:center;color:var(--muted)}noscript{display:block;padding:25px}.sample{margin:10px 0;border-left:2px solid var(--line);padding-left:12px}.sample small{display:block;color:var(--muted)}
@media(max-width:900px){.metrics{grid-template-columns:repeat(2,minmax(0,1fr))}.grid,.detailgrid{grid-template-columns:1fr}.insight{grid-template-columns:1fr;gap:8px}}
@media(max-width:520px){main{padding:18px 12px}header{padding:28px 18px}.panel,.metric{padding:16px}.metrics{gap:10px}.metric .value{font-size:26px}.detail-facts{grid-template-columns:repeat(2,minmax(0,1fr))}.footnotes{grid-template-columns:1fr;gap:6px}.barrow{grid-template-columns:58px 1fr 58px;gap:6px}.throughputrow{grid-template-columns:58px 1fr 72px;gap:6px}}
@media print{header{background:white;color:var(--ink)}header p,.meta,header .eyebrow{color:var(--muted)}body{background:white}.panel,.metric{break-inside:avoid}button,select{color:var(--ink)}main{max-width:none}.links{display:none}.grid{grid-template-columns:1fr 1fr}}
</style>
</head><body>
<header><div class="eyebrow">Flask · Application HTTP reliability</div><h1>Flask reliability under load</h1><p>Local and deployed application experiments. Workflow reliability requires a valid chat response within target. Partial snapshots never receive a passing verdict.</p><div class="meta" id="metadata"></div></header>
<noscript>This dashboard requires JavaScript to display its embedded local results. No internet connection is required.</noscript>
<main>
<section class="panel" style="margin-bottom:20px"><label for="target-select">Comparison group: same endpoint, authentication, declared backend, question and thresholds</label><select id="target-select" style="width:100%;min-width:0"></select><p class="muted" style="margin:8px 0 0">Local and deployed results stay in separate groups. Server configuration is operator-supplied in run notes.</p></section><div id="warnings"></div><section class="metrics" id="metrics" aria-label="Experiment overview"></section>
<section class="insight" id="insight" aria-label="Main finding"></section>
<div class="grid">
<section class="panel"><h2>Workflow outcomes by load</h2><p class="sub">Share of measured workflows · target marker shows required reliability</p><div class="legend" id="outcome-legend"></div><div id="reliability"></div></section>
<section class="panel"><h2>Total and successful throughput</h2><p class="sub">Workflows per second, including drain · fast failures inflate total traffic</p><div class="legend"><span style="--swatch:#aebbc0">All outcomes</span><span style="--swatch:var(--good)">Successful, including late</span></div><div id="throughput"></div></section>
<section class="panel"><h2>Successful workflow latency</h2><p class="sub">Seconds · failed workflows excluded · late successes included</p><div class="legend"><span style="--swatch:var(--good)">p50</span><span style="--swatch:var(--blue)">p95</span><span style="--swatch:var(--timeout)">p99</span></div><div class="chart" id="latency-chart"></div></section>
<section class="panel"><h2>What the failure records establish</h2><p class="sub">Observed measured workflows only · local exception evidence, not proven root causes</p><div id="failure-overview"></div></section>
<section class="panel wide"><h2>Experiment comparison</h2><p class="sub">Select a load level to inspect its evidence. Warm-up and preflight are excluded from these metrics.</p><div class="scroll"><table id="comparison"><thead><tr><th>Clients / stage</th><th class="num">Workflows</th><th class="num">Within target</th><th class="num">Late</th><th class="num">Failures¹</th><th class="num">Reliability</th><th class="num">p95 / p99</th><th class="num">Success/s</th><th>Verdict</th></tr></thead><tbody></tbody></table></div></section>
<section class="panel wide"><h2>Error codes</h2><p class="sub">Measured failures grouped by the app's error code and message · runs in this comparison group</p><div class="scroll"><table id="error-codes"><thead><tr><th>Error</th><th>Category</th><th class="num"># times found</th><th>Found in</th></tr></thead><tbody></tbody></table></div></section>
<section class="panel wide" id="detail-section"><details id="detail-toggle"><summary><h2>Run evidence</h2><span class="sub">Select to show the evidence for one experiment</span></summary><div class="detail-head"><p class="sub" id="detail-id"></p><div><label for="run-select">Experiment</label><select id="run-select"></select></div></div><div id="detail" aria-live="polite"></div></details></section>
</div>
<section class="footnotes"><div><h3>Read the verdict correctly</h3><p>Reliability = workflows successful within target ÷ all measured workflows. Late answers miss the target. A completed experiment can fail its reliability requirement.</p><p>¹ Failures include FAILED, DEADLINE_EXCEEDED and INTERRUPTED. Percentiles use nearest rank and include successful-but-late answers. The 1-client baseline has a small sample; one passing run does not establish long-term reliability.</p></div><div><h3>Scope and attribution</h3><p>This tests POST /api/v1/chat through the selected Flask deployment. Timings include network/proxy delays, Flask scheduling, backend work, citations, persistence and analytics. Internal Databricks invocations are not observed by this client.</p><p>Workers issue requests continuously without employee think time. Local debug-server results describe that setup; deployed-server capacity must be tested separately. Missing HTTP responses or generic exception chains require additional server-side investigation.</p></div></section>
<footer id="footer"></footer>
</main>
<script id="dashboard-data" type="application/json">__DATA__</script>
<script>
'use strict';
const DATA=JSON.parse(document.getElementById('dashboard-data').textContent);
const allRuns=DATA.runs;
let runs=allRuns;
const $=id=>document.getElementById(id);
const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const n=(v,d=0)=>v===null||v===undefined?'—':Number(v).toLocaleString('en-US',{minimumFractionDigits:d,maximumFractionDigits:d});
const pct=v=>v===null||v===undefined?'—':n(v,2)+'%';
const sum=(items,fn)=>items.reduce((a,x)=>a+fn(x),0);
const count=(r,k)=>r.summary.outcomes?.[k]||0;
const successful=r=>count(r,'SUCCESS_WITHIN_TARGET')+count(r,'SUCCESS_LATE');
const failures=r=>r.summary.workflows_started-successful(r);
const complete=r=>r.summary.run_status==='COMPLETE'&&r.summary.measurement_complete;
const verdict=r=>!complete(r)?'<span class="badge pending">INCOMPLETE</span>':r.summary.passed?'<span class="badge pass">PASS</span>':'<span class="badge fail">MISS</span>';
const COLORS={SUCCESS_WITHIN_TARGET:'var(--good)',SUCCESS_LATE:'var(--late)',FAILED:'var(--bad)',DEADLINE_EXCEEDED:'var(--timeout)',INTERRUPTED:'var(--other)'};
const LABELS={SUCCESS_WITHIN_TARGET:'Within target',SUCCESS_LATE:'Late success',FAILED:'Failed',DEADLINE_EXCEEDED:'Deadline',INTERRUPTED:'Interrupted'};
const chicago=value=>value?new Intl.DateTimeFormat('en-US',{timeZone:'America/Chicago',month:'short',day:'numeric',hour:'numeric',minute:'2-digit',second:'2-digit',timeZoneName:'short'}).format(new Date(value)):'—';
const link=(r,file,label)=>`<a href="${encodeURIComponent(r.folder)}/${encodeURIComponent(file)}">${esc(label||file)}</a>`;
let loaded=[];
let totals={};
function lineChart(element, series, xlabels, options={}){
 const width=Math.max(element.clientWidth||600,250),height=230,left=43,right=20,top=20,bottom=42;
 const values=series.flatMap(s=>s.values.filter(v=>v!==null&&v!==undefined));
 const max=options.max||Math.max(1,...values,options.target||0)*1.12;
 const positions=options.xvalues||xlabels.map((_,i)=>i),xmin=Math.min(...positions),xmax=Math.max(...positions);
 const x=i=>left+(xmax>xmin?(positions[i]-xmin)/(xmax-xmin):.5)*(width-left-right),y=v=>height-bottom-v/max*(height-top-bottom);
 let html=`<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="${esc(options.label||'Trend chart')}"><title>${esc(options.label||'Trend chart')}</title>`;
 for(let i=0;i<=4;i++){const val=max*i/4;html+=`<line class="axis" x1="${left}" y1="${y(val)}" x2="${width-right}" y2="${y(val)}"/><text x="${left-8}" y="${y(val)+4}" text-anchor="end">${n(val,0)}</text>`;}
 if(options.target!==undefined)html+=`<line class="threshold" x1="${left}" y1="${y(options.target)}" x2="${width-right}" y2="${y(options.target)}"/>`;
 xlabels.forEach((label,i)=>{if(xlabels.length<=6||i%2===0||i===xlabels.length-1)html+=`<text x="${x(i)}" y="${height-17}" text-anchor="middle">${esc(label)}</text>`;});
 series.forEach(s=>{let path='';s.values.forEach((v,i)=>{if(v===null||v===undefined){path+=' ';return;}path+=`${i===0||s.values[i-1]===null||s.values[i-1]===undefined?'M':'L'}${x(i)},${y(v)} `;});html+=`<path class="series" d="${path}" style="stroke:${s.color}"/>`;s.values.forEach((v,i)=>{if(v!==null&&v!==undefined)html+=`<circle cx="${x(i)}" cy="${y(v)}" r="4" style="fill:${s.color}"><title>${esc(xlabels[i])}: ${esc(s.label)} ${n(v,2)}${esc(options.unit||'')}</title></circle>`;});});
 html+=`<text x="${left}" y="12">${esc(options.unit||'')}</text><text x="${width-right}" y="${height-1}" text-anchor="end">${esc(options.xaxis||'Concurrent clients')}</text></svg>`;
 element.innerHTML=html;
}
function renderOverview(){
 loaded=runs.filter(complete);
 totals={workflows:sum(runs,r=>r.summary.workflows_started||0),good:sum(runs,successful),ontime:sum(runs,r=>count(r,'SUCCESS_WITHIN_TARGET')),failed:sum(runs,failures)};
 $('metadata').innerHTML=`<span>${runs.length} runs · ${loaded.length} completed</span><span>Endpoint: ${esc([...new Set(runs.map(r=>r.config.endpoint))].join(', '))}</span><span>Latest run start: ${esc(chicago(runs.map(r=>r.config.started_at).filter(Boolean).sort().slice(-1)[0]))}</span>`;
 const passed=loaded.filter(r=>r.summary.passed);
 const warnings=runs.flatMap(r=>r.checks.map(c=>r.folder+': '+c));
 const partial=runs.filter(r=>r.partial);
 if(partial.length)warnings.push(`${partial.length} run(s) have no readable summary.json. Counts and latency use finalized CSV rows only; unfinished workflows are not included. Partial percentages are provisional and cannot pass.`);
 DATA.skipped.forEach(r=>warnings.push(r.folder+': '+r.reason+'; excluded from this snapshot.'));
 $('warnings').innerHTML=warnings.length?`<div class="notice">${warnings.map(esc).join('<br>')}</div>`:'';
 const metrics=[['Completed experiments',n(loaded.length),`${loaded.length?n(Math.min(...loaded.map(r=>r.config.concurrency))):'—'}–${loaded.length?n(Math.max(...loaded.map(r=>r.config.concurrency))):'—'} concurrent clients tested`],['Observed measured workflows',n(totals.workflows),'Warm-up excluded · partial counts provisional'],['Runs meeting target',`${passed.length} / ${loaded.length}`,'Verdict uses each run’s own target'],['Successful workflows',n(totals.good),`${n(totals.ontime)} within target · ${n(totals.failed)} failures`]];
 $('metrics').innerHTML=metrics.map(([label,value,note])=>`<article class="metric"><div class="label">${esc(label)}</div><div class="value">${esc(value)}</div><p>${esc(note)}</p></article>`).join('');
 const misses=loaded.filter(r=>!r.summary.passed);
 $('insight').innerHTML=!loaded.length?'<strong>Partial results; verdict pending</strong><p>No completed measurement is available in this comparison group. Provisional statistics cover finalized CSV rows only and omit unfinished work.</p>':misses.length?`<strong>${misses.length} of ${loaded.length} completed runs missed target</strong><p>The first miss in load order is ${n(misses[0].config.concurrency)} clients at ${pct(misses[0].summary.reliability_percent)} within target. Use HTTP status, app error codes and server logs to investigate; client evidence alone does not establish the cause.</p>`:'<strong>All completed runs in this group meet target</strong><p>These observations describe this deployment and workload. Repeat near the operating boundary; a small passing sample does not establish long-term reliability.</p>';
 $('outcome-legend').innerHTML=Object.keys(LABELS).map(k=>`<span style="--swatch:${COLORS[k]}">${LABELS[k]}</span>`).join('');
 $('reliability').innerHTML=runs.map(r=>{const total=r.summary.workflows_started||0;const pieces=Object.keys(LABELS).map(k=>`<div class="segment" style="width:${total?100*count(r,k)/total:0}%;background:${COLORS[k]}" title="${LABELS[k]}: ${count(r,k)}"></div>`).join('');return `<div class="barrow"><span>${n(r.config.concurrency)} clients</span><div class="track" role="img" aria-label="${esc(`${r.config.concurrency} clients: ${pct(r.summary.reliability_percent)} within target`)}">${pieces}<i class="target" style="left:${r.summary.required_reliability_percent}%"></i></div><strong class="right">${pct(r.summary.reliability_percent)}</strong></div>`;}).join('')+'<div class="target-label">Dashed marker = required reliability (per-run threshold)</div>';
 const max=Math.max(1,...runs.map(r=>r.summary.completed_workflows_per_second_including_drain||0));
 $('throughput').innerHTML=runs.map(r=>{const total=r.summary.completed_workflows_per_second_including_drain,good=r.summary.successful_workflows_per_second_including_drain;if(total===null||total===undefined)return `<div class="throughputrow"><span>${n(r.config.concurrency)} clients</span><div class="muted">Pending completed measurement</div><div class="right">— / —</div></div>`;return `<div class="throughputrow"><span>${n(r.config.concurrency)} clients</span><div class="doubletrack" role="img" aria-label="${n(total,3)} total and ${n(good,3)} successful workflows per second"><i class="total" style="width:${100*total/max}%"></i><i class="successful" style="width:${100*good/max}%"></i></div><div class="right">${n(total,2)} / <strong>${n(good,2)}</strong></div></div>`;}).join('');
 $('comparison').querySelector('tbody').innerHTML=runs.map((r,i)=>`<tr><td><button type="button" data-run="${i}">${n(r.config.concurrency)} clients</button><div class="muted">${esc(r.config.run_note)}</div></td><td class="num">${n(r.summary.workflows_started)}</td><td class="num">${n(count(r,'SUCCESS_WITHIN_TARGET'))}</td><td class="num">${n(count(r,'SUCCESS_LATE'))}</td><td class="num">${n(failures(r))}</td><td class="num"><strong>${pct(r.summary.reliability_percent)}</strong></td><td class="num">${n(r.summary.successful_latency_seconds?.p95,1)} / ${n(r.summary.successful_latency_seconds?.p99,1)} s</td><td class="num">${n(r.summary.successful_workflows_per_second_including_drain,3)}</td><td>${verdict(r)}</td></tr>`).join('');
 $('run-select').innerHTML=runs.map((r,i)=>`<option value="${i}">${n(r.config.concurrency)} clients · ${esc(r.config.run_note||r.folder)}</option>`).join('');
 const signatures=new Map();runs.forEach(r=>r.failure_signatures.forEach(f=>{const key=[f.category,f.app_code,f.chain].filter(Boolean).join(' · ');signatures.set(key,(signatures.get(key)||0)+f.count)}));
 $('failure-overview').innerHTML=[...signatures.entries()].sort((a,b)=>b[1]-a[1]).map(([chain,count])=>`<div class="sample"><strong>${n(count)} workflows</strong><div class="mono">${esc(chain)}</div></div>`).join('')||'<p>No measured failures recorded in finalized rows.</p>';
 $('failure-overview').innerHTML+='<p class="muted" style="margin-top:18px">HTTP 401/403 indicates an authentication rejection; 429 indicates rate limiting at the responding layer. App error codes help distinguish backend and citation failures. Connection errors and client deadlines alone do not establish the server-side cause.</p>';
 const errorCodes=new Map();runs.forEach(r=>(r.error_codes||[]).forEach(e=>{const key=e.error+'\u0000'+e.category;const item=errorCodes.get(key)||{error:e.error,category:e.category,count:0,runs:[]};item.count+=e.count;item.runs.push(`${n(r.config.concurrency)} clients ×${n(e.count)}`);errorCodes.set(key,item);}));
 $('error-codes').querySelector('tbody').innerHTML=[...errorCodes.values()].sort((a,b)=>b.count-a.count).map(e=>`<tr><td class="mono">${esc(e.error)}</td><td>${esc(e.category)}</td><td class="num"><strong>${n(e.count)}</strong></td><td class="muted">${esc(e.runs.join(' · '))}</td></tr>`).join('')||'<tr><td colspan="4" class="muted">No measured failures recorded.</td></tr>';
 $('footer').textContent=`Static snapshot generated ${chicago(DATA.generated_at)}. Rebuild with: python3 build_stress_dashboard_FLASK.py. Sources: run.json, summary.json and measurement rows in workflows.csv under STRESS-* directories. Times shown in America/Chicago.`;
}
function renderLatency(){lineChart($('latency-chart'),[['p50','var(--good)'],['p95','var(--blue)'],['p99','var(--timeout)']].map(([key,color])=>({label:key,color,values:runs.map(r=>r.summary.successful_latency_seconds?.[key]??null)})),runs.map(r=>String(r.config.concurrency)),{unit:'s',xvalues:runs.map(r=>r.config.concurrency),label:'Successful workflow latency percentiles by concurrent clients'});}
let selected=0;
function countTable(counts,label){const entries=Object.entries(counts);return entries.length?`<table><thead><tr><th>${esc(label)}</th><th class="num">Count</th></tr></thead><tbody>${entries.map(([code,count])=>`<tr><td>${esc(code)}</td><td class="num">${n(count)}</td></tr>`).join('')}</tbody></table>`:'<p class="muted">No observed records.</p>';}
function renderDetails(index){
 selected=index;const r=runs[index];if(!r)return;const s=r.summary,c=r.config;
 $('run-select').value=String(index);$('detail-id').textContent=r.folder;
 const phase=s.phases?.find(p=>p.phase==='measurement');
 const http2xx=Object.entries(r.http_status_counts).filter(([code])=>/^2\d\d$/.test(code)).reduce((a,[,v])=>a+v,0);
 const httpObserved=Object.values(r.http_status_counts).reduce((a,b)=>a+b,0);
 $('detail').innerHTML=`<div class="detail-facts"><div class="number">${verdict(r)}<small>${pct(s.reliability_percent)} within ${n(c.target_seconds)} s</small></div><div class="number">${n(s.workflows_started)}<small>Observed measured workflows · ${n(c.concurrency)} clients</small></div><div class="number">${n(s.successful_latency_seconds?.p99,1)} s<small>Successful-workflow p99</small></div><div class="number">${n(http2xx)} / ${n(httpObserved)}<small>HTTP 2xx responses · not a chat-validity verdict</small></div></div>
 <p class="muted">Target ${esc(c.endpoint)} · Auth ${esc(c.auth||'unknown')} · Backend declared ${esc(c.backend_mode_declared||'unknown')} (not remotely verified)</p>
 <p class="muted">Started ${esc(chicago(c.started_at))} · Measurement ${n(c.duration_seconds)} s + drain (${n(phase?.elapsed_with_drain_seconds,1)} s total) · Warm-up ${n(c.warmup_seconds)} s · Deadline ${n(c.deadline_seconds)} s · Network-operation timeout ${n(c.network_timeout_seconds)} s</p>
 <p class="muted">Observed phase outcomes: ${esc(Object.entries(r.phase_outcomes).map(([key,value])=>`${key} = ${value}`).join('; ')||'No finalized workflows yet')}</p>
 <div class="detailgrid" style="margin-bottom:20px"><div><h3>HTTP status evidence</h3>${countTable(r.http_status_counts,'HTTP status / no response')}</div><div><h3>Application error codes</h3>${countTable(r.app_error_codes,'App error code')}<p class="muted">A valid HTTP 200 must also pass JSON/chat-schema checks. Source presence does not prove answer quality.</p></div></div>
 <div class="detailgrid"><div><h3>Reliability by workflow start minute</h3><p class="sub">Percent within target · cohorts based on when work started</p><div class="chart" id="minute-chart"></div></div><div><h3>Failure signatures</h3>${r.failure_signatures.length?`<div class="scroll"><table><thead><tr><th>Stage / category</th><th class="num">Count</th></tr></thead><tbody>${r.failure_signatures.map(f=>`<tr><td>${esc(f.stage)} · ${esc(f.category)}${f.app_code?` · ${esc(f.app_code)}`:''}<div class="mono">${esc(f.chain)}</div></td><td class="num">${n(f.count)}</td></tr>`).join('')}</tbody></table></div>`:'<p class="muted">No measured failures.</p>'}</div></div>
 <div class="detailgrid" style="margin-top:22px"><div><h3>Chat response latency</h3><div class="scroll"><table><thead><tr><th>Call group</th><th class="num">Mean</th><th class="num">p95</th><th class="num">p99</th></tr></thead><tbody>${[['Successful workflow',s.successful_latency_seconds],['Successful HTTP transport',r.successful_http_latency_seconds],['Failed workflow',s.failed_latency_seconds]].map(([name,v])=>`<tr><td>${name}</td><td class="num">${n(v?.mean,2)} s</td><td class="num">${n(v?.p95,2)} s</td><td class="num">${n(v?.p99,2)} s</td></tr>`).join('')}</tbody></table></div><p class="muted" style="margin-top:8px">HTTP transport includes response-body download. Workflow timing also includes validation, dispatch and result collection. Neither isolates model execution or citation time.</p></div><div><h3>Example failed workflow IDs</h3>${r.failure_samples.length?r.failure_samples.map(f=>`<div class="sample"><div class="mono">${esc(f.workflow_id)}</div><small>${esc(f.outcome)} · ${esc(chicago(f.started_at))}</small><small>App request ID: <span class="mono">${esc(f.request_id||'Unavailable')}</span> · HTTP ${esc(f.http_status||'no response')}</small></div>`).join(''):'<p class="muted">No failed workflows to inspect.</p>'}</div></div>
 <h3 style="margin-top:22px">Error codes in this run</h3>${(r.error_codes||[]).length?`<div class="scroll"><table><thead><tr><th>Error</th><th>Category</th><th class="num"># times found</th></tr></thead><tbody>${r.error_codes.map(e=>`<tr><td class="mono">${esc(e.error)}</td><td>${esc(e.category)}</td><td class="num">${n(e.count)}</td></tr>`).join('')}</tbody></table></div>`:'<p class="muted">No measured failures.</p>'}
 <div class="links">${r.files.map(file=>link(r,file)).join('')}</div><p class="muted" style="margin-top:10px">${r.checks.length?esc(r.checks.join(' ')):r.partial?`Partial CSV snapshot: ${n(r.csv_count)} finalized measurement rows; summary unavailable.`:`CSV cross-check: ${n(r.csv_count)} measurement rows and outcome counts match summary.json.`}</p>`;
 renderMinute();
}
function renderMinute(){const r=runs[selected];if(!r)return;const cohorts=r.summary.per_minute_start_cohorts||[];if(!cohorts.length){$('minute-chart').innerHTML='<p class="muted">No measurement rows yet.</p>';return;}lineChart($('minute-chart'),[{label:'Within target',color:'var(--good)',values:cohorts.map(c=>c.started?100*(c.outcomes.SUCCESS_WITHIN_TARGET||0)/c.started:null)}],cohorts.map(c=>String(c.minute)),{unit:'%',max:100,target:r.summary.required_reliability_percent,xaxis:'Start minute (0-based)',label:'Workflow reliability by measurement start minute'});}
if(!runs.length){$('metrics').innerHTML='<p class="empty">No Flask run metadata was found. Run a Flask experiment, then rebuild this dashboard.</p>';$('warnings').textContent=DATA.skipped.map(s=>s.folder+': '+s.reason).join('; ');}
else{const groups=[...new Set(allRuns.map(r=>r.group_key))];$('target-select').innerHTML=groups.map((key,i)=>`<option value="${i}">${esc(allRuns.find(r=>r.group_key===key).group_label)}</option>`).join('');const newest=allRuns.slice().sort((a,b)=>String(a.config.started_at).localeCompare(String(b.config.started_at))).slice(-1)[0];function selectGroup(i){runs=allRuns.filter(r=>r.group_key===groups[i]);renderOverview();renderLatency();renderDetails(runs.length-1);}$('target-select').value=String(groups.indexOf(newest.group_key));selectGroup(Number($('target-select').value));$('target-select').addEventListener('change',e=>selectGroup(Number(e.target.value)));$('run-select').addEventListener('change',e=>renderDetails(Number(e.target.value)));$('detail-toggle').addEventListener('toggle',()=>{if($('detail-toggle').open)renderMinute();});$('comparison').addEventListener('click',e=>{const button=e.target.closest('button[data-run]');if(button){$('detail-toggle').open=true;renderDetails(Number(button.dataset.run));$('detail-section').scrollIntoView({behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'instant':'smooth'});$('run-select').focus({preventScroll:true});}});let pending;window.addEventListener('resize',()=>{clearTimeout(pending);pending=setTimeout(()=>{renderLatency();renderMinute();},100);});}
</script></body></html>'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path('stress_Test/FLASK'))
    args = parser.parse_args()
    data = load_runs(args.root)
    serialized = json.dumps(data, ensure_ascii=True).replace('<', r'\u003c')
    args.root.mkdir(parents=True, exist_ok=True)
    output = args.root / 'flask_stress_test_dashboard.html'
    output.write_text(TEMPLATE.replace('__DATA__', serialized), encoding='utf-8')
    print(f'Created {output.resolve()} ({len(data["runs"])} runs; {len(data["skipped"])} skipped)')
    for run in data['runs']:
        if run['checks']:
            print(run['folder'], '; '.join(run['checks']))


if __name__ == '__main__':
    main()
