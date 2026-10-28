-- workspace.c360_prepared: daily pre-joined copies of the busiest Coaching360 sources (the data loads monthly).
-- Rerunnable. Users never read these directly; the level views filter them to the person's scope.
CREATE SCHEMA IF NOT EXISTS workspace.c360_prepared COMMENT 'Coaching360 pre-joined sources for the level views';

CREATE OR REPLACE MATERIALIZED VIEW workspace.c360_prepared.data_status
  SCHEDULE EVERY 1 DAY
  COMMENT 'Latest month with complete KPI data and the dataset as-of date used for overdue'
AS SELECT (SELECT max(make_date(Year, Month, 1)) FROM workspace.coaching360demo.branchkpi_sources__branchkpi_monthly_employeeperformance) AS LatestKpiMonth, (SELECT to_date(max(SourceFreshnessUtc)) FROM workspace.coaching360demo.coaching360_app_dpr__dbo_dpremployeescorecardmetrics) AS AsOfDate;

CREATE OR REPLACE MATERIALIZED VIEW workspace.c360_prepared.kpi_goals
  SCHEDULE EVERY 1 DAY
  COMMENT 'Where each scorecard goal comes from (fixed values or source column)'
AS SELECT * FROM VALUES
  ('LPE', 'Loans per employee', CAST(1.00 AS DECIMAL(19,4)), true, 'Fixed goal'),
  ('DACC loans', 'DACC loans per month', CAST(2 AS DECIMAL(19,4)), true, 'Fixed goal'),
  ('Delinquency - current month', 'Current-month delinquency rate', NULL, false, 'Goal from the KPI row (DLQCurrentMonthPerc_Goal)'),
  ('Delinquency - 30-89 day', '30-89 day delinquency rate', NULL, false, 'Goal from the KPI row (DLQ3089DayPerc_Goal)'),
  ('Outbound calls', 'Outbound calls per month', NULL, true, 'Goal from EmployeeGoals, GoalID 1'),
  ('Outbound contacts', 'Outbound contacts per month', NULL, true, 'Goal from EmployeeGoals, GoalID 2')
  AS goals(Measure, Description, Goal, IsHigherBetter, GoalSource);

CREATE OR REPLACE MATERIALIZED VIEW workspace.c360_prepared.employee_kpis
  SCHEDULE EVERY 1 DAY
  COMMENT 'Monthly employee production and delinquency with employee and branch names'
AS SELECT e.*, make_date(e.Year, e.Month, 1) AS KpiMonth, u.UserDWID AS EmployeeDWID,
       u.Name AS EmployeeName, u.UserTitle, b.BranchName
FROM workspace.coaching360demo.branchkpi_sources__branchkpi_monthly_employeeperformance e
LEFT JOIN workspace.coaching360demo.org_hierarchy__eda_ref_t_ref_user u ON CAST(u.TellerID AS BIGINT) = e.TellerID
LEFT JOIN workspace.coaching360demo.org_hierarchy__eda_ref_t_ref_branch b ON b.BranchNumber = e.Branch;

CREATE OR REPLACE MATERIALIZED VIEW workspace.c360_prepared.dpr_metrics
  SCHEDULE EVERY 1 DAY
  COMMENT 'DPR scorecard metrics with KPI definitions, employee directory id and name'
AS SELECT m.*, CAST(date_trunc('MONTH', m.MetricMonthEndDate) AS DATE) AS MetricMonth,
       k.KpiCode, k.KpiName, k.UnitOfMeasure, k.IsHigherBetter, u.UserDWID AS EmployeeDWID, u.Name AS EmployeeName
FROM workspace.coaching360demo.coaching360_app_dpr__dbo_dpremployeescorecardmetrics m
LEFT JOIN workspace.coaching360demo.coaching360_app_reference__dbo_kpidefinitions k ON k.KpiDefinitionId = m.KpiDefinitionId
LEFT JOIN workspace.coaching360demo.org_hierarchy__eda_ref_t_ref_user u ON u.TellerID = m.SourceTellerId;

CREATE OR REPLACE MATERIALIZED VIEW workspace.c360_prepared.coaching_records
  SCHEDULE EVERY 1 DAY
  COMMENT 'Coaching records with employee names'
AS SELECT c.*, u.Name AS EmployeeName
FROM workspace.coaching360demo.coaching360_app_workflow__dbo_coachingrecords c LEFT JOIN workspace.coaching360demo.org_hierarchy__eda_ref_t_ref_user u ON u.UserDWID = c.EmployeeId;

CREATE OR REPLACE MATERIALIZED VIEW workspace.c360_prepared.employee_kpi_scorecard
  SCHEDULE EVERY 1 DAY
  COMMENT 'Monthly KPI scorecard per employee: LPE, DACC loans, both delinquency measures, first lien, cash advance vs state average, calls and contacts, each with its goal. Dlq30To89Day is the 30-89 day rate (source column DLQ3060DayPerc_Actual).'
