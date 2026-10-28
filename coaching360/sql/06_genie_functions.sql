-- Trusted functions for the Genie spaces: each answers a common question in one call.
-- They read only their own level's views, so the person's scope applies. Rerunnable.
CREATE OR REPLACE FUNCTION workspace.c360_employee.my_scorecard(month_start STRING COMMENT 'Month to report as YYYY-MM (for example 2026-09) or any date in it; NULL means the latest month in the data')
RETURNS TABLE (KpiMonth DATE, BranchName STRING, Section STRING, Measure STRING, Actual DECIMAL(19,4), Goal DECIMAL(19,4), ActualDisplay STRING, GoalDisplay STRING, GoalType STRING, Status STRING, LastMonthDisplay STRING, LastMonthStatus STRING, YearToDateAverageDisplay STRING)
COMMENT 'My scorecard for one month (default: latest month with complete KPI data): monthly KPIs with goals and status (LPE, DACC loans, both delinquency measures, first lien, cash advance vs state average, calls, contacts), each with last month''s value and the year-to-date monthly average, then the DPR metrics. Report the Display and Status values as given.'
RETURN WITH m AS (SELECT coalesce(CAST(date_trunc('MONTH', try_to_date(CASE WHEN length(month_start) = 7 THEN concat(month_start, '-01') ELSE month_start END)) AS DATE), (SELECT LatestKpiMonth FROM workspace.c360_employee.data_status)) AS KpiMonth),
months AS (
  SELECT s.KpiMonth, s.BranchName, stack(10, 1, 'Loans booked', CAST(TotalLoans AS DECIMAL(19,4)), CAST(NULL AS DECIMAL(19,4)), 'count', CAST(NULL AS BOOLEAN), CAST(NULL AS STRING), 2, 'LPE (loans per employee)', CAST(LPE AS DECIMAL(19,4)), CAST(LpeGoal AS DECIMAL(19,4)), 'decimal', CAST(true AS BOOLEAN), CAST('Goal' AS STRING), 3, 'DACC loans', CAST(DACC_Loans AS DECIMAL(19,4)), CAST(DaccLoansGoal AS DECIMAL(19,4)), 'count', CAST(true AS BOOLEAN), CAST('Goal' AS STRING), 4, 'Delinquency - current month', CAST(DlqCurrentMonth AS DECIMAL(19,4)), CAST(DlqCurrentMonthGoal AS DECIMAL(19,4)), 'fraction', CAST(false AS BOOLEAN), CAST('Goal' AS STRING), 5, 'Delinquency - 30-89 day', CAST(Dlq30To89Day AS DECIMAL(19,4)), CAST(Dlq30To89DayGoal AS DECIMAL(19,4)), 'fraction', CAST(false AS BOOLEAN), CAST('Goal' AS STRING), 6, 'First lien - share of loans', CAST(FirstLienPercentage AS DECIMAL(19,4)), CAST(NULL AS DECIMAL(19,4)), 'percent', CAST(NULL AS BOOLEAN), CAST(NULL AS STRING), 7, 'First lien - share of volume', CAST(FirstLienVolumePercentage AS DECIMAL(19,4)), CAST(NULL AS DECIMAL(19,4)), 'percent', CAST(NULL AS BOOLEAN), CAST(NULL AS STRING), 8, 'Cash advance', CAST(CashAdvance AS DECIMAL(19,4)), CAST(StateAverageCashAdvance AS DECIMAL(19,4)), 'currency', CAST(true AS BOOLEAN), CAST('State average' AS STRING), 9, 'Outbound calls', CAST(OutboundCalls AS DECIMAL(19,4)), CAST(OutboundCallsGoal AS DECIMAL(19,4)), 'count', CAST(true AS BOOLEAN), CAST('Goal' AS STRING), 10, 'Outbound contacts', CAST(OutboundContacts AS DECIMAL(19,4)), CAST(OutboundContactsGoal AS DECIMAL(19,4)), 'count', CAST(true AS BOOLEAN), CAST('Goal' AS STRING)) AS (SortOrder, Measure, Actual, Goal, Unit, HigherIsBetter, GoalType)
  FROM workspace.c360_employee.my_kpi_scorecard s JOIN m
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
         CAST(d.MetricValue AS DECIMAL(19,4)) AS Actual, CAST(NULL AS DECIMAL(19,4)) AS Goal, CASE UnitOfMeasure WHEN 'Ratio' THEN 'fraction' WHEN 'Currency' THEN 'currency' ELSE 'decimal' END AS Unit,
         CAST(NULL AS BOOLEAN) AS HigherIsBetter, CAST(NULL AS STRING) AS GoalType,
         CAST(NULL AS DECIMAL(19,4)) AS LastMonth, CAST(NULL AS DECIMAL(19,4)) AS LastMonthGoal, CAST(NULL AS DECIMAL(19,4)) AS YearToDate
  FROM workspace.c360_employee.my_dpr_scorecard d JOIN m ON d.MetricMonth = m.KpiMonth)
SELECT KpiMonth, BranchName, IF(SortOrder < 100, 'Monthly KPIs', 'DPR metrics') AS Section, Measure, Actual, Goal,
       CASE Unit WHEN 'count' THEN format_number(Actual, 0) WHEN 'decimal' THEN format_number(Actual, 2) WHEN 'fraction' THEN concat(format_number(Actual * 100, 2), '%') WHEN 'percent' THEN concat(format_number(Actual, 1), '%') WHEN 'currency' THEN concat('$', format_number(Actual, 0)) ELSE format_number(Actual, 2) END AS ActualDisplay, CASE Unit WHEN 'count' THEN format_number(Goal, 0) WHEN 'decimal' THEN format_number(Goal, 2) WHEN 'fraction' THEN concat(format_number(Goal * 100, 2), '%') WHEN 'percent' THEN concat(format_number(Goal, 1), '%') WHEN 'currency' THEN concat('$', format_number(Goal, 0)) ELSE format_number(Goal, 2) END AS GoalDisplay, GoalType,
       CASE WHEN Goal IS NULL OR Actual IS NULL THEN NULL WHEN GoalType = 'State average' THEN IF(Actual >= Goal, 'Above state average', 'Below state average') WHEN HigherIsBetter THEN IF(Actual >= Goal, 'Met', 'Below goal') ELSE IF(Actual <= Goal, 'Met', 'Above goal') END AS Status,
       CASE Unit WHEN 'count' THEN format_number(LastMonth, 0) WHEN 'decimal' THEN format_number(LastMonth, 2) WHEN 'fraction' THEN concat(format_number(LastMonth * 100, 2), '%') WHEN 'percent' THEN concat(format_number(LastMonth, 1), '%') WHEN 'currency' THEN concat('$', format_number(LastMonth, 0)) ELSE format_number(LastMonth, 2) END AS LastMonthDisplay, CASE WHEN LastMonthGoal IS NULL OR LastMonth IS NULL THEN NULL WHEN GoalType = 'State average' THEN IF(LastMonth >= LastMonthGoal, 'Above state average', 'Below state average') WHEN HigherIsBetter THEN IF(LastMonth >= LastMonthGoal, 'Met', 'Below goal') ELSE IF(LastMonth <= LastMonthGoal, 'Met', 'Above goal') END AS LastMonthStatus,
       CASE Unit WHEN 'count' THEN format_number(YearToDate, 0) WHEN 'decimal' THEN format_number(YearToDate, 2) WHEN 'fraction' THEN concat(format_number(YearToDate * 100, 2), '%') WHEN 'percent' THEN concat(format_number(YearToDate, 1), '%') WHEN 'currency' THEN concat('$', format_number(YearToDate, 0)) ELSE format_number(YearToDate, 2) END AS YearToDateAverageDisplay
FROM (SELECT * FROM kpi UNION ALL SELECT * FROM dpr)
ORDER BY IF(SortOrder < 100, 0, 1), BranchName, SortOrder, Measure;

CREATE OR REPLACE FUNCTION workspace.c360_employee.my_success_plan(month_start STRING COMMENT 'Plan month as YYYY-MM (for example 2026-10); NULL means the current plan month (the month of the dataset as-of date)')
RETURNS TABLE (GoalMonth DATE, Status STRING, Approval STRING, IsLocked BOOLEAN, FocusType STRING, MetricFocusAreas STRING, CompetencyFocusAreas STRING, GoalStatement STRING, DevelopmentArea STRING, ActionPlan STRING, SuccessMeasures STRING, MonthlyKpiGoals STRING, DueDate DATE)
COMMENT 'My Success Plan for one month (default: the current plan month, the month of the dataset as-of date): status, whether it is approved or locked, metric and competency focus areas, goal statement and action plan.'
RETURN SELECT CAST(GoalMonth AS DATE), Status, IF(ApprovedUtc IS NULL, 'Not yet approved', concat('Approved ', date_format(ApprovedUtc, 'M/d/yyyy'))), LockedUtc IS NOT NULL, FocusType, array_join(from_json(nullif(MetricFocusAreas, ''), 'array<string>'), ', '), array_join(from_json(nullif(CompetencyFocusAreas, ''), 'array<string>'), ', '), GoalStatement, DevelopmentArea, ActionPlan, SuccessMeasures, MonthlyKpiGoals, CAST(DueDate AS DATE) FROM workspace.c360_employee.my_success_plans
WHERE CAST(date_trunc('MONTH', GoalMonth) AS DATE) = coalesce(CAST(date_trunc('MONTH', try_to_date(CASE WHEN length(month_start) = 7 THEN concat(month_start, '-01') ELSE month_start END)) AS DATE), CAST(date_trunc('MONTH', (SELECT AsOfDate FROM workspace.c360_employee.data_status)) AS DATE)) ORDER BY GoalMonth;

