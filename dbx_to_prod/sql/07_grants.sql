-- Grants for the app service principal
-- Generated from the trial workspace DDL (structure only, no data).
-- Run in order in the prod workspace with a serverless SQL warehouse.

-- Replace <app-sp-application-id> with the prod app's service principal application ID.
-- Least privilege: read everything the app and agents use, write only the log table.
GRANT USE CATALOG ON CATALOG workspace TO `<app-sp-application-id>`;
GRANT USE SCHEMA, SELECT ON SCHEMA workspace.performance_test TO `<app-sp-application-id>`;
GRANT USE SCHEMA ON SCHEMA workspace.default TO `<app-sp-application-id>`;
GRANT SELECT ON TABLE workspace.default.app_citation_registry TO `<app-sp-application-id>`;
GRANT SELECT ON TABLE workspace.default.branch_operations_chunks TO `<app-sp-application-id>`;
GRANT SELECT ON TABLE workspace.default.employee_handbook_chunks TO `<app-sp-application-id>`;
GRANT SELECT ON TABLE workspace.default.benefits_chunks TO `<app-sp-application-id>`;
GRANT SELECT ON TABLE workspace.default.coaching360_chunks TO `<app-sp-application-id>`;
GRANT SELECT, MODIFY ON TABLE workspace.default.flask_app_logs TO `<app-sp-application-id>`;
GRANT READ VOLUME ON VOLUME workspace.default.branch_operations_docs TO `<app-sp-application-id>`;
GRANT READ VOLUME ON VOLUME workspace.default.employee_handbook_docs TO `<app-sp-application-id>`;
GRANT READ VOLUME ON VOLUME workspace.default.benefits_docs TO `<app-sp-application-id>`;
GRANT READ VOLUME ON VOLUME workspace.performance_test.data TO `<app-sp-application-id>`;
GRANT USE SCHEMA ON SCHEMA workspace.coaching360demo TO `<app-sp-application-id>`;
GRANT READ VOLUME ON VOLUME workspace.coaching360demo.coaching360_docs TO `<app-sp-application-id>`;
-- Also grant the SP:  CAN_USE on the SQL warehouse, CAN_QUERY on every serving endpoint it calls
-- (Supervisor, Knowledge Assistants, perf-policy-citations, the fast-path model endpoint)
-- and CAN_RUN on the Genie spaces. notebooks/05 and 06 set the endpoint permissions.
-- Coaching360 grants (c360_* views, user_map, functions, directory tables) are in
-- sql/coaching360/05b_demo_grants_app.sql, applied by notebook 02b.
