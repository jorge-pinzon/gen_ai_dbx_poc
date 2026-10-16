# Databricks Supervisor stress-test guide

This guide describes an stress test in the supervisor agent (code: stress_test_DBX_3.py), the experiment process, and output. 

## Test goal

Measure whether the configured Supervisor workflow completes reliably within a chosen response-time target as simultaneous demand increases.

## 1. What the test measures

The script invokes the real Databricks Supervisor through the appliccurl -fsSL https://claude.ai/install.sh | bashation's existing client. Each workflow starts with empty conversation history and sends the configured question with a unique correlation ID.

```text
Parent runner: schedules work, enforces deadlines, and writes results
  └─ Persistent client process: one active workflow at a time
       ├─ Obtain or reuse an authentication token
       ├─ POST /serving-endpoints/{endpoint}/invocations
       ├─ Read and validate the response stream
       ├─ Continue approved worker calls when requested
       ├─ Validate final assistant output
       └─ Resolve citation labels through the configured resolver
```

A **workflow** is one call to the Supervisor's `answer()` method. An **invocation** is one call to the serving endpoint through `_invoke()`. An **HTTP attempt** is one inference POST within that invocation. One workflow can contain several invocations, and an invocation can contain a retry after an OAuth-related HTTP 401.

The script observes Supervisor-side HTTP requests made by the local client. It does not directly instrument every internal worker/model request made inside Databricks; use server traces for those details.

The measured workflow includes authentication, inference, approval continuations, final-output processing, citation lookup, and local dispatch/result-collection overhead. It is not a measurement of model execution time alone. It bypasses Flask's `/api/v1/chat` route and therefore does not measure frontend behavior, application authentication, Gunicorn scheduling, application guardrails, chat persistence, or analytics inserts.

## 2. Users, concurrency, and request counts

`--concurrency 10` creates up to ten persistent client processes. Each process owns its HTTP session, service instance, and token cache. A ready process starts another workflow as soon as its previous workflow completes, until the phase's submission window closes.

These clients are not separate authenticated employee accounts. They normally use the same configured service credentials. There is no reading time, think time, or fixed request-arrival rate.

There is no `TOTAL_REQUESTS` setting in this version. The number of workflows depends on concurrency, phase duration, response times, failures, and client overhead. With steady 20-second workflows, ten clients over 600 seconds would start approximately:

```text
10 × 600 / 20 ≈ 300 workflows
```

This is an illustration, not a quota. Fast failures can increase the number started. More completed workflows per second does not necessarily mean more successful answers per second.

For a company with 3,000 employees, concurrency describes people awaiting responses simultaneously, rather than the number employed, logged in, or viewing the application. Five hundred continuously busy clients impose more pressure than five hundred employees simply joining the application.

## 3. Configuration and prerequisites

Run commands from the repository root, using the Python environment where [requirements.txt](requirements.txt) is installed. `PYTHONPATH=src` makes the application's Python package discoverable for that command.

The runner uses the same `load_settings()` configuration as the application. It refuses to run unless `SUPERVISOR_MODE=databricks`, and its child processes also verify that the constructed service is a real Databricks Supervisor service.

Relevant application settings include:

| Setting | Purpose |
| --- | --- |
| `SUPERVISOR_MODE=databricks` | Required live mode. |
| `DATABRICKS_HOST` | Workspace hosting the serving endpoint. |
| `DATABRICKS_SUPERVISOR_ENDPOINT` | Supervisor endpoint name; `SUPERVISOR_ENDPOINT` is the compatibility fallback. |
| `DATABRICKS_CLIENT_ID`, `DATABRICKS_CLIENT_SECRET` | OAuth credentials when configured. |
| `DATABRICKS_TOKEN` | Supported development alternative, subject to application configuration validation. |
| `DATABRICKS_WAREHOUSE_ID` | Enables the configured Databricks citation resolver. |
| `REQUEST_TIMEOUT_SECONDS` | Network-operation timeout used by the Supervisor client; default 60 seconds. |

Development configuration can load allowlisted values from `.env`; process environment values take precedence. Production configuration follows the application's stricter validation and does not load `.env`. See [README.md](README.md) for complete setup and authentication rules.

The default question requests the policy specialist's answer about record retention. Use this unchanged for the first comparison across load levels. A later experiment can vary questions and specialists through separate runs. The runner currently accepts one question per run, not a question dataset.

## 4. Command-line arguments

```bash
PYTHONPATH=src python3 stress_test_DBX_3.py --help
```