CREATE OR REPLACE FUNCTION workspace.c360_employee.my_pending_acknowledgements()
RETURNS TABLE (CoachingDate DATE, TriggerType STRING, Topic STRING, KpiFocus STRING, ObservationSummary STRING, DaysWaiting INT)
COMMENT 'Coaching records about me still waiting for my acknowledgement, oldest first (any month; days counted to the dataset as-of date).'
RETURN SELECT CAST(CoachingDate AS DATE), TriggerType, coalesce(TopicCode, CompetencyCode), KpiFocusCode, ObservationSummary,
       datediff((SELECT AsOfDate FROM workspace.c360_employee.data_status), CAST(CoachingDate AS DATE))
FROM workspace.c360_employee.my_coaching_records WHERE Status = 'PendingAcknowledgement' ORDER BY 1;

CREATE OR REPLACE FUNCTION workspace.c360_employee.my_open_items()
RETURNS TABLE (ItemType STRING, Item STRING, Status STRING, ItemDate DATE, DueDate DATE)
COMMENT 'Everything still open for me: tasks, coaching records waiting for my acknowledgement, open policy violations and my active Success Plan.'
RETURN SELECT 'Task', Subject, Status, CAST(CreatedUtc AS DATE), CAST(DueDate AS DATE) FROM workspace.c360_employee.my_tasks WHERE Status <> 'Completed'
UNION ALL SELECT 'Coaching acknowledgement', coalesce(TopicCode, ObservationSummary), Status, CAST(CoachingDate AS DATE), CAST(DueDate AS DATE)
  FROM workspace.c360_employee.my_coaching_records WHERE Status = 'PendingAcknowledgement'
UNION ALL SELECT 'Policy violation', PolicyName, Status, ViolationDate, CorrectiveActionDueDate
  FROM workspace.c360_employee.my_policy_violations WHERE Status <> 'CorrectiveActionCompleted'
UNION ALL SELECT 'Success Plan', DevelopmentArea, Status, CAST(GoalMonth AS DATE), CAST(DueDate AS DATE) FROM workspace.c360_employee.my_success_plans WHERE Status = 'Active';

CREATE OR REPLACE FUNCTION workspace.c360_branch.team_scorecard(month_start STRING COMMENT 'Month to report as YYYY-MM (for example 2026-09) or any date in it; NULL means the latest month in the data')
RETURNS TABLE (KpiMonth DATE, EmployeeName STRING, UserTitle STRING, BranchName STRING, Coverage STRING, TotalLoans INT, LPE STRING, LpeGoal STRING, LpeStatus STRING, LastMonthLPE STRING, DACC_Loans INT, DaccLoansGoal INT, DaccStatus STRING, DlqCurrentMonth STRING, DlqCurrentMonthGoal STRING, DlqCurrentMonthStatus STRING, Dlq30To89Day STRING, Dlq30To89DayGoal STRING, Dlq30To89DayStatus STRING, LastMonthDlq30To89Day STRING, FirstLien STRING, OutboundCalls STRING, OutboundCallsGoal STRING, CallsStatus STRING, OutboundContacts STRING, OutboundContactsGoal STRING, ContactsStatus STRING, LastMonthDACC_Loans INT, LpeRankInBranch INT, LpeRank INT)
COMMENT 'Monthly scorecard per employee (default: latest month with complete KPI data), values ready to show: LPE, DACC loans, current-month and 30-89 day delinquency, first lien, calls and contacts, each with goal and status, plus last month''s LPE, DACC loans and 30-89 day delinquency, and LPE rank in the branch and across the team (1 = highest). Each branch ends with a ''Branch total'' row (branch LPE, DACC loans, delinquency, first lien; calls and contacts summed). Report values as given.'
RETURN WITH m AS (SELECT coalesce(CAST(date_trunc('MONTH', try_to_date(CASE WHEN length(month_start) = 7 THEN concat(month_start, '-01') ELSE month_start END)) AS DATE), (SELECT LatestKpiMonth FROM workspace.c360_branch.data_status)) AS KpiMonth),
emp AS (
  SELECT t.KpiMonth, t.EmployeeName, t.UserTitle, t.BranchName, t.Coverage, t.TotalLoans,
         format_number(t.LPE, 2) AS LPE, format_number(t.LpeGoal, 2) AS LpeGoal, CASE WHEN t.LpeGoal IS NULL OR t.LPE IS NULL THEN NULL WHEN t.LPE >= t.LpeGoal THEN 'Met' ELSE 'Below goal' END AS LpeStatus, format_number(p.LPE, 2) AS LastMonthLPE,
         t.DACC_Loans, t.DaccLoansGoal, CASE WHEN t.DaccLoansGoal IS NULL OR t.DACC_Loans IS NULL THEN NULL WHEN t.DACC_Loans >= t.DaccLoansGoal THEN 'Met' ELSE 'Below goal' END AS DaccStatus,
         concat(format_number(t.DlqCurrentMonth * 100, 2), '%') AS DlqCurrentMonth, concat(format_number(t.DlqCurrentMonthGoal * 100, 2), '%') AS DlqCurrentMonthGoal,
         CASE WHEN t.DlqCurrentMonthGoal IS NULL OR t.DlqCurrentMonth IS NULL THEN NULL WHEN t.DlqCurrentMonth <= t.DlqCurrentMonthGoal THEN 'Met' ELSE 'Above goal' END AS DlqCurrentMonthStatus,
         concat(format_number(t.Dlq30To89Day * 100, 2), '%') AS Dlq30To89Day, concat(format_number(t.Dlq30To89DayGoal * 100, 2), '%') AS Dlq30To89DayGoal,
         CASE WHEN t.Dlq30To89DayGoal IS NULL OR t.Dlq30To89Day IS NULL THEN NULL WHEN t.Dlq30To89Day <= t.Dlq30To89DayGoal THEN 'Met' ELSE 'Above goal' END AS Dlq30To89DayStatus, concat(format_number(p.Dlq30To89Day * 100, 2), '%') AS LastMonthDlq30To89Day,
         concat(format_number(t.FirstLienPercentage, 1), '%') AS FirstLien, format_number(t.OutboundCalls, 0) AS OutboundCalls,
         format_number(t.OutboundCallsGoal, 0) AS OutboundCallsGoal, CASE WHEN t.OutboundCallsGoal IS NULL OR t.OutboundCalls IS NULL THEN NULL WHEN t.OutboundCalls >= t.OutboundCallsGoal THEN 'Met' ELSE 'Below goal' END AS CallsStatus,
         format_number(t.OutboundContacts, 0) AS OutboundContacts, format_number(t.OutboundContactsGoal, 0) AS OutboundContactsGoal,
         CASE WHEN t.OutboundContactsGoal IS NULL OR t.OutboundContacts IS NULL THEN NULL WHEN t.OutboundContacts >= t.OutboundContactsGoal THEN 'Met' ELSE 'Below goal' END AS ContactsStatus, p.DACC_Loans AS LastMonthDACC_Loans,
         CAST(rank() OVER (PARTITION BY t.BranchName ORDER BY t.LPE DESC) AS INT) AS LpeRankInBranch,
         CAST(rank() OVER (ORDER BY t.LPE DESC) AS INT) AS LpeRank
  FROM workspace.c360_branch.team_kpi_scorecard t JOIN m ON t.KpiMonth = m.KpiMonth
  LEFT JOIN workspace.c360_branch.team_kpi_scorecard p ON p.TellerID = t.TellerID AND p.BranchNumber = t.BranchNumber AND p.KpiMonth = add_months(t.KpiMonth, -1)),
calls AS (
  SELECT BranchNumber, SUM(TotalLoans) AS TotalLoans, SUM(OutboundCalls) AS OutboundCalls, SUM(OutboundCallsGoal) AS OutboundCallsGoal,
         SUM(OutboundContacts) AS OutboundContacts, SUM(OutboundContactsGoal) AS OutboundContactsGoal
  FROM workspace.c360_branch.team_kpi_scorecard t JOIN m ON t.KpiMonth = m.KpiMonth GROUP BY BranchNumber),
total AS (
  -- One "Branch total" row per branch, from the branch scorecard (branch LPE is not an average of employees).
  SELECT b.KpiMonth, 'Branch total' AS EmployeeName, CAST(NULL AS STRING) AS UserTitle, b.BranchName, c.Coverage,
         CAST(k.TotalLoans AS INT), format_number(b.Direct_Loans_MTD_LPE, 2), format_number(1.00, 2), CASE WHEN 1.00 IS NULL OR b.Direct_Loans_MTD_LPE IS NULL THEN NULL WHEN b.Direct_Loans_MTD_LPE >= 1.00 THEN 'Met' ELSE 'Below goal' END, format_number(l.Direct_Loans_MTD_LPE, 2),
         b.Branch_DACC_Loans, CAST(NULL AS INT), CAST(NULL AS STRING),
         concat(format_number(b.DLQCurrentMonthPerc_Actual * 100, 2), '%'), concat(format_number(b.DLQCurrentMonthPerc_Goal * 100, 2), '%'), CASE WHEN b.DLQCurrentMonthPerc_Goal IS NULL OR b.DLQCurrentMonthPerc_Actual IS NULL THEN NULL WHEN b.DLQCurrentMonthPerc_Actual <= b.DLQCurrentMonthPerc_Goal THEN 'Met' ELSE 'Above goal' END,
         concat(format_number(b.DLQ3060DayPerc_Actual * 100, 2), '%'), concat(format_number(b.DLQ3089DayPerc_Goal * 100, 2), '%'), CASE WHEN b.DLQ3089DayPerc_Goal IS NULL OR b.DLQ3060DayPerc_Actual IS NULL THEN NULL WHEN b.DLQ3060DayPerc_Actual <= b.DLQ3089DayPerc_Goal THEN 'Met' ELSE 'Above goal' END, concat(format_number(l.DLQ3060DayPerc_Actual * 100, 2), '%'),
         concat(format_number(b.FirstLienPercentage, 1), '%'), format_number(k.OutboundCalls, 0), format_number(k.OutboundCallsGoal, 0), CASE WHEN k.OutboundCallsGoal IS NULL OR k.OutboundCalls IS NULL THEN NULL WHEN k.OutboundCalls >= k.OutboundCallsGoal THEN 'Met' ELSE 'Below goal' END,
         format_number(k.OutboundContacts, 0), format_number(k.OutboundContactsGoal, 0), CASE WHEN k.OutboundContactsGoal IS NULL OR k.OutboundContacts IS NULL THEN NULL WHEN k.OutboundContacts >= k.OutboundContactsGoal THEN 'Met' ELSE 'Below goal' END,
         l.Branch_DACC_Loans, CAST(NULL AS INT), CAST(NULL AS INT)
  FROM workspace.c360_branch.branch_monthly_performance b JOIN m ON b.KpiMonth = m.KpiMonth
  LEFT JOIN workspace.c360_branch.branch_monthly_performance l ON l.Branch = b.Branch AND l.KpiMonth = add_months(b.KpiMonth, -1)
  LEFT JOIN workspace.c360_branch.branches c ON c.BranchNumber = b.Branch
  LEFT JOIN calls k ON k.BranchNumber = b.Branch)
