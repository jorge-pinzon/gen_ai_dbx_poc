-- Coaching360 demo questions (demo_script.html) as plain SQL for the SQL editor.
-- Same numbers as the app, without the sign-in lookup: each person is fixed by id or name.
-- Rowan Jessup 500079, Riley Quimby 500072, Felicia Umberto 500004, Keisha Foxworth 500002.
-- Rates are fractions (0.0409 = 4.09%); data as of 2026-10-20, latest KPI month September 2026.

-- Q1 (Rowan Jessup): Show me my scorecard for September 2026.
SELECT KpiMonth, BranchName, TotalLoans, LPE, LpeGoal, DACC_Loans, DaccLoansGoal, DlqCurrentMonth, DlqCurrentMonthGoal,
       Dlq30To89Day, Dlq30To89DayGoal, FirstLienPercentage, CashAdvance, StateAverageCashAdvance,
       OutboundCalls, OutboundCallsGoal, OutboundContacts, OutboundContactsGoal
FROM workspace.c360_prepared.employee_kpi_scorecard
WHERE EmployeeDWID = 500079 AND KpiMonth = DATE'2026-09-01';

-- Q2 (Rowan Jessup): How does my September LPE compare to my goal and to August?
SELECT max(IF(KpiMonth = DATE'2026-09-01', LPE, NULL)) AS SeptemberLPE, max(LpeGoal) AS LpeGoal,
       max(IF(KpiMonth = DATE'2026-08-01', LPE, NULL)) AS AugustLPE, avg(LPE) AS YearToDateAvgLPE
FROM workspace.c360_prepared.employee_kpi_scorecard
WHERE EmployeeDWID = 500079 AND KpiMonth BETWEEN DATE'2026-01-01' AND DATE'2026-09-01';

-- Q3 (Rowan Jessup): Which of my September metrics met goal and which missed?
SELECT IF(LPE >= LpeGoal, 'Met', 'Missed') AS LPE, IF(DACC_Loans >= DaccLoansGoal, 'Met', 'Missed') AS DACC,
       IF(DlqCurrentMonth <= DlqCurrentMonthGoal, 'Met', 'Missed') AS DlqCurrent, IF(Dlq30To89Day <= Dlq30To89DayGoal, 'Met', 'Missed') AS Dlq30To89,
       IF(CashAdvance >= StateAverageCashAdvance, 'Met', 'Missed') AS CashAdvance, IF(OutboundCalls >= OutboundCallsGoal, 'Met', 'Missed') AS Calls,
       IF(OutboundContacts >= OutboundContactsGoal, 'Met', 'Missed') AS Contacts
FROM workspace.c360_prepared.employee_kpi_scorecard
WHERE EmployeeDWID = 500079 AND KpiMonth = DATE'2026-09-01';

-- Q4 (Riley Quimby): Show me my team's scorecard at Laurel Fork for September.
SELECT EmployeeName, UserTitle, TotalLoans, LPE, DACC_Loans, DlqCurrentMonth, Dlq30To89Day, FirstLienPercentage, OutboundCalls, OutboundContacts
FROM workspace.c360_prepared.employee_kpi_scorecard
WHERE BranchName = 'Laurel Fork' AND KpiMonth = DATE'2026-09-01'
ORDER BY LPE DESC;

-- Q5 (Riley Quimby): Who is the top performer at Laurel Fork, and who needs the most help?
SELECT EmployeeName, LPE, DACC_Loans, Dlq30To89Day, FirstLienPercentage, rank() OVER (ORDER BY LPE DESC) AS LpeRank
FROM workspace.c360_prepared.employee_kpi_scorecard
WHERE BranchName = 'Laurel Fork' AND KpiMonth = DATE'2026-09-01'
ORDER BY LPE DESC;

-- Q6 (Riley Quimby): Which employees are over the 30–89 day delinquency goal?
SELECT EmployeeName, BranchName, Dlq30To89Day, Dlq30To89DayGoal
FROM workspace.c360_prepared.employee_kpi_scorecard
WHERE BranchName IN ('Laurel Fork', 'Shenandoah Mills')   -- Shenandoah Mills: Riley's relief branch
  AND KpiMonth = DATE'2026-09-01' AND Dlq30To89Day > Dlq30To89DayGoal
ORDER BY Dlq30To89Day DESC;

