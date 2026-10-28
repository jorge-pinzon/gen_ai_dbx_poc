#!/usr/bin/env bash
# Point the Genie space at the app_fast_* copies (or back to app_vw_* with "rollback").
# Run from the repo root:  bash agent_descriptions/genie_space/apply_fast_views.sh [rollback]
set -euo pipefail
set -a; . ./.env; set +a
H=${DATABRICKS_HOST%/}; T=$DATABRICKS_TOKEN; SPACE=01f1b5eef2931f378b995a88cde37a28
DIR=agent_descriptions/genie_space
FILE=$DIR/serialized_space_fast.json; [ "${1:-}" = "rollback" ] && FILE=$DIR/serialized_space_backup.json
python3 -c 'import json,sys; print(json.dumps({"serialized_space": json.dumps(json.load(open(sys.argv[1])))}))' "$FILE" > /tmp/genie_patch_body.json
curl -s -X PATCH -H "Authorization: Bearer $T" -H 'Content-Type: application/json' \
  "$H/api/2.0/genie/spaces/$SPACE" -d @/tmp/genie_patch_body.json -o /dev/null -w "update HTTP %{http_code}\n"
rm -f /tmp/genie_patch_body.json
echo "== verification: tables now configured"
curl -s -H "Authorization: Bearer $T" "$H/api/2.0/genie/spaces/$SPACE?include_serialized_space=true" |
  python3 -c 'import sys,json; s=json.loads(json.load(sys.stdin)["serialized_space"]); print([t["identifier"].split(".")[-1] for t in s["data_sources"]["tables"]]); print("app_vw_ references left:", json.dumps(s).count("app_vw_"))'
