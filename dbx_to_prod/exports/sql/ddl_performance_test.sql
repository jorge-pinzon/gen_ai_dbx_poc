-- DDL exported read-only from workspace.performance_test (structure only, no data)

-- MANAGED: workspace.performance_test.app_evaluation_dataset
CREATE TABLE workspace.performance_test.app_evaluation_dataset (
  category STRING COLLATE UTF8_BINARY,
  expected_facts STRING COLLATE UTF8_BINARY,
  question STRING COLLATE UTF8_BINARY)
USING delta
TBLPROPERTIES (
  'delta.enableDeletionVectors' = 'true',
  'delta.feature.appendOnly' = 'supported',
  'delta.feature.deletionVectors' = 'supported',
  'delta.feature.invariants' = 'supported',
  'delta.minReaderVersion' = '3',
  'delta.minWriterVersion' = '7',
  'delta.parquet.compression.codec' = 'zstd',
  'delta.parquet.format.version' = '2.12.0',
  'delta.parquet.format.version.afe.internal' = '2.12.0');

-- MATERIALIZED_VIEW: workspace.performance_test.app_fast_branch_quarterly_summary
CREATE MATERIALIZED VIEW `workspace`.`performance_test`.`app_fast_branch_quarterly_summary` (
  region_id STRING COLLATE UTF8_BINARY,
  region_name STRING COLLATE UTF8_BINARY,
  branch_id STRING COLLATE UTF8_BINARY,
  branch_name STRING COLLATE UTF8_BINARY,
  cycle_id STRING COLLATE UTF8_BINARY,
  cycle_name STRING COLLATE UTF8_BINARY,
  employee_count BIGINT,
  total_target BIGINT,
  total_funded_amount BIGINT,
  branch_attainment_pct DOUBLE,
  funded_loan_count BIGINT,
  avg_rating DOUBLE,
  rating_1_count BIGINT,
  rating_2_count BIGINT,
  rating_3_count BIGINT,
  rating_4_count BIGINT,
  rating_5_count BIGINT,
  completed_review_count BIGINT,
  missing_review_count BIGINT)
COMMENT 'Daily materialized copy of app_vw_branch_quarterly_summary for the Flask performance fast path'
SCHEDULE EVERY 1 DAYS
AS SELECT * FROM workspace.performance_test.app_vw_branch_quarterly_summary;

-- MATERIALIZED_VIEW: workspace.performance_test.app_fast_employee_competency_summary
CREATE MATERIALIZED VIEW `workspace`.`performance_test`.`app_fast_employee_competency_summary` (
  employee_id STRING COLLATE UTF8_BINARY,
  employee_name STRING COLLATE UTF8_BINARY,
  cycle_id STRING COLLATE UTF8_BINARY,
  cycle_name STRING COLLATE UTF8_BINARY,
  competency_id STRING COLLATE UTF8_BINARY,
  competency_name STRING COLLATE UTF8_BINARY,
  competency_rating BIGINT,
  rating_label STRING COLLATE UTF8_BINARY,
  rated_by_employee_id STRING COLLATE UTF8_BINARY,
  rated_by_name STRING COLLATE UTF8_BINARY,
  rating_date TIMESTAMP)
COMMENT 'Daily materialized copy of app_vw_employee_competency_summary for the Flask performance fast path'
SCHEDULE EVERY 1 DAYS
AS SELECT * FROM workspace.performance_test.app_vw_employee_competency_summary;

-- MATERIALIZED_VIEW: workspace.performance_test.app_fast_employee_goal_status
CREATE MATERIALIZED VIEW `workspace`.`performance_test`.`app_fast_employee_goal_status` (
  employee_id STRING COLLATE UTF8_BINARY,
  employee_name STRING COLLATE UTF8_BINARY,
  goal_id STRING COLLATE UTF8_BINARY,
  goal_type STRING COLLATE UTF8_BINARY,
  goal_title STRING COLLATE UTF8_BINARY,
  goal_description STRING COLLATE UTF8_BINARY,
  goal_status STRING COLLATE UTF8_BINARY,
  goal_start_date TIMESTAMP,
  goal_due_date TIMESTAMP,
  cycle_id STRING COLLATE UTF8_BINARY,
  cycle_name STRING COLLATE UTF8_BINARY,
  completion_percent BIGINT,
  progress_note STRING COLLATE UTF8_BINARY,
  progress_date TIMESTAMP)
COMMENT 'Daily materialized copy of app_vw_employee_goal_status for the Flask performance fast path'
SCHEDULE EVERY 1 DAYS
AS SELECT * FROM workspace.performance_test.app_vw_employee_goal_status;

-- MATERIALIZED_VIEW: workspace.performance_test.app_fast_employee_performance_history
CREATE MATERIALIZED VIEW `workspace`.`performance_test`.`app_fast_employee_performance_history` (
  employee_id STRING COLLATE UTF8_BINARY,
  employee_name STRING COLLATE UTF8_BINARY,
  job_role_name STRING COLLATE UTF8_BINARY,
  branch_id STRING COLLATE UTF8_BINARY,
  branch_name STRING COLLATE UTF8_BINARY,
  region_id STRING COLLATE UTF8_BINARY,
  region_name STRING COLLATE UTF8_BINARY,
  manager_employee_id STRING COLLATE UTF8_BINARY,
  manager_name STRING COLLATE UTF8_BINARY,
  cycle_id STRING COLLATE UTF8_BINARY,
  cycle_name STRING COLLATE UTF8_BINARY,
  review_status STRING COLLATE UTF8_BINARY,
  final_rating BIGINT,
  rating_rationale STRING COLLATE UTF8_BINARY,
  target_amount BIGINT,
  funded_amount BIGINT,
  funded_loan_count BIGINT,
  attainment_percent DOUBLE,
  loan_rating BIGINT,
  meeting_status STRING COLLATE UTF8_BINARY,
  acknowledgment_status STRING COLLATE UTF8_BINARY,
  avg_competency_rating DOUBLE,
  active_goal_count BIGINT,
  avg_goal_completion DOUBLE)
COMMENT 'Daily materialized copy of app_vw_employee_performance_history for the Flask performance fast path'
SCHEDULE EVERY 1 DAYS
AS SELECT * FROM workspace.performance_test.app_vw_employee_performance_history;

