#!/usr/bin/env bash
# Copy the source PDFs and the data export (performance + Coaching360) from the trial workspace to prod.
# Needs the Databricks CLI (v0.205+) with two profiles in ~/.databrickscfg:
#   [trial]  host = https://dbc-957e994b-63c5.cloud.databricks.com   (current trial)
#   [prod]   host = https://<prod-workspace>.cloud.databricks.com
# Run notebook 02 in "export" mode in trial first, and notebook 01 in prod (it creates the volumes).
# Usage: bash dbx_to_prod/scripts/copy_between_workspaces.sh [trial-profile] [prod-profile]
set -euo pipefail
TRIAL=${1:-trial}
PROD=${2:-prod}
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT

VOLUMES=(
  "workspace/default/branch_operations_docs"
  "workspace/default/employee_handbook_docs"
  "workspace/default/benefits_docs"
  "workspace/performance_test/data"
  "workspace/coaching360demo/coaching360_docs"
  "workspace/performance_test/migration_staging"
)

for volume in "${VOLUMES[@]}"; do
  echo "== $volume"
  databricks fs cp -r "dbfs:/Volumes/$volume" "$WORK/$volume" --profile "$TRIAL"
  databricks fs cp -r "$WORK/$volume" "dbfs:/Volumes/$volume" --profile "$PROD" --overwrite
  databricks fs ls -l "dbfs:/Volumes/$volume" --profile "$PROD"
done
echo "Done. Next: notebook 02 in 'import' mode, then notebook 03 in prod."