SELECT * FROM (SELECT * FROM emp UNION ALL SELECT * FROM total)
ORDER BY BranchName, IF(EmployeeName = 'Branch total', 1, 0), LpeRankInBranch;

CREATE OR REPLACE FUNCTION workspace.c360_branch.team_dpr_scorecard(month_start STRING COMMENT 'Month to report as YYYY-MM (for example 2026-09) or any date in it; NULL means the latest month in the data')
RETURNS TABLE (MetricMonth DATE, EmployeeName STRING, KpiName STRING, MetricValue DECIMAL(19,8), UnitOfMeasure STRING, IsHigherBetter BOOLEAN)
COMMENT 'DPR metrics per employee for one month (default: latest month with complete KPI data). Ratios are fractions.'
RETURN SELECT MetricMonth, EmployeeName, KpiName, MetricValue, UnitOfMeasure, IsHigherBetter
FROM workspace.c360_branch.dpr_scorecard WHERE MetricMonth = coalesce(CAST(date_trunc('MONTH', try_to_date(CASE WHEN length(month_start) = 7 THEN concat(month_start, '-01') ELSE month_start END)) AS DATE), (SELECT LatestKpiMonth FROM workspace.c360_branch.data_status)) ORDER BY EmployeeName, KpiName;

CREATE OR REPLACE FUNCTION workspace.c360_branch.team_ranking(month_start STRING COMMENT 'Month to report as YYYY-MM (for example 2026-09) or any date in it; NULL means the latest month in the data')
RETURNS TABLE (KpiMonth DATE, EmployeeName STRING, UserTitle STRING, BranchName STRING, TotalLoans INT, LPE STRING, TotalVolume STRING, DlqCurrentMonth STRING, VolumeRank INT)
COMMENT 'Employees ranked by volume for one month (default: latest month with complete KPI data), values ready to show.'
RETURN SELECT KpiMonth, EmployeeName, UserTitle, BranchName, TotalLoans, format_number(LPE, 2), concat('$', format_number(TotalVolumeDollars, 0)),
       concat(format_number(DLQCurrentMonthPerc_Actual * 100, 2), '%'), CAST(rank() OVER (ORDER BY TotalVolumeDollars DESC) AS INT) AS VolumeRank
FROM workspace.c360_branch.employee_monthly_kpis WHERE KpiMonth = coalesce(CAST(date_trunc('MONTH', try_to_date(CASE WHEN length(month_start) = 7 THEN concat(month_start, '-01') ELSE month_start END)) AS DATE), (SELECT LatestKpiMonth FROM workspace.c360_branch.data_status)) ORDER BY VolumeRank;

CREATE OR REPLACE FUNCTION workspace.c360_branch.branch_scorecard(month_start STRING COMMENT 'Month to report as YYYY-MM (for example 2026-09) or any date in it; NULL means the latest month in the data')
RETURNS TABLE (KpiMonth DATE, DistrictName STRING, BranchNumber INT, BranchName STRING, BMName STRING, LPE STRING, DACC_Loans INT, DlqCurrentMonth STRING, DlqCurrentMonthGoal STRING, Dlq30To89Day STRING, Dlq30To89DayGoal STRING, Dlq30To89DayStatus STRING, FirstLien STRING, ROA STRING, TotalVolume STRING, LpeRank INT, Dlq30To89DayRank INT, FirstLienRank INT, VolumeRank INT)
COMMENT 'Branch scorecard (branch totals) for one month (default: latest month with complete KPI data), values ready to show: branch LPE, DACC loans, current-month and 30-89 day delinquency with goals, first lien, ROA and volume, with ranks among the branches in scope (LpeRank, FirstLienRank, VolumeRank: 1 = highest; Dlq30To89DayRank: 1 = lowest delinquency).'
RETURN SELECT KpiMonth, DistrictName, Branch, BranchName, BMName, format_number(Direct_Loans_MTD_LPE, 2), Branch_DACC_Loans,
       concat(format_number(DLQCurrentMonthPerc_Actual * 100, 2), '%'), concat(format_number(DLQCurrentMonthPerc_Goal * 100, 2), '%'), concat(format_number(DLQ3060DayPerc_Actual * 100, 2), '%'), concat(format_number(DLQ3089DayPerc_Goal * 100, 2), '%'),
       CASE WHEN DLQ3089DayPerc_Goal IS NULL OR DLQ3060DayPerc_Actual IS NULL THEN NULL WHEN DLQ3060DayPerc_Actual <= DLQ3089DayPerc_Goal THEN 'Met' ELSE 'Above goal' END, concat(format_number(FirstLienPercentage, 1), '%'), format_number(Branch_ROA_Percentage, 2),
       concat('$', format_number(TotalVolumeDollars, 0)),
       CAST(rank() OVER (ORDER BY Direct_Loans_MTD_LPE DESC) AS INT), CAST(rank() OVER (ORDER BY DLQ3060DayPerc_Actual ASC) AS INT),
       CAST(rank() OVER (ORDER BY FirstLienPercentage DESC) AS INT), CAST(rank() OVER (ORDER BY TotalVolumeDollars DESC) AS INT)
FROM workspace.c360_branch.branch_monthly_performance WHERE KpiMonth = coalesce(CAST(date_trunc('MONTH', try_to_date(CASE WHEN length(month_start) = 7 THEN concat(month_start, '-01') ELSE month_start END)) AS DATE), (SELECT LatestKpiMonth FROM workspace.c360_branch.data_status)) ORDER BY Branch;

CREATE OR REPLACE FUNCTION workspace.c360_branch.overdue_tasks()
RETURNS TABLE (EmployeeName STRING, BranchName STRING, Subject STRING, DueDate DATE, DaysOverdue INT, Status STRING, Severity STRING, AsOfDate DATE)
COMMENT 'Open tasks past their due date as of the dataset as-of date, per employee, oldest first.'
RETURN SELECT m.Name, m.BranchName, t.Subject, CAST(t.DueDate AS DATE), datediff((SELECT AsOfDate FROM workspace.c360_branch.data_status), CAST(t.DueDate AS DATE)), t.Status, t.Severity, (SELECT AsOfDate FROM workspace.c360_branch.data_status)
FROM workspace.c360_branch.tasks t JOIN workspace.c360_branch.team_members m ON m.UserDWID = t.AssignedToEmployeeId
WHERE t.Status <> 'Completed' AND CAST(t.DueDate AS DATE) < (SELECT AsOfDate FROM workspace.c360_branch.data_status) ORDER BY 5 DESC;

CREATE OR REPLACE FUNCTION workspace.c360_branch.pending_acknowledgements()
RETURNS TABLE (EmployeeName STRING, BranchName STRING, CoachingDate DATE, Topic STRING, DueDate DATE, DaysWaiting INT)
COMMENT 'Coaching records still waiting for the employee''s acknowledgement, oldest first (days counted to the dataset as-of date).'
RETURN SELECT c.EmployeeName, b.BranchName, CAST(c.CoachingDate AS DATE), coalesce(c.TopicCode, c.ObservationSummary), CAST(c.DueDate AS DATE),
       datediff((SELECT AsOfDate FROM workspace.c360_branch.data_status), CAST(c.CoachingDate AS DATE))
FROM workspace.c360_branch.coaching_records c LEFT JOIN workspace.c360_branch.branches b ON b.BranchDWID = c.OrganizationalUnitId
WHERE c.Status = 'PendingAcknowledgement' ORDER BY 6 DESC;

CREATE OR REPLACE FUNCTION workspace.c360_branch.visit_brief(branch_name STRING COMMENT 'Branch name (for example Laurel Fork) or branch number')
RETURNS TABLE (BranchName STRING, Coverage STRING, VisitDate DATE, VisitPurpose STRING, VisitStatus STRING, TopicTitle STRING, DiscussionNotes STRING, ActionPlan STRING, FollowUpRequired BOOLEAN, AssignedOwnerName STRING, FollowUpStatus STRING, TaskCompletedDate DATE, TaskDueDate DATE, ConfidentialLeadershipFeedback STRING, Note STRING)
COMMENT 'Latest branch visit for one branch in my scope: purpose, every topic with discussion and action plan, and the real follow-up status from the task (FollowUpStatus, TaskCompletedDate). Returns a Note row when the branch is not in scope.'
RETURN SELECT BranchName, Coverage, VisitDate, VisitPurpose, VisitStatus, TopicTitle, DiscussionNotes, ActionPlan, FollowUpRequired,
       AssignedOwnerName, FollowUpStatus, TaskCompletedDate, TaskDueDate, ConfidentialLeadershipFeedback, CAST(NULL AS STRING)
