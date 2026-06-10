---
name: signoz-writing-clickhouse-queries
description: >-
  Write raw ClickHouse SQL for a SigNoz dashboard panel — timeseries, value,
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
- Dashboard panels: timeseries charts, value widgets, and table breakdowns.

If the user asks for a dashboard panel but does not mention ClickHouse, still
use this skill.

## Signal Detection

Identify whether the request is about logs or traces.

- Logs: log lines, severity, body text, log volume, container logs, or
  structured log fields.
- Traces: spans, latency, duration, p99, trace analysis, HTTP operations, DB
  operations, or error spans.

If the request is ambiguous, ask the user to clarify.

## Reference Routing

- Logs: read
  [`references/clickhouse-logs-reference.md`](./references/clickhouse-logs-reference.md)
  before writing any query.
- Traces: read
  [`references/clickhouse-traces-reference.md`](./references/clickhouse-traces-reference.md)
  before writing any query.

Each reference covers table schemas, optimization patterns, attribute access
syntax, dashboard templates, query examples, and a validation checklist.

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
- Using plain `IN` instead of `GLOBAL IN` on the resource fingerprint subquery.
- Adding a resource CTE when there is no resource attribute filter.
- Logs query with `$start_datetime` or `$end_datetime`.
- Traces query with `$start_timestamp_nano` or `$end_timestamp_nano`.
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

1. Detect the signal: logs or traces.
2. Read the matching reference file before writing the query.
3. Pick the panel type: timeseries, value, or table.
4. Build the query using the required patterns from the reference.
5. Append the `SETTINGS log_comment` attribution clause.
6. Validate the result with the checklist in the reference.
