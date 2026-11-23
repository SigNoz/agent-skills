---
name: signoz-writing-clickhouse-queries
description: >-
  Write raw ClickHouse SQL for a SigNoz dashboard panel: timeseries, value,
  or table widgets that the builder UI cannot express (custom joins, window
  functions, regex extraction over log bodies, aggregations beyond builder
  syntax). Trigger when the user explicitly asks for a "ClickHouse query",
  a "raw SQL panel", a "custom SQL widget", or describes a SigNoz dashboard
  panel whose query needs SQL the builder cannot produce. Anchored to
  dashboard-panel SQL specifically. For ad-hoc data exploration that does
  not need to land in a panel, use `signoz-generating-queries` instead.
---

# Writing ClickHouse Queries for SigNoz Dashboards

## When to Use

Use this skill when the user asks for SigNoz queries involving:

- Logs: severity, body text, log volume, structured fields, containers,
  services, or environments.
- Traces: spans, latency, duration, p95 or p99, HTTP operations, DB
  operations, or error spans.
- Metrics: counter rates, gauge values, or histogram quantiles that the
  builder cannot express.
- Dashboard panels: timeseries charts, value widgets, and table breakdowns.

If the user asks for a dashboard panel but does not mention ClickHouse, still
use this skill.

## Signal Detection

Identify whether the request is about logs, traces, or metrics.

- Logs: log lines, severity, body text, log volume, container logs, or
  structured log fields.
- Traces: spans, latency, duration, p99, trace analysis, HTTP operations, DB
  operations, or error spans.
- Metrics: a named metric, a counter rate, a gauge value, or a histogram
  quantile.

If the request is ambiguous, ask the user to clarify.

## Reference Routing

Before writing any query, do these reads in order for the detected signal.

1. Read the schema resource. It lists the tables, columns, and column types
   from the schema bundled with the MCP server.
   - Logs: `signoz://dashboard/clickhouse-schema-for-logs`
   - Traces: `signoz://dashboard/clickhouse-schema-for-traces`
   - Metrics: `signoz://dashboard/clickhouse-schema-for-metrics`
2. Read the examples resource for worked query shapes.
   - Logs: `signoz://dashboard/clickhouse-logs-example`
   - Traces: `signoz://dashboard/clickhouse-traces-example`
   - Metrics: `signoz://dashboard/clickhouse-metrics-example`
3. Logs and traces: read the local reference,
   [`references/clickhouse-logs-reference.md`](./references/clickhouse-logs-reference.md)
   or
   [`references/clickhouse-traces-reference.md`](./references/clickhouse-traces-reference.md).
   It holds the optimization patterns, attribute access syntax, dashboard
   templates, and validation checklist that the resources do not state.
   Metrics has no local reference; reads 1 and 2 are its full guide.

Where an examples resource gives a column a different name or type than the
schema resource, use the schema resource. The schema resource is a snapshot
of the migrations bundled with the MCP server, so it can lag the tenant: a
column or index that a local reference names and the snapshot lacks can still
exist on the tenant. When the tenant rejects a table or column, follow the
tenant's error.

Metrics: where a Workflow step names the reference, build from the examples
resource and check column names and types against the schema resource.

The metrics examples assume a cumulative counter, underscore label names such
as `service_name`, and one join shape. A query that assumes wrong returns no
rows, or a fraction of the true value, without an error. For a metrics query:

1. Call `signoz_list_metrics` with the metric name and read its temporality.
   For a `Delta` counter, filter `temporality = 'Delta'` and compute the rate
   as `sum(value) / <bucket seconds>`. The `lagInFrame` difference in the
   examples is for cumulative counters only.
2. Call `signoz_get_field_keys` with `signal: "metrics"` and the metric name.
   Use the label names it returns, exactly as spelled, in
   `JSONExtractString(labels, '<name>')`: one tenant stores `service.name`,
   another `service_name`.
3. Keep the examples' join shape: `distributed_samples_v4` joined directly to
   the label subquery on the local `time_series_v4*` table, in one `SELECT`.
   If the samples are aggregated in a subquery before the join, read the
   labels from `distributed_time_series_v4*`. On a sharded cluster the local
   table holds only part of the series, and the join drops the rest.
