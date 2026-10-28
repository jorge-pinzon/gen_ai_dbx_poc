# Coaching360 agents: access layer (phase 2)

Unity Catalog views that give each agent only its level's data from `workspace.coaching360demo`.

| Schema | Agent | Who | Scope |
|---|---|---|---|
| `workspace.c360_employee` (25 views) | My Development | Account Representative, Assistant BM, BM Trainee | Own rows only (incl. own policy violations and ACE payout) |
| `workspace.c360_branch` (35 views) | Branch Leader | Branch Managers, active relief managers | Their branches (incl. confidential visit feedback) |
| `workspace.c360_district` (39 views) | District & Above | DM, RVP, SVP, COO, AVP Branch Assist, Director Ops Strategy, Branch Enablement, HR, Compliance, Legal, Audit | Their district / region / division; central roles see all branches |
| `workspace.c360_security` | (none) | Admins only | Login → directory user map, levels, branch scope, `me()`, `my_level()` |

Every view filters on the signed-in user (`current_user()` → `user_map` or directory e-mail) **and** checks
their level, so someone who reaches another level's schema gets no rows. Business Analyst and the
Coaching360 Application Administrator have no level (no data) until you decide otherwise.

## Files

- `build_sql.py`: the single source of the rules and views. Edit it, then run `python3 coaching360/build_sql.py`.
- `sql/01_security.sql` … `05_grants.sql`: generated; run in order in the SQL editor as an admin.
- `tests/access_tests.py`: read-only tests (73 checks) that run every view as fixed directory people.
  Run with `python3 coaching360/tests/access_tests.py`. All 73 passed on 2026-10-23, before anything was created.

## Run in the trial workspace

1. Create account groups `c360_employees`, `c360_branch_managers`, `c360_district_leaders`.
2. Run `sql/01_security.sql`, `02_employee_views.sql`, `03_branch_views.sql`, `04_district_views.sql`, `05_grants.sql`.
3. Test as each level without other users: map your own login to a directory person, query, then switch:
   ```sql
   INSERT INTO workspace.c360_security.user_map VALUES (current_user(), 500371, 'test: Account Representative', current_timestamp());
   SELECT workspace.c360_security.my_level();                -- employee
   SELECT COUNT(*) FROM workspace.c360_employee.my_coaching_records;   -- 21
   SELECT COUNT(*) FROM workspace.c360_branch.coaching_records;        -- 0 (gate)
   DELETE FROM workspace.c360_security.user_map WHERE databricks_user = current_user();
   ```
   Other personas: 500054 (Branch Manager), 500072 (BM + relief branch), 500003 (District Manager),
   500002 (RVP), 500001 (SVP), 500393 (HR Business Partner).
4. Before real users: remove the app service principal's `ALL PRIVILEGES` on `coaching360demo`
   (commented in `05_grants.sql`); agents must query as the signed-in user.

Next phases: three Genie spaces (one per schema), the Knowledge Assistant on
`coaching360_docs/Coaching_360_BRD_Version2.3.pdf`, optional per-level Supervisors, and app routing by group.

## Phase 3: agents and chat (built 2026-10-23)

- `build_agents.py` → `agents/`: three Genie spaces (one per level schema), the BRD Knowledge Assistant
  (`mariner-coaching360-guide`), four Supervisor tools and the Supervisor instructions section.
  All on existing infrastructure: Supervisor `mas-53dbd2d7-endpoint`, vector search `mariner-bot-endpoint`,
  SQL warehouse `55cdb78d4d2a62d0`.
- `tests/genie_examples_test.py`: runs all 22 Genie example SQLs as a persona of their level (all pass).
- `notebooks/setup_agents.py`: one-time setup; run in Databricks as yourself.
- App: start with `/coaching360` (the chat asks for a name) or `/coaching360 <name>`. The chat looks the
  name up in the directory and says whether it matches an employee and their position, which decides the
  Coaching360 level (no level question). It then sets the persona in `user_map` and sends each question to
  the existing Supervisor with a level directive. `/coaching360 switch` or `/coaching360 <another name>`
  changes person; `/coaching360 exit` leaves. Enable with `COACHING360_ENABLED=true`
  after the notebook has run. Demo only: anyone can pick any person, and concurrent users share one mapping.

## Phase 4: faster answers (2026-10-26)