-- MATERIALIZED_VIEW: workspace.performance_test.app_fast_employee_profile
CREATE MATERIALIZED VIEW `workspace`.`performance_test`.`app_fast_employee_profile` (
  employee_id STRING COLLATE UTF8_BINARY,
  employee_name STRING COLLATE UTF8_BINARY,
  email STRING COLLATE UTF8_BINARY,
  job_title STRING COLLATE UTF8_BINARY,
  job_role_id STRING COLLATE UTF8_BINARY,
  job_role_name STRING COLLATE UTF8_BINARY,
  branch_id STRING COLLATE UTF8_BINARY,
  branch_name STRING COLLATE UTF8_BINARY,
  manager_employee_id STRING COLLATE UTF8_BINARY,
  manager_name STRING COLLATE UTF8_BINARY,
  region_id STRING COLLATE UTF8_BINARY,
  region_name STRING COLLATE UTF8_BINARY,
  vp_employee_id STRING COLLATE UTF8_BINARY,
  vp_name STRING COLLATE UTF8_BINARY,
  hire_date TIMESTAMP,
  employment_status STRING COLLATE UTF8_BINARY,
  employment_type STRING COLLATE UTF8_BINARY)
COMMENT 'Daily materialized copy of app_vw_employee_profile for the Flask performance fast path'
SCHEDULE EVERY 1 DAYS
AS SELECT * FROM workspace.performance_test.app_vw_employee_profile;

-- MATERIALIZED_VIEW: workspace.performance_test.app_fast_employee_quarterly_performance
CREATE MATERIALIZED VIEW `workspace`.`performance_test`.`app_fast_employee_quarterly_performance` (
  employee_id STRING COLLATE UTF8_BINARY,
  employee_name STRING COLLATE UTF8_BINARY,
  branch_id STRING COLLATE UTF8_BINARY,
  branch_name STRING COLLATE UTF8_BINARY,
  region_id STRING COLLATE UTF8_BINARY,
  region_name STRING COLLATE UTF8_BINARY,
  cycle_id STRING COLLATE UTF8_BINARY,
  cycle_name STRING COLLATE UTF8_BINARY,
  cycle_start_date TIMESTAMP,
  cycle_end_date TIMESTAMP,
  cycle_status STRING COLLATE UTF8_BINARY,
  review_id STRING COLLATE UTF8_BINARY,
  review_status STRING COLLATE UTF8_BINARY,
  review_date TIMESTAMP,
  completed_date TIMESTAMP,
  final_rating BIGINT,
  rating_rationale STRING COLLATE UTF8_BINARY,
  reviewer_employee_id STRING COLLATE UTF8_BINARY,
  reviewer_name STRING COLLATE UTF8_BINARY,
  target_amount BIGINT,
  funded_loan_count BIGINT,
  funded_amount BIGINT,
  attainment_percent DOUBLE,
  loan_rating BIGINT,
  snapshot_status STRING COLLATE UTF8_BINARY,
  meeting_id STRING COLLATE UTF8_BINARY,
  meeting_status STRING COLLATE UTF8_BINARY,
  meeting_date TIMESTAMP,
  duration_minutes BIGINT,
  meeting_channel STRING COLLATE UTF8_BINARY,
  acknowledgment_id STRING COLLATE UTF8_BINARY,
  acknowledgment_status STRING COLLATE UTF8_BINARY,
  acknowledgment_date TIMESTAMP,
  acknowledgment_comment STRING COLLATE UTF8_BINARY)
COMMENT 'Daily materialized copy of app_vw_employee_quarterly_performance for the Flask performance fast path'
SCHEDULE EVERY 1 DAYS
AS SELECT * FROM workspace.performance_test.app_vw_employee_quarterly_performance;

-- VIEW: workspace.performance_test.app_fast_review_compliance
CREATE VIEW performance_test.app_fast_review_compliance (
  employee_id,
  employee_name,
  manager_employee_id,
  manager_name,
  branch_id,
  branch_name,
  region_id,
  region_name,
  cycle_id,
  cycle_name,
  cycle_end_date,
  review_due_date,
  review_status,
  meeting_status,
  meeting_date,
  acknowledgment_status,
  is_overdue,
  is_missing_meeting,
  is_missing_acknowledgment)
COMMENT 'Live review compliance over the app_fast_* copies for the Flask performance fast path'
WITH SCHEMA COMPENSATION
AS SELECT
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

-- MANAGED: workspace.performance_test.app_policy_chunks
CREATE TABLE workspace.performance_test.app_policy_chunks (
  chunk_id STRING COLLATE UTF8_BINARY,
  document_name STRING COLLATE UTF8_BINARY,
  document_version STRING COLLATE UTF8_BINARY,
  chunk_to_embed STRING COLLATE UTF8_BINARY,
  chunk_text STRING COLLATE UTF8_BINARY,
  chunk_position INT,
  source_volume_path STRING COLLATE UTF8_BINARY,
  processed_timestamp TIMESTAMP,
  document_title STRING COLLATE UTF8_BINARY,
  page_start INT,
  page_end INT)
USING delta
TBLPROPERTIES (
  'delta.enableChangeDataFeed' = 'true',
  'delta.enableDeletionVectors' = 'true',
  'delta.feature.appendOnly' = 'supported',
  'delta.feature.changeDataFeed' = 'supported',
  'delta.feature.deletionVectors' = 'supported',
  'delta.feature.invariants' = 'supported',
  'delta.minReaderVersion' = '3',
  'delta.minWriterVersion' = '7',
  'delta.parquet.compression.codec' = 'zstd',
  'delta.parquet.format.version' = '2.12.0',
  'delta.parquet.format.version.afe.internal' = '2.12.0');

-- MANAGED: workspace.performance_test.app_policy_chunks_backup_20260924_205300
CREATE TABLE workspace.performance_test.app_policy_chunks_backup_20260924_205300 (
  chunk_id STRING COLLATE UTF8_BINARY,
  document_name STRING COLLATE UTF8_BINARY,
  document_version STRING COLLATE UTF8_BINARY,
  chunk_to_embed STRING COLLATE UTF8_BINARY,
  chunk_text STRING COLLATE UTF8_BINARY,
  chunk_position INT,
  source_volume_path STRING COLLATE UTF8_BINARY,
  processed_timestamp TIMESTAMP,
  document_title STRING COLLATE UTF8_BINARY)
USING delta
TBLPROPERTIES (
  'delta.enableDeletionVectors' = 'true',
  'delta.feature.appendOnly' = 'supported',
  'delta.feature.deletionVectors' = 'supported',
  'delta.feature.invariants' = 'supported',
  'delta.minReaderVersion' = '3',
  'delta.minWriterVersion' = '7',
  'delta.parquet.compression.codec' = 'zstd',
  'delta.parquet.format.version' = '2.12.0',
  'delta.parquet.format.version.afe.internal' = '2.12.0');

-- MANAGED: workspace.performance_test.app_policy_chunks_rebuild
CREATE TABLE workspace.performance_test.app_policy_chunks_rebuild (
  chunk_id STRING COLLATE UTF8_BINARY,
  document_name STRING COLLATE UTF8_BINARY,
  document_version STRING COLLATE UTF8_BINARY,
  chunk_to_embed STRING COLLATE UTF8_BINARY,
  chunk_text STRING COLLATE UTF8_BINARY,
  chunk_position INT,
  source_volume_path STRING COLLATE UTF8_BINARY,
  processed_timestamp TIMESTAMP,
  document_title STRING COLLATE UTF8_BINARY,
  page_start INT,
  page_end INT)
