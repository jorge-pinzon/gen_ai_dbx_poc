-- workspace.c360_employee: Account Representatives, Assistant BMs and BM Trainees: own rows only.
-- Every view filters on the signed-in user and checks their level.

CREATE SCHEMA IF NOT EXISTS workspace.c360_employee COMMENT 'Coaching360 data for the employee agent (Account Representatives, Assistant BMs and BM Trainees: own rows only)';

CREATE OR REPLACE VIEW workspace.c360_employee.my_profile
COMMENT 'My directory record, branch and district.'
AS SELECT u.*, b.BranchNumber, b.BranchName, d.DistrictNumber, d.DistrictName FROM workspace.coaching360demo.org_hierarchy__eda_ref_t_ref_user u LEFT JOIN workspace.coaching360demo.org_hierarchy__eda_ref_t_ref_branch b ON b.BranchDWID = u.BranchDWID LEFT JOIN workspace.coaching360demo.org_hierarchy__eda_ref_t_ref_district d ON d.DistrictDWID = b.DistrictDWID WHERE u.UserDWID = (SELECT user_dwid FROM workspace.c360_security.my_person WHERE level IN ('employee', 'branch', 'district'));

CREATE OR REPLACE VIEW workspace.c360_employee.my_overview
COMMENT 'My one-row summary: latest-month KPIs and rank in my branch, open and overdue tasks, coaching, Success Plan and open violations.'
AS SELECT * FROM workspace.c360_prepared.employee_overview WHERE UserDWID = (SELECT user_dwid FROM workspace.c360_security.my_person WHERE level IN ('employee', 'branch', 'district'));

CREATE OR REPLACE VIEW workspace.c360_employee.my_kpi_scorecard
COMMENT 'My monthly scorecard: LPE, DACC loans, current-month and 30-89 day delinquency, first lien, cash advance vs state average, calls and contacts, each with its goal (one row per branch x month). Use this for ''my scorecard''.'
AS SELECT * FROM workspace.c360_prepared.employee_kpi_scorecard WHERE TellerID = (SELECT teller_id FROM workspace.c360_security.my_person WHERE level IN ('employee', 'branch', 'district'));

CREATE OR REPLACE VIEW workspace.c360_employee.my_monthly_kpis
COMMENT 'My monthly production and delinquency (one row per branch x month; KpiMonth is the month).'
AS SELECT * FROM workspace.c360_prepared.employee_kpis WHERE TellerID = (SELECT teller_id FROM workspace.c360_security.my_person WHERE level IN ('employee', 'branch', 'district'));

CREATE OR REPLACE VIEW workspace.c360_employee.my_dpr_scorecard
COMMENT 'My published DPR scorecard metrics (ratios are fractions; MetricMonth is the month).'
AS SELECT * FROM workspace.c360_prepared.dpr_metrics WHERE EmployeeDWID = (SELECT user_dwid FROM workspace.c360_security.my_person WHERE level IN ('employee', 'branch', 'district'));

CREATE OR REPLACE VIEW workspace.c360_employee.my_call_activity
COMMENT 'My daily outbound calls.'
AS SELECT * FROM workspace.coaching360demo.branchkpi_sources__reports_kpidashboard_calldata WHERE TellerID = (SELECT teller_id FROM workspace.c360_security.my_person WHERE level IN ('employee', 'branch', 'district'));

CREATE OR REPLACE VIEW workspace.c360_employee.my_call_goals
COMMENT 'My outbound call and contact targets.'
AS SELECT * FROM workspace.coaching360demo.branchkpi_sources__reports_kpidashboard_employeegoals WHERE TellerID = (SELECT teller_id FROM workspace.c360_security.my_person WHERE level IN ('employee', 'branch', 'district'));

CREATE OR REPLACE VIEW workspace.c360_employee.my_coaching_records
COMMENT 'Coaching records about me that are visible to me.'
AS SELECT * FROM workspace.c360_prepared.coaching_records WHERE EmployeeId = (SELECT user_dwid FROM workspace.c360_security.my_person WHERE level IN ('employee', 'branch', 'district')) AND VisibleToEmployee;

CREATE OR REPLACE VIEW workspace.c360_employee.my_coaching_comments
COMMENT 'Employee-visible comments on my coaching records (internal manager notes excluded).'
AS SELECT i.* FROM workspace.coaching360demo.coaching360_app_workflow__dbo_coachinginteractions i JOIN workspace.coaching360demo.coaching360_app_workflow__dbo_coachingrecords c ON c.CoachingRecordId = i.CoachingRecordId WHERE c.EmployeeId = (SELECT user_dwid FROM workspace.c360_security.my_person WHERE level IN ('employee', 'branch', 'district')) AND c.VisibleToEmployee AND NOT i.IsInternal;

CREATE OR REPLACE VIEW workspace.c360_employee.my_coaching_acknowledgements
COMMENT 'My acknowledgements of coaching records.'
AS SELECT * FROM workspace.coaching360demo.coaching360_app_workflow__dbo_coachingrecordacknowledgements WHERE EmployeeId = (SELECT user_dwid FROM workspace.c360_security.my_person WHERE level IN ('employee', 'branch', 'district'));

CREATE OR REPLACE VIEW workspace.c360_employee.my_success_plans
COMMENT 'My monthly Success Plans (IDPs).'
AS SELECT * FROM workspace.coaching360demo.coaching360_app_workflow__dbo_individualdevelopmentgoals WHERE EmployeeId = (SELECT user_dwid FROM workspace.c360_security.my_person WHERE level IN ('employee', 'branch', 'district')) AND NOT IsArchived;