-- Q7 (Rowan Jessup): What's in my Success Plan for October?
SELECT GoalMonth, Status, ApprovedUtc, MetricFocusAreas, CompetencyFocusAreas, GoalStatement, ActionPlan, SuccessMeasures
FROM workspace.coaching360demo.coaching360_app_workflow__dbo_individualdevelopmentgoals
WHERE EmployeeId = 500079 AND date_trunc('MONTH', GoalMonth) = DATE'2026-10-01';

-- Q8 (Rowan Jessup): What did I focus on in September, and did I hit it?
SELECT g.GoalMonth, g.MetricFocusAreas, g.CompetencyFocusAreas, g.ApprovedUtc, g.LockedUtc,
       s.LPE, s.LpeGoal, s.DACC_Loans, s.DaccLoansGoal
FROM workspace.coaching360demo.coaching360_app_workflow__dbo_individualdevelopmentgoals g
JOIN workspace.c360_prepared.employee_kpi_scorecard s ON s.EmployeeDWID = g.EmployeeId AND s.KpiMonth = DATE'2026-09-01'
WHERE g.EmployeeId = 500079 AND date_trunc('MONTH', g.GoalMonth) = DATE'2026-09-01';

-- Q9 (Riley Quimby): Which Success Plans on my team still need my approval?
SELECT o.Name, o.BranchName, g.GoalMonth, g.Status, g.DueDate
FROM workspace.coaching360demo.coaching360_app_workflow__dbo_individualdevelopmentgoals g
JOIN workspace.c360_prepared.employee_overview o ON o.UserDWID = g.EmployeeId
WHERE o.BranchName IN ('Laurel Fork', 'Shenandoah Mills') AND g.EmployeeId <> 500072   -- not Riley's own plan
  AND g.Status = 'Active' AND g.ApprovedUtc IS NULL
ORDER BY g.GoalMonth, o.BranchName, o.Name;

-- Q10 (Riley Quimby): Show me Rowan Jessup's coaching history.
SELECT CoachingDate, TriggerType, coalesce(TopicCode, CompetencyCode) AS Topic, KpiFocusCode, ObservationSummary, Status
FROM workspace.c360_prepared.coaching_records
WHERE EmployeeName = 'Rowan Jessup'
ORDER BY CoachingDate DESC;

-- Q11 (Riley Quimby): What did I coach Rowan on last, and what was the action plan?
SELECT CoachingDate, TriggerType, KpiFocusCode, CoachingProvided, RootCause, ActionRequired
FROM workspace.c360_prepared.coaching_records
WHERE EmployeeName = 'Rowan Jessup'
ORDER BY CoachingDate DESC
LIMIT 1;

-- Q12 (Riley Quimby): Show Rowan's LPE for each month from May to September 2026.
SELECT KpiMonth, LPE
FROM workspace.c360_prepared.employee_kpi_scorecard
WHERE EmployeeDWID = 500079 AND KpiMonth BETWEEN DATE'2026-05-01' AND DATE'2026-09-01'
ORDER BY KpiMonth;

-- Q13 (Riley Quimby): Help me prepare a KPI coaching conversation with Rowan about LPE.
SELECT KpiMonth, LPE, LpeGoal, TotalLoans, DACC_Loans, FirstLienPercentage, Dlq30To89Day
FROM workspace.c360_prepared.employee_kpi_scorecard
WHERE EmployeeDWID = 500079 AND KpiMonth BETWEEN DATE'2026-04-01' AND DATE'2026-09-01'
ORDER BY KpiMonth;

-- Q14 (Riley Quimby): Draft a recognition note for Selena Driscoll on her September results.
SELECT KpiMonth, LPE, DACC_Loans, DlqCurrentMonth, DlqCurrentMonthGoal, Dlq30To89Day, Dlq30To89DayGoal, FirstLienPercentage
FROM workspace.c360_prepared.employee_kpi_scorecard
WHERE EmployeeName = 'Selena Driscoll' AND KpiMonth IN (DATE'2026-08-01', DATE'2026-09-01')
ORDER BY KpiMonth DESC;

-- Q15 (Rowan Jessup): Do I have any coaching records waiting for my acknowledgement?
SELECT CoachingDate, TriggerType, KpiFocusCode, datediff(DATE'2026-10-20', CAST(CoachingDate AS DATE)) AS DaysWaiting
FROM workspace.c360_prepared.coaching_records
WHERE EmployeeId = 500079 AND Status = 'PendingAcknowledgement'
ORDER BY CoachingDate;