FROM workspace.c360_branch.visit_followups
WHERE BranchVisitId = (SELECT max_by(BranchVisitId, VisitDate) FROM workspace.c360_branch.visit_followups WHERE (lower(BranchName) = replace(lower(trim(branch_name)), ' branch', '') OR CAST(BranchNumber AS STRING) = trim(branch_name)))
UNION ALL
SELECT trim(branch_name), NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL,
       IF(EXISTS (SELECT 1 FROM workspace.c360_branch.branches WHERE (lower(BranchName) = replace(lower(trim(branch_name)), ' branch', '') OR CAST(BranchNumber AS STRING) = trim(branch_name))), 'No branch visits are recorded for this branch.',
          'No branch with this name is in your scope.')
WHERE NOT EXISTS (SELECT 1 FROM workspace.c360_branch.visit_followups WHERE (lower(BranchName) = replace(lower(trim(branch_name)), ' branch', '') OR CAST(BranchNumber AS STRING) = trim(branch_name)));

CREATE OR REPLACE FUNCTION workspace.c360_branch.open_visit_followups()
RETURNS TABLE (BranchName STRING, Coverage STRING, VisitDate DATE, TopicTitle STRING, AssignedOwnerName STRING, FollowUpStatus STRING, TaskDueDate DATE, ActionPlan STRING)
COMMENT 'Branch visit follow-ups that are not completed (open, in progress, overdue or without a task), oldest due first.'
RETURN SELECT BranchName, Coverage, VisitDate, TopicTitle, AssignedOwnerName, FollowUpStatus, TaskDueDate, ActionPlan
FROM workspace.c360_branch.visit_followups WHERE FollowUpRequired AND FollowUpStatus <> 'Completed' ORDER BY TaskDueDate;

CREATE OR REPLACE FUNCTION workspace.c360_branch.plans_awaiting_approval()
RETURNS TABLE (EmployeeName STRING, BranchName STRING, Coverage STRING, GoalMonth DATE, Status STRING, DueDate DATE, MetricFocusAreas STRING, CompetencyFocusAreas STRING)
COMMENT 'Success Plans submitted but not yet approved (status Active, no approval), any month.'
RETURN SELECT o.Name, o.BranchName, o.Coverage, CAST(g.GoalMonth AS DATE), g.Status, CAST(g.DueDate AS DATE),
       array_join(from_json(nullif(g.MetricFocusAreas, ''), 'array<string>'), ', '),
       array_join(from_json(nullif(g.CompetencyFocusAreas, ''), 'array<string>'), ', ')
FROM workspace.c360_branch.success_plans g JOIN workspace.c360_branch.team_overview o ON o.UserDWID = g.EmployeeId
WHERE g.Status = 'Active' AND g.ApprovedUtc IS NULL ORDER BY 4, 2, 1;

CREATE OR REPLACE FUNCTION workspace.c360_branch.team_success_plans(month_start STRING COMMENT 'Plan month as YYYY-MM (for example 2026-10); NULL means the current plan month (the month of the dataset as-of date)')
RETURNS TABLE (EmployeeName STRING, UserTitle STRING, BranchName STRING, Coverage STRING, GoalMonth DATE, Status STRING, Approval STRING, IsLocked BOOLEAN, FocusType STRING, MetricFocusAreas STRING, CompetencyFocusAreas STRING, GoalStatement STRING, DevelopmentArea STRING, ActionPlan STRING, SuccessMeasures STRING, MonthlyKpiGoals STRING, DueDate DATE)
COMMENT 'Every active team member''s Success Plan for one month (default: the current plan month), including who has no plan.'
RETURN SELECT o.Name, o.UserTitle, o.BranchName, o.Coverage,
       coalesce(CAST(g.GoalMonth AS DATE), coalesce(CAST(date_trunc('MONTH', try_to_date(CASE WHEN length(month_start) = 7 THEN concat(month_start, '-01') ELSE month_start END)) AS DATE), CAST(date_trunc('MONTH', (SELECT AsOfDate FROM workspace.c360_branch.data_status)) AS DATE))), coalesce(g.Status, 'No plan'),
       CASE WHEN g.EmployeeId IS NULL THEN NULL WHEN g.ApprovedUtc IS NULL THEN 'Not yet approved' ELSE concat('Approved ', date_format(g.ApprovedUtc, 'M/d/yyyy')) END,
       g.LockedUtc IS NOT NULL, g.FocusType, array_join(from_json(nullif(g.MetricFocusAreas, ''), 'array<string>'), ', '),
       array_join(from_json(nullif(g.CompetencyFocusAreas, ''), 'array<string>'), ', '), g.GoalStatement, g.DevelopmentArea, g.ActionPlan,
       g.SuccessMeasures, g.MonthlyKpiGoals, CAST(g.DueDate AS DATE)
FROM workspace.c360_branch.team_overview o
LEFT JOIN workspace.c360_branch.success_plans g ON g.EmployeeId = o.UserDWID AND CAST(date_trunc('MONTH', g.GoalMonth) AS DATE) = coalesce(CAST(date_trunc('MONTH', try_to_date(CASE WHEN length(month_start) = 7 THEN concat(month_start, '-01') ELSE month_start END)) AS DATE), CAST(date_trunc('MONTH', (SELECT AsOfDate FROM workspace.c360_branch.data_status)) AS DATE))
WHERE o.EmployeeActive ORDER BY o.BranchName, o.Name;

CREATE OR REPLACE FUNCTION workspace.c360_branch.coaching_history(employee_name STRING COMMENT 'Employee name or part of it (for example Rowan Jessup)')
RETURNS TABLE (CoachingDate DATE, EmployeeName STRING, TriggerType STRING, Topic STRING, KpiFocus STRING, Competency STRING, ObservationSummary STRING, CoachingProvided STRING, RootCause STRING, ActionRequired STRING, Status STRING, RecordsThisYear INT, KpiRecordsThisYear INT)
COMMENT 'Coaching records for one employee, newest first, with what was observed and coached, the root cause, the action plan and status, plus how many records (and KPI-triggered records) they have this year.'
RETURN SELECT CAST(CoachingDate AS DATE), EmployeeName, TriggerType, coalesce(TopicCode, CompetencyCode), KpiFocusCode, CompetencyCode,
       ObservationSummary, CoachingProvided, RootCause, ActionRequired, Status,
       CAST(SUM(IF(year(CoachingDate) = year((SELECT AsOfDate FROM workspace.c360_branch.data_status)), 1, 0)) OVER () AS INT),
       CAST(SUM(IF(year(CoachingDate) = year((SELECT AsOfDate FROM workspace.c360_branch.data_status)) AND nullif(KpiFocusCode, '') IS NOT NULL, 1, 0)) OVER () AS INT)
FROM workspace.c360_branch.coaching_records WHERE lower(EmployeeName) LIKE concat('%', lower(trim(employee_name)), '%') ORDER BY 1 DESC;

CREATE OR REPLACE FUNCTION workspace.c360_branch.employee_kpi_trend(employee_name STRING COMMENT 'Employee name or part of it (for example Rowan Jessup)')
RETURNS TABLE (KpiMonth DATE, EmployeeName STRING, BranchName STRING, LPE STRING, LpeGoal STRING, TotalLoans INT, DACC_Loans INT, Dlq30To89Day STRING, Dlq30To89DayGoal STRING, FirstLien STRING, OutboundCalls STRING, OutboundCallsGoal STRING, OutboundContacts STRING, OutboundContactsGoal STRING)
COMMENT 'One employee''s monthly KPIs for the last six months up to the latest month with complete KPI data, oldest first, values ready to show. Use it for trends and coaching-conversation preparation.'
RETURN SELECT KpiMonth, EmployeeName, BranchName, format_number(LPE, 2), format_number(LpeGoal, 2), TotalLoans, DACC_Loans, concat(format_number(Dlq30To89Day * 100, 2), '%'),
       concat(format_number(Dlq30To89DayGoal * 100, 2), '%'), concat(format_number(FirstLienPercentage, 1), '%'), format_number(OutboundCalls, 0), format_number(OutboundCallsGoal, 0),
       format_number(OutboundContacts, 0), format_number(OutboundContactsGoal, 0)
FROM workspace.c360_branch.team_kpi_scorecard
WHERE lower(EmployeeName) LIKE concat('%', lower(trim(employee_name)), '%')
  AND KpiMonth BETWEEN add_months(coalesce(CAST(NULL AS DATE), (SELECT LatestKpiMonth FROM workspace.c360_branch.data_status)), -5) AND coalesce(CAST(NULL AS DATE), (SELECT LatestKpiMonth FROM workspace.c360_branch.data_status))
ORDER BY KpiMonth;

CREATE OR REPLACE FUNCTION workspace.c360_branch.branch_brief(branch_name STRING COMMENT 'Branch name (for example Laurel Fork) or branch number')
RETURNS TABLE (Section STRING, Item STRING, Detail STRING)
COMMENT 'Everything to know before visiting one branch, in one call: latest-month branch KPIs and rank among the branches in scope, each employee''s LPE, delinquency, pending acknowledgements, open tasks and Success Plan, Success Plans awaiting approval, recent visits and open follow-ups. Returns a Note row when the branch is not in scope.'
RETURN WITH br AS (SELECT BranchDWID, BranchNumber, BranchName, Coverage FROM workspace.c360_branch.branches WHERE (lower(BranchName) = replace(lower(trim(branch_name)), ' branch', '') OR CAST(BranchNumber AS STRING) = trim(branch_name))),
m AS (SELECT coalesce(CAST(NULL AS DATE), (SELECT LatestKpiMonth FROM workspace.c360_branch.data_status)) AS KpiMonth),
perf AS (
  SELECT p.Branch, p.Direct_Loans_MTD_LPE, p.Branch_DACC_Loans, p.DLQ3060DayPerc_Actual, p.DLQ3089DayPerc_Goal, p.DLQCurrentMonthPerc_Actual,
         p.DLQCurrentMonthPerc_Goal, p.FirstLienPercentage,
         rank() OVER (ORDER BY p.Direct_Loans_MTD_LPE DESC) AS LpeRank, rank() OVER (ORDER BY p.DLQ3060DayPerc_Actual ASC) AS DlqRank,
         count(*) OVER () AS Branches
  FROM workspace.c360_branch.branch_monthly_performance p JOIN m ON p.KpiMonth = m.KpiMonth),
