"""Generate the Coaching360 access layer: one security schema and one view schema per level.

    python3 coaching360/build_sql.py            # writes coaching360/sql/*.sql

Every view is defined once below. `render(..., persona=...)` produces the same SQL with the
signed-in user replaced by a fixed person, which the access tests use to check scoping
read-only, before anything is created.

Access rules (agreed 2026-10-23):
- Employee level (Account Representative, Assistant Branch Manager, Branch Manager Trainee):
  only their own rows, including their own policy violations and ACE payout estimate.
- Branch level (Branch Managers, and relief managers during their active window): everything
  for the branches they lead, including confidential branch-visit feedback.
- District level and above: District Manager (own district), Regional VP (own region), SVP
  (own division), and the central roles (COO, AVP of Branch Assist, Director of Operations
  Strategy, Branch Enablement, HR, Compliance, Legal, Audit), which see all branches.
- Unity Catalog enforces this: each view filters on the signed-in user and checks their
  level, so a person who reaches another level's schema still gets no rows.
"""
import pathlib
import re

SRC = "workspace.coaching360demo"
SEC = "workspace.c360_security"
SCHEMAS = {"employee": "workspace.c360_employee", "branch": "workspace.c360_branch", "district": "workspace.c360_district"}
GROUPS = {"employee": "c360_employees", "branch": "c360_branch_managers", "district": "c360_district_leaders"}

EMPLOYEE_TITLES = ("Account Representative", "Assistant Branch Manager", "Branch Manager Trainee")
DISTRICT_TITLES = ("District Manager", "Regional Vice President", "Senior Vice President")
CENTRAL_TITLES = ("Chief Operating Officer", "AVP of Branch Assist", "Director of Operations Strategy",
                  "Branch Enablement Representative I", "Branch Enablement Representative II",
                  "Manager I - Branch Enablement", "HR Business Partner", "Compliance Analyst",
                  "Corporate Counsel", "Internal Auditor")


def t(name):
    return f"{SRC}.{name}"


USER, BRANCH, DISTRICT, REGION, DIVISION = (t("org_hierarchy__eda_ref_t_ref_user"), t("org_hierarchy__eda_ref_t_ref_branch"),
                                           t("org_hierarchy__eda_ref_t_ref_district"), t("org_hierarchy__eda_ref_t_ref_region"),
                                           t("org_hierarchy__eda_ref_t_ref_companydivision"))
q = lambda titles: ", ".join(f"'{x}'" for x in titles)
RELIEF_ACTIVE = ("current_date() BETWEEN coalesce(b.ReliefManagerStartDate, DATE'1900-01-01') "
                 "AND coalesce(b.ReliefManagerEndDate, DATE'2999-12-31')")

# --- security schema -------------------------------------------------------------------------
USER_LEVEL = f"""SELECT u.UserDWID AS user_dwid, u.UserName AS user_name, u.UserTitle AS title,
       CASE
         WHEN u.UserTitle = 'Branch Manager' THEN 'branch'
         WHEN EXISTS (SELECT 1 FROM {BRANCH} b WHERE lower(b.ReliefManagerUsername) = lower(u.UserName) AND {RELIEF_ACTIVE}) THEN 'branch'
         WHEN u.UserTitle IN ({q(EMPLOYEE_TITLES)}) THEN 'employee'
         WHEN u.UserTitle IN ({q(DISTRICT_TITLES + CENTRAL_TITLES)}) THEN 'district'
         ELSE 'none'
       END AS level
FROM {USER} u
WHERE u.EmployeeActive"""

BRANCH_SCOPE = f"""SELECT u.UserDWID AS user_dwid, b.BranchDWID AS branch_dwid, 'branch manager' AS reason
FROM {USER} u JOIN {BRANCH} b ON lower(b.BMUsername) = lower(u.UserName) WHERE u.EmployeeActive
UNION
SELECT u.UserDWID, b.BranchDWID, 'relief manager'
FROM {USER} u JOIN {BRANCH} b ON lower(b.ReliefManagerUsername) = lower(u.UserName) AND {RELIEF_ACTIVE} WHERE u.EmployeeActive
UNION
SELECT u.UserDWID, b.BranchDWID, 'district manager'
FROM {USER} u JOIN {DISTRICT} d ON lower(d.DMUsername) = lower(u.UserName)
JOIN {BRANCH} b ON b.DistrictDWID = d.DistrictDWID WHERE u.EmployeeActive
UNION
SELECT u.UserDWID, b.BranchDWID, 'regional vice president'
FROM {USER} u JOIN {REGION} r ON lower(r.VPUsername) = lower(u.UserName)
JOIN {DISTRICT} d ON d.RegionDWID = r.RegionDWID JOIN {BRANCH} b ON b.DistrictDWID = d.DistrictDWID WHERE u.EmployeeActive
UNION
SELECT u.UserDWID, b.BranchDWID, 'senior vice president'
FROM {USER} u JOIN {DIVISION} c ON lower(c.SVPUsername) = lower(u.UserName)
JOIN {REGION} r ON r.CompanyDivisionDWID = c.CompanyDivisionDWID JOIN {DISTRICT} d ON d.RegionDWID = r.RegionDWID
JOIN {BRANCH} b ON b.DistrictDWID = d.DistrictDWID WHERE u.EmployeeActive
UNION
SELECT u.UserDWID, b.BranchDWID, 'central role (all branches)'
FROM {USER} u CROSS JOIN {BRANCH} b WHERE u.EmployeeActive AND u.UserTitle IN ({q(CENTRAL_TITLES)})"""

# Each person's scope, computed once (daily materialized views keyed by user_dwid), so a level view
# does one small lookup instead of re-deriving the hierarchy for every filter.
PERSONA = f"""SELECT u.UserDWID AS user_dwid, l.level, CAST(u.TellerID AS BIGINT) AS teller_id, u.EmployeeNumber AS employee_number
FROM {USER} u JOIN {SEC}.user_level_live l ON l.user_dwid = u.UserDWID"""
SCOPE_BRANCHES = f"""SELECT DISTINCT s.user_dwid, l.level, b.BranchDWID AS branch_dwid, b.BranchNumber AS branch_number,
       b.DistrictDWID AS district_dwid, CAST(d.DistrictNumber AS INT) AS district_number, dm.UserDWID AS dm_dwid,
       s.reason, CASE WHEN s.reason = 'relief manager' THEN b.ReliefManagerEndDate END AS relief_until
FROM {SEC}.branch_scope_live s JOIN {SEC}.user_level_live l ON l.user_dwid = s.user_dwid
JOIN {BRANCH} b ON b.BranchDWID = s.branch_dwid JOIN {DISTRICT} d ON d.DistrictDWID = b.DistrictDWID
LEFT JOIN {USER} dm ON lower(dm.UserName) = lower(d.DMUsername)"""
SCOPE_PEOPLE = f"""SELECT DISTINCT s.user_dwid, s.level, u.UserDWID AS member_dwid, CAST(u.TellerID AS BIGINT) AS member_teller
FROM {SEC}.scope_branches_live s JOIN {USER} u ON u.BranchDWID = s.branch_dwid"""
SCOPE_TABLES = {  # name: (live definition, comment)
    "persona": (PERSONA, "Each active user: Coaching360 level, teller id and employee number"),
    "scope_branches": (SCOPE_BRANCHES, "Branches (with district and district manager) each active user can see, with their level and why (reason)"),
    "scope_people": (SCOPE_PEOPLE, "Employees at the branches each active user can see, with their level"),
}

# Every scoped filter checks the level in the same lookup; views_for() replaces @GATE@ per level.
GATE = "@GATE@"
ME = f"(SELECT user_dwid FROM {SEC}.my_person WHERE level {GATE})"
MY_TELLER = f"(SELECT teller_id FROM {SEC}.my_person WHERE level {GATE})"
MY_EMPNO = f"(SELECT employee_number FROM {SEC}.my_person WHERE level {GATE})"
MY_BRANCH_DWIDS = f"(SELECT branch_dwid FROM {SEC}.my_branches WHERE level {GATE})"
MY_BRANCH_NUMBERS = f"(SELECT branch_number FROM {SEC}.my_branches WHERE level {GATE})"
MY_DISTRICT_DWIDS = f"(SELECT district_dwid FROM {SEC}.my_branches WHERE level {GATE})"
MY_DISTRICT_NUMBERS = f"(SELECT district_number FROM {SEC}.my_branches WHERE level {GATE})"
TEAM_DWIDS = f"(SELECT member_dwid FROM {SEC}.my_team WHERE level {GATE})"
TEAM_TELLERS = f"(SELECT member_teller FROM {SEC}.my_team WHERE level {GATE})"
# District managers whose district is in scope (owners of district-level meetings without a branch).
SCOPE_DMS = f"(SELECT dm_dwid FROM {SEC}.my_branches WHERE level {GATE})"
# One row per branch in scope, saying how the person covers it (own branch, relief coverage, district...).
MY_COVERAGE = f"""SELECT branch_dwid, branch_number, level,
       CASE WHEN max(CASE WHEN reason = 'relief manager' THEN 0 ELSE 1 END) = 0
              THEN concat('Relief coverage until ', date_format(max(relief_until), 'M/d/yyyy'))
            WHEN max(CASE WHEN reason = 'branch manager' THEN 1 ELSE 0 END) = 1 THEN 'Own branch'
            ELSE 'In scope' END AS Coverage
FROM {SEC}.my_branches GROUP BY branch_dwid, branch_number, level"""
COVERAGE_JOIN = f"JOIN {SEC}.my_coverage c ON c.branch_dwid = o.BranchDWID AND c.level {GATE}"

# --- prepared schema: daily pre-joined copies of the busiest sources --------------------------
# The level views only filter these, so Genie's queries skip the name and definition joins.
PREP = "workspace.c360_prepared"
EMPLOYEE_PERF, DPR, COACHING = (t("branchkpi_sources__branchkpi_monthly_employeeperformance"),
                                t("coaching360_app_dpr__dbo_dpremployeescorecardmetrics"),
                                t("coaching360_app_workflow__dbo_coachingrecords"))
TASKS, IDP, VIOLATIONS = (t("coaching360_app_workflow__dbo_coachingtasks"), t("coaching360_app_workflow__dbo_individualdevelopmentgoals"),
                          t("policy_violations__policyviolations_app_violations"))
