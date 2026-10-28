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
