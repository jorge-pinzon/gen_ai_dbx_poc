-- Copied from coaching360/sql/05b_demo_grants_app.sql (service principal id replaced by a placeholder).
-- Demo grants (no groups): the app's service principal reads the level views and sets the
-- demo persona in user_map. Run once as the owner of the c360_* schemas.
GRANT USE SCHEMA, SELECT, EXECUTE ON SCHEMA workspace.c360_employee TO `<app-sp-application-id>`;
GRANT USE SCHEMA, SELECT, EXECUTE ON SCHEMA workspace.c360_branch TO `<app-sp-application-id>`;
GRANT USE SCHEMA, SELECT, EXECUTE ON SCHEMA workspace.c360_district TO `<app-sp-application-id>`;
GRANT USE SCHEMA ON SCHEMA workspace.c360_security TO `<app-sp-application-id>`;
GRANT EXECUTE ON FUNCTION workspace.c360_security.me TO `<app-sp-application-id>`;
GRANT EXECUTE ON FUNCTION workspace.c360_security.my_level TO `<app-sp-application-id>`;
GRANT SELECT ON TABLE workspace.c360_security.user_level TO `<app-sp-application-id>`;      -- the chat lists people per level
GRANT SELECT, MODIFY ON TABLE workspace.c360_security.user_map TO `<app-sp-application-id>`; -- the chat sets the chosen person

-- Added for prod (in trial the service principal has ALL PRIVILEGES on coaching360demo instead):
-- the chat's name lookup (src/mariner_genai_dbx/coaching360.py find_people) reads these directory tables.
GRANT USE SCHEMA ON SCHEMA workspace.coaching360demo TO `<app-sp-application-id>`;
GRANT SELECT ON TABLE workspace.coaching360demo.org_hierarchy__eda_ref_t_ref_user TO `<app-sp-application-id>`;
GRANT SELECT ON TABLE workspace.coaching360demo.org_hierarchy__eda_ref_t_ref_branch TO `<app-sp-application-id>`;
GRANT SELECT ON TABLE workspace.coaching360demo.org_hierarchy__eda_ref_t_ref_district TO `<app-sp-application-id>`;

-- Check (run as yourself): the service principal should appear on each schema.
SHOW GRANTS `<app-sp-application-id>` ON SCHEMA workspace.c360_employee;
