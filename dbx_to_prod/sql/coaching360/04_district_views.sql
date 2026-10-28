-- workspace.c360_district: District Managers / AVPs and above: their districts, regions or all branches.
-- Every view filters on the signed-in user and checks their level.

CREATE SCHEMA IF NOT EXISTS workspace.c360_district COMMENT 'Coaching360 data for the district agent (District Managers / AVPs and above: their districts, regions or all branches)';

CREATE OR REPLACE VIEW workspace.c360_district.branches
COMMENT 'Branches I can see, with district, region and Coverage (own branch, relief coverage until a date, or in scope).'
AS SELECT o.*, d.DistrictNumber, d.DistrictName, d.DMName, r.RegionNumber, r.RegionName, c.Coverage FROM workspace.coaching360demo.org_hierarchy__eda_ref_t_ref_branch o JOIN workspace.coaching360demo.org_hierarchy__eda_ref_t_ref_district d ON d.DistrictDWID = o.DistrictDWID JOIN workspace.coaching360demo.org_hierarchy__eda_ref_t_ref_region r ON r.RegionDWID = d.RegionDWID JOIN workspace.c360_security.my_coverage c ON c.branch_dwid = o.BranchDWID AND c.level = 'district';

CREATE OR REPLACE VIEW workspace.c360_district.team_members
COMMENT 'Employees assigned to those branches.'
AS SELECT u.*, b.BranchNumber, b.BranchName FROM workspace.coaching360demo.org_hierarchy__eda_ref_t_ref_user u JOIN workspace.coaching360demo.org_hierarchy__eda_ref_t_ref_branch b ON b.BranchDWID = u.BranchDWID WHERE u.BranchDWID IN (SELECT branch_dwid FROM workspace.c360_security.my_branches WHERE level = 'district');

CREATE OR REPLACE VIEW workspace.c360_district.team_overview
COMMENT 'One row per employee: name, title, branch, latest-month KPIs and rank in branch, open and overdue tasks, coaching in the last 90 days, pending acknowledgements, Success Plan status and open violations. Start here for team questions.'
AS SELECT o.*, c.Coverage FROM workspace.c360_prepared.employee_overview o JOIN workspace.c360_security.my_coverage c ON c.branch_dwid = o.BranchDWID AND c.level = 'district';

CREATE OR REPLACE VIEW workspace.c360_district.team_kpi_scorecard
COMMENT 'Monthly scorecard per employee: LPE, DACC loans, both delinquency measures, first lien, cash advance vs state average, calls and contacts, each with its goal, and the branch Coverage.'
AS SELECT o.*, c.Coverage FROM workspace.c360_prepared.employee_kpi_scorecard o JOIN workspace.c360_security.my_coverage c ON c.branch_dwid = o.BranchDWID AND c.level = 'district';

CREATE OR REPLACE VIEW workspace.c360_district.employee_monthly_kpis
COMMENT 'Monthly production and delinquency per employee, with EmployeeName, UserTitle, BranchName and KpiMonth.'
AS SELECT * FROM workspace.c360_prepared.employee_kpis WHERE Branch IN (SELECT branch_number FROM workspace.c360_security.my_branches WHERE level = 'district');

CREATE OR REPLACE VIEW workspace.c360_district.dpr_scorecard
COMMENT 'Published DPR scorecard metrics for the team, with EmployeeName, KpiName and MetricMonth.'
AS SELECT * FROM workspace.c360_prepared.dpr_metrics WHERE EmployeeDWID IN (SELECT member_dwid FROM workspace.c360_security.my_team WHERE level = 'district');

CREATE OR REPLACE VIEW workspace.c360_district.call_activity
COMMENT 'Daily outbound calls for the team.'
AS SELECT * FROM workspace.coaching360demo.branchkpi_sources__reports_kpidashboard_calldata WHERE TellerID IN (SELECT member_teller FROM workspace.c360_security.my_team WHERE level = 'district');

CREATE OR REPLACE VIEW workspace.c360_district.call_goals
COMMENT 'Outbound call and contact targets for the team.'
AS SELECT * FROM workspace.coaching360demo.branchkpi_sources__reports_kpidashboard_employeegoals WHERE TellerID IN (SELECT member_teller FROM workspace.c360_security.my_team WHERE level = 'district');

CREATE OR REPLACE VIEW workspace.c360_district.branch_monthly_performance
COMMENT 'Branch / BM monthly scorecard inputs, with BranchName, BMName, DistrictName and KpiMonth.'
AS SELECT * FROM workspace.c360_prepared.branch_performance WHERE Branch IN (SELECT branch_number FROM workspace.c360_security.my_branches WHERE level = 'district');

