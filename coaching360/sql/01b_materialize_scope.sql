-- One-time: replace the security scope views with daily materialized views (faster level views).
-- Run once in the SQL Editor (Run all), then rerun 05b_demo_grants_app.sql (the drop removes its grant).
CREATE OR REPLACE VIEW workspace.c360_security.user_level_live
COMMENT 'Active users and their Coaching360 agent level (live definition)'
AS SELECT u.UserDWID AS user_dwid, u.UserName AS user_name, u.UserTitle AS title,
       CASE
         WHEN u.UserTitle = 'Branch Manager' THEN 'branch'
         WHEN EXISTS (SELECT 1 FROM workspace.coaching360demo.org_hierarchy__eda_ref_t_ref_branch b WHERE lower(b.ReliefManagerUsername) = lower(u.UserName) AND current_date() BETWEEN coalesce(b.ReliefManagerStartDate, DATE'1900-01-01') AND coalesce(b.ReliefManagerEndDate, DATE'2999-12-31')) THEN 'branch'
         WHEN u.UserTitle IN ('Account Representative', 'Assistant Branch Manager', 'Branch Manager Trainee') THEN 'employee'
         WHEN u.UserTitle IN ('District Manager', 'Regional Vice President', 'Senior Vice President', 'Chief Operating Officer', 'AVP of Branch Assist', 'Director of Operations Strategy', 'Branch Enablement Representative I', 'Branch Enablement Representative II', 'Manager I - Branch Enablement', 'HR Business Partner', 'Compliance Analyst', 'Corporate Counsel', 'Internal Auditor') THEN 'district'
         ELSE 'none'
       END AS level
FROM workspace.coaching360demo.org_hierarchy__eda_ref_t_ref_user u
WHERE u.EmployeeActive;

CREATE OR REPLACE VIEW workspace.c360_security.branch_scope_live
COMMENT 'Branches each active user can see, and why (live definition)'
AS SELECT u.UserDWID AS user_dwid, b.BranchDWID AS branch_dwid, 'branch manager' AS reason
FROM workspace.coaching360demo.org_hierarchy__eda_ref_t_ref_user u JOIN workspace.coaching360demo.org_hierarchy__eda_ref_t_ref_branch b ON lower(b.BMUsername) = lower(u.UserName) WHERE u.EmployeeActive
UNION
SELECT u.UserDWID, b.BranchDWID, 'relief manager'
FROM workspace.coaching360demo.org_hierarchy__eda_ref_t_ref_user u JOIN workspace.coaching360demo.org_hierarchy__eda_ref_t_ref_branch b ON lower(b.ReliefManagerUsername) = lower(u.UserName) AND current_date() BETWEEN coalesce(b.ReliefManagerStartDate, DATE'1900-01-01') AND coalesce(b.ReliefManagerEndDate, DATE'2999-12-31') WHERE u.EmployeeActive
UNION
SELECT u.UserDWID, b.BranchDWID, 'district manager'
FROM workspace.coaching360demo.org_hierarchy__eda_ref_t_ref_user u JOIN workspace.coaching360demo.org_hierarchy__eda_ref_t_ref_district d ON lower(d.DMUsername) = lower(u.UserName)
JOIN workspace.coaching360demo.org_hierarchy__eda_ref_t_ref_branch b ON b.DistrictDWID = d.DistrictDWID WHERE u.EmployeeActive
UNION
SELECT u.UserDWID, b.BranchDWID, 'regional vice president'
FROM workspace.coaching360demo.org_hierarchy__eda_ref_t_ref_user u JOIN workspace.coaching360demo.org_hierarchy__eda_ref_t_ref_region r ON lower(r.VPUsername) = lower(u.UserName)
JOIN workspace.coaching360demo.org_hierarchy__eda_ref_t_ref_district d ON d.RegionDWID = r.RegionDWID JOIN workspace.coaching360demo.org_hierarchy__eda_ref_t_ref_branch b ON b.DistrictDWID = d.DistrictDWID WHERE u.EmployeeActive
UNION
SELECT u.UserDWID, b.BranchDWID, 'senior vice president'
FROM workspace.coaching360demo.org_hierarchy__eda_ref_t_ref_user u JOIN workspace.coaching360demo.org_hierarchy__eda_ref_t_ref_companydivision c ON lower(c.SVPUsername) = lower(u.UserName)
JOIN workspace.coaching360demo.org_hierarchy__eda_ref_t_ref_region r ON r.CompanyDivisionDWID = c.CompanyDivisionDWID JOIN workspace.coaching360demo.org_hierarchy__eda_ref_t_ref_district d ON d.RegionDWID = r.RegionDWID
JOIN workspace.coaching360demo.org_hierarchy__eda_ref_t_ref_branch b ON b.DistrictDWID = d.DistrictDWID WHERE u.EmployeeActive
UNION
SELECT u.UserDWID, b.BranchDWID, 'central role (all branches)'
FROM workspace.coaching360demo.org_hierarchy__eda_ref_t_ref_user u CROSS JOIN workspace.coaching360demo.org_hierarchy__eda_ref_t_ref_branch b WHERE u.EmployeeActive AND u.UserTitle IN ('Chief Operating Officer', 'AVP of Branch Assist', 'Director of Operations Strategy', 'Branch Enablement Representative I', 'Branch Enablement Representative II', 'Manager I - Branch Enablement', 'HR Business Partner', 'Compliance Analyst', 'Corporate Counsel', 'Internal Auditor');

-- If user_level / branch_scope are still plain views (first run only), drop them first:
--   DROP VIEW IF EXISTS workspace.c360_security.user_level;  DROP VIEW IF EXISTS workspace.c360_security.branch_scope;
-- When they are already materialized views, the statements below simply refresh their definition.
CREATE OR REPLACE MATERIALIZED VIEW workspace.c360_security.user_level
  SCHEDULE EVERY 1 DAY
  COMMENT 'Active users and their Coaching360 agent level: employee, branch, district or none'
AS SELECT * FROM workspace.c360_security.user_level_live;

CREATE OR REPLACE MATERIALIZED VIEW workspace.c360_security.branch_scope
  SCHEDULE EVERY 1 DAY
  COMMENT 'Branches each active user can see, and why'
AS SELECT * FROM workspace.c360_security.branch_scope_live;

-- After a directory change (new BM, relief manager, transfer), refresh right away:
-- REFRESH MATERIALIZED VIEW workspace.c360_security.user_level;  REFRESH MATERIALIZED VIEW workspace.c360_security.branch_scope;