people AS (
  SELECT s.EmployeeName, s.LPE, s.Dlq30To89Day, s.Dlq30To89DayGoal, s.DACC_Loans, o.PendingAcknowledgements, o.OpenTasks, o.OverdueTasks, o.SuccessPlanStatus
  FROM workspace.c360_branch.team_kpi_scorecard s JOIN m ON s.KpiMonth = m.KpiMonth JOIN br ON br.BranchNumber = s.BranchNumber
  LEFT JOIN workspace.c360_branch.team_overview o ON o.UserDWID = s.EmployeeDWID)
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
FROM workspace.c360_branch.team_overview o JOIN br ON br.BranchDWID = o.BranchDWID HAVING COUNT(*) > 0
UNION ALL
SELECT 'Success Plans awaiting approval', o.Name, concat(date_format(g.GoalMonth, 'MMMM yyyy'), coalesce(concat(', due ', date_format(g.DueDate, 'M/d/yyyy')), ''))
FROM workspace.c360_branch.success_plans g JOIN workspace.c360_branch.team_overview o ON o.UserDWID = g.EmployeeId JOIN br ON br.BranchDWID = o.BranchDWID
WHERE g.Status = 'Active' AND g.ApprovedUtc IS NULL
UNION ALL
SELECT 'Recent visits', date_format(v.VisitDate, 'M/d/yyyy'), concat(v.VisitPurpose, ' (', v.VisitStatus, ')')
FROM (SELECT DISTINCT f.BranchVisitId, f.VisitDate, f.VisitPurpose, f.VisitStatus FROM workspace.c360_branch.visit_followups f JOIN br ON br.BranchDWID = f.BranchDWID
      ORDER BY f.VisitDate DESC LIMIT 3) v
UNION ALL
SELECT 'Open visit follow-ups', concat(f.TopicTitle, ' (', date_format(f.VisitDate, 'M/d/yyyy'), ' visit)'),
       concat(f.FollowUpStatus, coalesce(concat(', due ', date_format(f.TaskDueDate, 'M/d/yyyy')), ''), coalesce(concat(', owner ', f.AssignedOwnerName), ''))
FROM workspace.c360_branch.visit_followups f JOIN br ON br.BranchDWID = f.BranchDWID WHERE f.FollowUpRequired AND f.FollowUpStatus <> 'Completed'
UNION ALL
SELECT 'Note', trim(branch_name), 'No branch with this name is in your scope.' WHERE NOT EXISTS (SELECT 1 FROM br);

CREATE OR REPLACE FUNCTION workspace.c360_district.team_scorecard(month_start STRING COMMENT 'Month to report as YYYY-MM (for example 2026-09) or any date in it; NULL means the latest month in the data')
RETURNS TABLE (KpiMonth DATE, EmployeeName STRING, UserTitle STRING, BranchName STRING, Coverage STRING, TotalLoans INT, LPE STRING, LpeGoal STRING, LpeStatus STRING, LastMonthLPE STRING, DACC_Loans INT, DaccLoansGoal INT, DaccStatus STRING, DlqCurrentMonth STRING, DlqCurrentMonthGoal STRING, DlqCurrentMonthStatus STRING, Dlq30To89Day STRING, Dlq30To89DayGoal STRING, Dlq30To89DayStatus STRING, LastMonthDlq30To89Day STRING, FirstLien STRING, OutboundCalls STRING, OutboundCallsGoal STRING, CallsStatus STRING, OutboundContacts STRING, OutboundContactsGoal STRING, ContactsStatus STRING, LastMonthDACC_Loans INT, LpeRankInBranch INT, LpeRank INT)
COMMENT 'Monthly scorecard per employee (default: latest month with complete KPI data), values ready to show: LPE, DACC loans, current-month and 30-89 day delinquency, first lien, calls and contacts, each with goal and status, plus last month''s LPE, DACC loans and 30-89 day delinquency, and LPE rank in the branch and across the team (1 = highest). Each branch ends with a ''Branch total'' row (branch LPE, DACC loans, delinquency, first lien; calls and contacts summed). Report values as given.'
RETURN WITH m AS (SELECT coalesce(CAST(date_trunc('MONTH', try_to_date(CASE WHEN length(month_start) = 7 THEN concat(month_start, '-01') ELSE month_start END)) AS DATE), (SELECT LatestKpiMonth FROM workspace.c360_district.data_status)) AS KpiMonth),
emp AS (
  SELECT t.KpiMonth, t.EmployeeName, t.UserTitle, t.BranchName, t.Coverage, t.TotalLoans,
         format_number(t.LPE, 2) AS LPE, format_number(t.LpeGoal, 2) AS LpeGoal, CASE WHEN t.LpeGoal IS NULL OR t.LPE IS NULL THEN NULL WHEN t.LPE >= t.LpeGoal THEN 'Met' ELSE 'Below goal' END AS LpeStatus, format_number(p.LPE, 2) AS LastMonthLPE,
         t.DACC_Loans, t.DaccLoansGoal, CASE WHEN t.DaccLoansGoal IS NULL OR t.DACC_Loans IS NULL THEN NULL WHEN t.DACC_Loans >= t.DaccLoansGoal THEN 'Met' ELSE 'Below goal' END AS DaccStatus,
         concat(format_number(t.DlqCurrentMonth * 100, 2), '%') AS DlqCurrentMonth, concat(format_number(t.DlqCurrentMonthGoal * 100, 2), '%') AS DlqCurrentMonthGoal,
         CASE WHEN t.DlqCurrentMonthGoal IS NULL OR t.DlqCurrentMonth IS NULL THEN NULL WHEN t.DlqCurrentMonth <= t.DlqCurrentMonthGoal THEN 'Met' ELSE 'Above goal' END AS DlqCurrentMonthStatus,
         concat(format_number(t.Dlq30To89Day * 100, 2), '%') AS Dlq30To89Day, concat(format_number(t.Dlq30To89DayGoal * 100, 2), '%') AS Dlq30To89DayGoal,
         CASE WHEN t.Dlq30To89DayGoal IS NULL OR t.Dlq30To89Day IS NULL THEN NULL WHEN t.Dlq30To89Day <= t.Dlq30To89DayGoal THEN 'Met' ELSE 'Above goal' END AS Dlq30To89DayStatus, concat(format_number(p.Dlq30To89Day * 100, 2), '%') AS LastMonthDlq30To89Day,
         concat(format_number(t.FirstLienPercentage, 1), '%') AS FirstLien, format_number(t.OutboundCalls, 0) AS OutboundCalls,
         format_number(t.OutboundCallsGoal, 0) AS OutboundCallsGoal, CASE WHEN t.OutboundCallsGoal IS NULL OR t.OutboundCalls IS NULL THEN NULL WHEN t.OutboundCalls >= t.OutboundCallsGoal THEN 'Met' ELSE 'Below goal' END AS CallsStatus,
         format_number(t.OutboundContacts, 0) AS OutboundContacts, format_number(t.OutboundContactsGoal, 0) AS OutboundContactsGoal,
         CASE WHEN t.OutboundContactsGoal IS NULL OR t.OutboundContacts IS NULL THEN NULL WHEN t.OutboundContacts >= t.OutboundContactsGoal THEN 'Met' ELSE 'Below goal' END AS ContactsStatus, p.DACC_Loans AS LastMonthDACC_Loans,
         CAST(rank() OVER (PARTITION BY t.BranchName ORDER BY t.LPE DESC) AS INT) AS LpeRankInBranch,
         CAST(rank() OVER (ORDER BY t.LPE DESC) AS INT) AS LpeRank
  FROM workspace.c360_district.team_kpi_scorecard t JOIN m ON t.KpiMonth = m.KpiMonth
  LEFT JOIN workspace.c360_district.team_kpi_scorecard p ON p.TellerID = t.TellerID AND p.BranchNumber = t.BranchNumber AND p.KpiMonth = add_months(t.KpiMonth, -1)),
calls AS (
  SELECT BranchNumber, SUM(TotalLoans) AS TotalLoans, SUM(OutboundCalls) AS OutboundCalls, SUM(OutboundCallsGoal) AS OutboundCallsGoal,
         SUM(OutboundContacts) AS OutboundContacts, SUM(OutboundContactsGoal) AS OutboundContactsGoal
  FROM workspace.c360_district.team_kpi_scorecard t JOIN m ON t.KpiMonth = m.KpiMonth GROUP BY BranchNumber),