CREATE OR REPLACE VIEW workspace.c360_district.branch_turnover
COMMENT 'Branch YTD turnover (retired from the BM scorecard).'
AS SELECT * FROM workspace.coaching360demo.branchkpi_sources__branchkpi_monthly_branchturnovergoal WHERE BranchNumber IN (SELECT branch_number FROM workspace.c360_security.my_branches WHERE level = 'district');

CREATE OR REPLACE VIEW workspace.c360_district.review_comment_approvals
COMMENT 'Branch months excluded from rolling averages.'
AS SELECT * FROM workspace.coaching360demo.branchkpi_sources__branchkpi_dbo_reviewcommentapproval WHERE Branch IN (SELECT branch_number FROM workspace.c360_security.my_branches WHERE level = 'district');

CREATE OR REPLACE VIEW workspace.c360_district.kpi_review_exclusions
COMMENT 'Employee months excluded from KPI review averages.'
AS SELECT * FROM workspace.coaching360demo.coaching360_app_workflow__dbo_kpireviewmonthexclusions WHERE BranchNumber IN (SELECT branch_number FROM workspace.c360_security.my_branches WHERE level = 'district');

CREATE OR REPLACE VIEW workspace.c360_district.coaching_records
COMMENT 'All coaching records at those branches.'
AS SELECT * FROM workspace.c360_prepared.coaching_records WHERE OrganizationalUnitId IN (SELECT branch_dwid FROM workspace.c360_security.my_branches WHERE level = 'district');

CREATE OR REPLACE VIEW workspace.c360_district.coaching_comments
COMMENT 'Comments on those coaching records, including internal manager notes.'
AS SELECT i.* FROM workspace.coaching360demo.coaching360_app_workflow__dbo_coachinginteractions i JOIN workspace.coaching360demo.coaching360_app_workflow__dbo_coachingrecords c ON c.CoachingRecordId = i.CoachingRecordId WHERE c.OrganizationalUnitId IN (SELECT branch_dwid FROM workspace.c360_security.my_branches WHERE level = 'district');

CREATE OR REPLACE VIEW workspace.c360_district.coaching_acknowledgements
COMMENT 'Employee acknowledgements of those coaching records.'
AS SELECT a.* FROM workspace.coaching360demo.coaching360_app_workflow__dbo_coachingrecordacknowledgements a JOIN workspace.coaching360demo.coaching360_app_workflow__dbo_coachingrecords c ON c.CoachingRecordId = a.CoachingRecordId WHERE c.OrganizationalUnitId IN (SELECT branch_dwid FROM workspace.c360_security.my_branches WHERE level = 'district');

CREATE OR REPLACE VIEW workspace.c360_district.success_plans
COMMENT 'Monthly Success Plans (IDPs) for the team.'
AS SELECT * FROM workspace.coaching360demo.coaching360_app_workflow__dbo_individualdevelopmentgoals WHERE EmployeeId IN (SELECT member_dwid FROM workspace.c360_security.my_team WHERE level = 'district') AND NOT IsArchived;

CREATE OR REPLACE VIEW workspace.c360_district.success_plan_comments
COMMENT 'Comments on the team''s Success Plans.'
AS SELECT c.* FROM workspace.coaching360demo.coaching360_app_workflow__dbo_individualdevelopmentgoalcomments c JOIN workspace.coaching360demo.coaching360_app_workflow__dbo_individualdevelopmentgoals g ON g.IndividualDevelopmentGoalId = c.IndividualDevelopmentGoalId WHERE g.EmployeeId IN (SELECT member_dwid FROM workspace.c360_security.my_team WHERE level = 'district') AND NOT g.IsArchived;

CREATE OR REPLACE VIEW workspace.c360_district.tasks
COMMENT 'Tasks assigned to the team (and to me).'
AS SELECT * FROM workspace.coaching360demo.coaching360_app_workflow__dbo_coachingtasks WHERE AssignedToEmployeeId IN (SELECT member_dwid FROM workspace.c360_security.my_team WHERE level = 'district') OR AssignedToEmployeeId = (SELECT user_dwid FROM workspace.c360_security.my_person WHERE level = 'district');

