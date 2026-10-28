-- Item 15: fast copies of the performance views for the Flask fast path.
-- The existing app_vw_* views are not changed (Genie keeps using them).
-- Six deterministic views become materialized views, refreshed daily.
-- app_vw_review_compliance uses current_timestamp() for "overdue", so its fast
-- copy stays a live view that reads the materialized copies.
-- Run after the performance data is loaded (notebooks/02_migrate_data.py).

CREATE MATERIALIZED VIEW IF NOT EXISTS workspace.performance_test.app_fast_employee_profile
  SCHEDULE EVERY 1 DAY
  COMMENT 'Daily materialized copy of app_vw_employee_profile for the Flask performance fast path'
AS SELECT * FROM workspace.performance_test.app_vw_employee_profile;

CREATE MATERIALIZED VIEW IF NOT EXISTS workspace.performance_test.app_fast_employee_quarterly_performance
  SCHEDULE EVERY 1 DAY
  COMMENT 'Daily materialized copy of app_vw_employee_quarterly_performance for the Flask performance fast path'
AS SELECT * FROM workspace.performance_test.app_vw_employee_quarterly_performance;

CREATE MATERIALIZED VIEW IF NOT EXISTS workspace.performance_test.app_fast_employee_competency_summary
  SCHEDULE EVERY 1 DAY
  COMMENT 'Daily materialized copy of app_vw_employee_competency_summary for the Flask performance fast path'
AS SELECT * FROM workspace.performance_test.app_vw_employee_competency_summary;

CREATE MATERIALIZED VIEW IF NOT EXISTS workspace.performance_test.app_fast_employee_goal_status
  SCHEDULE EVERY 1 DAY
  COMMENT 'Daily materialized copy of app_vw_employee_goal_status for the Flask performance fast path'
AS SELECT * FROM workspace.performance_test.app_vw_employee_goal_status;

CREATE MATERIALIZED VIEW IF NOT EXISTS workspace.performance_test.app_fast_employee_performance_history
  SCHEDULE EVERY 1 DAY
  COMMENT 'Daily materialized copy of app_vw_employee_performance_history for the Flask performance fast path'
AS SELECT * FROM workspace.performance_test.app_vw_employee_performance_history;

CREATE MATERIALIZED VIEW IF NOT EXISTS workspace.performance_test.app_fast_branch_quarterly_summary
  SCHEDULE EVERY 1 DAY
  COMMENT 'Daily materialized copy of app_vw_branch_quarterly_summary for the Flask performance fast path'
AS SELECT * FROM workspace.performance_test.app_vw_branch_quarterly_summary;

-- Same SQL as app_vw_review_compliance, reading the fast copies; "overdue" stays live.
CREATE OR REPLACE VIEW workspace.performance_test.app_fast_review_compliance
  COMMENT 'Live review compliance over the app_fast_* copies for the Flask performance fast path'
AS
SELECT
    qp.employee_id,
    qp.employee_name,
    ep.manager_employee_id,
    ep.manager_name,
    ep.branch_id,
    ep.branch_name,
    ep.region_id,
    ep.region_name,
    qp.cycle_id,
    qp.cycle_name,
    qp.cycle_end_date,
    pc.review_due_date,
    qp.review_status,
    qp.meeting_status,
    qp.meeting_date,
    qp.acknowledgment_status,
    -- Overdue: review not completed and due date has passed
    CASE WHEN qp.review_status != 'Completed' AND pc.review_due_date < CURRENT_TIMESTAMP()
         THEN true ELSE false END   AS is_overdue,
    -- Missing meeting: no meeting or not completed
    CASE WHEN qp.meeting_status IS NULL OR qp.meeting_status != 'Completed'
         THEN true ELSE false END   AS is_missing_meeting,
    -- Missing acknowledgment
    CASE WHEN qp.acknowledgment_status IS NULL OR qp.acknowledgment_status != 'Acknowledged'
         THEN true ELSE false END   AS is_missing_acknowledgment
FROM workspace.performance_test.app_fast_employee_quarterly_performance qp
JOIN workspace.performance_test.app_fast_employee_profile ep
    ON qp.employee_id = ep.employee_id
JOIN workspace.performance_test.performance_cycle pc
    ON qp.cycle_id = pc.cycle_id;
