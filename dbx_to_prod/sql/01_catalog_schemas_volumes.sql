-- Catalog, schemas and volumes
-- Generated from the trial workspace DDL (structure only, no data).
-- Run in order in the prod workspace with a serverless SQL warehouse.

-- New serverless workspaces already have the `workspace` catalog. If prod uses another
-- catalog, run scripts/retarget.py first (it rewrites every file in dbx_to_prod).
CREATE CATALOG IF NOT EXISTS workspace;
CREATE SCHEMA IF NOT EXISTS workspace.default;
CREATE SCHEMA IF NOT EXISTS workspace.performance_test;
-- Coaching360 source tables and the BRD (notebook 02 loads the tables; the c360_* schemas come from sql/coaching360).
CREATE SCHEMA IF NOT EXISTS workspace.coaching360demo;

-- Source PDFs (one volume per document domain; sub-folders are allowed).
CREATE VOLUME IF NOT EXISTS workspace.default.branch_operations_docs;
CREATE VOLUME IF NOT EXISTS workspace.default.employee_handbook_docs;
CREATE VOLUME IF NOT EXISTS workspace.default.benefits_docs;
CREATE VOLUME IF NOT EXISTS workspace.performance_test.data;
CREATE VOLUME IF NOT EXISTS workspace.coaching360demo.coaching360_docs;

-- Temporary landing area for the performance data export (drop after migration).
CREATE VOLUME IF NOT EXISTS workspace.performance_test.migration_staging;
