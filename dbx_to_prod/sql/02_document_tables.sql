-- Document pipeline tables (parsed documents and chunks)
-- Generated from the trial workspace DDL (structure only, no data).
-- Run in order in the prod workspace with a serverless SQL warehouse.

-- workspace.default.branch_operations_parsed_documents
CREATE TABLE IF NOT EXISTS workspace.default.branch_operations_parsed_documents (
  document_id STRING,
  domain STRING,
  source_path STRING,
  file_name STRING,
  file_size_bytes BIGINT,
  source_modified_at TIMESTAMP,
  parsed_content VARIANT,
  parsed_at TIMESTAMP)
USING delta;

-- workspace.default.branch_operations_chunks
CREATE TABLE IF NOT EXISTS workspace.default.branch_operations_chunks (
  chunk_id STRING,
  document_id STRING,
  domain STRING,
  source_path STRING,
  volume_path STRING,
  file_name STRING,
  document_title STRING,
  page_start INT,
  page_end INT,
  page_chunk_number INT,
  first_element_position INT,
  last_element_position INT,
  minimum_confidence DOUBLE,
  chunk_text STRING,
  embedding_text STRING,
  character_count INT,
  citation_label STRING,
  created_at TIMESTAMP)
USING delta
TBLPROPERTIES (
  'delta.enableChangeDataFeed' = 'true',
  'delta.deletedFileRetentionDuration' = 'interval 90 days',
  'delta.logRetentionDuration' = 'interval 90 days');

-- workspace.default.employee_handbook_parsed_documents
CREATE TABLE IF NOT EXISTS workspace.default.employee_handbook_parsed_documents (
  document_id STRING,
  domain STRING,
  source_path STRING,
  file_name STRING,
  file_size_bytes BIGINT,
  source_modified_at TIMESTAMP,
  parsed_content VARIANT,
  parsed_at TIMESTAMP)
USING delta;

-- workspace.default.employee_handbook_chunks
CREATE TABLE IF NOT EXISTS workspace.default.employee_handbook_chunks (
  chunk_id STRING,
  document_id STRING,
  domain STRING,
  source_path STRING,
  volume_path STRING,
  file_name STRING,
  document_title STRING,
  page_start INT,
  page_end INT,
  page_chunk_number INT,
  first_element_position INT,
  last_element_position INT,
  minimum_confidence DOUBLE,
  chunk_text STRING,
  embedding_text STRING,
  character_count INT,
  citation_label STRING,
  created_at TIMESTAMP)
USING delta
TBLPROPERTIES (
  'delta.enableChangeDataFeed' = 'true',
  'delta.deletedFileRetentionDuration' = 'interval 90 days',
  'delta.logRetentionDuration' = 'interval 90 days');

-- workspace.default.benefits_parsed_documents
CREATE TABLE IF NOT EXISTS workspace.default.benefits_parsed_documents (
  document_id STRING,
  domain STRING,
  source_path STRING,
  file_name STRING,
  file_size_bytes BIGINT,
  source_modified_at TIMESTAMP,
  parsed_content VARIANT,
  parsed_at TIMESTAMP)
USING delta;

-- workspace.default.benefits_chunks
CREATE TABLE IF NOT EXISTS workspace.default.benefits_chunks (
  chunk_id STRING,
  document_id STRING,
  domain STRING,
  source_path STRING,
  volume_path STRING,
  file_name STRING,
  document_title STRING,
  page_start INT,
  page_end INT,
  page_chunk_number INT,
  first_element_position INT,
  last_element_position INT,
  minimum_confidence DOUBLE,
  chunk_text STRING,
  embedding_text STRING,
  character_count INT,
  citation_label STRING,
  created_at TIMESTAMP)
USING delta
TBLPROPERTIES (
  'delta.enableChangeDataFeed' = 'true',
  'delta.deletedFileRetentionDuration' = 'interval 90 days',
  'delta.logRetentionDuration' = 'interval 90 days');

-- Coaching360 BRD (mariner-coaching360-guide)
-- workspace.default.coaching360_parsed_documents
CREATE TABLE IF NOT EXISTS workspace.default.coaching360_parsed_documents (
  document_id STRING,
  domain STRING,
  source_path STRING,
  file_name STRING,
  file_size_bytes BIGINT,
  source_modified_at TIMESTAMP,
  parsed_content VARIANT,
  parsed_at TIMESTAMP)
USING delta;

-- workspace.default.coaching360_chunks
CREATE TABLE IF NOT EXISTS workspace.default.coaching360_chunks (
  chunk_id STRING,
  document_id STRING,
  domain STRING,
  source_path STRING,
  volume_path STRING,
  file_name STRING,
  document_title STRING,
  page_start INT,
  page_end INT,
  page_chunk_number INT,
  first_element_position INT,
  last_element_position INT,
  minimum_confidence DOUBLE,
  chunk_text STRING,
  embedding_text STRING,
  character_count INT,
  citation_label STRING,
  created_at TIMESTAMP)
USING delta
TBLPROPERTIES (
  'delta.enableChangeDataFeed' = 'true',
  'delta.deletedFileRetentionDuration' = 'interval 90 days',
  'delta.logRetentionDuration' = 'interval 90 days');

-- The *_document_elements tables are created by notebooks/03_ingest_documents.py (CREATE OR REPLACE).