# One date for "overdue" everywhere: the dataset's as-of date (last DPR publish), not today.
AS_OF = f"(SELECT to_date(max(SourceFreshnessUtc)) FROM {DPR})"
# "Latest month" means the latest month with complete monthly KPI data, for every measure.
LATEST_KPI_MONTH = f"(SELECT max(make_date(Year, Month, 1)) FROM {EMPLOYEE_PERF})"
CALLS, CALL_GOALS = t("branchkpi_sources__reports_kpidashboard_calldata"), t("branchkpi_sources__reports_kpidashboard_employeegoals")
# Fixed goals (agreed 2026-10-26). Delinquency goals come from each KPI row; call and contact
# goals from EmployeeGoals (GoalID 1 = outbound calls, 2 = outbound contacts) per teller.
LPE_GOAL, DACC_GOAL = "1.00", "2"
PREPARED = {
    "data_status": (f"SELECT {LATEST_KPI_MONTH} AS LatestKpiMonth, {AS_OF} AS AsOfDate",
                    "Latest month with complete KPI data and the dataset as-of date used for overdue"),
    "kpi_goals": (f"""SELECT * FROM VALUES
  ('LPE', 'Loans per employee', CAST({LPE_GOAL} AS DECIMAL(19,4)), true, 'Fixed goal'),
  ('DACC loans', 'DACC loans per month', CAST({DACC_GOAL} AS DECIMAL(19,4)), true, 'Fixed goal'),
  ('Delinquency - current month', 'Current-month delinquency rate', NULL, false, 'Goal from the KPI row (DLQCurrentMonthPerc_Goal)'),
  ('Delinquency - 30-89 day', '30-89 day delinquency rate', NULL, false, 'Goal from the KPI row (DLQ3089DayPerc_Goal)'),
  ('Outbound calls', 'Outbound calls per month', NULL, true, 'Goal from EmployeeGoals, GoalID 1'),
  ('Outbound contacts', 'Outbound contacts per month', NULL, true, 'Goal from EmployeeGoals, GoalID 2')
  AS goals(Measure, Description, Goal, IsHigherBetter, GoalSource)""", "Where each scorecard goal comes from (fixed values or source column)"),
    "employee_kpis": (f"""SELECT e.*, make_date(e.Year, e.Month, 1) AS KpiMonth, u.UserDWID AS EmployeeDWID,
       u.Name AS EmployeeName, u.UserTitle, b.BranchName
FROM {EMPLOYEE_PERF} e
LEFT JOIN {USER} u ON CAST(u.TellerID AS BIGINT) = e.TellerID
LEFT JOIN {BRANCH} b ON b.BranchNumber = e.Branch""", "Monthly employee production and delinquency with employee and branch names"),
    # DPR EmployeeId is the DPR app's own id, not the directory UserDWID; SourceTellerId matches the
    # directory TellerID on every row, so people are matched by teller id (EmployeeDWID).
    "dpr_metrics": (f"""SELECT m.*, CAST(date_trunc('MONTH', m.MetricMonthEndDate) AS DATE) AS MetricMonth,
       k.KpiCode, k.KpiName, k.UnitOfMeasure, k.IsHigherBetter, u.UserDWID AS EmployeeDWID, u.Name AS EmployeeName
FROM {DPR} m
LEFT JOIN {t('coaching360_app_reference__dbo_kpidefinitions')} k ON k.KpiDefinitionId = m.KpiDefinitionId
LEFT JOIN {USER} u ON u.TellerID = m.SourceTellerId""", "DPR scorecard metrics with KPI definitions, employee directory id and name"),
    "coaching_records": (f"""SELECT c.*, u.Name AS EmployeeName
FROM {COACHING} c LEFT JOIN {USER} u ON u.UserDWID = c.EmployeeId""", "Coaching records with employee names"),
    # The personal scorecard: monthly KPIs with their goals, plus calls and contacts against goal.
    "employee_kpi_scorecard": (f"""WITH calls AS (
  SELECT TellerID, CAST(date_trunc('MONTH', call_date) AS DATE) AS KpiMonth,
         SUM(OutboundCalls) AS OutboundCalls, SUM(OutboundContacts) AS OutboundContacts
  FROM {CALLS} GROUP BY TellerID, CAST(date_trunc('MONTH', call_date) AS DATE)),
goals AS (
  SELECT TellerID, MAX(CASE WHEN GoalID = 1 THEN TargetValue END) AS OutboundCallsGoal,
         MAX(CASE WHEN GoalID = 2 THEN TargetValue END) AS OutboundContactsGoal
  FROM {CALL_GOALS} GROUP BY TellerID)
SELECT u.UserDWID AS EmployeeDWID, u.Name AS EmployeeName, u.UserTitle, e.TellerID, e.Branch AS BranchNumber,
       b.BranchDWID, b.BranchName, make_date(e.Year, e.Month, 1) AS KpiMonth,
       e.TotalLoans, e.LPE, CAST({LPE_GOAL} AS DECIMAL(19,4)) AS LpeGoal,
       e.DACC_Loans, CAST({DACC_GOAL} AS INT) AS DaccLoansGoal,
       e.DLQCurrentMonthPerc_Actual AS DlqCurrentMonth, e.DLQCurrentMonthPerc_Goal AS DlqCurrentMonthGoal,
       e.DLQ3060DayPerc_Actual AS Dlq30To89Day, e.DLQ3089DayPerc_Goal AS Dlq30To89DayGoal,
       e.FirstLienPercentage, e.FirstLienVolumePercentage, e.FirstLienVolumeDollars,
       e.Employee_Cash_Advance AS CashAdvance, e.Average_State_Cash_Advance AS StateAverageCashAdvance,
       e.TotalVolumeDollars, c.OutboundCalls, g.OutboundCallsGoal, c.OutboundContacts, g.OutboundContactsGoal
FROM {EMPLOYEE_PERF} e
LEFT JOIN {USER} u ON CAST(u.TellerID AS BIGINT) = e.TellerID
LEFT JOIN {BRANCH} b ON b.BranchNumber = e.Branch
LEFT JOIN calls c ON c.TellerID = e.TellerID AND c.KpiMonth = make_date(e.Year, e.Month, 1)
LEFT JOIN goals g ON g.TellerID = e.TellerID""",
        "Monthly KPI scorecard per employee: LPE, DACC loans, both delinquency measures, first lien, cash advance vs state average, calls and contacts, each with its goal. Dlq30To89Day is the 30-89 day rate (source column DLQ3060DayPerc_Actual)."),
    # Branch visit topics with the real follow-up status, which lives on the task the visit created.
    "visit_followups": (f"""SELECT v.BranchVisitId, v.OrganizationalUnitId AS BranchDWID, b.BranchNumber, b.BranchName,
       CAST(v.VisitDate AS DATE) AS VisitDate, v.VisitStatus, v.VisitPurpose, v.IsConfidentialVisit, v.ConfidentialLeadershipFeedback,
       p.BranchVisitTopicId, p.TopicTitle, p.IsMandatory, p.DiscussionNotes, p.ActionPlan, p.FollowUpRequired,
       p.AssignedOwnerName, p.AssignedOwnerEmployeeId, CAST(p.DueDate AS DATE) AS FollowUpDueDate,
       k.CoachingTaskId, k.Status AS TaskStatus, CAST(k.CompletedUtc AS DATE) AS TaskCompletedDate, CAST(k.DueDate AS DATE) AS TaskDueDate,
       CASE WHEN NOT p.FollowUpRequired THEN 'No follow-up needed'
            WHEN k.CoachingTaskId IS NULL THEN 'No task created'
            WHEN k.Status = 'Completed' THEN 'Completed'
            WHEN CAST(k.DueDate AS DATE) < a.AsOfDate THEN 'Overdue'
            ELSE k.Status END AS FollowUpStatus,
       a.AsOfDate
FROM {t('coaching360_app_workflow__dbo_branchvisits')} v
JOIN {t('coaching360_app_workflow__dbo_branchvisittopics')} p ON p.BranchVisitId = v.BranchVisitId
LEFT JOIN {BRANCH} b ON b.BranchDWID = v.OrganizationalUnitId
LEFT JOIN {TASKS} k ON k.ParentType = 'BranchVisit' AND k.ParentId = v.BranchVisitId
  AND k.Subject = concat('Branch visit action item: ', p.TopicTitle)
CROSS JOIN (SELECT {AS_OF} AS AsOfDate) a""",
        "Branch visit topics with branch name and the follow-up task's status and completion date (FollowUpStatus; overdue as of AsOfDate)"),
    "branch_performance": (f"""SELECT p.*, make_date(p.Year, p.Month, 1) AS KpiMonth, b.BranchName, b.BMName, d.DistrictName
FROM {t('branchkpi_sources__branchkpi_monthly_branchperformance')} p
LEFT JOIN {BRANCH} b ON b.BranchNumber = p.Branch
LEFT JOIN {DISTRICT} d ON d.DistrictDWID = b.DistrictDWID""", "Branch monthly scorecard inputs with branch, manager and district names"),
    # One row per employee: the answer to "who is on my team and how are they doing".
    "employee_overview": (f"""WITH latest AS (SELECT {LATEST_KPI_MONTH} AS month),
as_of AS (SELECT {AS_OF} AS AsOfDate),
kpi AS (
  SELECT e.TellerID, SUM(e.TotalLoans) AS TotalLoans, AVG(e.LPE) AS LPE, SUM(e.TotalVolumeDollars) AS TotalVolumeDollars
  FROM {EMPLOYEE_PERF} e JOIN latest ON make_date(e.Year, e.Month, 1) = latest.month GROUP BY e.TellerID),
tasks AS (
  SELECT AssignedToEmployeeId AS id, count_if(Status <> 'Completed') AS OpenTasks,
         count_if(Status <> 'Completed' AND CAST(DueDate AS DATE) < (SELECT AsOfDate FROM as_of)) AS OverdueTasks
  FROM {TASKS} GROUP BY AssignedToEmployeeId),
coaching AS (
  SELECT EmployeeId AS id, MAX(CoachingDate) AS LastCoachingDate,
         count_if(CAST(CoachingDate AS DATE) > date_sub((SELECT AsOfDate FROM as_of), 90)) AS CoachingRecordsLast90Days,
         count_if(Status = 'PendingAcknowledgement') AS PendingAcknowledgements
  FROM {COACHING} GROUP BY EmployeeId),
plans AS (
  SELECT EmployeeId AS id, MAX(GoalMonth) AS SuccessPlanMonth, max_by(Status, GoalMonth) AS SuccessPlanStatus
  FROM {IDP} WHERE NOT IsArchived GROUP BY EmployeeId),
violations AS (
  SELECT EmployeeId AS employee_number, count_if(Status <> 'CorrectiveActionCompleted') AS OpenPolicyViolations
  FROM {VIOLATIONS} GROUP BY EmployeeId)
SELECT u.UserDWID, u.Name, u.UserTitle, u.EmployeeActive, u.SeniorityDate, u.BranchDWID,
       b.BranchNumber, b.BranchName, d.DistrictName,
       latest.month AS LatestKpiMonth, kpi.TotalLoans, kpi.LPE, kpi.TotalVolumeDollars,
       CASE WHEN kpi.TellerID IS NOT NULL THEN rank() OVER (PARTITION BY b.BranchNumber, kpi.TellerID IS NULL ORDER BY kpi.TotalVolumeDollars DESC) END AS VolumeRankInBranch,
       coalesce(tasks.OpenTasks, 0) AS OpenTasks, coalesce(tasks.OverdueTasks, 0) AS OverdueTasks,
       coaching.LastCoachingDate, coalesce(coaching.CoachingRecordsLast90Days, 0) AS CoachingRecordsLast90Days,
       coalesce(coaching.PendingAcknowledgements, 0) AS PendingAcknowledgements,
       plans.SuccessPlanMonth, plans.SuccessPlanStatus, coalesce(violations.OpenPolicyViolations, 0) AS OpenPolicyViolations,
       (SELECT AsOfDate FROM as_of) AS AsOfDate
FROM {USER} u
JOIN {BRANCH} b ON b.BranchDWID = u.BranchDWID
LEFT JOIN {DISTRICT} d ON d.DistrictDWID = b.DistrictDWID
CROSS JOIN latest
LEFT JOIN kpi ON kpi.TellerID = CAST(u.TellerID AS BIGINT)
LEFT JOIN tasks ON tasks.id = u.UserDWID
LEFT JOIN coaching ON coaching.id = u.UserDWID
LEFT JOIN plans ON plans.id = u.UserDWID
LEFT JOIN violations ON violations.employee_number = u.EmployeeNumber""",
                          "One row per employee: latest-month KPIs and rank in branch, open and overdue tasks, coaching, Success Plan and open violations (counts as of AsOfDate)"),
}


def p(name):
    return f"{PREP}.{name}"

VIOLATION_COLUMNS = "* EXCEPT (PayloadJson, ManagementChainJson, AccountNumber, AccountId), concat('****', right(AccountNumber, 4)) AS AccountNumberLast4"
PAYOUT_EMPLOYEE_COLUMNS = "* EXCEPT (BMPayout, BMEstPayout, BMlpe, Column_1, Column_2, Column_3)"

REFERENCE = {
    "kpi_definitions": t("coaching360_app_reference__dbo_kpidefinitions"),
    "kpi_scoring_rules": t("coaching360_app_reference__dbo_kpiscoringrules"),
    "kpi_scoring_bands": t("coaching360_app_reference__dbo_kpiscoringbands"),
    "competency_behaviors": t("coaching360_app_reference__dbo_competencybehaviors"),
    "coaching_reference_values": t("coaching360_app_reference__dbo_coachingreferencevalues"),
    "performance_measures": t("branchkpi_sources__branchkpi_dbo_performancemeasurement"),
    "performance_goals": t("branchkpi_sources__branchkpi_dbo_performancegoal"),
    "performance_expectations": t("branchkpi_sources__branchkpi_dbo_performanceexpectation"),
    "roa_state_floor": t("branchkpi_sources__branchkpi_dbo_roastatefloor"),
    "kpi_dashboard_goals": t("branchkpi_sources__reports_kpidashboard_goals"),
    "policies": t("policy_violations__policyviolations_app_policies"),
    "data_status": p("data_status"),
    "kpi_goals": p("kpi_goals"),
    "violation_types": t("policy_violations__policyviolations_app_violationtypes"),
}