USING delta
TBLPROPERTIES (
  'delta.enableDeletionVectors' = 'true',
  'delta.feature.appendOnly' = 'supported',
  'delta.feature.deletionVectors' = 'supported',
  'delta.feature.invariants' = 'supported',
  'delta.minReaderVersion' = '3',
  'delta.minWriterVersion' = '7',
  'delta.parquet.compression.codec' = 'zstd',
  'delta.parquet.format.version' = '2.12.0',
  'delta.parquet.format.version.afe.internal' = '2.12.0',
  'delta.workloadBasedColumns.deltaFileStatistics' = '`chunk_text`');

-- VIEW: workspace.performance_test.app_vw_branch_quarterly_summary
CREATE VIEW performance_test.app_vw_branch_quarterly_summary (
  region_id,
  region_name,
  branch_id,
  branch_name,
  cycle_id,
  cycle_name,
  employee_count,
  total_target,
  total_funded_amount,
  branch_attainment_pct,
  funded_loan_count,
  avg_rating,
  rating_1_count,
  rating_2_count,
  rating_3_count,
  rating_4_count,
  rating_5_count,
  completed_review_count,
  missing_review_count)
WITH SCHEMA COMPENSATION
AS SELECT
    ep.region_id,
    ep.region_name,
    ep.branch_id,
    ep.branch_name,
    qp.cycle_id,
    qp.cycle_name,
    COUNT(DISTINCT qp.employee_id)  AS employee_count,
    SUM(qp.target_amount)           AS total_target,
    SUM(qp.funded_amount)           AS total_funded_amount,
    CASE WHEN SUM(qp.target_amount) > 0
         THEN ROUND(CAST(SUM(qp.funded_amount) AS DOUBLE) / SUM(qp.target_amount), 4)
         ELSE NULL END              AS branch_attainment_pct,
    SUM(qp.funded_loan_count)       AS funded_loan_count,
    ROUND(AVG(qp.final_rating), 2)  AS avg_rating,
    SUM(CASE WHEN qp.final_rating = 1 THEN 1 ELSE 0 END) AS rating_1_count,
    SUM(CASE WHEN qp.final_rating = 2 THEN 1 ELSE 0 END) AS rating_2_count,
    SUM(CASE WHEN qp.final_rating = 3 THEN 1 ELSE 0 END) AS rating_3_count,
    SUM(CASE WHEN qp.final_rating = 4 THEN 1 ELSE 0 END) AS rating_4_count,
    SUM(CASE WHEN qp.final_rating = 5 THEN 1 ELSE 0 END) AS rating_5_count,
    SUM(CASE WHEN qp.review_status = 'Completed' THEN 1 ELSE 0 END) AS completed_review_count,
    SUM(CASE WHEN qp.review_status != 'Completed' OR qp.review_status IS NULL THEN 1 ELSE 0 END) AS missing_review_count
FROM workspace.performance_test.app_vw_employee_quarterly_performance qp
JOIN workspace.performance_test.app_vw_employee_profile ep
    ON qp.employee_id = ep.employee_id
WHERE ep.branch_id IS NOT NULL
GROUP BY ep.region_id, ep.region_name, ep.branch_id, ep.branch_name, qp.cycle_id, qp.cycle_name;

-- VIEW: workspace.performance_test.app_vw_employee_competency_summary
CREATE VIEW performance_test.app_vw_employee_competency_summary (
  employee_id,
  employee_name,
  cycle_id,
  cycle_name,
  competency_id,
  competency_name,
  competency_rating,
  rating_label,
  rated_by_employee_id,
  rated_by_name,
  rating_date)
WITH SCHEMA COMPENSATION
AS SELECT
    cr.employee_id,
    ep.employee_name,
    cr.cycle_id,
    pc.cycle_name,
    cr.competency_id,
    c.competency_name,
    cr.rating                       AS competency_rating,
    cr.rating_label,
    cr.rated_by_employee_id,
    mgr.full_name                   AS rated_by_name,
    cr.rating_date
FROM workspace.performance_test.competency_rating cr
JOIN workspace.performance_test.app_vw_employee_profile ep
    ON cr.employee_id = ep.employee_id
JOIN workspace.performance_test.performance_cycle pc
    ON cr.cycle_id = pc.cycle_id
JOIN workspace.performance_test.competency c
    ON cr.competency_id = c.competency_id
LEFT JOIN workspace.performance_test.employee mgr
    ON cr.rated_by_employee_id = mgr.employee_id;

-- VIEW: workspace.performance_test.app_vw_employee_goal_status
CREATE VIEW performance_test.app_vw_employee_goal_status (
  employee_id,
  employee_name,
  goal_id,
  goal_type,
  goal_title,
  goal_description,
  goal_status,
  goal_start_date,
  goal_due_date,
  cycle_id,
  cycle_name,
  completion_percent,
  progress_note,
  progress_date)
WITH SCHEMA COMPENSATION
AS SELECT
    pg.employee_id,
    ep.employee_name,
    pg.goal_id,
    pg.goal_type,
    pg.goal_title,
    pg.goal_description,
    pg.goal_status,
    pg.start_date                   AS goal_start_date,
    pg.due_date                     AS goal_due_date,
    gp.cycle_id,
    pc.cycle_name,
    gp.completion_percent,
    gp.progress_note,
    gp.progress_date
FROM workspace.performance_test.performance_goal pg
JOIN workspace.performance_test.app_vw_employee_profile ep
    ON pg.employee_id = ep.employee_id
LEFT JOIN (
    -- Latest progress per goal per cycle
    SELECT *
    FROM (
        SELECT *,
            ROW_NUMBER() OVER (PARTITION BY goal_id, cycle_id ORDER BY progress_date DESC) AS rn
        FROM workspace.performance_test.goal_progress
    )
    WHERE rn = 1
) gp ON pg.goal_id = gp.goal_id
LEFT JOIN workspace.performance_test.performance_cycle pc
    ON gp.cycle_id = pc.cycle_id;

-- VIEW: workspace.performance_test.app_vw_employee_performance_history
CREATE VIEW performance_test.app_vw_employee_performance_history (
  employee_id,
  employee_name,
  job_role_name,
  branch_id,
  branch_name,
  region_id,
  region_name,
  manager_employee_id,
  manager_name,
  cycle_id,
  cycle_name,
  review_status,
  final_rating,
  rating_rationale,
  target_amount,
  funded_amount,
  funded_loan_count,
  attainment_percent,
  loan_rating,
  meeting_status,
  acknowledgment_status,
  avg_competency_rating,
  active_goal_count,
  avg_goal_completion)
