-- Performance tables
-- Generated from the trial workspace DDL (structure only, no data).
-- Run in order in the prod workspace with a serverless SQL warehouse.

-- Performance source data (18 tables). Data is loaded by notebooks/02_migrate_data.py.

-- workspace.performance_test.region
CREATE TABLE IF NOT EXISTS workspace.performance_test.region (
  region_id STRING,
  region_name STRING,
  vp_employee_id STRING,
  effective_start_date TIMESTAMP,
  is_active BOOLEAN)
USING delta;

-- workspace.performance_test.branch
CREATE TABLE IF NOT EXISTS workspace.performance_test.branch (
  branch_id STRING,
  branch_name STRING,
  region_id STRING,
  city STRING,
  state STRING,
  manager_employee_id STRING,
  effective_start_date TIMESTAMP,
  is_active BOOLEAN)
USING delta;

-- workspace.performance_test.job_role
CREATE TABLE IF NOT EXISTS workspace.performance_test.job_role (
  job_role_id STRING,
  job_role_name STRING,
  role_category STRING,
  hierarchy_level BIGINT,
  is_active BOOLEAN)
USING delta;

-- workspace.performance_test.employee
CREATE TABLE IF NOT EXISTS workspace.performance_test.employee (
  employee_id STRING,
  first_name STRING,
  last_name STRING,
  full_name STRING,
  email STRING,
  job_title STRING,
  hire_date TIMESTAMP,
  employment_status STRING,
  employment_type STRING)
USING delta;

-- workspace.performance_test.employee_assignment
CREATE TABLE IF NOT EXISTS workspace.performance_test.employee_assignment (
  assignment_id STRING,
  employee_id STRING,
  job_role_id STRING,
  region_id STRING,
  branch_id STRING,
  manager_employee_id STRING,
  effective_start_date TIMESTAMP,
  effective_end_date DOUBLE,
  is_current BOOLEAN)
USING delta;

-- workspace.performance_test.performance_cycle
CREATE TABLE IF NOT EXISTS workspace.performance_test.performance_cycle (
  cycle_id STRING,
  cycle_name STRING,
  start_date TIMESTAMP,
  end_date TIMESTAMP,
  review_due_date TIMESTAMP,
  cycle_status STRING)
USING delta;

-- workspace.performance_test.performance_target
CREATE TABLE IF NOT EXISTS workspace.performance_test.performance_target (
  target_id STRING,
  cycle_id STRING,
  target_scope_type STRING,
  target_scope_id STRING,
  target_metric STRING,
  target_value BIGINT,
  currency STRING,
  assigned_date TIMESTAMP,
  approved_by_employee_id STRING)
USING delta;

-- workspace.performance_test.metric_snapshot
CREATE TABLE IF NOT EXISTS workspace.performance_test.metric_snapshot (
  snapshot_id STRING,
  review_id STRING,
  employee_id STRING,
  cycle_id STRING,
  target_amount BIGINT,
  funded_loan_count BIGINT,
  funded_amount BIGINT,
  attainment_percent DOUBLE,
  loan_rating BIGINT,
  snapshot_date TIMESTAMP,
  snapshot_status STRING)
USING delta;

-- workspace.performance_test.loan_transaction
CREATE TABLE IF NOT EXISTS workspace.performance_test.loan_transaction (
  loan_id STRING,
  source_loan_id STRING,
  employee_id STRING,
  cycle_id STRING,
  branch_id STRING,
  application_date TIMESTAMP,
  loan_status STRING,
  loan_amount BIGINT,
  loan_product STRING,
  borrower_segment STRING,
  funded_date TIMESTAMP)
USING delta;

-- workspace.performance_test.employee_review
CREATE TABLE IF NOT EXISTS workspace.performance_test.employee_review (
  review_id STRING,
  employee_id STRING,
  cycle_id STRING,
  reviewer_employee_id STRING,
  branch_id STRING,
  review_status STRING,
  final_rating BIGINT,
  rating_rationale STRING,
  review_date TIMESTAMP,
  completed_date TIMESTAMP)
USING delta;

-- workspace.performance_test.review_meeting
CREATE TABLE IF NOT EXISTS workspace.performance_test.review_meeting (
  meeting_id STRING,
  review_id STRING,
  employee_id STRING,
  manager_employee_id STRING,
  meeting_date TIMESTAMP,
  duration_minutes BIGINT,
  meeting_status STRING,
  meeting_purpose STRING,
  meeting_channel STRING)
USING delta;

-- workspace.performance_test.employee_acknowledgment
CREATE TABLE IF NOT EXISTS workspace.performance_test.employee_acknowledgment (
  acknowledgment_id STRING,
  review_id STRING,
  employee_id STRING,
  acknowledgment_status STRING,
  acknowledgment_date TIMESTAMP,
  employee_comment STRING)
USING delta;

-- workspace.performance_test.competency
CREATE TABLE IF NOT EXISTS workspace.performance_test.competency (
  competency_id STRING,
  competency_name STRING,
  competency_description STRING,
  display_order BIGINT,
  is_active BOOLEAN)
