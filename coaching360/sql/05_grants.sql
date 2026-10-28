-- Groups and grants. Create the three account groups first (Settings > Identity and access),
-- add each person to exactly one, then run this file as an admin.
GRANT USE CATALOG ON CATALOG workspace TO `c360_employees`, `c360_branch_managers`, `c360_district_leaders`;
GRANT USE SCHEMA, SELECT, EXECUTE ON SCHEMA workspace.c360_employee TO `c360_employees`;
GRANT USE SCHEMA, SELECT, EXECUTE ON SCHEMA workspace.c360_branch TO `c360_branch_managers`;
GRANT USE SCHEMA, SELECT, EXECUTE ON SCHEMA workspace.c360_district TO `c360_district_leaders`;

-- Nobody reads the raw tables or the security objects directly.
-- The app's service principal currently has ALL PRIVILEGES on workspace.coaching360demo; agents must query as the
-- signed-in user (on-behalf-of-user), so remove it after the app is switched over:
-- REVOKE ALL PRIVILEGES ON SCHEMA workspace.coaching360demo FROM `9480056c-9708-40af-92da-c35b15cf61fa`;

-- Read access to the BRD for the shared RAG agent:
GRANT READ VOLUME ON VOLUME workspace.coaching360demo.coaching360_docs TO `c360_employees`, `c360_branch_managers`, `c360_district_leaders`;