AS WITH calls AS (
  SELECT TellerID, CAST(date_trunc('MONTH', call_date) AS DATE) AS KpiMonth,
         SUM(OutboundCalls) AS OutboundCalls, SUM(OutboundContacts) AS OutboundContacts
  FROM workspace.coaching360demo.branchkpi_sources__reports_kpidashboard_calldata GROUP BY TellerID, CAST(date_trunc('MONTH', call_date) AS DATE)),
goals AS (
  SELECT TellerID, MAX(CASE WHEN GoalID = 1 THEN TargetValue END) AS OutboundCallsGoal,
         MAX(CASE WHEN GoalID = 2 THEN TargetValue END) AS OutboundContactsGoal
  FROM workspace.coaching360demo.branchkpi_sources__reports_kpidashboard_employeegoals GROUP BY TellerID)
SELECT u.UserDWID AS EmployeeDWID, u.Name AS EmployeeName, u.UserTitle, e.TellerID, e.Branch AS BranchNumber,
       b.BranchDWID, b.BranchName, make_date(e.Year, e.Month, 1) AS KpiMonth,
       e.TotalLoans, e.LPE, CAST(1.00 AS DECIMAL(19,4)) AS LpeGoal,
       e.DACC_Loans, CAST(2 AS INT) AS DaccLoansGoal,
       e.DLQCurrentMonthPerc_Actual AS DlqCurrentMonth, e.DLQCurrentMonthPerc_Goal AS DlqCurrentMonthGoal,
       e.DLQ3060DayPerc_Actual AS Dlq30To89Day, e.DLQ3089DayPerc_Goal AS Dlq30To89DayGoal,
       e.FirstLienPercentage, e.FirstLienVolumePercentage, e.FirstLienVolumeDollars,
       e.Employee_Cash_Advance AS CashAdvance, e.Average_State_Cash_Advance AS StateAverageCashAdvance,
       e.TotalVolumeDollars, c.OutboundCalls, g.OutboundCallsGoal, c.OutboundContacts, g.OutboundContactsGoal
FROM workspace.coaching360demo.branchkpi_sources__branchkpi_monthly_employeeperformance e
LEFT JOIN workspace.coaching360demo.org_hierarchy__eda_ref_t_ref_user u ON CAST(u.TellerID AS BIGINT) = e.TellerID
LEFT JOIN workspace.coaching360demo.org_hierarchy__eda_ref_t_ref_branch b ON b.BranchNumber = e.Branch
LEFT JOIN calls c ON c.TellerID = e.TellerID AND c.KpiMonth = make_date(e.Year, e.Month, 1)
LEFT JOIN goals g ON g.TellerID = e.TellerID;

CREATE OR REPLACE MATERIALIZED VIEW workspace.c360_prepared.visit_followups
  SCHEDULE EVERY 1 DAY
  COMMENT 'Branch visit topics with branch name and the follow-up task''s status and completion date (FollowUpStatus; overdue as of AsOfDate)'
AS SELECT v.BranchVisitId, v.OrganizationalUnitId AS BranchDWID, b.BranchNumber, b.BranchName,
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
FROM workspace.coaching360demo.coaching360_app_workflow__dbo_branchvisits v
JOIN workspace.coaching360demo.coaching360_app_workflow__dbo_branchvisittopics p ON p.BranchVisitId = v.BranchVisitId
LEFT JOIN workspace.coaching360demo.org_hierarchy__eda_ref_t_ref_branch b ON b.BranchDWID = v.OrganizationalUnitId
LEFT JOIN workspace.coaching360demo.coaching360_app_workflow__dbo_coachingtasks k ON k.ParentType = 'BranchVisit' AND k.ParentId = v.BranchVisitId
  AND k.Subject = concat('Branch visit action item: ', p.TopicTitle)
CROSS JOIN (SELECT (SELECT to_date(max(SourceFreshnessUtc)) FROM workspace.coaching360demo.coaching360_app_dpr__dbo_dpremployeescorecardmetrics) AS AsOfDate) a;

CREATE OR REPLACE MATERIALIZED VIEW workspace.c360_prepared.branch_performance
  SCHEDULE EVERY 1 DAY
  COMMENT 'Branch monthly scorecard inputs with branch, manager and district names'
AS SELECT p.*, make_date(p.Year, p.Month, 1) AS KpiMonth, b.BranchName, b.BMName, d.DistrictName
FROM workspace.coaching360demo.branchkpi_sources__branchkpi_monthly_branchperformance p
LEFT JOIN workspace.coaching360demo.org_hierarchy__eda_ref_t_ref_branch b ON b.BranchNumber = p.Branch
LEFT JOIN workspace.coaching360demo.org_hierarchy__eda_ref_t_ref_district d ON d.DistrictDWID = b.DistrictDWID;

CREATE OR REPLACE MATERIALIZED VIEW workspace.c360_prepared.employee_overview
  SCHEDULE EVERY 1 DAY
  COMMENT 'One row per employee: latest-month KPIs and rank in branch, open and overdue tasks, coaching, Success Plan and open violations (counts as of AsOfDate)'