4. Check the result. Run the SQL through `signoz_execute_builder_query` as a
   `clickhouse_sql` query over a short window, and run `signoz_query_metrics`
   for the same metric, window, step, filter, and grouping. Compare one
   group: the final values when the builder can express the same
   calculation, otherwise the plain rate or sum that the SQL builds on. If
   they differ, or the SQL returns no rows, fix the query before giving it
   to the user. If the tools are unavailable, say the query was not checked.

If the client cannot read `signoz://` resources in this session, use the
local reference for logs and traces. For metrics, tell the user that the
metrics schema could not be read; do not guess table or column names.

## Quick Reference

- Timeseries panel: return rows of `(ts, value)` for a chart over time.
- Value panel: return a single `value` for a stat or counter widget.
- Table panel: return labelled columns for a grouped breakdown.

## Key Variables by Signal

### Logs

- Timestamp type: `UInt64` in nanoseconds.
- Time filter: `$start_timestamp_nano` and `$end_timestamp_nano`.
- Bucket filter: `$start_timestamp` and `$end_timestamp`.
- Display conversion: `fromUnixTimestamp64Nano(timestamp)`.
- Main table: `signoz_logs.distributed_logs_v2`.
- Resource table: `signoz_logs.distributed_logs_v2_resource`.

### Traces

- Timestamp type: `DateTime64(9)`.
- Time filter: `$start_datetime` and `$end_datetime`.
- Bucket filter: `$start_timestamp` and `$end_timestamp`.
- Display conversion: use the timestamp directly.
- Main table: `signoz_traces.distributed_signoz_index_v3`.
- Resource table: `signoz_traces.distributed_traces_v3_resource`.

## Top Anti-Patterns

- Missing `ts_bucket_start BETWEEN $start_timestamp - 1800 AND $end_timestamp`.
- Plain `IN` / `JOIN` whose subquery reads a distributed table: with
  `distributed_product_mode='deny'` it fails. Prefer the time-bounded fingerprint
  `GLOBAL IN` pattern or a local subquery table. Use `GLOBAL JOIN` only for a
  demonstrably small, bounded RHS; it broadcasts that dataset to every shard.
- Adding a resource CTE when there is no resource attribute filter.
- Omitting a non-aggregated projection from `GROUP BY`, including computed
  projections such as `JSONExtractString(body, ...)`.
- Logs query with `$start_datetime` or `$end_datetime`.
- Traces query with `$start_timestamp_nano` or `$end_timestamp_nano`.
- Traces `timestamp` compared with an epoch-millisecond number: the column is
  `DateTime64(9)`, so `timestamp BETWEEN 1791920500000 AND ...` fails with
  `Decimal math overflow`. Use `$start_datetime` and `$end_datetime`, or
  `toDateTime64(<epoch seconds>, 9)` for a literal.
- `=` or `!=` on `attributes_number['key']` with an integer literal: the map
  values are `Float64`, so `attributes_number['http.status_code'] != 200`
  fails with `Bad get: has UInt64, requested Float64`. Write `200.0` or
  `toFloat64(200)`.
- Logs query against `signoz_logs.logs`, bare `logs`, or `distributed_logs`;
  always use `signoz_logs.distributed_logs_v2`.
- Traces query with `resources_string['service.name']` instead of
  `resource_string_service$$name`.

## Query Attribution

Every generated query MUST end with a `SETTINGS` clause for monitoring:

```sql
SELECT ...
FROM ...
WHERE ...
SETTINGS log_comment = 'signoz-writing-clickhouse-queries skill | YYYY-MM-DD'
```

Replace `YYYY-MM-DD` with today's date (e.g., `2026-04-03`). If the query
already has a `SETTINGS` clause, append `log_comment` to it with a comma.

## Workflow

1. Detect the signal (logs, traces, or metrics), then read its schema and
   examples resources, reads 1 and 2 in Reference Routing.
2. Read the matching reference file before writing the query.
3. Pick the panel type: timeseries, value, or table.
4. Build the query using the required patterns from the reference.
5. Append the `SETTINGS log_comment` attribution clause.
6. Validate the result with the checklist in the reference.