WITH SCHEMA COMPENSATION
AS SELECT
    qp.employee_id,
    qp.employee_name,
    ep.job_role_name,
    ep.branch_id,
    ep.branch_name,
    ep.region_id,
    ep.region_name,
    ep.manager_employee_id,
    ep.manager_name,
    qp.cycle_id,
    qp.cycle_name,
    qp.review_status,
    qp.final_rating,
    qp.rating_rationale,
    qp.target_amount,
    qp.funded_amount,
    qp.funded_loan_count,
    qp.attainment_percent,
    qp.loan_rating,
    qp.meeting_status,
    qp.acknowledgment_status,
    -- Avg competency rating for the cycle
    comp_avg.avg_competency_rating,
    -- Latest goal completion
    goal_agg.active_goal_count,
    goal_agg.avg_goal_completion
FROM workspace.performance_test.app_vw_employee_quarterly_performance qp
JOIN workspace.performance_test.app_vw_employee_profile ep
    ON qp.employee_id = ep.employee_id
LEFT JOIN (
    SELECT employee_id, cycle_id, ROUND(AVG(competency_rating), 2) AS avg_competency_rating
    FROM workspace.performance_test.app_vw_employee_competency_summary
    GROUP BY employee_id, cycle_id
) comp_avg ON qp.employee_id = comp_avg.employee_id AND qp.cycle_id = comp_avg.cycle_id
LEFT JOIN (
    SELECT employee_id, cycle_id, 
           COUNT(*) AS active_goal_count,
           ROUND(AVG(completion_percent), 1) AS avg_goal_completion
    FROM workspace.performance_test.app_vw_employee_goal_status
    WHERE cycle_id IS NOT NULL
    GROUP BY employee_id, cycle_id
) goal_agg ON qp.employee_id = goal_agg.employee_id AND qp.cycle_id = goal_agg.cycle_id;

-- VIEW: workspace.performance_test.app_vw_employee_profile
CREATE VIEW performance_test.app_vw_employee_profile (
  employee_id,
  employee_name,
  email,
  job_title,
  job_role_id,
  job_role_name,
  branch_id,
  branch_name,
  manager_employee_id,
  manager_name,
  region_id,
  region_name,
  vp_employee_id,
  vp_name,
  hire_date,
  employment_status,
  employment_type)
WITH SCHEMA COMPENSATION
AS SELECT
    e.employee_id,
    e.full_name                     AS employee_name,
    e.email,
    e.job_title,
    jr.job_role_id,
    jr.job_role_name,
    ea.branch_id,
    b.branch_name,
    ea.manager_employee_id,
    mgr.full_name                   AS manager_name,
    COALESCE(ea.region_id, b.region_id) AS region_id,
    r.region_name,
    r.vp_employee_id,
    vp.full_name                    AS vp_name,
    e.hire_date,
    e.employment_status,
    e.employment_type
FROM workspace.performance_test.employee e
LEFT JOIN workspace.performance_test.employee_assignment ea
    ON e.employee_id = ea.employee_id AND ea.is_current = true
LEFT JOIN workspace.performance_test.job_role jr
    ON ea.job_role_id = jr.job_role_id
LEFT JOIN workspace.performance_test.branch b
    ON ea.branch_id = b.branch_id
LEFT JOIN workspace.performance_test.region r
    ON COALESCE(ea.region_id, b.region_id) = r.region_id
LEFT JOIN workspace.performance_test.employee mgr
    ON ea.manager_employee_id = mgr.employee_id
LEFT JOIN workspace.performance_test.employee vp
    ON r.vp_employee_id = vp.employee_id;

-- VIEW: workspace.performance_test.app_vw_employee_quarterly_performance
CREATE VIEW performance_test.app_vw_employee_quarterly_performance (
  employee_id,
  employee_name,
  branch_id,
  branch_name,
  region_id,
  region_name,
  cycle_id,
  cycle_name,
  cycle_start_date,
  cycle_end_date,
  cycle_status,
  review_id,
  review_status,
  review_date,
  completed_date,
  final_rating,
  rating_rationale,
  reviewer_employee_id,
  reviewer_name,
  target_amount,
  funded_loan_count,
  funded_amount,
  attainment_percent,
  loan_rating,
  snapshot_status,
  meeting_id,
  meeting_status,
  meeting_date,
  duration_minutes,
  meeting_channel,
  acknowledgment_id,
  acknowledgment_status,
  acknowledgment_date,
  acknowledgment_comment)
WITH SCHEMA COMPENSATION
AS SELECT
    er.employee_id,
    ep.employee_name,
    ep.branch_id,
    ep.branch_name,
    ep.region_id,
    ep.region_name,
    er.cycle_id,
    pc.cycle_name,
    pc.start_date                   AS cycle_start_date,
    pc.end_date                     AS cycle_end_date,
    pc.cycle_status,
    er.review_id,
    er.review_status,
    er.review_date,
    er.completed_date,
    er.final_rating,
    er.rating_rationale,
    er.reviewer_employee_id,
    rev_emp.full_name               AS reviewer_name,
    ms.target_amount,
    ms.funded_loan_count,
    ms.funded_amount,
    ms.attainment_percent,
    ms.loan_rating,
    ms.snapshot_status,
    rm.meeting_id,
    rm.meeting_status,
    rm.meeting_date,
    rm.duration_minutes,
    rm.meeting_channel,
    ack.acknowledgment_id,
    ack.acknowledgment_status,
    ack.acknowledgment_date,
    ack.employee_comment            AS acknowledgment_comment
FROM workspace.performance_test.employee_review er
JOIN workspace.performance_test.app_vw_employee_profile ep
    ON er.employee_id = ep.employee_id
JOIN workspace.performance_test.performance_cycle pc
    ON er.cycle_id = pc.cycle_id
LEFT JOIN workspace.performance_test.employee rev_emp
    ON er.reviewer_employee_id = rev_emp.employee_id
LEFT JOIN workspace.performance_test.metric_snapshot ms
    ON er.review_id = ms.review_id
LEFT JOIN workspace.performance_test.review_meeting rm
    ON er.review_id = rm.review_id
LEFT JOIN workspace.performance_test.employee_acknowledgment ack
    ON er.review_id = ack.review_id;

-- VIEW: workspace.performance_test.app_vw_review_compliance
CREATE VIEW performance_test.app_vw_review_compliance (
  employee_id,
  employee_name,
  manager_employee_id,
  manager_name,
  branch_id,
  branch_name,
  region_id,
  region_name,
  cycle_id,
  cycle_name,
  cycle_end_date,
  review_due_date,
  review_status,
  meeting_status,
  meeting_date,
  acknowledgment_status,
  is_overdue,
  is_missing_meeting,
  is_missing_acknowledgment)
WITH SCHEMA COMPENSATION
AS SELECT
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
FROM workspace.performance_test.app_vw_employee_quarterly_performance qp
JOIN workspace.performance_test.app_vw_employee_profile ep
    ON qp.employee_id = ep.employee_id