# --- employee views: own rows only --------------------------------------------------------------
EMPLOYEE_VIEWS = {
    "my_profile": (f"SELECT u.*, b.BranchNumber, b.BranchName, d.DistrictNumber, d.DistrictName FROM {USER} u "
                   f"LEFT JOIN {BRANCH} b ON b.BranchDWID = u.BranchDWID LEFT JOIN {DISTRICT} d ON d.DistrictDWID = b.DistrictDWID "
                   f"WHERE u.UserDWID = {ME}", "My directory record, branch and district."),
    "my_overview": (f"SELECT * FROM {p('employee_overview')} WHERE UserDWID = {ME}",
                    "My one-row summary: latest-month KPIs and rank in my branch, open and overdue tasks, coaching, Success Plan and open violations."),
    "my_kpi_scorecard": (f"SELECT * FROM {p('employee_kpi_scorecard')} WHERE TellerID = {MY_TELLER}",
                         "My monthly scorecard: LPE, DACC loans, current-month and 30-89 day delinquency, first lien, cash advance vs state average, "
                         "calls and contacts, each with its goal (one row per branch x month). Use this for 'my scorecard'."),
    "my_monthly_kpis": (f"SELECT * FROM {p('employee_kpis')} WHERE TellerID = {MY_TELLER}",
                        "My monthly production and delinquency (one row per branch x month; KpiMonth is the month)."),
    "my_dpr_scorecard": (f"SELECT * FROM {p('dpr_metrics')} WHERE EmployeeDWID = {ME}",
                         "My published DPR scorecard metrics (ratios are fractions; MetricMonth is the month)."),
    "my_call_activity": (f"SELECT * FROM {t('branchkpi_sources__reports_kpidashboard_calldata')} WHERE TellerID = {MY_TELLER}",
                         "My daily outbound calls."),
    "my_call_goals": (f"SELECT * FROM {t('branchkpi_sources__reports_kpidashboard_employeegoals')} WHERE TellerID = {MY_TELLER}",
                      "My outbound call and contact targets."),
    "my_coaching_records": (f"SELECT * FROM {p('coaching_records')} WHERE EmployeeId = {ME} AND VisibleToEmployee",
                            "Coaching records about me that are visible to me."),
    "my_coaching_comments": (f"SELECT i.* FROM {t('coaching360_app_workflow__dbo_coachinginteractions')} i "
                             f"JOIN {t('coaching360_app_workflow__dbo_coachingrecords')} c ON c.CoachingRecordId = i.CoachingRecordId "
                             f"WHERE c.EmployeeId = {ME} AND c.VisibleToEmployee AND NOT i.IsInternal",
                             "Employee-visible comments on my coaching records (internal manager notes excluded)."),
    "my_coaching_acknowledgements": (f"SELECT * FROM {t('coaching360_app_workflow__dbo_coachingrecordacknowledgements')} WHERE EmployeeId = {ME}",
                                     "My acknowledgements of coaching records."),
    "my_success_plans": (f"SELECT * FROM {t('coaching360_app_workflow__dbo_individualdevelopmentgoals')} WHERE EmployeeId = {ME} AND NOT IsArchived",
                         "My monthly Success Plans (IDPs)."),
    "my_success_plan_comments": (f"SELECT c.* FROM {t('coaching360_app_workflow__dbo_individualdevelopmentgoalcomments')} c "
                                 f"JOIN {t('coaching360_app_workflow__dbo_individualdevelopmentgoals')} g ON g.IndividualDevelopmentGoalId = c.IndividualDevelopmentGoalId "
                                 f"WHERE g.EmployeeId = {ME} AND NOT g.IsArchived", "Comments on my Success Plans."),
    "my_tasks": (f"SELECT * FROM {t('coaching360_app_workflow__dbo_coachingtasks')} WHERE AssignedToEmployeeId = {ME}",
                 "Tasks and action items assigned to me."),
    "my_ace_payout": (f"SELECT {PAYOUT_EMPLOYEE_COLUMNS} FROM {t('crm_ace_payout__crm_ace_usp_getbmemployeemonthlypayoutestimate')} WHERE TELLER_ID = {MY_TELLER}",
                      "My ACE incentive payout estimate (branch manager payout columns removed)."),
    "my_policy_violations": (f"SELECT {VIOLATION_COLUMNS} FROM {t('policy_violations__policyviolations_app_violations')} WHERE EmployeeId = {MY_EMPNO}",
                             "Policy violations recorded about me (account numbers masked)."),
}

# --- branch and district views: everything for the branches in scope ---------------------------
TEAM_VIEWS = {
    "branches": (f"SELECT o.*, d.DistrictNumber, d.DistrictName, d.DMName, r.RegionNumber, r.RegionName, c.Coverage FROM {BRANCH} o "
                 f"JOIN {DISTRICT} d ON d.DistrictDWID = o.DistrictDWID JOIN {REGION} r ON r.RegionDWID = d.RegionDWID {COVERAGE_JOIN}",
                 "Branches I can see, with district, region and Coverage (own branch, relief coverage until a date, or in scope)."),
    "team_members": (f"SELECT u.*, b.BranchNumber, b.BranchName FROM {USER} u JOIN {BRANCH} b ON b.BranchDWID = u.BranchDWID "
                     f"WHERE u.BranchDWID IN {MY_BRANCH_DWIDS}", "Employees assigned to those branches."),
    "team_overview": (f"SELECT o.*, c.Coverage FROM {p('employee_overview')} o {COVERAGE_JOIN}",
                      "One row per employee: name, title, branch, latest-month KPIs and rank in branch, open and overdue tasks, "
                      "coaching in the last 90 days, pending acknowledgements, Success Plan status and open violations. Start here for team questions."),
    "team_kpi_scorecard": (f"SELECT o.*, c.Coverage FROM {p('employee_kpi_scorecard')} o {COVERAGE_JOIN}",
                           "Monthly scorecard per employee: LPE, DACC loans, both delinquency measures, first lien, cash advance vs state average, "
                           "calls and contacts, each with its goal, and the branch Coverage."),
    "employee_monthly_kpis": (f"SELECT * FROM {p('employee_kpis')} WHERE Branch IN {MY_BRANCH_NUMBERS}",
                              "Monthly production and delinquency per employee, with EmployeeName, UserTitle, BranchName and KpiMonth."),
    "dpr_scorecard": (f"SELECT * FROM {p('dpr_metrics')} WHERE EmployeeDWID IN {TEAM_DWIDS}",
                      "Published DPR scorecard metrics for the team, with EmployeeName, KpiName and MetricMonth."),
    "call_activity": (f"SELECT * FROM {t('branchkpi_sources__reports_kpidashboard_calldata')} WHERE TellerID IN {TEAM_TELLERS}",
                      "Daily outbound calls for the team."),
    "call_goals": (f"SELECT * FROM {t('branchkpi_sources__reports_kpidashboard_employeegoals')} WHERE TellerID IN {TEAM_TELLERS}",
                   "Outbound call and contact targets for the team."),
    "branch_monthly_performance": (f"SELECT * FROM {p('branch_performance')} WHERE Branch IN {MY_BRANCH_NUMBERS}",
                                   "Branch / BM monthly scorecard inputs, with BranchName, BMName, DistrictName and KpiMonth."),
    "branch_turnover": (f"SELECT * FROM {t('branchkpi_sources__branchkpi_monthly_branchturnovergoal')} WHERE BranchNumber IN {MY_BRANCH_NUMBERS}",
                        "Branch YTD turnover (retired from the BM scorecard)."),
    "review_comment_approvals": (f"SELECT * FROM {t('branchkpi_sources__branchkpi_dbo_reviewcommentapproval')} WHERE Branch IN {MY_BRANCH_NUMBERS}",
                                 "Branch months excluded from rolling averages."),
    "kpi_review_exclusions": (f"SELECT * FROM {t('coaching360_app_workflow__dbo_kpireviewmonthexclusions')} WHERE BranchNumber IN {MY_BRANCH_NUMBERS}",
                              "Employee months excluded from KPI review averages."),
    "coaching_records": (f"SELECT * FROM {p('coaching_records')} WHERE OrganizationalUnitId IN {MY_BRANCH_DWIDS}",
                         "All coaching records at those branches."),
    "coaching_comments": (f"SELECT i.* FROM {t('coaching360_app_workflow__dbo_coachinginteractions')} i "
                          f"JOIN {t('coaching360_app_workflow__dbo_coachingrecords')} c ON c.CoachingRecordId = i.CoachingRecordId "
                          f"WHERE c.OrganizationalUnitId IN {MY_BRANCH_DWIDS}", "Comments on those coaching records, including internal manager notes."),
    "coaching_acknowledgements": (f"SELECT a.* FROM {t('coaching360_app_workflow__dbo_coachingrecordacknowledgements')} a "
                                  f"JOIN {t('coaching360_app_workflow__dbo_coachingrecords')} c ON c.CoachingRecordId = a.CoachingRecordId "
                                  f"WHERE c.OrganizationalUnitId IN {MY_BRANCH_DWIDS}", "Employee acknowledgements of those coaching records."),
    "success_plans": (f"SELECT * FROM {t('coaching360_app_workflow__dbo_individualdevelopmentgoals')} WHERE EmployeeId IN {TEAM_DWIDS} AND NOT IsArchived",
                      "Monthly Success Plans (IDPs) for the team."),
    "success_plan_comments": (f"SELECT c.* FROM {t('coaching360_app_workflow__dbo_individualdevelopmentgoalcomments')} c "
                              f"JOIN {t('coaching360_app_workflow__dbo_individualdevelopmentgoals')} g ON g.IndividualDevelopmentGoalId = c.IndividualDevelopmentGoalId "
                              f"WHERE g.EmployeeId IN {TEAM_DWIDS} AND NOT g.IsArchived", "Comments on the team's Success Plans."),
    "tasks": (f"SELECT * FROM {t('coaching360_app_workflow__dbo_coachingtasks')} WHERE AssignedToEmployeeId IN {TEAM_DWIDS} OR AssignedToEmployeeId = {ME}",
              "Tasks assigned to the team (and to me)."),
    "branch_visits": (f"SELECT * FROM {t('coaching360_app_workflow__dbo_branchvisits')} WHERE OrganizationalUnitId IN {MY_BRANCH_DWIDS}",
                      "Branch visit reports, including confidential leadership feedback."),
    "visit_followups": (f"SELECT o.*, c.Coverage FROM {p('visit_followups')} o {COVERAGE_JOIN}",
                        "Branch visits by topic with BranchName, discussion, action plan and the follow-up task's real status "
                        "(FollowUpStatus, TaskStatus, TaskCompletedDate). Use this for visit briefs and follow-up status."),
    "branch_visit_topics": (f"SELECT p.* FROM {t('coaching360_app_workflow__dbo_branchvisittopics')} p "
                            f"JOIN {t('coaching360_app_workflow__dbo_branchvisits')} v ON v.BranchVisitId = p.BranchVisitId "
                            f"WHERE v.OrganizationalUnitId IN {MY_BRANCH_DWIDS}", "Discussion topics and follow-ups from those visits."),
    "branch_visit_plans": (f"SELECT * FROM {t('coaching360_app_workflow__dbo_branchvisitplanningplaceholders')} WHERE OrganizationalUnitId IN {MY_BRANCH_DWIDS}",
                           "Planned branch visits."),
    "ace_payouts": (f"SELECT * FROM {t('crm_ace_payout__crm_ace_usp_getbmemployeemonthlypayoutestimate')} WHERE Branch IN {MY_BRANCH_NUMBERS}",
                    "ACE incentive payout estimates for employees and BMs at those branches."),
    "policy_violations": (f"SELECT {VIOLATION_COLUMNS} FROM {t('policy_violations__policyviolations_app_violations')} WHERE BranchNumber IN {MY_BRANCH_NUMBERS}",
                          "Policy violations at those branches (account numbers masked)."),
}
MEETINGS, PARTICIPANTS = t("coaching360_app_workflow__dbo_accountabilitymeetings"), t("coaching360_app_workflow__dbo_accountabilitymeetingparticipants")
BRANCH_ONLY = {
    # Branch meetings, plus district meetings this BM attended (only their own participant notes).
    "accountability_meetings": (f"SELECT * FROM {MEETINGS} WHERE OrganizationalUnitId IN {MY_BRANCH_DWIDS} "
                                f"OR AccountabilityMeetingId IN (SELECT AccountabilityMeetingId FROM {PARTICIPANTS} WHERE EmployeeId = {ME})",
                                "Accountability meetings at my branches and district meetings I attended."),
    "accountability_participants": (f"SELECT p.* FROM {PARTICIPANTS} p JOIN {MEETINGS} m ON m.AccountabilityMeetingId = p.AccountabilityMeetingId "
                                    f"WHERE m.OrganizationalUnitId IN {MY_BRANCH_DWIDS} OR p.EmployeeId = {ME}",
                                    "Participant notes and plans of action (district meetings: my own notes only)."),
}
DISTRICT_ONLY = {
    "accountability_meetings": (f"SELECT * FROM {MEETINGS} WHERE OrganizationalUnitId IN {MY_BRANCH_DWIDS} "
                                f"OR (OrganizationalUnitId IS NULL AND OwnerEmployeeId IN {SCOPE_DMS})",
                                "Branch meetings and district (DM with BMs) meetings in scope."),
    "accountability_participants": (f"SELECT p.* FROM {PARTICIPANTS} p JOIN {MEETINGS} m ON m.AccountabilityMeetingId = p.AccountabilityMeetingId "
                                    f"WHERE m.OrganizationalUnitId IN {MY_BRANCH_DWIDS} OR (m.OrganizationalUnitId IS NULL AND m.OwnerEmployeeId IN {SCOPE_DMS})",
                                    "Participant notes and plans of action for those meetings."),
    "districts": (f"SELECT d.*, r.RegionNumber, r.RegionName, r.VPName FROM {DISTRICT} d JOIN {REGION} r ON r.RegionDWID = d.RegionDWID "
                  f"WHERE d.DistrictDWID IN {MY_DISTRICT_DWIDS}", "Districts I can see."),
    "district_monthly_performance": (f"SELECT * FROM {t('branchkpi_sources__branchkpi_monthly_districtperformance')} WHERE DistrictNumber IN {MY_DISTRICT_NUMBERS}",
                                     "District / AVP monthly scorecard inputs."),
    "district_turnover": (f"SELECT * FROM {t('branchkpi_sources__branchkpi_monthly_turnovergoal')} WHERE DistrictNumber IN {MY_DISTRICT_NUMBERS}",
                          "Monthly district turnover % (2026+ KPI = trailing 12-month sum, lower is better)."),
    "avp_payouts": (f"SELECT * FROM {t('crm_ace_payout__crm_ace_usp_getavpmonthlypayoutestimate')} WHERE CAST(districtnumber AS INT) IN {MY_DISTRICT_NUMBERS}",
                    "District manager (AVP) ACE payout estimates."),
}

