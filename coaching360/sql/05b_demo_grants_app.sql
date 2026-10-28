-- Demo grants (no groups): the app's service principal reads the level views and sets the
-- demo persona in user_map. Run once as the owner of the c360_* schemas.
GRANT USE SCHEMA, SELECT, EXECUTE ON SCHEMA workspace.c360_employee TO `9480056c-9708-40af-92da-c35b15cf61fa`;
GRANT USE SCHEMA, SELECT, EXECUTE ON SCHEMA workspace.c360_branch TO `9480056c-9708-40af-92da-c35b15cf61fa`;
GRANT USE SCHEMA, SELECT, EXECUTE ON SCHEMA workspace.c360_district TO `9480056c-9708-40af-92da-c35b15cf61fa`;
GRANT USE SCHEMA ON SCHEMA workspace.c360_security TO `9480056c-9708-40af-92da-c35b15cf61fa`;
GRANT EXECUTE ON FUNCTION workspace.c360_security.me TO `9480056c-9708-40af-92da-c35b15cf61fa`;
GRANT EXECUTE ON FUNCTION workspace.c360_security.my_level TO `9480056c-9708-40af-92da-c35b15cf61fa`;
GRANT SELECT ON TABLE workspace.c360_security.user_level TO `9480056c-9708-40af-92da-c35b15cf61fa`;      -- the chat lists people per level
GRANT SELECT, MODIFY ON TABLE workspace.c360_security.user_map TO `9480056c-9708-40af-92da-c35b15cf61fa`; -- the chat sets the chosen person

-- Check (run as yourself): the service principal should appear on each schema.
SHOW GRANTS `9480056c-9708-40af-92da-c35b15cf61fa` ON SCHEMA workspace.c360_employee;