| Argument | Code default | Meaning |
| --- | --- | --- |
| `--concurrency` | `10` | Maximum active client workflows. Positive integer. |
| `--duration-seconds` | `600` | Measurement-phase submission window. |
| `--warmup-seconds` | `30` | Warm-up submission window; zero disables warm-up. |
| `--target-seconds` | `60` | Maximum elapsed time for a successful workflow to count toward the reliability target. |
| `--deadline-seconds` | `180` | Overall local workflow deadline; must be at least the target. |
| `--startup-timeout-seconds` | `60` | Worker initialization timeout. |
| `--min-reliability-percent` | `99` | Minimum percentage of measured workflows that must succeed within target. |
| `--output-dir` | `stress_Test` | Parent directory for a unique run directory. |
| `--question` | Policy routing directive in `QUESTION` | Complete question sent to the Supervisor after the correlation prefix. |
| `--expected-agent` | `mariner-policy-assistant` | Agent name to check against reported agent names. Observation only; does not determine pass/fail. |
| `--run-note` | Empty | Operator notes, such as stage, endpoint configuration, and background traffic. Do not include secrets. |

Durations and thresholds accept decimal values where appropriate. Numeric values are validated for their allowed ranges.

The experiment below uses a **60-second warm-up**, explicitly overriding the code's 30-second default.

## 5. Execution lifecycle

1. Parse arguments, load configuration, and require live mode.
2. Create a unique run directory and write `run.json`.
3. Start one process and execute one **preflight** workflow. A successful result, including a successful-but-late result, permits the test to continue. A failed preflight stops the run.
4. Initialize the remaining client processes before load measurement.
5. Run **warm-up** at the configured concurrency, then drain its outstanding workflows. Warm-up outcomes do not count toward the measured reliability verdict.
6. Run **measurement**, continually replacing completed workflows during its configured duration.
7. Stop submitting new work when the measurement window ends. Drain outstanding workflows, subject to their own deadlines.
8. Stop worker processes, write `summary.json`, and return an exit code.

Total wall-clock runtime includes initialization, preflight, warm-up, and draining, so it exceeds `--duration-seconds`. Each phase uses distinct workflow IDs. Load stages are separate commands; the script does not automatically run the whole experiment or ramp between concurrency levels.

Persistent processes are used because an overdue Python thread cannot reliably be stopped. The parent polls for events and deadlines, terminates an overdue process, finalizes its open records, and starts a replacement. Deadline enforcement has polling, scheduling, and process-termination overhead; it is not exact to the millisecond.

Terminating a local process does not guarantee cancellation of work already running remotely, including model execution or SQL statements. Replacements can therefore start while remote work from an earlier local timeout is still finishing.

## 6. Experiment plan for 3,000 employees

These employee percentages are planning scenarios, not adoption forecasts. Use 60-second warm-up, 60-second completion target, 180-second deadline, and 99% required reliability for comparisons unless your business requirement changes.

| Stage | Concurrent clients | Share of 3,000 employees | Measured duration | Purpose |
| --- | ---: | ---: | ---: | --- |
| 1. Baseline | 1 | 0.03% | 5 minutes | Establish normal latency and verify tracing. |
| 2. Light load | 5 | 0.17% | 10 minutes | Verify reliability with modest parallel traffic. |
| 3. Moderate load | 10 | 0.33% | 10 minutes | Establish an initial operating benchmark. |
| 4. Increased load | 20 | 0.67% | 10 minutes | Identify rising latency, queuing, and failures. |
| 5. High load | 30 | 1% | 10 minutes | Assess 1% of employees awaiting answers simultaneously. |
| 6. Stress boundary | 50 | 1.67% | 10 minutes | Compare with the concurrency where earlier tests showed failures. |
| 7. Heavy stress | 75 | 2.5% | 5 minutes | Assess behavior beyond the acceptable operating range. |
| 8. Extreme stress | 100 | 3.33% | 5 minutes | Check overload behavior and successful throughput. |
| 9. Large surge | 200 | 6.67% | 5 minutes | Assess a substantial increase in simultaneous requests. |
| 10. Major surge | 300 | 10% | 5 minutes | Identify bottlenecks before the 500-client scenario. |
| 11. 500-client scenario | 500 | 16.67% | 5 minutes | Measure reliability and latency under sustained demand from 500 busy clients. |
| 12. Recovery | 5 | 0.17% | 10 minutes | Confirm reliability and latency recover after stress. |

Run stages sequentially and allow each command to finish draining before starting another. Finding the first failing stage is useful evidence; completing every high-load stage is not required to identify the operating boundary. Continue beyond that boundary only as a deliberate overload experiment, then run recovery.

At high concurrency, the runner creates hundreds of operating-system processes. Monitor the load generator's CPU, memory, network, process count, and file-descriptor usage. Five hundred configured clients do not prove five hundred requests were continuously in flight if the generator is constrained or replacing workers. Generator startup failures and collection delays must not be attributed automatically to Databricks.