LEVEL_GATE = {"employee": "IN ('employee', 'branch', 'district')", "branch": "= 'branch'", "district": "= 'district'"}
SESSION_VIEWS = {  # the signed-in person's rows of the scope tables (me() runs once per lookup)
    "my_person": ("persona", "The signed-in person: level, teller id and employee number"),
    "my_branches": ("scope_branches", "Branches the signed-in person can see"),
    "my_team": ("scope_people", "Employees at the branches the signed-in person can see"),
}


def views_for(level):
    if level == "employee":
        body = dict(EMPLOYEE_VIEWS)
    else:
        body = dict(TEAM_VIEWS) | (BRANCH_ONLY if level == "branch" else DISTRICT_ONLY)
    out = {}
    for name, (sql, comment) in body.items():
        # Every scoped lookup carries the level check, so no view can skip it.
        assert GATE in sql and "me()" not in sql, name
        out[name] = (sql.replace(GATE, LEVEL_GATE[level]), comment)
    for name, source in REFERENCE.items():
        out[name] = (f"SELECT * FROM {source}", "Reference data (same for every level).")
    return out


def render(sql, persona=None):
    """Return the SQL as written, or with the signed-in user replaced by a fixed person and every
    security and prepared object replaced by its live definition (for tests, before anything exists)."""
    if persona is None:
        return sql
    sql = sql.replace(f"{SEC}.my_coverage", f"({MY_COVERAGE})")
    for view, (table, _) in SESSION_VIEWS.items():
        sql = sql.replace(f"{SEC}.{view}", f"(SELECT * FROM ({SCOPE_TABLES[table][0]}) WHERE user_dwid = {int(persona)})")
    sql = sql.replace(f"{SEC}.scope_branches_live", f"({SCOPE_BRANCHES})")
    sql = sql.replace(f"{SEC}.branch_scope_live", f"({BRANCH_SCOPE})").replace(f"{SEC}.user_level_live", f"({USER_LEVEL})")
    for name, (definition, _) in PREPARED.items():
        sql = sql.replace(f"{PREP}.{name}", f"({definition})")
    return sql


def security_sql():
    return f"""-- Coaching360 security schema: who is signed in, their level and the branches they can see.
-- Owned by an admin. Users never read these objects directly; the level views use them.
CREATE SCHEMA IF NOT EXISTS {SEC} COMMENT 'Coaching360 access rules (identity, level, branch scope)';

-- Maps Databricks logins to directory users. The demo directory uses synthetic e-mails, so add
-- rows here; in prod, me() also matches the directory e-mail to the login automatically.
CREATE TABLE IF NOT EXISTS {SEC}.user_map (
  databricks_user STRING NOT NULL COMMENT 'Databricks login (e-mail), as returned by current_user()',
  user_dwid INT NOT NULL COMMENT 'Directory UserDWID (org_hierarchy__eda_ref_t_ref_user)',
  note STRING,
  updated_at TIMESTAMP)
COMMENT 'Databricks login to Coaching360 directory user';

-- Live definitions. The level views read the materialized copies below, so each query does a
-- small lookup instead of recomputing the hierarchy (refreshed daily; relief windows are by date).
CREATE OR REPLACE VIEW {SEC}.user_level_live
COMMENT 'Active users and their Coaching360 agent level (live definition)'
AS {USER_LEVEL};

CREATE OR REPLACE VIEW {SEC}.branch_scope_live
COMMENT 'Branches each active user can see, and why (live definition)'
AS {BRANCH_SCOPE};

CREATE MATERIALIZED VIEW IF NOT EXISTS {SEC}.user_level
  SCHEDULE EVERY 1 DAY
  COMMENT 'Active users and their Coaching360 agent level: employee, branch, district or none'
AS SELECT * FROM {SEC}.user_level_live;

CREATE MATERIALIZED VIEW IF NOT EXISTS {SEC}.branch_scope
  SCHEDULE EVERY 1 DAY
  COMMENT 'Branches each active user can see, and why'
AS SELECT * FROM {SEC}.branch_scope_live;

CREATE OR REPLACE FUNCTION {SEC}.me()
RETURNS INT
COMMENT 'Directory UserDWID of the signed-in user (user_map first, then directory e-mail)'
RETURN coalesce(
  (SELECT max(user_dwid) FROM {SEC}.user_map WHERE lower(databricks_user) = lower(current_user())),
  (SELECT max(UserDWID) FROM {USER} WHERE EmployeeActive AND lower(UserEmail) = lower(current_user())));

CREATE OR REPLACE FUNCTION {SEC}.my_level()
RETURNS STRING
COMMENT 'Coaching360 level of the signed-in user'
RETURN (SELECT max(level) FROM {SEC}.user_level WHERE user_dwid = {SEC}.me());
"""  + "\n" + scope_sql()


def scope_sql():
    """Scope tables computed once per person, and the signed-in person's rows of them."""
    q = lambda text: text.replace("'", "''")
    parts = ["-- Scope computed once: one small lookup per level view instead of re-deriving the hierarchy.",
             "-- Rerunnable. Run after the user_level / branch_scope live views exist."]
    for name, (definition, comment) in SCOPE_TABLES.items():
        parts.append(f"CREATE OR REPLACE VIEW {SEC}.{name}_live\nCOMMENT '{q(comment)} (live definition)'\nAS {definition};\n")
    for name, (_, comment) in SCOPE_TABLES.items():
        parts.append(f"CREATE OR REPLACE MATERIALIZED VIEW {SEC}.{name}\n  SCHEDULE EVERY 1 DAY\n  COMMENT '{q(comment)}'\n"
                     f"AS SELECT * FROM {SEC}.{name}_live;\n")
    for view, (table, comment) in SESSION_VIEWS.items():
        parts.append(f"CREATE OR REPLACE VIEW {SEC}.{view}\nCOMMENT '{q(comment)}'\nAS SELECT * FROM {SEC}.{table} WHERE user_dwid = {SEC}.me();\n")
    parts.append(f"CREATE OR REPLACE VIEW {SEC}.my_coverage\nCOMMENT 'How the signed-in person covers each branch in scope'\nAS {MY_COVERAGE};\n")
    parts.append("-- After a directory change, refresh right away (user_level and branch_scope first):\n"
                 + "".join(f"-- REFRESH MATERIALIZED VIEW {SEC}.{name};\n" for name in SCOPE_TABLES))
    return "\n".join(parts)


def prepared_sql():
    """Daily pre-joined copies of the busiest sources, read by the level views."""
    q = lambda text: text.replace("'", "''")
    parts = [f"-- {PREP}: daily pre-joined copies of the busiest Coaching360 sources (the data loads monthly).",
             "-- Rerunnable. Users never read these directly; the level views filter them to the person's scope.",
             f"CREATE SCHEMA IF NOT EXISTS {PREP} COMMENT 'Coaching360 pre-joined sources for the level views';\n"]
    for name, (definition, comment) in PREPARED.items():
        parts.append(f"CREATE OR REPLACE MATERIALIZED VIEW {PREP}.{name}\n  SCHEDULE EVERY 1 DAY\n  COMMENT '{q(comment)}'\nAS {definition};\n")
    parts.append("-- To pick up new source data right away:\n"
                 + "".join(f"-- REFRESH MATERIALIZED VIEW {PREP}.{name};\n" for name in PREPARED))
    return "\n".join(parts)


def materialize_scope_sql():
    """One-time change for an existing setup: swap the scope views for materialized copies."""
    return f"""-- One-time: replace the security scope views with daily materialized views (faster level views).
-- Run once in the SQL Editor (Run all), then rerun 05b_demo_grants_app.sql (the drop removes its grant).
CREATE OR REPLACE VIEW {SEC}.user_level_live
COMMENT 'Active users and their Coaching360 agent level (live definition)'
AS {USER_LEVEL};

CREATE OR REPLACE VIEW {SEC}.branch_scope_live
COMMENT 'Branches each active user can see, and why (live definition)'
AS {BRANCH_SCOPE};

-- If user_level / branch_scope are still plain views (first run only), drop them first:
--   DROP VIEW IF EXISTS {SEC}.user_level;  DROP VIEW IF EXISTS {SEC}.branch_scope;
-- When they are already materialized views, the statements below simply refresh their definition.
CREATE OR REPLACE MATERIALIZED VIEW {SEC}.user_level
  SCHEDULE EVERY 1 DAY
  COMMENT 'Active users and their Coaching360 agent level: employee, branch, district or none'
AS SELECT * FROM {SEC}.user_level_live;

CREATE OR REPLACE MATERIALIZED VIEW {SEC}.branch_scope
  SCHEDULE EVERY 1 DAY
  COMMENT 'Branches each active user can see, and why'
AS SELECT * FROM {SEC}.branch_scope_live;

-- After a directory change (new BM, relief manager, transfer), refresh right away:
-- REFRESH MATERIALIZED VIEW {SEC}.user_level;  REFRESH MATERIALIZED VIEW {SEC}.branch_scope;
"""


