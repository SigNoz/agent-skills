---
name: signoz-clickhouse-query
description: Write optimised ClickHouse queries for SigNoz OpenTelemetry data to build dashboard panels. Use this skill whenever the user asks to query SigNoz logs or traces, build a log-based or trace-based dashboard panel, analyse log volume, error rates, span counts, latency, duration distributions, or filter by service, severity, container, or environment — even if they don't mention ClickHouse. Trigger for logs (severity, body, log volume) AND traces (spans, latency, duration, p99, HTTP/DB operations).
---

# Writing ClickHouse Queries for SigNoz Dashboards

## Signal Detection

Identify whether the request is about **logs** or **traces**:

| User mentions | Signal |
|---|---|
| log lines, severity, body text, log volume, container logs, structured log fields | **Logs** |
| spans, latency, duration, p99, HTTP/DB operations, trace, error spans | **Traces** |

If ambiguous, ask the user to clarify.

## Reference Routing

- **Logs**: Read [`references/clickhouse-logs-reference.md`](./references/clickhouse-logs-reference.md) before writing any query.
- **Traces**: Read [`references/clickhouse-traces-reference.md`](./references/clickhouse-traces-reference.md) before writing any query.

Each reference covers: table schemas, the mandatory optimizations like resource filter CTE pattern, attribute access syntax, dashboard panel templates, query examples, and a validation checklist.

## Quick Reference

| Panel type | Returns | Use when |
|---|---|---|
| Timeseries | rows of `(ts, value)` | chart over time |
| Value | single `value` | stat/counter widget |
| Table | rows of labelled columns | breakdown by dimension |

## Key Variables by Signal

| | Logs | Traces |
|---|---|---|
| Timestamp type | `UInt64` (nanoseconds) | `DateTime64(9)` |
| Time filter | `$start_timestamp_nano` / `$end_timestamp_nano` | `$start_datetime` / `$end_datetime` |
| Bucket filter | `$start_timestamp` / `$end_timestamp` | `$start_timestamp` / `$end_timestamp` |
| Display conversion | `fromUnixTimestamp64Nano(timestamp)` | direct |
| Main table | `signoz_logs.distributed_logs_v2` | `signoz_traces.distributed_signoz_index_v3` |
| Resource table | `signoz_logs.distributed_logs_v2_resource` | `signoz_traces.distributed_traces_v3_resource` |

## Top Anti-Patterns

- Missing `ts_bucket_start BETWEEN $start_timestamp - 1800 AND $end_timestamp`
- Forgetting `GLOBAL IN` (not plain `IN`) on the resource fingerprint subquery
- Adding a resource CTE when there is no resource attribute filter
- **[Logs]** Using `$start_datetime` / `$end_datetime` (those are for traces)
- **[Traces]** Using `$start_timestamp_nano` / `$end_timestamp_nano` (those are for logs)
- **[Traces]** Using `resources_string['service.name']` instead of `resource_string_service$$name`

## Workflow

1. **Detect signal**: Logs or traces? Use the table above.
2. **Read the reference**: Load the appropriate reference file before writing any query.
3. **Pick the panel type**: Timeseries, Value, or Table.
4. **Build the query** following the mandatory patterns from the reference doc.
5. **Validate** using the checklist at the bottom of the reference doc.
