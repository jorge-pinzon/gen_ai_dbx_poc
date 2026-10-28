-- Run BEFORE deploying the app version that writes per-stage timings.
-- Without these columns every analytics INSERT fails (and is silently dropped).
ALTER TABLE workspace.default.flask_app_logs ADD COLUMNS (
  inference_ms BIGINT COMMENT 'Supervisor/fast-path model time for the request',
  citations_ms BIGINT COMMENT 'Citation validation time after the model answered'
);

-- Per-stage timings (milliseconds since the model call started: tool chosen, tool result,
-- first answer text, answer prepared; plus Coaching360 setup time). Run this, then set
-- ANALYTICS_STAGE_TIMINGS=true. Until then the app writes the rows without it.
ALTER TABLE workspace.default.flask_app_logs ADD COLUMNS (
  stage_timings_json STRING COMMENT 'Per-stage milliseconds, e.g. {"coaching360":3,"tool":4400,"result":26400,"text":29600,"prepared":32200}'
);