# --- trusted functions: one call answers a common question (Genie uses them as trusted assets) ---
# Genie trusted functions do not accept DATE arguments, so the month is a string ('2026-09' or '2026-09-15').
MONTH_PARAM = ("month_start STRING COMMENT 'Month to report as YYYY-MM (for example 2026-09) or any date in it; "
               "NULL means the latest month in the data'")
MONTH_START = "CAST(date_trunc('MONTH', try_to_date(CASE WHEN length(month_start) = 7 THEN concat(month_start, '-01') ELSE month_start END)) AS DATE)"


def month_of(x):
    """The requested month, or the latest month with complete KPI data (never the calendar month)."""
    return f"coalesce({MONTH_START}, (SELECT LatestKpiMonth FROM {x}.data_status))"


AS_OF_DATE = "(SELECT AsOfDate FROM {x}.data_status)"
PLAN_MONTH_PARAM = ("month_start STRING COMMENT 'Plan month as YYYY-MM (for example 2026-10); NULL means the current plan month "
                    "(the month of the dataset as-of date)'")
PLAN_COLUMNS = ("GoalMonth DATE, Status STRING, Approval STRING, IsLocked BOOLEAN, FocusType STRING, MetricFocusAreas STRING, "
                "CompetencyFocusAreas STRING, GoalStatement STRING, DevelopmentArea STRING, ActionPlan STRING, SuccessMeasures STRING, "
                "MonthlyKpiGoals STRING, DueDate DATE")
PLAN_SELECT = ("CAST(GoalMonth AS DATE), Status, IF(ApprovedUtc IS NULL, 'Not yet approved', concat('Approved ', date_format(ApprovedUtc, 'M/d/yyyy'))), "
               "LockedUtc IS NOT NULL, FocusType, array_join(from_json(nullif(MetricFocusAreas, ''), 'array<string>'), ', '), "
               "array_join(from_json(nullif(CompetencyFocusAreas, ''), 'array<string>'), ', '), GoalStatement, DevelopmentArea, ActionPlan, "
               "SuccessMeasures, MonthlyKpiGoals, CAST(DueDate AS DATE)")


def plan_month_of(x):
    return f"coalesce({MONTH_START}, CAST(date_trunc('MONTH', (SELECT AsOfDate FROM {x}.data_status)) AS DATE))"
# Scorecard rows: (order, measure, actual, goal, unit, higher is better, goal type). Units decide the display.
SCORECARD_ROWS = [
    (1, "Loans booked", "TotalLoans", "NULL", "count", "NULL", "NULL"),
    (2, "LPE (loans per employee)", "LPE", "LpeGoal", "decimal", "true", "'Goal'"),
    (3, "DACC loans", "DACC_Loans", "DaccLoansGoal", "count", "true", "'Goal'"),
    (4, "Delinquency - current month", "DlqCurrentMonth", "DlqCurrentMonthGoal", "fraction", "false", "'Goal'"),
    (5, "Delinquency - 30-89 day", "Dlq30To89Day", "Dlq30To89DayGoal", "fraction", "false", "'Goal'"),
    (6, "First lien - share of loans", "FirstLienPercentage", "NULL", "percent", "NULL", "NULL"),
    (7, "First lien - share of volume", "FirstLienVolumePercentage", "NULL", "percent", "NULL", "NULL"),
    (8, "Cash advance", "CashAdvance", "StateAverageCashAdvance", "currency", "true", "'State average'"),
    (9, "Outbound calls", "OutboundCalls", "OutboundCallsGoal", "count", "true", "'Goal'"),
    (10, "Outbound contacts", "OutboundContacts", "OutboundContactsGoal", "count", "true", "'Goal'"),
]
D = "DECIMAL(19,4)"


def display(value, unit):
    return (f"CASE {unit} WHEN 'count' THEN format_number({value}, 0) WHEN 'decimal' THEN format_number({value}, 2) "
            f"WHEN 'fraction' THEN concat(format_number({value} * 100, 2), '%') WHEN 'percent' THEN concat(format_number({value}, 1), '%') "
            f"WHEN 'currency' THEN concat('$', format_number({value}, 0)) ELSE format_number({value}, 2) END")


def status(actual, goal, higher, goal_type):
    return (f"CASE WHEN {goal} IS NULL OR {actual} IS NULL THEN NULL "
            f"WHEN {goal_type} = 'State average' THEN IF({actual} >= {goal}, 'Above state average', 'Below state average') "
            f"WHEN {higher} THEN IF({actual} >= {goal}, 'Met', 'Below goal') ELSE IF({actual} <= {goal}, 'Met', 'Above goal') END")


def f2(value):
    return f"format_number({value}, 2)"


def pct(fraction):  # 0.0409 -> 4.09%
    return f"concat(format_number({fraction} * 100, 2), '%')"


def pct1(percent):  # 54.58 -> 54.6%
    return f"concat(format_number({percent}, 1), '%')"


def money(value):
    return f"concat('$', format_number({value}, 0))"


def met(actual, goal, higher):
    return f"CASE WHEN {goal} IS NULL OR {actual} IS NULL THEN NULL WHEN {actual} {'>=' if higher else '<='} {goal} THEN 'Met' ELSE '{'Below' if higher else 'Above'} goal' END"


# Branch brief: one long-form table (Section, Item, Detail) built from the level's views.
BRANCH_BRIEF = """WITH br AS (SELECT BranchDWID, BranchNumber, BranchName, Coverage FROM {x}.branches WHERE {match}),
m AS (SELECT {month} AS KpiMonth),
perf AS (
  SELECT p.Branch, p.Direct_Loans_MTD_LPE, p.Branch_DACC_Loans, p.DLQ3060DayPerc_Actual, p.DLQ3089DayPerc_Goal, p.DLQCurrentMonthPerc_Actual,
         p.DLQCurrentMonthPerc_Goal, p.FirstLienPercentage,
         rank() OVER (ORDER BY p.Direct_Loans_MTD_LPE DESC) AS LpeRank, rank() OVER (ORDER BY p.DLQ3060DayPerc_Actual ASC) AS DlqRank,
         count(*) OVER () AS Branches
  FROM {x}.branch_monthly_performance p JOIN m ON p.KpiMonth = m.KpiMonth),
people AS (
  SELECT s.EmployeeName, s.LPE, s.Dlq30To89Day, s.Dlq30To89DayGoal, s.DACC_Loans, o.PendingAcknowledgements, o.OpenTasks, o.OverdueTasks, o.SuccessPlanStatus
  FROM {x}.team_kpi_scorecard s JOIN m ON s.KpiMonth = m.KpiMonth JOIN br ON br.BranchNumber = s.BranchNumber
  LEFT JOIN {x}.team_overview o ON o.UserDWID = s.EmployeeDWID)
SELECT 'Branch KPIs', concat(br.BranchName, ' (', date_format(m.KpiMonth, 'MMMM yyyy'), coalesce(concat(', ', nullif(br.Coverage, 'In scope')), ''), ')'),
       concat('LPE ', format_number(perf.Direct_Loans_MTD_LPE, 2), ' (rank ', perf.LpeRank, ' of ', perf.Branches, '); DACC loans ', perf.Branch_DACC_Loans,
              '; 30-89 day delinquency ', format_number(perf.DLQ3060DayPerc_Actual * 100, 2), '% vs goal ', format_number(perf.DLQ3089DayPerc_Goal * 100, 2),
              '% (rank ', perf.DlqRank, ' of ', perf.Branches, ', 1 = lowest); current-month delinquency ', format_number(perf.DLQCurrentMonthPerc_Actual * 100, 2),
              '% vs goal ', format_number(perf.DLQCurrentMonthPerc_Goal * 100, 2), '%; first lien ', format_number(perf.FirstLienPercentage, 1), '%')
FROM br JOIN perf ON perf.Branch = br.BranchNumber CROSS JOIN m
UNION ALL
SELECT 'Employees', EmployeeName,
       concat('LPE ', format_number(LPE, 2), ' (goal 1.00); 30-89 day delinquency ', format_number(Dlq30To89Day * 100, 2), '%',
              IF(Dlq30To89Day <= Dlq30To89DayGoal, ' (under goal)', ' (over goal)'), '; DACC loans ', DACC_Loans,
              '; pending acknowledgements ', coalesce(PendingAcknowledgements, 0), '; open tasks ', coalesce(OpenTasks, 0),
              ' (', coalesce(OverdueTasks, 0), ' overdue); Success Plan ', coalesce(SuccessPlanStatus, 'none'))
FROM people
UNION ALL
SELECT 'Branch totals', 'Pending acknowledgements and open tasks',
       concat(SUM(o.PendingAcknowledgements), ' coaching records pending acknowledgement; ', SUM(o.OpenTasks), ' open tasks (', SUM(o.OverdueTasks), ' overdue)')
FROM {x}.team_overview o JOIN br ON br.BranchDWID = o.BranchDWID HAVING COUNT(*) > 0
UNION ALL
SELECT 'Success Plans awaiting approval', o.Name, concat(date_format(g.GoalMonth, 'MMMM yyyy'), coalesce(concat(', due ', date_format(g.DueDate, 'M/d/yyyy')), ''))
FROM {x}.success_plans g JOIN {x}.team_overview o ON o.UserDWID = g.EmployeeId JOIN br ON br.BranchDWID = o.BranchDWID
WHERE g.Status = 'Active' AND g.ApprovedUtc IS NULL
UNION ALL
SELECT 'Recent visits', date_format(v.VisitDate, 'M/d/yyyy'), concat(v.VisitPurpose, ' (', v.VisitStatus, ')')
FROM (SELECT DISTINCT f.BranchVisitId, f.VisitDate, f.VisitPurpose, f.VisitStatus FROM {x}.visit_followups f JOIN br ON br.BranchDWID = f.BranchDWID
      ORDER BY f.VisitDate DESC LIMIT 3) v
UNION ALL
SELECT 'Open visit follow-ups', concat(f.TopicTitle, ' (', date_format(f.VisitDate, 'M/d/yyyy'), ' visit)'),
       concat(f.FollowUpStatus, coalesce(concat(', due ', date_format(f.TaskDueDate, 'M/d/yyyy')), ''), coalesce(concat(', owner ', f.AssignedOwnerName), ''))
FROM {x}.visit_followups f JOIN br ON br.BranchDWID = f.BranchDWID WHERE f.FollowUpRequired AND f.FollowUpStatus <> 'Completed'
UNION ALL
SELECT 'Note', trim(branch_name), 'No branch with this name is in your scope.' WHERE NOT EXISTS (SELECT 1 FROM br)"""