CREATE OR REPLACE VIEW workspace.c360_district.branch_visits
COMMENT 'Branch visit reports, including confidential leadership feedback.'
AS SELECT * FROM workspace.coaching360demo.coaching360_app_workflow__dbo_branchvisits WHERE OrganizationalUnitId IN (SELECT branch_dwid FROM workspace.c360_security.my_branches WHERE level = 'district');

CREATE OR REPLACE VIEW workspace.c360_district.visit_followups
COMMENT 'Branch visits by topic with BranchName, discussion, action plan and the follow-up task''s real status (FollowUpStatus, TaskStatus, TaskCompletedDate). Use this for visit briefs and follow-up status.'
AS SELECT o.*, c.Coverage FROM workspace.c360_prepared.visit_followups o JOIN workspace.c360_security.my_coverage c ON c.branch_dwid = o.BranchDWID AND c.level = 'district';

CREATE OR REPLACE VIEW workspace.c360_district.branch_visit_topics
COMMENT 'Discussion topics and follow-ups from those visits.'
AS SELECT p.* FROM workspace.coaching360demo.coaching360_app_workflow__dbo_branchvisittopics p JOIN workspace.coaching360demo.coaching360_app_workflow__dbo_branchvisits v ON v.BranchVisitId = p.BranchVisitId WHERE v.OrganizationalUnitId IN (SELECT branch_dwid FROM workspace.c360_security.my_branches WHERE level = 'district');

CREATE OR REPLACE VIEW workspace.c360_district.branch_visit_plans
COMMENT 'Planned branch visits.'
AS SELECT * FROM workspace.coaching360demo.coaching360_app_workflow__dbo_branchvisitplanningplaceholders WHERE OrganizationalUnitId IN (SELECT branch_dwid FROM workspace.c360_security.my_branches WHERE level = 'district');

CREATE OR REPLACE VIEW workspace.c360_district.ace_payouts
COMMENT 'ACE incentive payout estimates for employees and BMs at those branches.'
AS SELECT * FROM workspace.coaching360demo.crm_ace_payout__crm_ace_usp_getbmemployeemonthlypayoutestimate WHERE Branch IN (SELECT branch_number FROM workspace.c360_security.my_branches WHERE level = 'district');

CREATE OR REPLACE VIEW workspace.c360_district.policy_violations
COMMENT 'Policy violations at those branches (account numbers masked).'
AS SELECT * EXCEPT (PayloadJson, ManagementChainJson, AccountNumber, AccountId), concat('****', right(AccountNumber, 4)) AS AccountNumberLast4 FROM workspace.coaching360demo.policy_violations__policyviolations_app_violations WHERE BranchNumber IN (SELECT branch_number FROM workspace.c360_security.my_branches WHERE level = 'district');

CREATE OR REPLACE VIEW workspace.c360_district.accountability_meetings
COMMENT 'Branch meetings and district (DM with BMs) meetings in scope.'
AS SELECT * FROM workspace.coaching360demo.coaching360_app_workflow__dbo_accountabilitymeetings WHERE OrganizationalUnitId IN (SELECT branch_dwid FROM workspace.c360_security.my_branches WHERE level = 'district') OR (OrganizationalUnitId IS NULL AND OwnerEmployeeId IN (SELECT dm_dwid FROM workspace.c360_security.my_branches WHERE level = 'district'));

CREATE OR REPLACE VIEW workspace.c360_district.accountability_participants
COMMENT 'Participant notes and plans of action for those meetings.'
AS SELECT p.* FROM workspace.coaching360demo.coaching360_app_workflow__dbo_accountabilitymeetingparticipants p JOIN workspace.coaching360demo.coaching360_app_workflow__dbo_accountabilitymeetings m ON m.AccountabilityMeetingId = p.AccountabilityMeetingId WHERE m.OrganizationalUnitId IN (SELECT branch_dwid FROM workspace.c360_security.my_branches WHERE level = 'district') OR (m.OrganizationalUnitId IS NULL AND m.OwnerEmployeeId IN (SELECT dm_dwid FROM workspace.c360_security.my_branches WHERE level = 'district'));

CREATE OR REPLACE VIEW workspace.c360_district.districts
COMMENT 'Districts I can see.'
AS SELECT d.*, r.RegionNumber, r.RegionName, r.VPName FROM workspace.coaching360demo.org_hierarchy__eda_ref_t_ref_district d JOIN workspace.coaching360demo.org_hierarchy__eda_ref_t_ref_region r ON r.RegionDWID = d.RegionDWID WHERE d.DistrictDWID IN (SELECT district_dwid FROM workspace.c360_security.my_branches WHERE level = 'district');