JOIN workspace.performance_test.performance_cycle pc
    ON qp.cycle_id = pc.cycle_id;

-- MANAGED: workspace.performance_test.branch
CREATE TABLE workspace.performance_test.branch (
  branch_id STRING COLLATE UTF8_BINARY,
  branch_name STRING COLLATE UTF8_BINARY,
  region_id STRING COLLATE UTF8_BINARY,
  city STRING COLLATE UTF8_BINARY,
  state STRING COLLATE UTF8_BINARY,
  manager_employee_id STRING COLLATE UTF8_BINARY,
  effective_start_date TIMESTAMP,
  is_active BOOLEAN)
USING delta
TBLPROPERTIES (
  'delta.enableDeletionVectors' = 'true',
  'delta.feature.appendOnly' = 'supported',
  'delta.feature.deletionVectors' = 'supported',
  'delta.feature.invariants' = 'supported',
  'delta.minReaderVersion' = '3',
  'delta.minWriterVersion' = '7',
  'delta.parquet.compression.codec' = 'zstd',
  'delta.parquet.format.version' = '2.12.0',
  'delta.parquet.format.version.afe.internal' = '2.12.0');

-- MANAGED: workspace.performance_test.career_aspiration
CREATE TABLE workspace.performance_test.career_aspiration (
  aspiration_id STRING COLLATE UTF8_BINARY,
  employee_id STRING COLLATE UTF8_BINARY,
  aspiration_year BIGINT,
  desired_role STRING COLLATE UTF8_BINARY,
  target_timeline STRING COLLATE UTF8_BINARY,
  development_needs STRING COLLATE UTF8_BINARY,
  recorded_by_employee_id STRING COLLATE UTF8_BINARY,
  recorded_date TIMESTAMP)
USING delta
TBLPROPERTIES (
  'delta.enableDeletionVectors' = 'true',
  'delta.feature.appendOnly' = 'supported',
  'delta.feature.deletionVectors' = 'supported',
  'delta.feature.invariants' = 'supported',
  'delta.minReaderVersion' = '3',
  'delta.minWriterVersion' = '7',
  'delta.parquet.compression.codec' = 'zstd',
  'delta.parquet.format.version' = '2.12.0',
  'delta.parquet.format.version.afe.internal' = '2.12.0');

-- MANAGED: workspace.performance_test.competency
CREATE TABLE workspace.performance_test.competency (
  competency_id STRING COLLATE UTF8_BINARY,
  competency_name STRING COLLATE UTF8_BINARY,
  competency_description STRING COLLATE UTF8_BINARY,
  display_order BIGINT,
  is_active BOOLEAN)
USING delta
TBLPROPERTIES (
  'delta.enableDeletionVectors' = 'true',
  'delta.feature.appendOnly' = 'supported',
  'delta.feature.deletionVectors' = 'supported',
  'delta.feature.invariants' = 'supported',
  'delta.minReaderVersion' = '3',
  'delta.minWriterVersion' = '7',
  'delta.parquet.compression.codec' = 'zstd',
  'delta.parquet.format.version' = '2.12.0',
  'delta.parquet.format.version.afe.internal' = '2.12.0');

-- MANAGED: workspace.performance_test.competency_rating
CREATE TABLE workspace.performance_test.competency_rating (
  competency_rating_id STRING COLLATE UTF8_BINARY,
  review_id STRING COLLATE UTF8_BINARY,
  employee_id STRING COLLATE UTF8_BINARY,
  cycle_id STRING COLLATE UTF8_BINARY,
  competency_id STRING COLLATE UTF8_BINARY,
  rating BIGINT,
  rating_label STRING COLLATE UTF8_BINARY,
  rated_by_employee_id STRING COLLATE UTF8_BINARY,
  rating_date TIMESTAMP)
USING delta
TBLPROPERTIES (
  'delta.enableDeletionVectors' = 'true',
  'delta.feature.appendOnly' = 'supported',
  'delta.feature.deletionVectors' = 'supported',
  'delta.feature.invariants' = 'supported',
  'delta.minReaderVersion' = '3',
  'delta.minWriterVersion' = '7',
  'delta.parquet.compression.codec' = 'zstd',
  'delta.parquet.format.version' = '2.12.0',
  'delta.parquet.format.version.afe.internal' = '2.12.0');

-- MANAGED: workspace.performance_test.employee
CREATE TABLE workspace.performance_test.employee (
  employee_id STRING COLLATE UTF8_BINARY,
  first_name STRING COLLATE UTF8_BINARY,
  last_name STRING COLLATE UTF8_BINARY,
  full_name STRING COLLATE UTF8_BINARY,
  email STRING COLLATE UTF8_BINARY,
  job_title STRING COLLATE UTF8_BINARY,
  hire_date TIMESTAMP,
  employment_status STRING COLLATE UTF8_BINARY,
  employment_type STRING COLLATE UTF8_BINARY)
USING delta
TBLPROPERTIES (
  'delta.enableDeletionVectors' = 'true',
  'delta.feature.appendOnly' = 'supported',
  'delta.feature.deletionVectors' = 'supported',
  'delta.feature.invariants' = 'supported',
  'delta.minReaderVersion' = '3',
  'delta.minWriterVersion' = '7',
  'delta.parquet.compression.codec' = 'zstd',
  'delta.parquet.format.version' = '2.12.0',
  'delta.parquet.format.version.afe.internal' = '2.12.0');

-- MANAGED: workspace.performance_test.employee_acknowledgment
CREATE TABLE workspace.performance_test.employee_acknowledgment (
  acknowledgment_id STRING COLLATE UTF8_BINARY,
  review_id STRING COLLATE UTF8_BINARY,
  employee_id STRING COLLATE UTF8_BINARY,
  acknowledgment_status STRING COLLATE UTF8_BINARY,
  acknowledgment_date TIMESTAMP,
  employee_comment STRING COLLATE UTF8_BINARY)
USING delta
TBLPROPERTIES (
  'delta.enableDeletionVectors' = 'true',
  'delta.feature.appendOnly' = 'supported',
  'delta.feature.deletionVectors' = 'supported',
  'delta.feature.invariants' = 'supported',
  'delta.minReaderVersion' = '3',
  'delta.minWriterVersion' = '7',
  'delta.parquet.compression.codec' = 'zstd',
  'delta.parquet.format.version' = '2.12.0',
  'delta.parquet.format.version.afe.internal' = '2.12.0');

-- MANAGED: workspace.performance_test.employee_assignment
CREATE TABLE workspace.performance_test.employee_assignment (
  assignment_id STRING COLLATE UTF8_BINARY,
  employee_id STRING COLLATE UTF8_BINARY,
  job_role_id STRING COLLATE UTF8_BINARY,
  region_id STRING COLLATE UTF8_BINARY,
  branch_id STRING COLLATE UTF8_BINARY,
  manager_employee_id STRING COLLATE UTF8_BINARY,
  effective_start_date TIMESTAMP,
  effective_end_date DOUBLE,
  is_current BOOLEAN)