DM_VISIT_CADENCE = """WITH a AS (SELECT AsOfDate FROM {x}.data_status),
visits AS (
  SELECT b.DistrictDWID,
         count_if(v.VisitStatus = 'Submitted' AND NOT v.IsArchived) AS Completed, count_if(v.VisitStatus = 'Draft') AS Drafts,
         count_if(CAST(v.VisitDate AS DATE) >= date_trunc('MONTH', a.AsOfDate)) AS ThisMonth,
         max(IF(v.VisitStatus = 'Submitted' AND NOT v.IsArchived, CAST(v.VisitDate AS DATE), NULL)) AS LastVisit
  FROM {x}.branch_visits v JOIN {x}.branches b ON b.BranchDWID = v.OrganizationalUnitId CROSS JOIN a GROUP BY b.DistrictDWID),
plans AS (
  SELECT b.DistrictDWID, count_if(p.Status = 'Active' AND CAST(p.VisitDate AS DATE) > a.AsOfDate) AS Scheduled,
         count_if(p.Status = 'Active' AND CAST(p.VisitDate AS DATE) <= a.AsOfDate) AS Overdue
  FROM {x}.branch_visit_plans p JOIN {x}.branches b ON b.BranchDWID = p.OrganizationalUnitId CROSS JOIN a GROUP BY b.DistrictDWID),
stale AS (
  SELECT b.DistrictDWID, count_if(l.LastVisit IS NULL OR l.LastVisit < date_sub(a.AsOfDate, 30)) AS Stale
  FROM {x}.branches b CROSS JOIN a
  LEFT JOIN (SELECT OrganizationalUnitId, max(CAST(VisitDate AS DATE)) AS LastVisit FROM {x}.branch_visits
             WHERE VisitStatus = 'Submitted' AND NOT IsArchived GROUP BY OrganizationalUnitId) l ON l.OrganizationalUnitId = b.BranchDWID
  GROUP BY b.DistrictDWID)
SELECT d.DMName, d.DistrictName, CAST(coalesce(v.Completed, 0) AS INT), CAST(coalesce(p.Scheduled, 0) AS INT), CAST(coalesce(p.Overdue, 0) AS INT),
       CAST(coalesce(v.Drafts, 0) AS INT), CAST(coalesce(v.ThisMonth, 0) AS INT), v.LastVisit, CAST(coalesce(s.Stale, 0) AS INT), (SELECT AsOfDate FROM a)
FROM {x}.districts d LEFT JOIN visits v ON v.DistrictDWID = d.DistrictDWID LEFT JOIN plans p ON p.DistrictDWID = d.DistrictDWID
LEFT JOIN stale s ON s.DistrictDWID = d.DistrictDWID ORDER BY d.DistrictName"""