total AS (
  -- One "Branch total" row per branch, from the branch scorecard (branch LPE is not an average of employees).
  SELECT b.KpiMonth, 'Branch total' AS EmployeeName, CAST(NULL AS STRING) AS UserTitle, b.BranchName, c.Coverage,
         CAST(k.TotalLoans AS INT), format_number(b.Direct_Loans_MTD_LPE, 2), format_number(1.00, 2), CASE WHEN 1.00 IS NULL OR b.Direct_Loans_MTD_LPE IS NULL THEN NULL WHEN b.Direct_Loans_MTD_LPE >= 1.00 THEN 'Met' ELSE 'Below goal' END, format_number(l.Direct_Loans_MTD_LPE, 2),
         b.Branch_DACC_Loans, CAST(NULL AS INT), CAST(NULL AS STRING),
         concat(format_number(b.DLQCurrentMonthPerc_Actual * 100, 2), '%'), concat(format_number(b.DLQCurrentMonthPerc_Goal * 100, 2), '%'), CASE WHEN b.DLQCurrentMonthPerc_Goal IS NULL OR b.DLQCurrentMonthPerc_Actual IS NULL THEN NULL WHEN b.DLQCurrentMonthPerc_Actual <= b.DLQCurrentMonthPerc_Goal THEN 'Met' ELSE 'Above goal' END,
         concat(format_number(b.DLQ3060DayPerc_Actual * 100, 2), '%'), concat(format_number(b.DLQ3089DayPerc_Goal * 100, 2), '%'), CASE WHEN b.DLQ3089DayPerc_Goal IS NULL OR b.DLQ3060DayPerc_Actual IS NULL THEN NULL WHEN b.DLQ3060DayPerc_Actual <= b.DLQ3089DayPerc_Goal THEN 'Met' ELSE 'Above goal' END, concat(format_number(l.DLQ3060DayPerc_Actual * 100, 2), '%'),
         concat(format_number(b.FirstLienPercentage, 1), '%'), format_number(k.OutboundCalls, 0), format_number(k.OutboundCallsGoal, 0), CASE WHEN k.OutboundCallsGoal IS NULL OR k.OutboundCalls IS NULL THEN NULL WHEN k.OutboundCalls >= k.OutboundCallsGoal THEN 'Met' ELSE 'Below goal' END,
         format_number(k.OutboundContacts, 0), format_number(k.OutboundContactsGoal, 0), CASE WHEN k.OutboundContactsGoal IS NULL OR k.OutboundContacts IS NULL THEN NULL WHEN k.OutboundContacts >= k.OutboundContactsGoal THEN 'Met' ELSE 'Below goal' END,
         l.Branch_DACC_Loans, CAST(NULL AS INT), CAST(NULL AS INT)
  FROM workspace.c360_district.branch_monthly_performance b JOIN m ON b.KpiMonth = m.KpiMonth
  LEFT JOIN workspace.c360_district.branch_monthly_performance l ON l.Branch = b.Branch AND l.KpiMonth = add_months(b.KpiMonth, -1)
  LEFT JOIN workspace.c360_district.branches c ON c.BranchNumber = b.Branch
  LEFT JOIN calls k ON k.BranchNumber = b.Branch)
SELECT * FROM (SELECT * FROM emp UNION ALL SELECT * FROM total)
ORDER BY BranchName, IF(EmployeeName = 'Branch total', 1, 0), LpeRankInBranch;

CREATE OR REPLACE FUNCTION workspace.c360_district.team_dpr_scorecard(month_start STRING COMMENT 'Month to report as YYYY-MM (for example 2026-09) or any date in it; NULL means the latest month in the data')
RETURNS TABLE (MetricMonth DATE, EmployeeName STRING, KpiName STRING, MetricValue DECIMAL(19,8), UnitOfMeasure STRING, IsHigherBetter BOOLEAN)
COMMENT 'DPR metrics per employee for one month (default: latest month with complete KPI data). Ratios are fractions.'
RETURN SELECT MetricMonth, EmployeeName, KpiName, MetricValue, UnitOfMeasure, IsHigherBetter
FROM workspace.c360_district.dpr_scorecard WHERE MetricMonth = coalesce(CAST(date_trunc('MONTH', try_to_date(CASE WHEN length(month_start) = 7 THEN concat(month_start, '-01') ELSE month_start END)) AS DATE), (SELECT LatestKpiMonth FROM workspace.c360_district.data_status)) ORDER BY EmployeeName, KpiName;

CREATE OR REPLACE FUNCTION workspace.c360_district.team_ranking(month_start STRING COMMENT 'Month to report as YYYY-MM (for example 2026-09) or any date in it; NULL means the latest month in the data')
RETURNS TABLE (KpiMonth DATE, EmployeeName STRING, UserTitle STRING, BranchName STRING, TotalLoans INT, LPE STRING, TotalVolume STRING, DlqCurrentMonth STRING, VolumeRank INT)
COMMENT 'Employees ranked by volume for one month (default: latest month with complete KPI data), values ready to show.'
RETURN SELECT KpiMonth, EmployeeName, UserTitle, BranchName, TotalLoans, format_number(LPE, 2), concat('$', format_number(TotalVolumeDollars, 0)),
       concat(format_number(DLQCurrentMonthPerc_Actual * 100, 2), '%'), CAST(rank() OVER (ORDER BY TotalVolumeDollars DESC) AS INT) AS VolumeRank
FROM workspace.c360_district.employee_monthly_kpis WHERE KpiMonth = coalesce(CAST(date_trunc('MONTH', try_to_date(CASE WHEN length(month_start) = 7 THEN concat(month_start, '-01') ELSE month_start END)) AS DATE), (SELECT LatestKpiMonth FROM workspace.c360_district.data_status)) ORDER BY VolumeRank;

CREATE OR REPLACE FUNCTION workspace.c360_district.branch_scorecard(month_start STRING COMMENT 'Month to report as YYYY-MM (for example 2026-09) or any date in it; NULL means the latest month in the data')
RETURNS TABLE (KpiMonth DATE, DistrictName STRING, BranchNumber INT, BranchName STRING, BMName STRING, LPE STRING, DACC_Loans INT, DlqCurrentMonth STRING, DlqCurrentMonthGoal STRING, Dlq30To89Day STRING, Dlq30To89DayGoal STRING, Dlq30To89DayStatus STRING, FirstLien STRING, ROA STRING, TotalVolume STRING, LpeRank INT, Dlq30To89DayRank INT, FirstLienRank INT, VolumeRank INT)
COMMENT 'Branch scorecard (branch totals) for one month (default: latest month with complete KPI data), values ready to show: branch LPE, DACC loans, current-month and 30-89 day delinquency with goals, first lien, ROA and volume, with ranks among the branches in scope (LpeRank, FirstLienRank, VolumeRank: 1 = highest; Dlq30To89DayRank: 1 = lowest delinquency).'
RETURN SELECT KpiMonth, DistrictName, Branch, BranchName, BMName, format_number(Direct_Loans_MTD_LPE, 2), Branch_DACC_Loans,
       concat(format_number(DLQCurrentMonthPerc_Actual * 100, 2), '%'), concat(format_number(DLQCurrentMonthPerc_Goal * 100, 2), '%'), concat(format_number(DLQ3060DayPerc_Actual * 100, 2), '%'), concat(format_number(DLQ3089DayPerc_Goal * 100, 2), '%'),
       CASE WHEN DLQ3089DayPerc_Goal IS NULL OR DLQ3060DayPerc_Actual IS NULL THEN NULL WHEN DLQ3060DayPerc_Actual <= DLQ3089DayPerc_Goal THEN 'Met' ELSE 'Above goal' END, concat(format_number(FirstLienPercentage, 1), '%'), format_number(Branch_ROA_Percentage, 2),
       concat('$', format_number(TotalVolumeDollars, 0)),
       CAST(rank() OVER (ORDER BY Direct_Loans_MTD_LPE DESC) AS INT), CAST(rank() OVER (ORDER BY DLQ3060DayPerc_Actual ASC) AS INT),
       CAST(rank() OVER (ORDER BY FirstLienPercentage DESC) AS INT), CAST(rank() OVER (ORDER BY TotalVolumeDollars DESC) AS INT)
FROM workspace.c360_district.branch_monthly_performance WHERE KpiMonth = coalesce(CAST(date_trunc('MONTH', try_to_date(CASE WHEN length(month_start) = 7 THEN concat(month_start, '-01') ELSE month_start END)) AS DATE), (SELECT LatestKpiMonth FROM workspace.c360_district.data_status)) ORDER BY Branch;

CREATE OR REPLACE FUNCTION workspace.c360_district.overdue_tasks()
RETURNS TABLE (EmployeeName STRING, BranchName STRING, Subject STRING, DueDate DATE, DaysOverdue INT, Status STRING, Severity STRING, AsOfDate DATE)
COMMENT 'Open tasks past their due date as of the dataset as-of date, per employee, oldest first.'
RETURN SELECT m.Name, m.BranchName, t.Subject, CAST(t.DueDate AS DATE), datediff((SELECT AsOfDate FROM workspace.c360_district.data_status), CAST(t.DueDate AS DATE)), t.Status, t.Severity, (SELECT AsOfDate FROM workspace.c360_district.data_status)
FROM workspace.c360_district.tasks t JOIN workspace.c360_district.team_members m ON m.UserDWID = t.AssignedToEmployeeId
WHERE t.Status <> 'Completed' AND CAST(t.DueDate AS DATE) < (SELECT AsOfDate FROM workspace.c360_district.data_status) ORDER BY 5 DESC;

CREATE OR REPLACE FUNCTION workspace.c360_district.pending_acknowledgements()
RETURNS TABLE (EmployeeName STRING, BranchName STRING, CoachingDate DATE, Topic STRING, DueDate DATE, DaysWaiting INT)
COMMENT 'Coaching records still waiting for the employee''s acknowledgement, oldest first (days counted to the dataset as-of date).'
RETURN SELECT c.EmployeeName, b.BranchName, CAST(c.CoachingDate AS DATE), coalesce(c.TopicCode, c.ObservationSummary), CAST(c.DueDate AS DATE),
       datediff((SELECT AsOfDate FROM workspace.c360_district.data_status), CAST(c.CoachingDate AS DATE))
FROM workspace.c360_district.coaching_records c LEFT JOIN workspace.c360_district.branches b ON b.BranchDWID = c.OrganizationalUnitId
WHERE c.Status = 'PendingAcknowledgement' ORDER BY 6 DESC;