CREATE OR REPLACE VIEW workspace.c360_district.district_monthly_performance
COMMENT 'District / AVP monthly scorecard inputs.'
AS SELECT * FROM workspace.coaching360demo.branchkpi_sources__branchkpi_monthly_districtperformance WHERE DistrictNumber IN (SELECT district_number FROM workspace.c360_security.my_branches WHERE level = 'district');

CREATE OR REPLACE VIEW workspace.c360_district.district_turnover
COMMENT 'Monthly district turnover % (2026+ KPI = trailing 12-month sum, lower is better).'
AS SELECT * FROM workspace.coaching360demo.branchkpi_sources__branchkpi_monthly_turnovergoal WHERE DistrictNumber IN (SELECT district_number FROM workspace.c360_security.my_branches WHERE level = 'district');

CREATE OR REPLACE VIEW workspace.c360_district.avp_payouts
COMMENT 'District manager (AVP) ACE payout estimates.'
AS SELECT * FROM workspace.coaching360demo.crm_ace_payout__crm_ace_usp_getavpmonthlypayoutestimate WHERE CAST(districtnumber AS INT) IN (SELECT district_number FROM workspace.c360_security.my_branches WHERE level = 'district');

CREATE OR REPLACE VIEW workspace.c360_district.kpi_definitions
COMMENT 'Reference data (same for every level).'
AS SELECT * FROM workspace.coaching360demo.coaching360_app_reference__dbo_kpidefinitions;

CREATE OR REPLACE VIEW workspace.c360_district.kpi_scoring_rules
COMMENT 'Reference data (same for every level).'
AS SELECT * FROM workspace.coaching360demo.coaching360_app_reference__dbo_kpiscoringrules;

CREATE OR REPLACE VIEW workspace.c360_district.kpi_scoring_bands
COMMENT 'Reference data (same for every level).'
AS SELECT * FROM workspace.coaching360demo.coaching360_app_reference__dbo_kpiscoringbands;

CREATE OR REPLACE VIEW workspace.c360_district.competency_behaviors
COMMENT 'Reference data (same for every level).'
AS SELECT * FROM workspace.coaching360demo.coaching360_app_reference__dbo_competencybehaviors;

CREATE OR REPLACE VIEW workspace.c360_district.coaching_reference_values
COMMENT 'Reference data (same for every level).'
AS SELECT * FROM workspace.coaching360demo.coaching360_app_reference__dbo_coachingreferencevalues;

CREATE OR REPLACE VIEW workspace.c360_district.performance_measures
COMMENT 'Reference data (same for every level).'
AS SELECT * FROM workspace.coaching360demo.branchkpi_sources__branchkpi_dbo_performancemeasurement;

CREATE OR REPLACE VIEW workspace.c360_district.performance_goals
COMMENT 'Reference data (same for every level).'
AS SELECT * FROM workspace.coaching360demo.branchkpi_sources__branchkpi_dbo_performancegoal;

CREATE OR REPLACE VIEW workspace.c360_district.performance_expectations
COMMENT 'Reference data (same for every level).'
AS SELECT * FROM workspace.coaching360demo.branchkpi_sources__branchkpi_dbo_performanceexpectation;

CREATE OR REPLACE VIEW workspace.c360_district.roa_state_floor
COMMENT 'Reference data (same for every level).'
AS SELECT * FROM workspace.coaching360demo.branchkpi_sources__branchkpi_dbo_roastatefloor;

CREATE OR REPLACE VIEW workspace.c360_district.kpi_dashboard_goals
COMMENT 'Reference data (same for every level).'
AS SELECT * FROM workspace.coaching360demo.branchkpi_sources__reports_kpidashboard_goals;

CREATE OR REPLACE VIEW workspace.c360_district.policies
COMMENT 'Reference data (same for every level).'
AS SELECT * FROM workspace.coaching360demo.policy_violations__policyviolations_app_policies;

CREATE OR REPLACE VIEW workspace.c360_district.data_status
COMMENT 'Reference data (same for every level).'
AS SELECT * FROM workspace.c360_prepared.data_status;

CREATE OR REPLACE VIEW workspace.c360_district.kpi_goals
COMMENT 'Reference data (same for every level).'
AS SELECT * FROM workspace.c360_prepared.kpi_goals;

CREATE OR REPLACE VIEW workspace.c360_district.violation_types
COMMENT 'Reference data (same for every level).'
AS SELECT * FROM workspace.coaching360demo.policy_violations__policyviolations_app_violationtypes;