USING delta
TBLPROPERTIES (
  'delta.enableDeletionVectors' = 'true',
  'delta.feature.appendOnly' = 'supported',
  'delta.feature.deletionVectors' = 'supported',
  'delta.feature.invariants' = 'supported',
  'delta.minReaderVersion' = '3',
  'delta.minWriterVersion' = '7',
  'delta.parquet.compression.codec' = 'zstd',
  'delta.parquet.format.version' = '2.12.0',
  'delta.parquet.format.version.afe.internal' = '2.12.0');

-- MANAGED: workspace.performance_test.employee_review
CREATE TABLE workspace.performance_test.employee_review (
  review_id STRING COLLATE UTF8_BINARY,
  employee_id STRING COLLATE UTF8_BINARY,
  cycle_id STRING COLLATE UTF8_BINARY,
  reviewer_employee_id STRING COLLATE UTF8_BINARY,
  branch_id STRING COLLATE UTF8_BINARY,
  review_status STRING COLLATE UTF8_BINARY,
  final_rating BIGINT,
  rating_rationale STRING COLLATE UTF8_BINARY,
  review_date TIMESTAMP,
  completed_date TIMESTAMP)
USING delta
TBLPROPERTIES (
  'delta.enableDeletionVectors' = 'true',
  'delta.feature.appendOnly' = 'supported',
  'delta.feature.deletionVectors' = 'supported',
  'delta.feature.invariants' = 'supported',
  'delta.minReaderVersion' = '3',
  'delta.minWriterVersion' = '7',
  'delta.parquet.compression.codec' = 'zstd',
  'delta.parquet.format.version' = '2.12.0',
  'delta.parquet.format.version.afe.internal' = '2.12.0');

-- MANAGED: workspace.performance_test.goal_progress
CREATE TABLE workspace.performance_test.goal_progress (
  progress_id STRING COLLATE UTF8_BINARY,
  goal_id STRING COLLATE UTF8_BINARY,
  cycle_id STRING COLLATE UTF8_BINARY,
  completion_percent BIGINT,
  progress_note STRING COLLATE UTF8_BINARY,
  progress_date TIMESTAMP,
  updated_by_employee_id STRING COLLATE UTF8_BINARY)
USING delta
TBLPROPERTIES (
  'delta.enableDeletionVectors' = 'true',
  'delta.feature.appendOnly' = 'supported',
  'delta.feature.deletionVectors' = 'supported',
  'delta.feature.invariants' = 'supported',
  'delta.minReaderVersion' = '3',
  'delta.minWriterVersion' = '7',
  'delta.parquet.compression.codec' = 'zstd',
  'delta.parquet.format.version' = '2.12.0',
  'delta.parquet.format.version.afe.internal' = '2.12.0');

-- MANAGED: workspace.performance_test.job_role
CREATE TABLE workspace.performance_test.job_role (
  job_role_id STRING COLLATE UTF8_BINARY,
  job_role_name STRING COLLATE UTF8_BINARY,
  role_category STRING COLLATE UTF8_BINARY,
  hierarchy_level BIGINT,
  is_active BOOLEAN)
USING delta
TBLPROPERTIES (
  'delta.enableDeletionVectors' = 'true',
  'delta.feature.appendOnly' = 'supported',
  'delta.feature.deletionVectors' = 'supported',
  'delta.feature.invariants' = 'supported',
  'delta.minReaderVersion' = '3',
  'delta.minWriterVersion' = '7',
  'delta.parquet.compression.codec' = 'zstd',
  'delta.parquet.format.version' = '2.12.0',
  'delta.parquet.format.version.afe.internal' = '2.12.0');

-- MANAGED: workspace.performance_test.loan_transaction
CREATE TABLE workspace.performance_test.loan_transaction (
  loan_id STRING COLLATE UTF8_BINARY,
  source_loan_id STRING COLLATE UTF8_BINARY,
  employee_id STRING COLLATE UTF8_BINARY,
  cycle_id STRING COLLATE UTF8_BINARY,
  branch_id STRING COLLATE UTF8_BINARY,
  application_date TIMESTAMP,
  loan_status STRING COLLATE UTF8_BINARY,
  loan_amount BIGINT,
  loan_product STRING COLLATE UTF8_BINARY,
  borrower_segment STRING COLLATE UTF8_BINARY,
  funded_date TIMESTAMP)
USING delta
TBLPROPERTIES (
  'delta.enableDeletionVectors' = 'true',
  'delta.feature.appendOnly' = 'supported',
  'delta.feature.deletionVectors' = 'supported',
  'delta.feature.invariants' = 'supported',
  'delta.minReaderVersion' = '3',
  'delta.minWriterVersion' = '7',
  'delta.parquet.compression.codec' = 'zstd',
  'delta.parquet.format.version' = '2.12.0',
  'delta.parquet.format.version.afe.internal' = '2.12.0');

-- MANAGED: workspace.performance_test.meeting_note
CREATE TABLE workspace.performance_test.meeting_note (
  note_id STRING COLLATE UTF8_BINARY,
  meeting_id STRING COLLATE UTF8_BINARY,
  discussion_topic STRING COLLATE UTF8_BINARY,
  note_text STRING COLLATE UTF8_BINARY,
  created_by_employee_id STRING COLLATE UTF8_BINARY,
  created_at TIMESTAMP,
  visibility STRING COLLATE UTF8_BINARY)
USING delta
TBLPROPERTIES (
  'delta.enableDeletionVectors' = 'true',
  'delta.feature.appendOnly' = 'supported',
  'delta.feature.deletionVectors' = 'supported',
  'delta.feature.invariants' = 'supported',
  'delta.minReaderVersion' = '3',
  'delta.minWriterVersion' = '7',
  'delta.parquet.compression.codec' = 'zstd',
  'delta.parquet.format.version' = '2.12.0',
  'delta.parquet.format.version.afe.internal' = '2.12.0');

-- MANAGED: workspace.performance_test.metric_snapshot
CREATE TABLE workspace.performance_test.metric_snapshot (
  snapshot_id STRING COLLATE UTF8_BINARY,
  review_id STRING COLLATE UTF8_BINARY,
  employee_id STRING COLLATE UTF8_BINARY,
  cycle_id STRING COLLATE UTF8_BINARY,
  target_amount BIGINT,
  funded_loan_count BIGINT,
  funded_amount BIGINT,
  attainment_percent DOUBLE,
  loan_rating BIGINT,
  snapshot_date TIMESTAMP,
  snapshot_status STRING COLLATE UTF8_BINARY)