def functions_for(level):
    """name: (parameters, returned columns, comment, body). Bodies read only this level's views."""
    x = SCHEMAS[level]
    as_of = AS_OF_DATE.format(x=x)
    if level == "employee":
        stack = ", ".join(f"{o}, '{m}', CAST({a} AS {D}), CAST({g} AS {D}), '{u}', CAST({h} AS BOOLEAN), CAST({gt} AS STRING)"
                          for o, m, a, g, u, h, gt in SCORECARD_ROWS)
        dpr_unit = "CASE UnitOfMeasure WHEN 'Ratio' THEN 'fraction' WHEN 'Currency' THEN 'currency' ELSE 'decimal' END"
        return {
            "my_scorecard": (MONTH_PARAM, f"KpiMonth DATE, BranchName STRING, Section STRING, Measure STRING, Actual {D}, Goal {D}, "
                                          "ActualDisplay STRING, GoalDisplay STRING, GoalType STRING, Status STRING, "
                                          "LastMonthDisplay STRING, LastMonthStatus STRING, YearToDateAverageDisplay STRING",
                             "My scorecard for one month (default: latest month with complete KPI data): monthly KPIs with goals and status "
                             "(LPE, DACC loans, both delinquency measures, first lien, cash advance vs state average, calls, contacts), "
                             "each with last month's value and the year-to-date monthly average, then the DPR metrics. "
                             "Report the Display and Status values as given.",
                             f"""WITH m AS (SELECT {month_of(x)} AS KpiMonth),
months AS (
  SELECT s.KpiMonth, s.BranchName, stack({len(SCORECARD_ROWS)}, {stack}) AS (SortOrder, Measure, Actual, Goal, Unit, HigherIsBetter, GoalType)
  FROM {x}.my_kpi_scorecard s JOIN m
    ON s.KpiMonth BETWEEN least(add_months(m.KpiMonth, -1), make_date(year(m.KpiMonth), 1, 1)) AND m.KpiMonth),
ytd AS (
  SELECT y.BranchName, y.SortOrder, AVG(y.Actual) AS YearToDate
  FROM months y JOIN m ON year(y.KpiMonth) = year(m.KpiMonth) GROUP BY y.BranchName, y.SortOrder),
kpi AS (
  SELECT c.KpiMonth, c.BranchName, c.SortOrder, c.Measure, c.Actual, c.Goal, c.Unit, c.HigherIsBetter, c.GoalType,
         p.Actual AS LastMonth, p.Goal AS LastMonthGoal, ytd.YearToDate
  FROM months c JOIN m ON c.KpiMonth = m.KpiMonth
  LEFT JOIN months p ON p.BranchName = c.BranchName AND p.SortOrder = c.SortOrder AND p.KpiMonth = add_months(c.KpiMonth, -1)
  LEFT JOIN ytd ON ytd.BranchName = c.BranchName AND ytd.SortOrder = c.SortOrder),
dpr AS (
  SELECT d.MetricMonth AS KpiMonth, CAST(NULL AS STRING) AS BranchName, 100 AS SortOrder, d.KpiName AS Measure,
         CAST(d.MetricValue AS {D}) AS Actual, CAST(NULL AS {D}) AS Goal, {dpr_unit} AS Unit,
         CAST(NULL AS BOOLEAN) AS HigherIsBetter, CAST(NULL AS STRING) AS GoalType,
         CAST(NULL AS {D}) AS LastMonth, CAST(NULL AS {D}) AS LastMonthGoal, CAST(NULL AS {D}) AS YearToDate
  FROM {x}.my_dpr_scorecard d JOIN m ON d.MetricMonth = m.KpiMonth)
SELECT KpiMonth, BranchName, IF(SortOrder < 100, 'Monthly KPIs', 'DPR metrics') AS Section, Measure, Actual, Goal,
       {display('Actual', 'Unit')} AS ActualDisplay, {display('Goal', 'Unit')} AS GoalDisplay, GoalType,
       {status('Actual', 'Goal', 'HigherIsBetter', 'GoalType')} AS Status,
       {display('LastMonth', 'Unit')} AS LastMonthDisplay, {status('LastMonth', 'LastMonthGoal', 'HigherIsBetter', 'GoalType')} AS LastMonthStatus,
       {display('YearToDate', 'Unit')} AS YearToDateAverageDisplay
FROM (SELECT * FROM kpi UNION ALL SELECT * FROM dpr)
ORDER BY IF(SortOrder < 100, 0, 1), BranchName, SortOrder, Measure"""),
            "my_success_plan": (PLAN_MONTH_PARAM, PLAN_COLUMNS,
                                "My Success Plan for one month (default: the current plan month, the month of the dataset as-of date): status, "
                                "whether it is approved or locked, metric and competency focus areas, goal statement and action plan.",
                                f"""SELECT {PLAN_SELECT} FROM {x}.my_success_plans
WHERE CAST(date_trunc('MONTH', GoalMonth) AS DATE) = {plan_month_of(x)} ORDER BY GoalMonth"""),
            "my_pending_acknowledgements": ("", "CoachingDate DATE, TriggerType STRING, Topic STRING, KpiFocus STRING, ObservationSummary STRING, DaysWaiting INT",
                                            "Coaching records about me still waiting for my acknowledgement, oldest first (any month; days counted to the dataset as-of date).",
                                            f"""SELECT CAST(CoachingDate AS DATE), TriggerType, coalesce(TopicCode, CompetencyCode), KpiFocusCode, ObservationSummary,
       datediff({as_of}, CAST(CoachingDate AS DATE))
FROM {x}.my_coaching_records WHERE Status = 'PendingAcknowledgement' ORDER BY 1"""),
            "my_open_items": ("", "ItemType STRING, Item STRING, Status STRING, ItemDate DATE, DueDate DATE",
                              "Everything still open for me: tasks, coaching records waiting for my acknowledgement, open policy violations and my active Success Plan.",
                              f"""SELECT 'Task', Subject, Status, CAST(CreatedUtc AS DATE), CAST(DueDate AS DATE) FROM {x}.my_tasks WHERE Status <> 'Completed'
UNION ALL SELECT 'Coaching acknowledgement', coalesce(TopicCode, ObservationSummary), Status, CAST(CoachingDate AS DATE), CAST(DueDate AS DATE)
  FROM {x}.my_coaching_records WHERE Status = 'PendingAcknowledgement'
UNION ALL SELECT 'Policy violation', PolicyName, Status, ViolationDate, CorrectiveActionDueDate
  FROM {x}.my_policy_violations WHERE Status <> 'CorrectiveActionCompleted'
UNION ALL SELECT 'Success Plan', DevelopmentArea, Status, CAST(GoalMonth AS DATE), CAST(DueDate AS DATE) FROM {x}.my_success_plans WHERE Status = 'Active'"""),
        }
    branch_match = ("(lower(BranchName) = replace(lower(trim(branch_name)), ' branch', '') "
                    "OR CAST(BranchNumber AS STRING) = trim(branch_name))")
    visit_columns = ("BranchName STRING, Coverage STRING, VisitDate DATE, VisitPurpose STRING, VisitStatus STRING, TopicTitle STRING, "
                     "DiscussionNotes STRING, ActionPlan STRING, FollowUpRequired BOOLEAN, AssignedOwnerName STRING, FollowUpStatus STRING, "
                     "TaskCompletedDate DATE, TaskDueDate DATE, ConfidentialLeadershipFeedback STRING, Note STRING")
    team = {
        "team_scorecard": (MONTH_PARAM, "KpiMonth DATE, EmployeeName STRING, UserTitle STRING, BranchName STRING, Coverage STRING, TotalLoans INT, "
                                        "LPE STRING, LpeGoal STRING, LpeStatus STRING, LastMonthLPE STRING, DACC_Loans INT, DaccLoansGoal INT, DaccStatus STRING, "
                                        "DlqCurrentMonth STRING, DlqCurrentMonthGoal STRING, DlqCurrentMonthStatus STRING, "
                                        "Dlq30To89Day STRING, Dlq30To89DayGoal STRING, Dlq30To89DayStatus STRING, LastMonthDlq30To89Day STRING, "
                                        "FirstLien STRING, OutboundCalls STRING, OutboundCallsGoal STRING, CallsStatus STRING, "
                                        "OutboundContacts STRING, OutboundContactsGoal STRING, ContactsStatus STRING, LastMonthDACC_Loans INT, "
                                        "LpeRankInBranch INT, LpeRank INT",
                           "Monthly scorecard per employee (default: latest month with complete KPI data), values ready to show: LPE, DACC loans, "
                           "current-month and 30-89 day delinquency, first lien, calls and contacts, each with goal and status, plus last month's LPE, "
                           "DACC loans and 30-89 day delinquency, and LPE rank in the branch and across the team (1 = highest). Each branch ends with a "
                           "'Branch total' row (branch LPE, DACC loans, delinquency, first lien; calls and contacts summed). Report values as given.",
                           f"""WITH m AS (SELECT {month_of(x)} AS KpiMonth),
emp AS (
  SELECT t.KpiMonth, t.EmployeeName, t.UserTitle, t.BranchName, t.Coverage, t.TotalLoans,
         {f2('t.LPE')} AS LPE, {f2('t.LpeGoal')} AS LpeGoal, {met('t.LPE', 't.LpeGoal', True)} AS LpeStatus, {f2('p.LPE')} AS LastMonthLPE,
         t.DACC_Loans, t.DaccLoansGoal, {met('t.DACC_Loans', 't.DaccLoansGoal', True)} AS DaccStatus,
         {pct('t.DlqCurrentMonth')} AS DlqCurrentMonth, {pct('t.DlqCurrentMonthGoal')} AS DlqCurrentMonthGoal,
         {met('t.DlqCurrentMonth', 't.DlqCurrentMonthGoal', False)} AS DlqCurrentMonthStatus,
         {pct('t.Dlq30To89Day')} AS Dlq30To89Day, {pct('t.Dlq30To89DayGoal')} AS Dlq30To89DayGoal,
         {met('t.Dlq30To89Day', 't.Dlq30To89DayGoal', False)} AS Dlq30To89DayStatus, {pct('p.Dlq30To89Day')} AS LastMonthDlq30To89Day,
         {pct1('t.FirstLienPercentage')} AS FirstLien, format_number(t.OutboundCalls, 0) AS OutboundCalls,
         format_number(t.OutboundCallsGoal, 0) AS OutboundCallsGoal, {met('t.OutboundCalls', 't.OutboundCallsGoal', True)} AS CallsStatus,
         format_number(t.OutboundContacts, 0) AS OutboundContacts, format_number(t.OutboundContactsGoal, 0) AS OutboundContactsGoal,
         {met('t.OutboundContacts', 't.OutboundContactsGoal', True)} AS ContactsStatus, p.DACC_Loans AS LastMonthDACC_Loans,
         CAST(rank() OVER (PARTITION BY t.BranchName ORDER BY t.LPE DESC) AS INT) AS LpeRankInBranch,
         CAST(rank() OVER (ORDER BY t.LPE DESC) AS INT) AS LpeRank
  FROM {x}.team_kpi_scorecard t JOIN m ON t.KpiMonth = m.KpiMonth
  LEFT JOIN {x}.team_kpi_scorecard p ON p.TellerID = t.TellerID AND p.BranchNumber = t.BranchNumber AND p.KpiMonth = add_months(t.KpiMonth, -1)),
calls AS (
  SELECT BranchNumber, SUM(TotalLoans) AS TotalLoans, SUM(OutboundCalls) AS OutboundCalls, SUM(OutboundCallsGoal) AS OutboundCallsGoal,
         SUM(OutboundContacts) AS OutboundContacts, SUM(OutboundContactsGoal) AS OutboundContactsGoal
  FROM {x}.team_kpi_scorecard t JOIN m ON t.KpiMonth = m.KpiMonth GROUP BY BranchNumber),
total AS (
  -- One "Branch total" row per branch, from the branch scorecard (branch LPE is not an average of employees).
  SELECT b.KpiMonth, 'Branch total' AS EmployeeName, CAST(NULL AS STRING) AS UserTitle, b.BranchName, c.Coverage,
         CAST(k.TotalLoans AS INT), {f2('b.Direct_Loans_MTD_LPE')}, {f2(LPE_GOAL)}, {met('b.Direct_Loans_MTD_LPE', LPE_GOAL, True)}, {f2('l.Direct_Loans_MTD_LPE')},
         b.Branch_DACC_Loans, CAST(NULL AS INT), CAST(NULL AS STRING),
         {pct('b.DLQCurrentMonthPerc_Actual')}, {pct('b.DLQCurrentMonthPerc_Goal')}, {met('b.DLQCurrentMonthPerc_Actual', 'b.DLQCurrentMonthPerc_Goal', False)},
         {pct('b.DLQ3060DayPerc_Actual')}, {pct('b.DLQ3089DayPerc_Goal')}, {met('b.DLQ3060DayPerc_Actual', 'b.DLQ3089DayPerc_Goal', False)}, {pct('l.DLQ3060DayPerc_Actual')},
         {pct1('b.FirstLienPercentage')}, format_number(k.OutboundCalls, 0), format_number(k.OutboundCallsGoal, 0), {met('k.OutboundCalls', 'k.OutboundCallsGoal', True)},
         format_number(k.OutboundContacts, 0), format_number(k.OutboundContactsGoal, 0), {met('k.OutboundContacts', 'k.OutboundContactsGoal', True)},
         l.Branch_DACC_Loans, CAST(NULL AS INT), CAST(NULL AS INT)
  FROM {x}.branch_monthly_performance b JOIN m ON b.KpiMonth = m.KpiMonth
  LEFT JOIN {x}.branch_monthly_performance l ON l.Branch = b.Branch AND l.KpiMonth = add_months(b.KpiMonth, -1)
  LEFT JOIN {x}.branches c ON c.BranchNumber = b.Branch
  LEFT JOIN calls k ON k.BranchNumber = b.Branch)
SELECT * FROM (SELECT * FROM emp UNION ALL SELECT * FROM total)
ORDER BY BranchName, IF(EmployeeName = 'Branch total', 1, 0), LpeRankInBranch"""),
        "team_dpr_scorecard": (MONTH_PARAM, "MetricMonth DATE, EmployeeName STRING, KpiName STRING, MetricValue DECIMAL(19,8), UnitOfMeasure STRING, IsHigherBetter BOOLEAN",
                               "DPR metrics per employee for one month (default: latest month with complete KPI data). Ratios are fractions.",
                               f"""SELECT MetricMonth, EmployeeName, KpiName, MetricValue, UnitOfMeasure, IsHigherBetter
FROM {x}.dpr_scorecard WHERE MetricMonth = {month_of(x)} ORDER BY EmployeeName, KpiName"""),
        "team_ranking": (MONTH_PARAM, "KpiMonth DATE, EmployeeName STRING, UserTitle STRING, BranchName STRING, TotalLoans INT, LPE STRING, "
                                      "TotalVolume STRING, DlqCurrentMonth STRING, VolumeRank INT",
                         "Employees ranked by volume for one month (default: latest month with complete KPI data), values ready to show.",
                         f"""SELECT KpiMonth, EmployeeName, UserTitle, BranchName, TotalLoans, {f2('LPE')}, {money('TotalVolumeDollars')},
       {pct('DLQCurrentMonthPerc_Actual')}, CAST(rank() OVER (ORDER BY TotalVolumeDollars DESC) AS INT) AS VolumeRank
FROM {x}.employee_monthly_kpis WHERE KpiMonth = {month_of(x)} ORDER BY VolumeRank"""),
        "branch_scorecard": (MONTH_PARAM, "KpiMonth DATE, DistrictName STRING, BranchNumber INT, BranchName STRING, BMName STRING, LPE STRING, "
                                          "DACC_Loans INT, DlqCurrentMonth STRING, DlqCurrentMonthGoal STRING, Dlq30To89Day STRING, Dlq30To89DayGoal STRING, "
                                          "Dlq30To89DayStatus STRING, FirstLien STRING, ROA STRING, TotalVolume STRING, "
                                          "LpeRank INT, Dlq30To89DayRank INT, FirstLienRank INT, VolumeRank INT",
                             "Branch scorecard (branch totals) for one month (default: latest month with complete KPI data), values ready to show: "
                             "branch LPE, DACC loans, current-month and 30-89 day delinquency with goals, first lien, ROA and volume, with ranks among "
                             "the branches in scope (LpeRank, FirstLienRank, VolumeRank: 1 = highest; Dlq30To89DayRank: 1 = lowest delinquency).",
                             f"""SELECT KpiMonth, DistrictName, Branch, BranchName, BMName, {f2('Direct_Loans_MTD_LPE')}, Branch_DACC_Loans,
       {pct('DLQCurrentMonthPerc_Actual')}, {pct('DLQCurrentMonthPerc_Goal')}, {pct('DLQ3060DayPerc_Actual')}, {pct('DLQ3089DayPerc_Goal')},
       {met('DLQ3060DayPerc_Actual', 'DLQ3089DayPerc_Goal', False)}, {pct1('FirstLienPercentage')}, format_number(Branch_ROA_Percentage, 2),
       {money('TotalVolumeDollars')},
       CAST(rank() OVER (ORDER BY Direct_Loans_MTD_LPE DESC) AS INT), CAST(rank() OVER (ORDER BY DLQ3060DayPerc_Actual ASC) AS INT),
       CAST(rank() OVER (ORDER BY FirstLienPercentage DESC) AS INT), CAST(rank() OVER (ORDER BY TotalVolumeDollars DESC) AS INT)
FROM {x}.branch_monthly_performance WHERE KpiMonth = {month_of(x)} ORDER BY Branch"""),
        "overdue_tasks": ("", "EmployeeName STRING, BranchName STRING, Subject STRING, DueDate DATE, DaysOverdue INT, Status STRING, Severity STRING, AsOfDate DATE",
                          "Open tasks past their due date as of the dataset as-of date, per employee, oldest first.",
                          f"""SELECT m.Name, m.BranchName, t.Subject, CAST(t.DueDate AS DATE), datediff({as_of}, CAST(t.DueDate AS DATE)), t.Status, t.Severity, {as_of}
FROM {x}.tasks t JOIN {x}.team_members m ON m.UserDWID = t.AssignedToEmployeeId
WHERE t.Status <> 'Completed' AND CAST(t.DueDate AS DATE) < {as_of} ORDER BY 5 DESC"""),
        "pending_acknowledgements": ("", "EmployeeName STRING, BranchName STRING, CoachingDate DATE, Topic STRING, DueDate DATE, DaysWaiting INT",
                                     "Coaching records still waiting for the employee's acknowledgement, oldest first (days counted to the dataset as-of date).",
                                     f"""SELECT c.EmployeeName, b.BranchName, CAST(c.CoachingDate AS DATE), coalesce(c.TopicCode, c.ObservationSummary), CAST(c.DueDate AS DATE),
       datediff({as_of}, CAST(c.CoachingDate AS DATE))
FROM {x}.coaching_records c LEFT JOIN {x}.branches b ON b.BranchDWID = c.OrganizationalUnitId
WHERE c.Status = 'PendingAcknowledgement' ORDER BY 6 DESC"""),
        "visit_brief": ("branch_name STRING COMMENT 'Branch name (for example Laurel Fork) or branch number'", visit_columns,
                        "Latest branch visit for one branch in my scope: purpose, every topic with discussion and action plan, and the real "
                        "follow-up status from the task (FollowUpStatus, TaskCompletedDate). Returns a Note row when the branch is not in scope.",
                        f"""SELECT BranchName, Coverage, VisitDate, VisitPurpose, VisitStatus, TopicTitle, DiscussionNotes, ActionPlan, FollowUpRequired,
       AssignedOwnerName, FollowUpStatus, TaskCompletedDate, TaskDueDate, ConfidentialLeadershipFeedback, CAST(NULL AS STRING)
FROM {x}.visit_followups
WHERE BranchVisitId = (SELECT max_by(BranchVisitId, VisitDate) FROM {x}.visit_followups WHERE {branch_match})
UNION ALL
SELECT trim(branch_name), NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL,
       IF(EXISTS (SELECT 1 FROM {x}.branches WHERE {branch_match}), 'No branch visits are recorded for this branch.',
          'No branch with this name is in your scope.')
WHERE NOT EXISTS (SELECT 1 FROM {x}.visit_followups WHERE {branch_match})"""),
        "open_visit_followups": ("", "BranchName STRING, Coverage STRING, VisitDate DATE, TopicTitle STRING, AssignedOwnerName STRING, FollowUpStatus STRING, "
                                     "TaskDueDate DATE, ActionPlan STRING",
                                 "Branch visit follow-ups that are not completed (open, in progress, overdue or without a task), oldest due first.",
                                 f"""SELECT BranchName, Coverage, VisitDate, TopicTitle, AssignedOwnerName, FollowUpStatus, TaskDueDate, ActionPlan
FROM {x}.visit_followups WHERE FollowUpRequired AND FollowUpStatus <> 'Completed' ORDER BY TaskDueDate"""),
        "plans_awaiting_approval": ("", "EmployeeName STRING, BranchName STRING, Coverage STRING, GoalMonth DATE, Status STRING, DueDate DATE, "
                                        "MetricFocusAreas STRING, CompetencyFocusAreas STRING",
                                    "Success Plans submitted but not yet approved (status Active, no approval), any month.",
                                    f"""SELECT o.Name, o.BranchName, o.Coverage, CAST(g.GoalMonth AS DATE), g.Status, CAST(g.DueDate AS DATE),
       array_join(from_json(nullif(g.MetricFocusAreas, ''), 'array<string>'), ', '),
       array_join(from_json(nullif(g.CompetencyFocusAreas, ''), 'array<string>'), ', ')
FROM {x}.success_plans g JOIN {x}.team_overview o ON o.UserDWID = g.EmployeeId
WHERE g.Status = 'Active' AND g.ApprovedUtc IS NULL ORDER BY 4, 2, 1"""),
        "team_success_plans": (PLAN_MONTH_PARAM, "EmployeeName STRING, UserTitle STRING, BranchName STRING, Coverage STRING, " + PLAN_COLUMNS,
                               "Every active team member's Success Plan for one month (default: the current plan month), including who has no plan.",
                               f"""SELECT o.Name, o.UserTitle, o.BranchName, o.Coverage,
       coalesce(CAST(g.GoalMonth AS DATE), {plan_month_of(x)}), coalesce(g.Status, 'No plan'),
       CASE WHEN g.EmployeeId IS NULL THEN NULL WHEN g.ApprovedUtc IS NULL THEN 'Not yet approved' ELSE concat('Approved ', date_format(g.ApprovedUtc, 'M/d/yyyy')) END,
       g.LockedUtc IS NOT NULL, g.FocusType, array_join(from_json(nullif(g.MetricFocusAreas, ''), 'array<string>'), ', '),
       array_join(from_json(nullif(g.CompetencyFocusAreas, ''), 'array<string>'), ', '), g.GoalStatement, g.DevelopmentArea, g.ActionPlan,
       g.SuccessMeasures, g.MonthlyKpiGoals, CAST(g.DueDate AS DATE)
FROM {x}.team_overview o
LEFT JOIN {x}.success_plans g ON g.EmployeeId = o.UserDWID AND CAST(date_trunc('MONTH', g.GoalMonth) AS DATE) = {plan_month_of(x)}
WHERE o.EmployeeActive ORDER BY o.BranchName, o.Name"""),
        "coaching_history": ("employee_name STRING COMMENT 'Employee name or part of it (for example Rowan Jessup)'",
                             "CoachingDate DATE, EmployeeName STRING, TriggerType STRING, Topic STRING, KpiFocus STRING, Competency STRING, "
                             "ObservationSummary STRING, CoachingProvided STRING, RootCause STRING, ActionRequired STRING, Status STRING, "
                             "RecordsThisYear INT, KpiRecordsThisYear INT",
                             "Coaching records for one employee, newest first, with what was observed and coached, the root cause, the action plan "
                             "and status, plus how many records (and KPI-triggered records) they have this year.",
                             f"""SELECT CAST(CoachingDate AS DATE), EmployeeName, TriggerType, coalesce(TopicCode, CompetencyCode), KpiFocusCode, CompetencyCode,
       ObservationSummary, CoachingProvided, RootCause, ActionRequired, Status,
       CAST(SUM(IF(year(CoachingDate) = year({as_of}), 1, 0)) OVER () AS INT),
       CAST(SUM(IF(year(CoachingDate) = year({as_of}) AND nullif(KpiFocusCode, '') IS NOT NULL, 1, 0)) OVER () AS INT)
FROM {x}.coaching_records WHERE lower(EmployeeName) LIKE concat('%', lower(trim(employee_name)), '%') ORDER BY 1 DESC"""),
        "employee_kpi_trend": ("employee_name STRING COMMENT 'Employee name or part of it (for example Rowan Jessup)'",
                               "KpiMonth DATE, EmployeeName STRING, BranchName STRING, LPE STRING, LpeGoal STRING, TotalLoans INT, DACC_Loans INT, "
                               "Dlq30To89Day STRING, Dlq30To89DayGoal STRING, FirstLien STRING, OutboundCalls STRING, OutboundCallsGoal STRING, "
                               "OutboundContacts STRING, OutboundContactsGoal STRING",
                               "One employee's monthly KPIs for the last six months up to the latest month with complete KPI data, oldest first, "
                               "values ready to show. Use it for trends and coaching-conversation preparation.",
                               f"""SELECT KpiMonth, EmployeeName, BranchName, {f2('LPE')}, {f2('LpeGoal')}, TotalLoans, DACC_Loans, {pct('Dlq30To89Day')},
       {pct('Dlq30To89DayGoal')}, {pct1('FirstLienPercentage')}, format_number(OutboundCalls, 0), format_number(OutboundCallsGoal, 0),
       format_number(OutboundContacts, 0), format_number(OutboundContactsGoal, 0)
FROM {x}.team_kpi_scorecard
WHERE lower(EmployeeName) LIKE concat('%', lower(trim(employee_name)), '%')
  AND KpiMonth BETWEEN add_months({month_of(x)}, -5) AND {month_of(x)}
ORDER BY KpiMonth""".replace(MONTH_START, "CAST(NULL AS DATE)")),
        "branch_brief": ("branch_name STRING COMMENT 'Branch name (for example Laurel Fork) or branch number'", "Section STRING, Item STRING, Detail STRING",
                         "Everything to know before visiting one branch, in one call: latest-month branch KPIs and rank among the branches in "
                         "scope, each employee's LPE, delinquency, pending acknowledgements, open tasks and Success Plan, Success Plans awaiting "
                         "approval, recent visits and open follow-ups. Returns a Note row when the branch is not in scope.",
                         BRANCH_BRIEF.format(x=x, month=month_of(x).replace(MONTH_START, "CAST(NULL AS DATE)"), match=branch_match)),
    }
    if level == "district":
        team |= {
                "district_comparison": (MONTH_PARAM, "KpiMonth DATE, DistrictNumber INT, DistrictName STRING, DMName STRING, LPE STRING, DACC_Loans INT, "
                                                 "DlqScore STRING, DlqGoalStatus STRING, RoaScore STRING, FirstLien STRING, TotalVolume STRING, "
                                                 "LpeRank INT, DlqScoreRank INT, RoaScoreRank INT, FirstLienRank INT",
                                    "Districts in scope side by side for one month (default: latest month with complete KPI data), values ready to show: "
                                    "LPE, DACC loans, the delinquency score (100 = on goal, higher is better), the ROA score, first lien and volume, "
                                    "with ranks (1 = best).",
                                    f"""SELECT make_date(p.Year, p.Month, 1), p.DistrictNumber, d.DistrictName, d.DMName, {f2('p.DistrictLPE')},
       CAST(p.District_DACC_Loans AS INT), format_number(p.DLQ_30_89_Percentage, 1), IF(p.DLQ_30_89_Percentage >= 100, 'Meets goal', 'Misses goal'),
       format_number(p.ROA_Percentage, 1), {pct1('p.FirstLienPercentage')}, {money('p.TotalVolumeDollars')},
       CAST(rank() OVER (ORDER BY p.DistrictLPE DESC) AS INT), CAST(rank() OVER (ORDER BY p.DLQ_30_89_Percentage DESC) AS INT),
       CAST(rank() OVER (ORDER BY p.ROA_Percentage DESC) AS INT), CAST(rank() OVER (ORDER BY p.FirstLienPercentage DESC) AS INT)
FROM {x}.district_monthly_performance p JOIN {x}.districts d ON CAST(d.DistrictNumber AS INT) = p.DistrictNumber
WHERE make_date(p.Year, p.Month, 1) = {month_of(x)} ORDER BY p.DistrictNumber"""),
        "dm_visit_cadence": ("", "DMName STRING, DistrictName STRING, CompletedVisits INT, ScheduledVisits INT, OverdueVisits INT, DraftVisits INT, "
                                     "VisitsThisMonth INT, LastVisitDate DATE, BranchesNotVisitedIn30Days INT, AsOfDate DATE",
                                 "Branch visit cadence per district manager in scope: completed (submitted) visits, scheduled planned visits, overdue "
                                 "planned visits (planned date on or before the dataset as-of date and not yet done), drafts, visits this month and "
                                 "branches without a visit in 30 days.",
                                 DM_VISIT_CADENCE.format(x=x)),
        }
    return team


