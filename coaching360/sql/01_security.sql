-- Coaching360 security schema: who is signed in, their level and the branches they can see.
-- Owned by an admin. Users never read these objects directly; the level views use them.
CREATE SCHEMA IF NOT EXISTS workspace.c360_security COMMENT 'Coaching360 access rules (identity, level, branch scope)';

-- Maps Databricks logins to directory users. The demo directory uses synthetic e-mails, so add
-- rows here; in prod, me() also matches the directory e-mail to the login automatically.
CREATE TABLE IF NOT EXISTS workspace.c360_security.user_map (
  databricks_user STRING NOT NULL COMMENT 'Databricks login (e-mail), as returned by current_user()',
  user_dwid INT NOT NULL COMMENT 'Directory UserDWID (org_hierarchy__eda_ref_t_ref_user)',
  note STRING,
  updated_at TIMESTAMP)
COMMENT 'Databricks login to Coaching360 directory user';

-- Live definitions. The level views read the materialized copies below, so each query does a
-- small lookup instead of recomputing the hierarchy (refreshed daily; relief windows are by date).
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

CREATE MATERIALIZED VIEW IF NOT EXISTS workspace.c360_security.user_level
  SCHEDULE EVERY 1 DAY
  COMMENT 'Active users and their Coaching360 agent level: employee, branch, district or none'
AS SELECT * FROM workspace.c360_security.user_level_live;

CREATE MATERIALIZED VIEW IF NOT EXISTS workspace.c360_security.branch_scope
  SCHEDULE EVERY 1 DAY
  COMMENT 'Branches each active user can see, and why'
AS SELECT * FROM workspace.c360_security.branch_scope_live;

CREATE OR REPLACE FUNCTION workspace.c360_security.me()
RETURNS INT
COMMENT 'Directory UserDWID of the signed-in user (user_map first, then directory e-mail)'
RETURN coalesce(
  (SELECT max(user_dwid) FROM workspace.c360_security.user_map WHERE lower(databricks_user) = lower(current_user())),
  (SELECT max(UserDWID) FROM workspace.coaching360demo.org_hierarchy__eda_ref_t_ref_user WHERE EmployeeActive AND lower(UserEmail) = lower(current_user())));

CREATE OR REPLACE FUNCTION workspace.c360_security.my_level()
RETURNS STRING
COMMENT 'Coaching360 level of the signed-in user'
RETURN (SELECT max(level) FROM workspace.c360_security.user_level WHERE user_dwid = workspace.c360_security.me());

-- Scope computed once: one small lookup per level view instead of re-deriving the hierarchy.
-- Rerunnable. Run after the user_level / branch_scope live views exist.
CREATE OR REPLACE VIEW workspace.c360_security.persona_live
COMMENT 'Each active user: Coaching360 level, teller id and employee number (live definition)'
AS SELECT u.UserDWID AS user_dwid, l.level, CAST(u.TellerID AS BIGINT) AS teller_id, u.EmployeeNumber AS employee_number
FROM workspace.coaching360demo.org_hierarchy__eda_ref_t_ref_user u JOIN workspace.c360_security.user_level_live l ON l.user_dwid = u.UserDWID;

CREATE OR REPLACE VIEW workspace.c360_security.scope_branches_live
COMMENT 'Branches (with district and district manager) each active user can see, with their level and why (reason) (live definition)'
AS SELECT DISTINCT s.user_dwid, l.level, b.BranchDWID AS branch_dwid, b.BranchNumber AS branch_number,
       b.DistrictDWID AS district_dwid, CAST(d.DistrictNumber AS INT) AS district_number, dm.UserDWID AS dm_dwid,
       s.reason, CASE WHEN s.reason = 'relief manager' THEN b.ReliefManagerEndDate END AS relief_until
FROM workspace.c360_security.branch_scope_live s JOIN workspace.c360_security.user_level_live l ON l.user_dwid = s.user_dwid
JOIN workspace.coaching360demo.org_hierarchy__eda_ref_t_ref_branch b ON b.BranchDWID = s.branch_dwid JOIN workspace.coaching360demo.org_hierarchy__eda_ref_t_ref_district d ON d.DistrictDWID = b.DistrictDWID
LEFT JOIN workspace.coaching360demo.org_hierarchy__eda_ref_t_ref_user dm ON lower(dm.UserName) = lower(d.DMUsername);

CREATE OR REPLACE VIEW workspace.c360_security.scope_people_live
COMMENT 'Employees at the branches each active user can see, with their level (live definition)'
AS SELECT DISTINCT s.user_dwid, s.level, u.UserDWID AS member_dwid, CAST(u.TellerID AS BIGINT) AS member_teller
FROM workspace.c360_security.scope_branches_live s JOIN workspace.coaching360demo.org_hierarchy__eda_ref_t_ref_user u ON u.BranchDWID = s.branch_dwid;

CREATE OR REPLACE MATERIALIZED VIEW workspace.c360_security.persona
  SCHEDULE EVERY 1 DAY
  COMMENT 'Each active user: Coaching360 level, teller id and employee number'
AS SELECT * FROM workspace.c360_security.persona_live;

CREATE OR REPLACE MATERIALIZED VIEW workspace.c360_security.scope_branches
  SCHEDULE EVERY 1 DAY
  COMMENT 'Branches (with district and district manager) each active user can see, with their level and why (reason)'
AS SELECT * FROM workspace.c360_security.scope_branches_live;

CREATE OR REPLACE MATERIALIZED VIEW workspace.c360_security.scope_people
  SCHEDULE EVERY 1 DAY
  COMMENT 'Employees at the branches each active user can see, with their level'
AS SELECT * FROM workspace.c360_security.scope_people_live;

CREATE OR REPLACE VIEW workspace.c360_security.my_person
COMMENT 'The signed-in person: level, teller id and employee number'
AS SELECT * FROM workspace.c360_security.persona WHERE user_dwid = workspace.c360_security.me();

CREATE OR REPLACE VIEW workspace.c360_security.my_branches
COMMENT 'Branches the signed-in person can see'
AS SELECT * FROM workspace.c360_security.scope_branches WHERE user_dwid = workspace.c360_security.me();

CREATE OR REPLACE VIEW workspace.c360_security.my_team
COMMENT 'Employees at the branches the signed-in person can see'
AS SELECT * FROM workspace.c360_security.scope_people WHERE user_dwid = workspace.c360_security.me();

CREATE OR REPLACE VIEW workspace.c360_security.my_coverage
COMMENT 'How the signed-in person covers each branch in scope'
AS SELECT branch_dwid, branch_number, level,
       CASE WHEN max(CASE WHEN reason = 'relief manager' THEN 0 ELSE 1 END) = 0
              THEN concat('Relief coverage until ', date_format(max(relief_until), 'M/d/yyyy'))
            WHEN max(CASE WHEN reason = 'branch manager' THEN 1 ELSE 0 END) = 1 THEN 'Own branch'
            ELSE 'In scope' END AS Coverage
FROM workspace.c360_security.my_branches GROUP BY branch_dwid, branch_number, level;

-- After a directory change, refresh right away (user_level and branch_scope first):
-- REFRESH MATERIALIZED VIEW workspace.c360_security.persona;
-- REFRESH MATERIALIZED VIEW workspace.c360_security.scope_branches;
-- REFRESH MATERIALIZED VIEW workspace.c360_security.scope_people;