USING delta
TBLPROPERTIES (
  'delta.enableDeletionVectors' = 'true',
  'delta.feature.appendOnly' = 'supported',
  'delta.feature.deletionVectors' = 'supported',
  'delta.feature.invariants' = 'supported',
  'delta.minReaderVersion' = '3',
  'delta.minWriterVersion' = '7',
  'delta.parquet.compression.codec' = 'zstd',
  'delta.parquet.format.version' = '2.12.0',
  'delta.parquet.format.version.afe.internal' = '2.12.0');

-- VIEW: workspace.performance_test.perf_citation_registry
CREATE VIEW performance_test.perf_citation_registry (
  document_id COMMENT 'Registry document_id: SHA2(domain, source path)',
  document_version COMMENT 'Registry document_version: SHA2 of all (page,text) of the document',
  chunk_id COMMENT 'Registry chunk_id: SHA2(version, page, text)',
  document_title COMMENT 'Registry document_title (exact value Flask validates)',
  domain,
  source_volume_path,
  page_start,
  page_end,
  chunk_text COMMENT 'Exact approved passage text (same bytes as registry chunk_text)',
  retrieval_id COMMENT 'SHA2-256 of document_id|document_version|chunk_id; index primary key')
COMMENT 'Authoritative citation registry for the Employee Performance Policy. Same IDs as workspace.default.app_citation_registry. Flask DATABRICKS_CITATION_REGISTRY_TABLE.'
WITH SCHEMA COMPENSATION
AS SELECT document_id, document_version, chunk_id, document_title, domain, source_volume_path,
          page_start, page_end, chunk_text, retrieval_id
   FROM workspace.performance_test.perf_policy_retrieval;

-- VIEW: workspace.performance_test.perf_policy_candidates_v
CREATE VIEW performance_test.perf_policy_candidates_v (
  source_chunk_id,
  document_id,
  document_version,
  chunk_id,
  document_title,
  domain,
  source_volume_path,
  page_start,
  page_end,
  chunk_text,
  retrieval_id,
  registry_match_count,
  registry_id_match_count,
  source_dup_count)
COMMENT 'Perf policy passages with registry-formula IDs and exact-match validation against workspace.default.app_citation_registry'
WITH SCHEMA COMPENSATION
AS WITH src AS (
  SELECT chunk_id AS source_chunk_id,
         'Employee Performance Policy' AS domain,
         document_name AS document_title,
         source_volume_path,
         TRY_CAST(page_start AS INT) AS page_start,
         CAST(chunk_text AS STRING) AS chunk_text
  FROM workspace.performance_test.app_policy_chunks
  WHERE source_volume_path LIKE '/Volumes/workspace/performance_test/data/%'
),
valid AS (
  SELECT * FROM src
  WHERE page_start >= 1 AND chunk_text IS NOT NULL AND document_title IS NOT NULL AND source_volume_path IS NOT NULL
),
docs AS (
  SELECT domain, document_title, source_volume_path,
         SHA2(TO_JSON(NAMED_STRUCT('domain', domain, 'path', source_volume_path)), 256) AS document_id,
         SHA2(TO_JSON(SORT_ARRAY(COLLECT_SET(NAMED_STRUCT('page', page_start, 'text', chunk_text)))), 256) AS document_version
  FROM valid GROUP BY domain, document_title, source_volume_path
),
cand AS (
  SELECT v.source_chunk_id, d.document_id, d.document_version,
         SHA2(TO_JSON(NAMED_STRUCT('version', d.document_version, 'page', v.page_start, 'text', v.chunk_text)), 256) AS chunk_id,
         d.document_title, d.domain, d.source_volume_path, v.page_start, v.page_start AS page_end, v.chunk_text
  FROM docs d JOIN valid v
    ON d.domain = v.domain AND d.document_title = v.document_title AND d.source_volume_path = v.source_volume_path
)
SELECT c.*,
       SHA2(CONCAT_WS('|', c.document_id, c.document_version, c.chunk_id), 256) AS retrieval_id,
       (SELECT COUNT(*) FROM workspace.default.app_citation_registry r
         WHERE r.domain = c.domain AND r.source_volume_path = c.source_volume_path
           AND r.page_start = c.page_start AND r.chunk_text = c.chunk_text) AS registry_match_count,
       (SELECT COUNT(*) FROM workspace.default.app_citation_registry r
         WHERE r.domain = c.domain AND r.source_volume_path = c.source_volume_path
           AND r.page_start = c.page_start AND r.chunk_text = c.chunk_text
           AND r.document_id = c.document_id AND r.document_version = c.document_version
           AND r.chunk_id = c.chunk_id AND r.document_title = c.document_title) AS registry_id_match_count,
       (SELECT COUNT(*) FROM valid v2
         WHERE v2.source_volume_path = c.source_volume_path AND v2.page_start = c.page_start
           AND v2.chunk_text = c.chunk_text) AS source_dup_count
FROM cand c;

-- MANAGED: workspace.performance_test.perf_policy_retrieval
CREATE TABLE workspace.performance_test.perf_policy_retrieval (
  retrieval_id STRING COLLATE UTF8_BINARY NOT NULL COMMENT 'SHA2-256 of document_id|document_version|chunk_id; index primary key',
  chunk_text STRING COLLATE UTF8_BINARY NOT NULL COMMENT 'Exact approved passage text (same bytes as registry chunk_text)',
  document_id STRING COLLATE UTF8_BINARY NOT NULL COMMENT 'Registry document_id: SHA2(domain, source path)',
  document_version STRING COLLATE UTF8_BINARY NOT NULL COMMENT 'Registry document_version: SHA2 of all (page,text) of the document',
  chunk_id STRING COLLATE UTF8_BINARY NOT NULL COMMENT 'Registry chunk_id: SHA2(version, page, text)',
  document_title STRING COLLATE UTF8_BINARY NOT NULL COMMENT 'Registry document_title (exact value Flask validates)',
  page_start INT NOT NULL,
  page_end INT NOT NULL,
  domain STRING COLLATE UTF8_BINARY NOT NULL,
  source_volume_path STRING COLLATE UTF8_BINARY NOT NULL,
  source_chunk_id STRING COLLATE UTF8_BINARY COMMENT 'Lineage: chunk_id in workspace.performance_test.app_policy_chunks',
  refreshed_at TIMESTAMP NOT NULL)
USING delta
COMMENT 'Approved Employee Performance Policy passages with authoritative citation metadata for structured retrieval'
TBLPROPERTIES (
  'delta.enableChangeDataFeed' = 'true',
  'delta.enableDeletionVectors' = 'true',
  'delta.enableRowTracking' = 'true',
  'delta.feature.appendOnly' = 'supported',
  'delta.feature.changeDataFeed' = 'supported',
  'delta.feature.deletionVectors' = 'supported',
  'delta.feature.domainMetadata' = 'supported',
  'delta.feature.invariants' = 'supported',
  'delta.feature.rowTracking' = 'supported',
  'delta.minReaderVersion' = '3',
  'delta.minWriterVersion' = '7',
  'delta.parquet.compression.codec' = 'zstd',
  'delta.parquet.format.version' = '2.12.0',
  'delta.parquet.format.version.afe.internal' = '2.12.0');