Keep endpoint configuration and background traffic consistent across comparisons. Record changes to scaling limits, deployed versions, worker dependencies, and SQL warehouse settings in `--run-note` or accompanying experiment notes. The runner does not retrieve an endpoint configuration snapshot automatically.

### Example: stage 1

```bash
PYTHONPATH=src python3 stress_test_DBX_3.py \
  --concurrency 1 \
  --duration-seconds 300 \
  --warmup-seconds 60 \
  --target-seconds 60 \
  --deadline-seconds 180 \
  --min-reliability-percent 99 \
  --run-note "Stage 1: baseline"
```

### Example: stage 11

```bash
PYTHONPATH=src python3 stress_test_DBX_3.py \
  --concurrency 500 \
  --duration-seconds 300 \
  --warmup-seconds 60 \
  --target-seconds 60 \
  --deadline-seconds 180 \
  --min-reliability-percent 99 \
  --run-note "Stage 11: 500-client sustained stress scenario"
```

For other stages, change concurrency, measured duration, and run note using the table. A backslash must be the final character on its line. Each command runs only one concurrency level.

## 7. Correlation IDs and trace lookup

Run IDs use a UTC timestamp and an eight-character UUID suffix:

```text
STRESS-20261015_162939-3cf819fc
```

Workflow IDs add phase and sequence number:

```text
STRESS-20261015_162939-3cf819fc-measurement-000001
```

The Supervisor input begins with:

```text
[STRESS_TEST_ID=STRESS-20261015_162939-3cf819fc-measurement-000001]
```

Search traces for the workflow ID, or its common run prefix, when input capture is available. This prefix is message content, not a dedicated Databricks trace-ID header. HTTP request IDs, when returned in the supported response headers, are recorded separately. The local session argument is not a server-side conversation identifier: the production client discards it and explicitly sends history.

All saved timestamps and run-ID timestamps use UTC. Convert them when comparing with local dashboards or operator notes.

## 8. Output files

Each run creates:

```text
stress_Test/<run_id>/
  run.json
  summary.json
  workflows.csv
  invocations.csv
  attempts.csv
  events.csv
```

| File | Content |
| --- | --- |
| `run.json` | Run ID, UTC start time, endpoint name, effective settings, citation-enabled flag, question length/hash, expected agent, and operator note. |
| `summary.json` | Measurement verdict, outcome counts, latency distributions, throughput, failure categories, per-minute start cohorts, and phase timings. |
| `workflows.csv` | One finalized row per workflow across all phases, including stage, timing, inference/citation outcomes, source/agent flags, and reported token usage. |
| `invocations.csv` | One finalized row per observed Supervisor invocation, including outcome, duration, HTTP status, terminal marker, and available request ID. |
| `attempts.csv` | One finalized row per inference HTTP attempt; exposes failed attempts hidden by successful retries. |
| `events.csv` | Detailed workflow starts and invocation, attempt, authentication, stream, and citation events. |

The parent is the only file writer. It flushes files after records are written. Local CSV output does not intentionally contain raw questions, answers, credentials, or exception messages. The question hash supports matching workload identity without saving its text. `--run-note` is saved as supplied by the operator. Databricks-side tracing may still capture the transmitted question.

Child-process production logging is disabled by the runner to avoid raw stream logging and timing distortion. Use the saved metadata and Databricks traces for diagnosis.

## 9. Outcomes and interpretation

| Workflow outcome | Meaning | Counts toward reliability numerator? |
| --- | --- | --- |
| `SUCCESS_WITHIN_TARGET` | Returned successfully at or below the target, before the overall deadline. | Yes |
| `SUCCESS_LATE` | Returned successfully after target but before the overall deadline. | No |
| `FAILED` | A client/workflow operation raised an error. | No |
| `DEADLINE_EXCEEDED` | Overall deadline reached; the local worker is stopped, or completion is observed too late. | No |
| `INTERRUPTED` | Active workflow finalized when a phase is aborted, such as by Ctrl+C or a runner error. | No |

### Reliability and pass/fail

```text
reliability_percent = 100 × SUCCESS_WITHIN_TARGET / measured workflows
```

For a normally completed measurement, finalized workflow rows account for the workflows started. Warm-up and preflight rows are excluded. A run passes only if measurement completed normally, there is at least one measured workflow, and reliability meets `--min-reliability-percent`.

`run_status: COMPLETE` means the experiment finished; it does not mean the reliability requirement passed. Check `passed` separately. Small samples give an initial impression, not statistical proof of 99% long-term reliability. At a 99% threshold, one miss in fewer than 100 workflows causes the sample to fall below the requirement.

### Latency

Successful latency combines `SUCCESS_WITHIN_TARGET` and `SUCCESS_LATE`. Failed latency includes failed, deadline-exceeded, and interrupted workflows. Percentiles use the nearest-rank convention. Missing samples produce `null` statistics, not zero-second latency.