USING delta;

-- workspace.performance_test.competency_rating
CREATE TABLE IF NOT EXISTS workspace.performance_test.competency_rating (
  competency_rating_id STRING,
  review_id STRING,
  employee_id STRING,
  cycle_id STRING,
  competency_id STRING,
  rating BIGINT,
  rating_label STRING,
  rated_by_employee_id STRING,
  rating_date TIMESTAMP)
USING delta;

-- workspace.performance_test.performance_goal
CREATE TABLE IF NOT EXISTS workspace.performance_test.performance_goal (
  goal_id STRING,
  employee_id STRING,
  goal_type STRING,
  goal_title STRING,
  goal_description STRING,
  start_date TIMESTAMP,
  due_date TIMESTAMP,
  goal_status STRING,
  created_by_employee_id STRING)
USING delta;

-- workspace.performance_test.goal_progress
CREATE TABLE IF NOT EXISTS workspace.performance_test.goal_progress (
  progress_id STRING,
  goal_id STRING,
  cycle_id STRING,
  completion_percent BIGINT,
  progress_note STRING,
  progress_date TIMESTAMP,
  updated_by_employee_id STRING)
USING delta;

-- workspace.performance_test.career_aspiration
CREATE TABLE IF NOT EXISTS workspace.performance_test.career_aspiration (
  aspiration_id STRING,
  employee_id STRING,
  aspiration_year BIGINT,
  desired_role STRING,
  target_timeline STRING,
  development_needs STRING,
  recorded_by_employee_id STRING,
  recorded_date TIMESTAMP)
USING delta;

-- workspace.performance_test.meeting_note
CREATE TABLE IF NOT EXISTS workspace.performance_test.meeting_note (
  note_id STRING,
  meeting_id STRING,
  discussion_topic STRING,
  note_text STRING,
  created_by_employee_id STRING,
  created_at TIMESTAMP,
  visibility STRING)
USING delta;

-- Performance policy chunks (source of performance_index) and structured retrieval (source of perf_policy_retrieval_index).

-- workspace.performance_test.app_policy_chunks
CREATE TABLE IF NOT EXISTS workspace.performance_test.app_policy_chunks (
  chunk_id STRING,
  document_name STRING,
  document_version STRING,
  chunk_to_embed STRING,
  chunk_text STRING,
  chunk_position INT,
  source_volume_path STRING,
  processed_timestamp TIMESTAMP,
  document_title STRING,
  page_start INT,
  page_end INT)
USING delta
TBLPROPERTIES (
  'delta.enableChangeDataFeed' = 'true',
  'delta.deletedFileRetentionDuration' = 'interval 90 days',
  'delta.logRetentionDuration' = 'interval 90 days');

-- workspace.performance_test.perf_policy_retrieval
CREATE TABLE IF NOT EXISTS workspace.performance_test.perf_policy_retrieval (
  retrieval_id STRING NOT NULL COMMENT 'SHA2-256 of document_id|document_version|chunk_id; index primary key',
  chunk_text STRING NOT NULL COMMENT 'Exact approved passage text (same bytes as registry chunk_text)',
  document_id STRING NOT NULL COMMENT 'Registry document_id: SHA2(domain, source path)',
  document_version STRING NOT NULL COMMENT 'Registry document_version: SHA2 of all (page,text) of the document',
  chunk_id STRING NOT NULL COMMENT 'Registry chunk_id: SHA2(version, page, text)',
  document_title STRING NOT NULL COMMENT 'Registry document_title (exact value Flask validates)',
  page_start INT NOT NULL,
  page_end INT NOT NULL,
  domain STRING NOT NULL,
  source_volume_path STRING NOT NULL,
  source_chunk_id STRING COMMENT 'Lineage: chunk_id in workspace.performance_test.app_policy_chunks',
  refreshed_at TIMESTAMP NOT NULL)
USING delta
COMMENT 'Approved Employee Performance Policy passages with authoritative citation metadata for structured retrieval'
TBLPROPERTIES (
  'delta.enableChangeDataFeed' = 'true',
  'delta.deletedFileRetentionDuration' = 'interval 90 days',
  'delta.logRetentionDuration' = 'interval 90 days');

-- workspace.performance_test.perf_policy_retrieval_rejects
CREATE TABLE IF NOT EXISTS workspace.performance_test.perf_policy_retrieval_rejects (
  source_chunk_id STRING,
  source_volume_path STRING,
  page_start INT,
  reason STRING,
  registry_match_count BIGINT,
  rejected_at TIMESTAMP)
USING delta
COMMENT 'Source chunks rejected from structured retrieval (missing/ambiguous registry match, invalid page, out-of-scope path)';

-- workspace.performance_test.app_evaluation_dataset
CREATE TABLE IF NOT EXISTS workspace.performance_test.app_evaluation_dataset (
  category STRING,
  expected_facts STRING,
  question STRING)
USING delta;