CREATE OR REPLACE VIEW workspace.c360_employee.my_success_plan_comments
COMMENT 'Comments on my Success Plans.'
AS SELECT c.* FROM workspace.coaching360demo.coaching360_app_workflow__dbo_individualdevelopmentgoalcomments c JOIN workspace.coaching360demo.coaching360_app_workflow__dbo_individualdevelopmentgoals g ON g.IndividualDevelopmentGoalId = c.IndividualDevelopmentGoalId WHERE g.EmployeeId = (SELECT user_dwid FROM workspace.c360_security.my_person WHERE level IN ('employee', 'branch', 'district')) AND NOT g.IsArchived;

CREATE OR REPLACE VIEW workspace.c360_employee.my_tasks
COMMENT 'Tasks and action items assigned to me.'
AS SELECT * FROM workspace.coaching360demo.coaching360_app_workflow__dbo_coachingtasks WHERE AssignedToEmployeeId = (SELECT user_dwid FROM workspace.c360_security.my_person WHERE level IN ('employee', 'branch', 'district'));

CREATE OR REPLACE VIEW workspace.c360_employee.my_ace_payout
COMMENT 'My ACE incentive payout estimate (branch manager payout columns removed).'
AS SELECT * EXCEPT (BMPayout, BMEstPayout, BMlpe, Column_1, Column_2, Column_3) FROM workspace.coaching360demo.crm_ace_payout__crm_ace_usp_getbmemployeemonthlypayoutestimate WHERE TELLER_ID = (SELECT teller_id FROM workspace.c360_security.my_person WHERE level IN ('employee', 'branch', 'district'));

CREATE OR REPLACE VIEW workspace.c360_employee.my_policy_violations
COMMENT 'Policy violations recorded about me (account numbers masked).'
AS SELECT * EXCEPT (PayloadJson, ManagementChainJson, AccountNumber, AccountId), concat('****', right(AccountNumber, 4)) AS AccountNumberLast4 FROM workspace.coaching360demo.policy_violations__policyviolations_app_violations WHERE EmployeeId = (SELECT employee_number FROM workspace.c360_security.my_person WHERE level IN ('employee', 'branch', 'district'));

CREATE OR REPLACE VIEW workspace.c360_employee.kpi_definitions
COMMENT 'Reference data (same for every level).'
AS SELECT * FROM workspace.coaching360demo.coaching360_app_reference__dbo_kpidefinitions;

CREATE OR REPLACE VIEW workspace.c360_employee.kpi_scoring_rules
COMMENT 'Reference data (same for every level).'
AS SELECT * FROM workspace.coaching360demo.coaching360_app_reference__dbo_kpiscoringrules;

CREATE OR REPLACE VIEW workspace.c360_employee.kpi_scoring_bands
COMMENT 'Reference data (same for every level).'
AS SELECT * FROM workspace.coaching360demo.coaching360_app_reference__dbo_kpiscoringbands;

CREATE OR REPLACE VIEW workspace.c360_employee.competency_behaviors
COMMENT 'Reference data (same for every level).'
AS SELECT * FROM workspace.coaching360demo.coaching360_app_reference__dbo_competencybehaviors;

CREATE OR REPLACE VIEW workspace.c360_employee.coaching_reference_values
COMMENT 'Reference data (same for every level).'
AS SELECT * FROM workspace.coaching360demo.coaching360_app_reference__dbo_coachingreferencevalues;

CREATE OR REPLACE VIEW workspace.c360_employee.performance_measures
COMMENT 'Reference data (same for every level).'
AS SELECT * FROM workspace.coaching360demo.branchkpi_sources__branchkpi_dbo_performancemeasurement;

CREATE OR REPLACE VIEW workspace.c360_employee.performance_goals
COMMENT 'Reference data (same for every level).'
AS SELECT * FROM workspace.coaching360demo.branchkpi_sources__branchkpi_dbo_performancegoal;

CREATE OR REPLACE VIEW workspace.c360_employee.performance_expectations
COMMENT 'Reference data (same for every level).'
AS SELECT * FROM workspace.coaching360demo.branchkpi_sources__branchkpi_dbo_performanceexpectation;

CREATE OR REPLACE VIEW workspace.c360_employee.roa_state_floor
COMMENT 'Reference data (same for every level).'
AS SELECT * FROM workspace.coaching360demo.branchkpi_sources__branchkpi_dbo_roastatefloor;

CREATE OR REPLACE VIEW workspace.c360_employee.kpi_dashboard_goals
COMMENT 'Reference data (same for every level).'
AS SELECT * FROM workspace.coaching360demo.branchkpi_sources__reports_kpidashboard_goals;

CREATE OR REPLACE VIEW workspace.c360_employee.policies
COMMENT 'Reference data (same for every level).'
AS SELECT * FROM workspace.coaching360demo.policy_violations__policyviolations_app_policies;

CREATE OR REPLACE VIEW workspace.c360_employee.data_status
COMMENT 'Reference data (same for every level).'
AS SELECT * FROM workspace.c360_prepared.data_status;

CREATE OR REPLACE VIEW workspace.c360_employee.kpi_goals
COMMENT 'Reference data (same for every level).'
AS SELECT * FROM workspace.c360_prepared.kpi_goals;

CREATE OR REPLACE VIEW workspace.c360_employee.violation_types
COMMENT 'Reference data (same for every level).'
AS SELECT * FROM workspace.coaching360demo.policy_violations__policyviolations_app_violationtypes;