`inference_seconds` sums the recorded Supervisor invocation durations, including associated authentication and retries. `citation_seconds` measures the resolver separately. Neither is a server-only model-execution metric. Synthetic records for killed operations use time since the parent received their start event, so their durations are approximate.

### Throughput

Both workflow-throughput fields use measurement elapsed time **including drain**:

```text
completed_workflows_per_second_including_drain = finalized workflows / elapsed time
successful_workflows_per_second_including_drain = successful workflows / elapsed time
```

The completed count includes failures; the successful count includes late successes. The invocation-success percentage is separate from workflow reliability and has no 60-second target criterion. Review `attempts.csv` for initial failures followed by a successful retry.

### Failure attribution

`stage` identifies where a failure surfaced; `error_category` classifies its available evidence. Categories include `RATE_LIMITED`, `AUTHENTICATION`, `HTTP_ERROR`, `NETWORK_TIMEOUT`, `CONNECTION_ERROR`, `INCOMPLETE_STREAM`, `STREAM_ERROR`, and the generic `CLIENT_ERROR`. Parent-generated categories include `WORKFLOW_DEADLINE`, `WORKER_EXIT`, and `RUN_ABORTED`.

Exception diagnostics retain exception class names and available HTTP status, rather than raw error text or response bodies. A generic client error does not prove the endpoint itself failed. Investigate `events.csv`, invocation/attempt records, and server traces together.

A workflow can have successful inference and failed citations. Likewise, an invocation may return successfully but final workflow validation or a later continuation may fail. Report these separately when attributing endpoint problems.

### Per-minute data and quality flags

`per_minute_start_cohorts` groups workflows by the minute they **started**, relative to measurement start, even when they finished later. It is not a graph of completions per wall-clock minute.

`expected_agent_reported`, `has_sources`, and `source_count` are observations. They do not change the reliability verdict and do not prove a correct, grounded answer. Reported agent names may come from response content or approval information; use server traces to verify actual worker execution.

## 10. Code map

| Component | Responsibility |
| --- | --- |
| `parse_args()` / `require_live()` | Validate CLI settings and reject mock mode. |
| `main()` | Load configuration, create artifacts, orchestrate phases, summarize, and set exit status. |
| `worker_main()` | Build a process-local real service, execute jobs, and send observations to the parent. |
| `ObservedSupervisor` | Reuse the production invocation/approval logic with local telemetry. |
| `StreamObserver` | Recognize completion markers and explicit failed/incomplete stream events. |
| `ObservedCitations` | Time citation resolution and record failures independently. |
| `spawn_slot()` / `stop_slot()` | Manage worker processes and their pipes. |
| `run_phase()` | Schedule duration-based work, collect events, enforce deadlines, and drain. |
| `record_event()` / `abandon_workflow()` | Track active operations and finalize records when workers stop. |
| `finish_workflow()` | Apply final elapsed-time classification and save workflow results. |
| `Results` | Write and flush CSV files from one parent process. |
| `error_details()` | Extract allowlisted exception diagnostics. |
| `latency_stats()` / `summarize()` | Compute distributions, reliability, throughput, and measurement-only summaries. |

The instrumentation is contained in the stress-test script. It subclasses the production service and accesses its HTTP session and citation resolver; changes to those client internals should be checked against the harness tests.

## 11. Interruption, exit codes, and verification

Ctrl+C triggers cleanup and attempts to preserve active workflow outcomes and a partial summary. Interrupted or errored experiments never receive a passing verdict. Forced process termination, machine shutdown, or a filesystem failure may prevent cleanup or summary creation; flushed CSV records remain the available evidence.

| Exit code | Meaning |
| --- | --- |
| `0` | Completed measurement passed the reliability requirement. |
| `1` | Finished run failed the requirement, or an error was caught during execution. |
| `130` | Keyboard interruption handled by the runner. |
| `2` | Argument parser rejected invalid CLI arguments. |

Configuration/output initialization errors before the protected execution block can exit without `summary.json`; inspect terminal output. A missing summary does not mean a passing run.

Run the focused offline tests with:

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -p test_stress_test_dbx_3.py -v
```

The tests in [tests/test_stress_test_dbx_3.py](tests/test_stress_test_dbx_3.py) cover live-mode enforcement, argument validation, error attribution, retries, stream failures, continuations, citation failures, metrics, process deadlines, interruption, and simulated sustained runs. They do not send live Databricks requests.

After each live stage, compare `summary.json` with client records and Databricks endpoint metrics/traces. Repeat levels near the first failing stage and run recovery after overload. The operating result is the highest repeatable load that meets the chosen target under the documented configuration and workload.