Where the time went (branch persona, 2026-10-23): Supervisor plans about 4 s, Genie 14–22 s, Supervisor
rewrites 3–6 s. The changes below shorten the Genie part and the wait you see; the Supervisor hops are unchanged.

| Step | What | Where |
|---|---|---|
| 1 | Scope computed once: `persona`, `scope_branches`, `scope_people` (daily materialized views) and `my_person`, `my_branches`, `my_team`. Each view does one level-checked lookup instead of re-deriving the hierarchy per filter. | `sql/01c_scope_once.sql` |
| 2 | Answer tables: `my_overview` / `team_overview`, one row per employee with latest KPIs, rank in branch, open/overdue tasks, coaching, Success Plan and violations. KPI views gain `KpiMonth`, names and `BranchName`. | `sql/02`–`04` |
| 3 | Pre-joined sources in `workspace.c360_prepared` (daily materialized views): employee KPIs, DPR metrics, coaching records, branch performance, employee overview. | `sql/01d_prepared.sql` |
| 4 | Trusted functions in each level schema (`my_scorecard`, `my_open_items`, `team_ranking`, `team_scorecard`, `branch_scorecard`, `overdue_tasks`, `pending_acknowledgements`), registered in the Genie spaces. | `sql/06_genie_functions.sql`, `agents/genie_*.json` |
| 5 | Genie column descriptions and synonyms, examples that use the functions and overview tables, and a "one query, no exploration" rule. | `agents/genie_*.json` |
| 8 | The app reads the level's two main views in the background as soon as a person is chosen. | `src/mariner_genai_dbx/coaching360.py` |
| 9 | Genie's table is shown (checked, masked) while the Supervisor writes the answer; the answer replaces it. | `live_preview.py`, `web.py` |
| 10 | Per-stage timings: app log line `Chat stages` and `flask_app_logs.stage_timings_json` (optional); benchmark script. | `tests/speed_benchmark.py` |

Apply (as yourself, with `DATABRICKS_TOKEN` in `.env`): `python3 coaching360/apply_speedups.py`.
It runs `01c`, `01d`, `02`–`04`, `06`, `05b` (adds EXECUTE for the functions), then updates the three
Genie spaces. Then check: `python3 coaching360/tests/access_tests.py`, `python3 coaching360/tests/genie_examples_test.py`,
and `python3 coaching360/tests/speed_benchmark.py after` followed by `--compare baseline after`.

The materialized views refresh daily (the data loads monthly). After loading new data or a directory
change, refresh them right away (the `REFRESH` lines at the end of `01c` and `01d`).
`team_overview` / `my_overview` counts (overdue tasks, coaching in the last 90 days) are as of `AsOfDate`.

## Phase 5: answer accuracy (2026-10-26, from the 20-question demo review)

- Personal scorecard: `my_scorecard(month)` returns the monthly KPIs (LPE, DACC loans, current-month and
  30-89 day delinquency, first lien, cash advance vs state average, outbound calls and contacts) with goal,
  display value and status computed in SQL, then the DPR metrics as a second section. Team: `team_scorecard`.
- Goals come from one place (`c360_prepared.kpi_goals`, `employee_kpi_scorecard`): LPE 1.00, DACC loans 2 a
  month, delinquency goals from the KPI row, calls / contacts from EmployeeGoals (GoalID 1 / 2).
- Months: no month means the latest month with complete KPI data (`data_status.LatestKpiMonth`), never the
  calendar month. The app remembers a month named earlier in the conversation and passes it on.
- One as-of date for "overdue" and day counts: `data_status.AsOfDate` (last DPR publish, 2026-10-20).
- Visits: `visit_followups` joins each topic to its follow-up task (ParentType BranchVisit, ParentId = visit,
  subject "Branch visit action item: <topic>"); `visit_brief(branch name)` resolves the branch inside the
  person's scope and says so when it is not; `open_visit_followups()` lists what is still open.
- Coverage: `branches`, `team_overview`, `team_kpi_scorecard` and `visit_followups` say "Relief coverage until <date>".
- Timeout: Coaching360 answers stop after `COACHING360_TIMEOUT_SECONDS` (default 120) with a clear message.
- Regression: `tests/regression_test.py` runs the conversations in `tests/regression_cases.json` through the
  running app and checks the key numbers.
- Not possible: temperature cannot be set for the Supervisor or Genie (Agent Bricks does not expose it);
  the goal math is in SQL instead, and the directive tells the Supervisor to report values as returned.
