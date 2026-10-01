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

- Logs: severity, body text, keys inside a JSON log body, log volume,
  structured fields, containers, services, or environments.
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
- Body column: `body` (String) on legacy and dual-ingestion tenants;
  `body_v2` (JSON, with a typed `body_v2.message` String sub-column) on JSON
  body tenants, where `body` is written empty. The logs reference has the
  detection queries and every `body_v2` access pattern.

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
- Logs query against `signoz_logs.logs`, bare `logs`, or `distributed_logs`;
  always use `signoz_logs.distributed_logs_v2`.
- Traces query with `resources_string['service.name']` instead of
  `resource_string_service$$name`.
- Logs query with `JSONExtractString(body, ...)` or `lower(body) LIKE` on a
  JSON body tenant: `body` is empty there, so the panel shows no data. Read
  keys with ``dynamicElement(body_v2.`key`, '<type>')`` and message
  text with `body_v2.message`.
- Bare `` body_v2.`key` `` compared to a literal, or a `body_v2` key filter
  without `has(JSONAllPaths(body_v2), '<key>')`.

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

## Running the SQL

Dashboards fill the `$start_*` and `$end_*` variables when a panel renders. To
run or dry-run the same SQL outside a dashboard, wrap it in a `clickhouse_sql`
envelope; the backend fills the same variables from `start` and `end` (epoch
milliseconds):

```json
{
  "schemaVersion": "v1",
  "start": 1759300000000,
  "end": 1759300900000,
  "requestType": "time_series",
  "compositeQuery": {
    "queries": [
      {"type": "clickhouse_sql", "spec": {"name": "A", "query": "<SQL>", "disabled": false}}
    ]
  }
}
```

- Direct HTTP: `POST /api/v5/query_range` with the `SIGNOZ-API-KEY` header.
- MCP: pass the same object as `query` to `signoz_execute_builder_query`.
- `requestType`: `time_series` for `(ts, value)` rows, `scalar` for value and
  table panels, `raw` for row listings.
- Dashboard variables go in a top-level `variables` map; SigNoz runs the SQL
  as written, so the tenant's ClickHouse grants are the only limit.

## Workflow

1. Detect the signal: logs or traces.
2. Read the matching reference file before writing the query.
3. For logs, decide which body column the tenant uses (legacy `body` or
   JSON `body_v2`) before writing any body predicate: read `use_json_body`
   from `GET /api/v2/features` when calling SigNoz over HTTP; on the SigNoz
   MCP server (from Claude, another coding agent, or an agent inside SigNoz)
   run the SQL probe from the reference through `signoz_execute_builder_query`.
4. Pick the panel type: timeseries, value, or table.
5. Build the query using the required patterns from the reference.
6. Append the `SETTINGS log_comment` attribution clause.
7. Validate the result with the checklist in the reference.