AS WITH latest AS (SELECT (SELECT max(make_date(Year, Month, 1)) FROM workspace.coaching360demo.branchkpi_sources__branchkpi_monthly_employeeperformance) AS month),
as_of AS (SELECT (SELECT to_date(max(SourceFreshnessUtc)) FROM workspace.coaching360demo.coaching360_app_dpr__dbo_dpremployeescorecardmetrics) AS AsOfDate),
kpi AS (
  SELECT e.TellerID, SUM(e.TotalLoans) AS TotalLoans, AVG(e.LPE) AS LPE, SUM(e.TotalVolumeDollars) AS TotalVolumeDollars
  FROM workspace.coaching360demo.branchkpi_sources__branchkpi_monthly_employeeperformance e JOIN latest ON make_date(e.Year, e.Month, 1) = latest.month GROUP BY e.TellerID),
tasks AS (
  SELECT AssignedToEmployeeId AS id, count_if(Status <> 'Completed') AS OpenTasks,
         count_if(Status <> 'Completed' AND CAST(DueDate AS DATE) < (SELECT AsOfDate FROM as_of)) AS OverdueTasks
  FROM workspace.coaching360demo.coaching360_app_workflow__dbo_coachingtasks GROUP BY AssignedToEmployeeId),
coaching AS (
  SELECT EmployeeId AS id, MAX(CoachingDate) AS LastCoachingDate,
         count_if(CAST(CoachingDate AS DATE) > date_sub((SELECT AsOfDate FROM as_of), 90)) AS CoachingRecordsLast90Days,
         count_if(Status = 'PendingAcknowledgement') AS PendingAcknowledgements
  FROM workspace.coaching360demo.coaching360_app_workflow__dbo_coachingrecords GROUP BY EmployeeId),
plans AS (
  SELECT EmployeeId AS id, MAX(GoalMonth) AS SuccessPlanMonth, max_by(Status, GoalMonth) AS SuccessPlanStatus
  FROM workspace.coaching360demo.coaching360_app_workflow__dbo_individualdevelopmentgoals WHERE NOT IsArchived GROUP BY EmployeeId),
violations AS (
  SELECT EmployeeId AS employee_number, count_if(Status <> 'CorrectiveActionCompleted') AS OpenPolicyViolations
  FROM workspace.coaching360demo.policy_violations__policyviolations_app_violations GROUP BY EmployeeId)
SELECT u.UserDWID, u.Name, u.UserTitle, u.EmployeeActive, u.SeniorityDate, u.BranchDWID,
       b.BranchNumber, b.BranchName, d.DistrictName,
       latest.month AS LatestKpiMonth, kpi.TotalLoans, kpi.LPE, kpi.TotalVolumeDollars,
       CASE WHEN kpi.TellerID IS NOT NULL THEN rank() OVER (PARTITION BY b.BranchNumber, kpi.TellerID IS NULL ORDER BY kpi.TotalVolumeDollars DESC) END AS VolumeRankInBranch,
       coalesce(tasks.OpenTasks, 0) AS OpenTasks, coalesce(tasks.OverdueTasks, 0) AS OverdueTasks,
       coaching.LastCoachingDate, coalesce(coaching.CoachingRecordsLast90Days, 0) AS CoachingRecordsLast90Days,
       coalesce(coaching.PendingAcknowledgements, 0) AS PendingAcknowledgements,
       plans.SuccessPlanMonth, plans.SuccessPlanStatus, coalesce(violations.OpenPolicyViolations, 0) AS OpenPolicyViolations,
       (SELECT AsOfDate FROM as_of) AS AsOfDate
FROM workspace.coaching360demo.org_hierarchy__eda_ref_t_ref_user u
JOIN workspace.coaching360demo.org_hierarchy__eda_ref_t_ref_branch b ON b.BranchDWID = u.BranchDWID
LEFT JOIN workspace.coaching360demo.org_hierarchy__eda_ref_t_ref_district d ON d.DistrictDWID = b.DistrictDWID
CROSS JOIN latest
LEFT JOIN kpi ON kpi.TellerID = CAST(u.TellerID AS BIGINT)
LEFT JOIN tasks ON tasks.id = u.UserDWID
LEFT JOIN coaching ON coaching.id = u.UserDWID
LEFT JOIN plans ON plans.id = u.UserDWID
LEFT JOIN violations ON violations.employee_number = u.EmployeeNumber;

-- To pick up new source data right away:
-- REFRESH MATERIALIZED VIEW workspace.c360_prepared.data_status;
-- REFRESH MATERIALIZED VIEW workspace.c360_prepared.kpi_goals;
-- REFRESH MATERIALIZED VIEW workspace.c360_prepared.employee_kpis;
-- REFRESH MATERIALIZED VIEW workspace.c360_prepared.dpr_metrics;
-- REFRESH MATERIALIZED VIEW workspace.c360_prepared.coaching_records;
-- REFRESH MATERIALIZED VIEW workspace.c360_prepared.employee_kpi_scorecard;
-- REFRESH MATERIALIZED VIEW workspace.c360_prepared.visit_followups;
-- REFRESH MATERIALIZED VIEW workspace.c360_prepared.branch_performance;
-- REFRESH MATERIALIZED VIEW workspace.c360_prepared.employee_overview;