-- Q16 (Felicia Umberto): Give me an overview of the branches in my district.
SELECT Branch, BranchName, Direct_Loans_MTD_LPE AS LPE, DLQ3060DayPerc_Actual AS Dlq30To89Day, FirstLienPercentage
FROM workspace.c360_prepared.branch_performance
WHERE DistrictName = 'Shenandoah' AND KpiMonth = DATE'2026-09-01'
ORDER BY Branch;

-- Q17 (Felicia Umberto): Which branches have the most coaching records pending acknowledgement or open tasks?
SELECT BranchName, SUM(PendingAcknowledgements) AS PendingAcknowledgements, SUM(OpenTasks) AS OpenTasks
FROM workspace.c360_prepared.employee_overview
WHERE DistrictName = 'Shenandoah'
GROUP BY BranchName
ORDER BY PendingAcknowledgements DESC, OpenTasks DESC;

-- Q18 (Felicia Umberto): Help me plan my next visit to Laurel Fork. What should I know before I walk in?
SELECT BranchName, Direct_Loans_MTD_LPE AS LPE, DLQ3060DayPerc_Actual AS Dlq30To89Day,
       rank() OVER (ORDER BY Direct_Loans_MTD_LPE DESC) AS LpeRank, rank() OVER (ORDER BY DLQ3060DayPerc_Actual) AS DlqRank
FROM workspace.c360_prepared.branch_performance
WHERE DistrictName = 'Shenandoah' AND KpiMonth = DATE'2026-09-01'
ORDER BY BranchName = 'Laurel Fork' DESC, LpeRank;

-- Q19 (Felicia Umberto): What follow-ups came out of my October 7 visit to Laurel Fork, and are they done?
SELECT VisitDate, TopicTitle, ActionPlan, AssignedOwnerName, TaskDueDate, FollowUpStatus, TaskCompletedDate
FROM workspace.c360_prepared.visit_followups
WHERE BranchName = 'Laurel Fork' AND VisitDate = DATE'2026-10-07' AND FollowUpRequired;

-- Q20 (Keisha Foxworth): How is District 902 doing compared to the other districts in my region?
SELECT d.DistrictName, p.DistrictLPE, p.DLQ_30_89_Percentage AS DlqScore, p.ROA_Percentage AS RoaScore, p.FirstLienPercentage
FROM workspace.coaching360demo.branchkpi_sources__branchkpi_monthly_districtperformance p
JOIN workspace.coaching360demo.org_hierarchy__eda_ref_t_ref_district d ON CAST(d.DistrictNumber AS INT) = p.DistrictNumber
WHERE p.Year = 2026 AND p.Month = 9 AND p.DistrictNumber IN (901, 902, 903)
ORDER BY p.DistrictNumber;

-- Q21 (Keisha Foxworth): Are my district managers keeping up with branch visits?
SELECT d.DMName,
       (SELECT count(*) FROM workspace.coaching360demo.coaching360_app_workflow__dbo_branchvisits v JOIN workspace.coaching360demo.org_hierarchy__eda_ref_t_ref_branch b ON b.BranchDWID = v.OrganizationalUnitId
        WHERE b.DistrictDWID = d.DistrictDWID AND v.VisitStatus = 'Submitted' AND NOT v.IsArchived) AS CompletedVisits,
       (SELECT count_if(CAST(p.VisitDate AS DATE) > DATE'2026-10-20') FROM workspace.coaching360demo.coaching360_app_workflow__dbo_branchvisitplanningplaceholders p JOIN workspace.coaching360demo.org_hierarchy__eda_ref_t_ref_branch b ON b.BranchDWID = p.OrganizationalUnitId
        WHERE b.DistrictDWID = d.DistrictDWID AND p.Status = 'Active') AS ScheduledVisits,
       (SELECT count_if(CAST(p.VisitDate AS DATE) <= DATE'2026-10-20') FROM workspace.coaching360demo.coaching360_app_workflow__dbo_branchvisitplanningplaceholders p JOIN workspace.coaching360demo.org_hierarchy__eda_ref_t_ref_branch b ON b.BranchDWID = p.OrganizationalUnitId
        WHERE b.DistrictDWID = d.DistrictDWID AND p.Status = 'Active') AS OverdueVisits
FROM workspace.coaching360demo.org_hierarchy__eda_ref_t_ref_district d
WHERE CAST(d.DistrictNumber AS INT) IN (901, 902, 903)
ORDER BY d.DMName;