CREATE OR REPLACE FUNCTION workspace.c360_district.visit_brief(branch_name STRING COMMENT 'Branch name (for example Laurel Fork) or branch number')
RETURNS TABLE (BranchName STRING, Coverage STRING, VisitDate DATE, VisitPurpose STRING, VisitStatus STRING, TopicTitle STRING, DiscussionNotes STRING, ActionPlan STRING, FollowUpRequired BOOLEAN, AssignedOwnerName STRING, FollowUpStatus STRING, TaskCompletedDate DATE, TaskDueDate DATE, ConfidentialLeadershipFeedback STRING, Note STRING)
COMMENT 'Latest branch visit for one branch in my scope: purpose, every topic with discussion and action plan, and the real follow-up status from the task (FollowUpStatus, TaskCompletedDate). Returns a Note row when the branch is not in scope.'
RETURN SELECT BranchName, Coverage, VisitDate, VisitPurpose, VisitStatus, TopicTitle, DiscussionNotes, ActionPlan, FollowUpRequired,
       AssignedOwnerName, FollowUpStatus, TaskCompletedDate, TaskDueDate, ConfidentialLeadershipFeedback, CAST(NULL AS STRING)
FROM workspace.c360_district.visit_followups
WHERE BranchVisitId = (SELECT max_by(BranchVisitId, VisitDate) FROM workspace.c360_district.visit_followups WHERE (lower(BranchName) = replace(lower(trim(branch_name)), ' branch', '') OR CAST(BranchNumber AS STRING) = trim(branch_name)))
UNION ALL
SELECT trim(branch_name), NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL,
       IF(EXISTS (SELECT 1 FROM workspace.c360_district.branches WHERE (lower(BranchName) = replace(lower(trim(branch_name)), ' branch', '') OR CAST(BranchNumber AS STRING) = trim(branch_name))), 'No branch visits are recorded for this branch.',
          'No branch with this name is in your scope.')
WHERE NOT EXISTS (SELECT 1 FROM workspace.c360_district.visit_followups WHERE (lower(BranchName) = replace(lower(trim(branch_name)), ' branch', '') OR CAST(BranchNumber AS STRING) = trim(branch_name)));

CREATE OR REPLACE FUNCTION workspace.c360_district.open_visit_followups()
RETURNS TABLE (BranchName STRING, Coverage STRING, VisitDate DATE, TopicTitle STRING, AssignedOwnerName STRING, FollowUpStatus STRING, TaskDueDate DATE, ActionPlan STRING)
COMMENT 'Branch visit follow-ups that are not completed (open, in progress, overdue or without a task), oldest due first.'
RETURN SELECT BranchName, Coverage, VisitDate, TopicTitle, AssignedOwnerName, FollowUpStatus, TaskDueDate, ActionPlan
FROM workspace.c360_district.visit_followups WHERE FollowUpRequired AND FollowUpStatus <> 'Completed' ORDER BY TaskDueDate;

CREATE OR REPLACE FUNCTION workspace.c360_district.plans_awaiting_approval()
RETURNS TABLE (EmployeeName STRING, BranchName STRING, Coverage STRING, GoalMonth DATE, Status STRING, DueDate DATE, MetricFocusAreas STRING, CompetencyFocusAreas STRING)
COMMENT 'Success Plans submitted but not yet approved (status Active, no approval), any month.'
RETURN SELECT o.Name, o.BranchName, o.Coverage, CAST(g.GoalMonth AS DATE), g.Status, CAST(g.DueDate AS DATE),
       array_join(from_json(nullif(g.MetricFocusAreas, ''), 'array<string>'), ', '),
       array_join(from_json(nullif(g.CompetencyFocusAreas, ''), 'array<string>'), ', ')
FROM workspace.c360_district.success_plans g JOIN workspace.c360_district.team_overview o ON o.UserDWID = g.EmployeeId
WHERE g.Status = 'Active' AND g.ApprovedUtc IS NULL ORDER BY 4, 2, 1;

CREATE OR REPLACE FUNCTION workspace.c360_district.team_success_plans(month_start STRING COMMENT 'Plan month as YYYY-MM (for example 2026-10); NULL means the current plan month (the month of the dataset as-of date)')
RETURNS TABLE (EmployeeName STRING, UserTitle STRING, BranchName STRING, Coverage STRING, GoalMonth DATE, Status STRING, Approval STRING, IsLocked BOOLEAN, FocusType STRING, MetricFocusAreas STRING, CompetencyFocusAreas STRING, GoalStatement STRING, DevelopmentArea STRING, ActionPlan STRING, SuccessMeasures STRING, MonthlyKpiGoals STRING, DueDate DATE)
COMMENT 'Every active team member''s Success Plan for one month (default: the current plan month), including who has no plan.'
RETURN SELECT o.Name, o.UserTitle, o.BranchName, o.Coverage,
       coalesce(CAST(g.GoalMonth AS DATE), coalesce(CAST(date_trunc('MONTH', try_to_date(CASE WHEN length(month_start) = 7 THEN concat(month_start, '-01') ELSE month_start END)) AS DATE), CAST(date_trunc('MONTH', (SELECT AsOfDate FROM workspace.c360_district.data_status)) AS DATE))), coalesce(g.Status, 'No plan'),
       CASE WHEN g.EmployeeId IS NULL THEN NULL WHEN g.ApprovedUtc IS NULL THEN 'Not yet approved' ELSE concat('Approved ', date_format(g.ApprovedUtc, 'M/d/yyyy')) END,
       g.LockedUtc IS NOT NULL, g.FocusType, array_join(from_json(nullif(g.MetricFocusAreas, ''), 'array<string>'), ', '),
       array_join(from_json(nullif(g.CompetencyFocusAreas, ''), 'array<string>'), ', '), g.GoalStatement, g.DevelopmentArea, g.ActionPlan,
       g.SuccessMeasures, g.MonthlyKpiGoals, CAST(g.DueDate AS DATE)
FROM workspace.c360_district.team_overview o
LEFT JOIN workspace.c360_district.success_plans g ON g.EmployeeId = o.UserDWID AND CAST(date_trunc('MONTH', g.GoalMonth) AS DATE) = coalesce(CAST(date_trunc('MONTH', try_to_date(CASE WHEN length(month_start) = 7 THEN concat(month_start, '-01') ELSE month_start END)) AS DATE), CAST(date_trunc('MONTH', (SELECT AsOfDate FROM workspace.c360_district.data_status)) AS DATE))
WHERE o.EmployeeActive ORDER BY o.BranchName, o.Name;

CREATE OR REPLACE FUNCTION workspace.c360_district.coaching_history(employee_name STRING COMMENT 'Employee name or part of it (for example Rowan Jessup)')
RETURNS TABLE (CoachingDate DATE, EmployeeName STRING, TriggerType STRING, Topic STRING, KpiFocus STRING, Competency STRING, ObservationSummary STRING, CoachingProvided STRING, RootCause STRING, ActionRequired STRING, Status STRING, RecordsThisYear INT, KpiRecordsThisYear INT)
COMMENT 'Coaching records for one employee, newest first, with what was observed and coached, the root cause, the action plan and status, plus how many records (and KPI-triggered records) they have this year.'
RETURN SELECT CAST(CoachingDate AS DATE), EmployeeName, TriggerType, coalesce(TopicCode, CompetencyCode), KpiFocusCode, CompetencyCode,
       ObservationSummary, CoachingProvided, RootCause, ActionRequired, Status,
       CAST(SUM(IF(year(CoachingDate) = year((SELECT AsOfDate FROM workspace.c360_district.data_status)), 1, 0)) OVER () AS INT),
       CAST(SUM(IF(year(CoachingDate) = year((SELECT AsOfDate FROM workspace.c360_district.data_status)) AND nullif(KpiFocusCode, '') IS NOT NULL, 1, 0)) OVER () AS INT)
FROM workspace.c360_district.coaching_records WHERE lower(EmployeeName) LIKE concat('%', lower(trim(employee_name)), '%') ORDER BY 1 DESC;

CREATE OR REPLACE FUNCTION workspace.c360_district.employee_kpi_trend(employee_name STRING COMMENT 'Employee name or part of it (for example Rowan Jessup)')
RETURNS TABLE (KpiMonth DATE, EmployeeName STRING, BranchName STRING, LPE STRING, LpeGoal STRING, TotalLoans INT, DACC_Loans INT, Dlq30To89Day STRING, Dlq30To89DayGoal STRING, FirstLien STRING, OutboundCalls STRING, OutboundCallsGoal STRING, OutboundContacts STRING, OutboundContactsGoal STRING)
COMMENT 'One employee''s monthly KPIs for the last six months up to the latest month with complete KPI data, oldest first, values ready to show. Use it for trends and coaching-conversation preparation.'
RETURN SELECT KpiMonth, EmployeeName, BranchName, format_number(LPE, 2), format_number(LpeGoal, 2), TotalLoans, DACC_Loans, concat(format_number(Dlq30To89Day * 100, 2), '%'),
       concat(format_number(Dlq30To89DayGoal * 100, 2), '%'), concat(format_number(FirstLienPercentage, 1), '%'), format_number(OutboundCalls, 0), format_number(OutboundCallsGoal, 0),
       format_number(OutboundContacts, 0), format_number(OutboundContactsGoal, 0)
FROM workspace.c360_district.team_kpi_scorecard
WHERE lower(EmployeeName) LIKE concat('%', lower(trim(employee_name)), '%')
  AND KpiMonth BETWEEN add_months(coalesce(CAST(NULL AS DATE), (SELECT LatestKpiMonth FROM workspace.c360_district.data_status)), -5) AND coalesce(CAST(NULL AS DATE), (SELECT LatestKpiMonth FROM workspace.c360_district.data_status))
ORDER BY KpiMonth;