-- MANAGED: workspace.performance_test.perf_policy_retrieval_rejects
CREATE TABLE workspace.performance_test.perf_policy_retrieval_rejects (
  source_chunk_id STRING COLLATE UTF8_BINARY,
  source_volume_path STRING COLLATE UTF8_BINARY,
  page_start INT,
  reason STRING COLLATE UTF8_BINARY,
  registry_match_count BIGINT,
  rejected_at TIMESTAMP)
USING delta
COMMENT 'Source chunks rejected from structured retrieval (missing/ambiguous registry match, invalid page, out-of-scope path)'
TBLPROPERTIES (
  'delta.enableDeletionVectors' = 'true',
  'delta.enableRowTracking' = 'true',
  'delta.feature.appendOnly' = 'supported',
  'delta.feature.deletionVectors' = 'supported',
  'delta.feature.domainMetadata' = 'supported',
  'delta.feature.invariants' = 'supported',
  'delta.feature.rowTracking' = 'supported',
  'delta.minReaderVersion' = '3',
  'delta.minWriterVersion' = '7',
  'delta.parquet.compression.codec' = 'zstd',
  'delta.parquet.format.version' = '2.12.0',
  'delta.parquet.format.version.afe.internal' = '2.12.0');

-- MANAGED: workspace.performance_test.performance_cycle
CREATE TABLE workspace.performance_test.performance_cycle (
  cycle_id STRING COLLATE UTF8_BINARY,
  cycle_name STRING COLLATE UTF8_BINARY,
  start_date TIMESTAMP,
  end_date TIMESTAMP,
  review_due_date TIMESTAMP,
  cycle_status STRING COLLATE UTF8_BINARY)
USING delta
TBLPROPERTIES (
  'delta.enableDeletionVectors' = 'true',
  'delta.feature.appendOnly' = 'supported',
  'delta.feature.deletionVectors' = 'supported',
  'delta.feature.invariants' = 'supported',
  'delta.minReaderVersion' = '3',
  'delta.minWriterVersion' = '7',
  'delta.parquet.compression.codec' = 'zstd',
  'delta.parquet.format.version' = '2.12.0',
  'delta.parquet.format.version.afe.internal' = '2.12.0');

-- MANAGED: workspace.performance_test.performance_goal
CREATE TABLE workspace.performance_test.performance_goal (
  goal_id STRING COLLATE UTF8_BINARY,
  employee_id STRING COLLATE UTF8_BINARY,
  goal_type STRING COLLATE UTF8_BINARY,
  goal_title STRING COLLATE UTF8_BINARY,
  goal_description STRING COLLATE UTF8_BINARY,
  start_date TIMESTAMP,
  due_date TIMESTAMP,
  goal_status STRING COLLATE UTF8_BINARY,
  created_by_employee_id STRING COLLATE UTF8_BINARY)
USING delta
TBLPROPERTIES (
  'delta.enableDeletionVectors' = 'true',
  'delta.feature.appendOnly' = 'supported',
  'delta.feature.deletionVectors' = 'supported',
  'delta.feature.invariants' = 'supported',
  'delta.minReaderVersion' = '3',
  'delta.minWriterVersion' = '7',
  'delta.parquet.compression.codec' = 'zstd',
  'delta.parquet.format.version' = '2.12.0',
  'delta.parquet.format.version.afe.internal' = '2.12.0');

-- MANAGED: workspace.performance_test.performance_target
CREATE TABLE workspace.performance_test.performance_target (
  target_id STRING COLLATE UTF8_BINARY,
  cycle_id STRING COLLATE UTF8_BINARY,
  target_scope_type STRING COLLATE UTF8_BINARY,
  target_scope_id STRING COLLATE UTF8_BINARY,
  target_metric STRING COLLATE UTF8_BINARY,
  target_value BIGINT,
  currency STRING COLLATE UTF8_BINARY,
  assigned_date TIMESTAMP,
  approved_by_employee_id STRING COLLATE UTF8_BINARY)
USING delta
TBLPROPERTIES (
  'delta.enableDeletionVectors' = 'true',
  'delta.feature.appendOnly' = 'supported',
  'delta.feature.deletionVectors' = 'supported',
  'delta.feature.invariants' = 'supported',
  'delta.minReaderVersion' = '3',
  'delta.minWriterVersion' = '7',
  'delta.parquet.compression.codec' = 'zstd',
  'delta.parquet.format.version' = '2.12.0',
  'delta.parquet.format.version.afe.internal' = '2.12.0');

-- MANAGED: workspace.performance_test.region
CREATE TABLE workspace.performance_test.region (
  region_id STRING COLLATE UTF8_BINARY,
  region_name STRING COLLATE UTF8_BINARY,
  vp_employee_id STRING COLLATE UTF8_BINARY,
  effective_start_date TIMESTAMP,
  is_active BOOLEAN)
USING delta
TBLPROPERTIES (
  'delta.enableDeletionVectors' = 'true',
  'delta.feature.appendOnly' = 'supported',
  'delta.feature.deletionVectors' = 'supported',
  'delta.feature.invariants' = 'supported',
  'delta.minReaderVersion' = '3',
  'delta.minWriterVersion' = '7',
  'delta.parquet.compression.codec' = 'zstd',
  'delta.parquet.format.version' = '2.12.0',
  'delta.parquet.format.version.afe.internal' = '2.12.0');

-- MANAGED: workspace.performance_test.review_meeting
CREATE TABLE workspace.performance_test.review_meeting (
  meeting_id STRING COLLATE UTF8_BINARY,
  review_id STRING COLLATE UTF8_BINARY,
  employee_id STRING COLLATE UTF8_BINARY,
  manager_employee_id STRING COLLATE UTF8_BINARY,
  meeting_date TIMESTAMP,
  duration_minutes BIGINT,
  meeting_status STRING COLLATE UTF8_BINARY,
  meeting_purpose STRING COLLATE UTF8_BINARY,
  meeting_channel STRING COLLATE UTF8_BINARY)
USING delta
TBLPROPERTIES (
  'delta.enableDeletionVectors' = 'true',
  'delta.feature.appendOnly' = 'supported',
  'delta.feature.deletionVectors' = 'supported',
  'delta.feature.invariants' = 'supported',
  'delta.minReaderVersion' = '3',
  'delta.minWriterVersion' = '7',
  'delta.parquet.compression.codec' = 'zstd',
  'delta.parquet.format.version' = '2.12.0',
  'delta.parquet.format.version.afe.internal' = '2.12.0');