def functions_sql():
    q = lambda text: text.replace("'", "''")
    parts = ["-- Trusted functions for the Genie spaces: each answers a common question in one call.",
             "-- They read only their own level's views, so the person's scope applies. Rerunnable."]
    for level in SCHEMAS:
        for name, (params, returns, comment, body) in functions_for(level).items():
            parts.append(f"CREATE OR REPLACE FUNCTION {SCHEMAS[level]}.{name}({params})\nRETURNS TABLE ({returns})\n"
                         f"COMMENT '{q(comment)}'\nRETURN {body};\n")
    return "\n".join(parts)


def views_sql(level):
    schema = SCHEMAS[level]
    who = {"employee": "Account Representatives, Assistant BMs and BM Trainees: own rows only",
           "branch": "Branch Managers and active relief managers: their branches",
           "district": "District Managers / AVPs and above: their districts, regions or all branches"}[level]
    parts = [f"-- {schema}: {who}.\n-- Every view filters on the signed-in user and checks their level.\n",
             f"CREATE SCHEMA IF NOT EXISTS {schema} COMMENT 'Coaching360 data for the {level} agent ({who})';\n"]
    for name, (sql, comment) in views_for(level).items():
        parts.append(f"CREATE OR REPLACE VIEW {schema}.{name}\nCOMMENT '{comment.replace(chr(39), chr(39) * 2)}'\nAS {sql};\n")
    return "\n".join(parts)


def grants_sql():
    lines = ["-- Groups and grants. Create the three account groups first (Settings > Identity and access),",
             "-- add each person to exactly one, then run this file as an admin.",
             f"GRANT USE CATALOG ON CATALOG workspace TO `{GROUPS['employee']}`, `{GROUPS['branch']}`, `{GROUPS['district']}`;"]
    for level, group in GROUPS.items():
        lines.append(f"GRANT USE SCHEMA, SELECT, EXECUTE ON SCHEMA {SCHEMAS[level]} TO `{group}`;")
    lines += ["",
              "-- Nobody reads the raw tables or the security objects directly.",
              f"-- The app's service principal currently has ALL PRIVILEGES on {SRC}; agents must query as the",
              "-- signed-in user (on-behalf-of-user), so remove it after the app is switched over:",
              f"-- REVOKE ALL PRIVILEGES ON SCHEMA {SRC} FROM `9480056c-9708-40af-92da-c35b15cf61fa`;",
              "",
              "-- Read access to the BRD for the shared RAG agent:",
              f"GRANT READ VOLUME ON VOLUME {SRC}.coaching360_docs TO `{GROUPS['employee']}`, `{GROUPS['branch']}`, `{GROUPS['district']}`;"]
    return "\n".join(lines) + "\n"


APP_SP = "9480056c-9708-40af-92da-c35b15cf61fa"


def demo_grants_sql():
    """Grants for the chat demo: the app's service principal runs every query, and the chat sets
    which person it acts as by writing user_map (see coaching360/README.md). No groups needed."""
    sp = f"`{APP_SP}`"
    lines = ["-- Demo grants (no groups): the app's service principal reads the level views and sets the",
             "-- demo persona in user_map. Run once as the owner of the c360_* schemas.",
             f"GRANT USE SCHEMA, SELECT, EXECUTE ON SCHEMA {SCHEMAS['employee']} TO {sp};",
             f"GRANT USE SCHEMA, SELECT, EXECUTE ON SCHEMA {SCHEMAS['branch']} TO {sp};",
             f"GRANT USE SCHEMA, SELECT, EXECUTE ON SCHEMA {SCHEMAS['district']} TO {sp};",
             f"GRANT USE SCHEMA ON SCHEMA {SEC} TO {sp};",
             f"GRANT EXECUTE ON FUNCTION {SEC}.me TO {sp};",
             f"GRANT EXECUTE ON FUNCTION {SEC}.my_level TO {sp};",
             f"GRANT SELECT ON TABLE {SEC}.user_level TO {sp};      -- the chat lists people per level",
             f"GRANT SELECT, MODIFY ON TABLE {SEC}.user_map TO {sp}; -- the chat sets the chosen person",
             "",
             "-- Check (run as yourself): the service principal should appear on each schema.",
             f"SHOW GRANTS {sp} ON SCHEMA {SCHEMAS['employee']};"]
    return "\n".join(lines) + "\n"


def main():
    out = pathlib.Path(__file__).resolve().parent / "sql"
    out.mkdir(exist_ok=True)
    (out / "01_security.sql").write_text(security_sql())
    for i, level in enumerate(("employee", "branch", "district"), start=2):
        (out / f"0{i}_{level}_views.sql").write_text(views_sql(level))
    (out / "05_grants.sql").write_text(grants_sql())
    (out / "05b_demo_grants_app.sql").write_text(demo_grants_sql())
    (out / "01b_materialize_scope.sql").write_text(materialize_scope_sql())
    (out / "01c_scope_once.sql").write_text(scope_sql())
    (out / "01d_prepared.sql").write_text(prepared_sql())
    (out / "06_genie_functions.sql").write_text(functions_sql())
    for f in sorted(out.iterdir()):
        print(f"{f.name:28} {len(re.findall(r'CREATE OR REPLACE VIEW', f.read_text())):3} views  {f.stat().st_size:6} bytes")


if __name__ == "__main__":
    main()