CREATE OR REPLACE FUNCTION workspace.c360_district.branch_brief(branch_name STRING COMMENT 'Branch name (for example Laurel Fork) or branch number')
RETURNS TABLE (Section STRING, Item STRING, Detail STRING)
COMMENT 'Everything to know before visiting one branch, in one call: latest-month branch KPIs and rank among the branches in scope, each employee''s LPE, delinquency, pending acknowledgements, open tasks and Success Plan, Success Plans awaiting approval, recent visits and open follow-ups. Returns a Note row when the branch is not in scope.'
RETURN WITH br AS (SELECT BranchDWID, BranchNumber, BranchName, Coverage FROM workspace.c360_district.branches WHERE (lower(BranchName) = replace(lower(trim(branch_name)), ' branch', '') OR CAST(BranchNumber AS STRING) = trim(branch_name))),
m AS (SELECT coalesce(CAST(NULL AS DATE), (SELECT LatestKpiMonth FROM workspace.c360_district.data_status)) AS KpiMonth),
perf AS (
  SELECT p.Branch, p.Direct_Loans_MTD_LPE, p.Branch_DACC_Loans, p.DLQ3060DayPerc_Actual, p.DLQ3089DayPerc_Goal, p.DLQCurrentMonthPerc_Actual,
         p.DLQCurrentMonthPerc_Goal, p.FirstLienPercentage,
         rank() OVER (ORDER BY p.Direct_Loans_MTD_LPE DESC) AS LpeRank, rank() OVER (ORDER BY p.DLQ3060DayPerc_Actual ASC) AS DlqRank,
         count(*) OVER () AS Branches
  FROM workspace.c360_district.branch_monthly_performance p JOIN m ON p.KpiMonth = m.KpiMonth),
people AS (
  SELECT s.EmployeeName, s.LPE, s.Dlq30To89Day, s.Dlq30To89DayGoal, s.DACC_Loans, o.PendingAcknowledgements, o.OpenTasks, o.OverdueTasks, o.SuccessPlanStatus
  FROM workspace.c360_district.team_kpi_scorecard s JOIN m ON s.KpiMonth = m.KpiMonth JOIN br ON br.BranchNumber = s.BranchNumber
  LEFT JOIN workspace.c360_district.team_overview o ON o.UserDWID = s.EmployeeDWID)
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
FROM workspace.c360_district.team_overview o JOIN br ON br.BranchDWID = o.BranchDWID HAVING COUNT(*) > 0
UNION ALL
SELECT 'Success Plans awaiting approval', o.Name, concat(date_format(g.GoalMonth, 'MMMM yyyy'), coalesce(concat(', due ', date_format(g.DueDate, 'M/d/yyyy')), ''))
FROM workspace.c360_district.success_plans g JOIN workspace.c360_district.team_overview o ON o.UserDWID = g.EmployeeId JOIN br ON br.BranchDWID = o.BranchDWID
WHERE g.Status = 'Active' AND g.ApprovedUtc IS NULL
UNION ALL
SELECT 'Recent visits', date_format(v.VisitDate, 'M/d/yyyy'), concat(v.VisitPurpose, ' (', v.VisitStatus, ')')
FROM (SELECT DISTINCT f.BranchVisitId, f.VisitDate, f.VisitPurpose, f.VisitStatus FROM workspace.c360_district.visit_followups f JOIN br ON br.BranchDWID = f.BranchDWID
      ORDER BY f.VisitDate DESC LIMIT 3) v
UNION ALL
SELECT 'Open visit follow-ups', concat(f.TopicTitle, ' (', date_format(f.VisitDate, 'M/d/yyyy'), ' visit)'),
       concat(f.FollowUpStatus, coalesce(concat(', due ', date_format(f.TaskDueDate, 'M/d/yyyy')), ''), coalesce(concat(', owner ', f.AssignedOwnerName), ''))
FROM workspace.c360_district.visit_followups f JOIN br ON br.BranchDWID = f.BranchDWID WHERE f.FollowUpRequired AND f.FollowUpStatus <> 'Completed'
UNION ALL
SELECT 'Note', trim(branch_name), 'No branch with this name is in your scope.' WHERE NOT EXISTS (SELECT 1 FROM br);

CREATE OR REPLACE FUNCTION workspace.c360_district.district_comparison(month_start STRING COMMENT 'Month to report as YYYY-MM (for example 2026-09) or any date in it; NULL means the latest month in the data')
RETURNS TABLE (KpiMonth DATE, DistrictNumber INT, DistrictName STRING, DMName STRING, LPE STRING, DACC_Loans INT, DlqScore STRING, DlqGoalStatus STRING, RoaScore STRING, FirstLien STRING, TotalVolume STRING, LpeRank INT, DlqScoreRank INT, RoaScoreRank INT, FirstLienRank INT)
COMMENT 'Districts in scope side by side for one month (default: latest month with complete KPI data), values ready to show: LPE, DACC loans, the delinquency score (100 = on goal, higher is better), the ROA score, first lien and volume, with ranks (1 = best).'
RETURN SELECT make_date(p.Year, p.Month, 1), p.DistrictNumber, d.DistrictName, d.DMName, format_number(p.DistrictLPE, 2),
       CAST(p.District_DACC_Loans AS INT), format_number(p.DLQ_30_89_Percentage, 1), IF(p.DLQ_30_89_Percentage >= 100, 'Meets goal', 'Misses goal'),
       format_number(p.ROA_Percentage, 1), concat(format_number(p.FirstLienPercentage, 1), '%'), concat('$', format_number(p.TotalVolumeDollars, 0)),
       CAST(rank() OVER (ORDER BY p.DistrictLPE DESC) AS INT), CAST(rank() OVER (ORDER BY p.DLQ_30_89_Percentage DESC) AS INT),
       CAST(rank() OVER (ORDER BY p.ROA_Percentage DESC) AS INT), CAST(rank() OVER (ORDER BY p.FirstLienPercentage DESC) AS INT)
FROM workspace.c360_district.district_monthly_performance p JOIN workspace.c360_district.districts d ON CAST(d.DistrictNumber AS INT) = p.DistrictNumber
WHERE make_date(p.Year, p.Month, 1) = coalesce(CAST(date_trunc('MONTH', try_to_date(CASE WHEN length(month_start) = 7 THEN concat(month_start, '-01') ELSE month_start END)) AS DATE), (SELECT LatestKpiMonth FROM workspace.c360_district.data_status)) ORDER BY p.DistrictNumber;

CREATE OR REPLACE FUNCTION workspace.c360_district.dm_visit_cadence()
RETURNS TABLE (DMName STRING, DistrictName STRING, CompletedVisits INT, ScheduledVisits INT, OverdueVisits INT, DraftVisits INT, VisitsThisMonth INT, LastVisitDate DATE, BranchesNotVisitedIn30Days INT, AsOfDate DATE)
COMMENT 'Branch visit cadence per district manager in scope: completed (submitted) visits, scheduled planned visits, overdue planned visits (planned date on or before the dataset as-of date and not yet done), drafts, visits this month and branches without a visit in 30 days.'
RETURN WITH a AS (SELECT AsOfDate FROM workspace.c360_district.data_status),
visits AS (
  SELECT b.DistrictDWID,
         count_if(v.VisitStatus = 'Submitted' AND NOT v.IsArchived) AS Completed, count_if(v.VisitStatus = 'Draft') AS Drafts,
         count_if(CAST(v.VisitDate AS DATE) >= date_trunc('MONTH', a.AsOfDate)) AS ThisMonth,
         max(IF(v.VisitStatus = 'Submitted' AND NOT v.IsArchived, CAST(v.VisitDate AS DATE), NULL)) AS LastVisit
  FROM workspace.c360_district.branch_visits v JOIN workspace.c360_district.branches b ON b.BranchDWID = v.OrganizationalUnitId CROSS JOIN a GROUP BY b.DistrictDWID),
plans AS (
  SELECT b.DistrictDWID, count_if(p.Status = 'Active' AND CAST(p.VisitDate AS DATE) > a.AsOfDate) AS Scheduled,
         count_if(p.Status = 'Active' AND CAST(p.VisitDate AS DATE) <= a.AsOfDate) AS Overdue
  FROM workspace.c360_district.branch_visit_plans p JOIN workspace.c360_district.branches b ON b.BranchDWID = p.OrganizationalUnitId CROSS JOIN a GROUP BY b.DistrictDWID),
stale AS (
  SELECT b.DistrictDWID, count_if(l.LastVisit IS NULL OR l.LastVisit < date_sub(a.AsOfDate, 30)) AS Stale
  FROM workspace.c360_district.branches b CROSS JOIN a
  LEFT JOIN (SELECT OrganizationalUnitId, max(CAST(VisitDate AS DATE)) AS LastVisit FROM workspace.c360_district.branch_visits
             WHERE VisitStatus = 'Submitted' AND NOT IsArchived GROUP BY OrganizationalUnitId) l ON l.OrganizationalUnitId = b.BranchDWID
  GROUP BY b.DistrictDWID)
SELECT d.DMName, d.DistrictName, CAST(coalesce(v.Completed, 0) AS INT), CAST(coalesce(p.Scheduled, 0) AS INT), CAST(coalesce(p.Overdue, 0) AS INT),
       CAST(coalesce(v.Drafts, 0) AS INT), CAST(coalesce(v.ThisMonth, 0) AS INT), v.LastVisit, CAST(coalesce(s.Stale, 0) AS INT), (SELECT AsOfDate FROM a)
FROM workspace.c360_district.districts d LEFT JOIN visits v ON v.DistrictDWID = d.DistrictDWID LEFT JOIN plans p ON p.DistrictDWID = d.DistrictDWID
LEFT JOIN stale s ON s.DistrictDWID = d.DistrictDWID ORDER BY d.DistrictName;
