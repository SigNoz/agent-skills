---
description: Write optimised ClickHouse queries for SigNoz logs or building dashboard panels based on logs. Use this skill whenever the user asks to query SigNoz logs, build a log-based dashboard panel, analyse log volume or error rates, filter logs by service or severity, or explore log attributes — even if they don't mention ClickHouse. If the request could be logs or traces, prefer this skill when the user mentions log lines, severity, body text, or structured log fields. For trace-based queries (spans, latency, duration), use the traces skill instead.
---

# Writing ClickHouse Queries for SigNoz Logs Dashboards

Read [clickhouse-logs-reference.md](./clickhouse-logs-reference.md) for full schema and query reference before writing any query. It covers:

- All table schemas (`distributed_logs_v2`, `distributed_logs_v2_resource`)
- The mandatory resource filter CTE pattern and timestamp bucketing
- Attribute access syntax (map access, indexed columns, resource attributes)
- Dashboard panel query templates (timeseries, value, table)
- Real-world query examples (log counts, error rates, payload auditing)
- The **critical timestamp difference** vs traces (nanoseconds, different variables)

## Quick Reference

| Panel type | Returns | Use when |
|---|---|---|
| Timeseries | rows of `(ts, value)` | chart over time |
| Value | single `value` | stat/counter widget |
| Table | rows of labelled columns | breakdown by dimension |

**Key variables** — logs use nanoseconds:
- `$start_timestamp_nano` / `$end_timestamp_nano` — filter `timestamp` (UInt64 ns)
- `$start_timestamp` / `$end_timestamp` — filter `ts_bucket_start` (seconds)

**Top anti-patterns to avoid:**
- Missing `ts_bucket_start BETWEEN $start_timestamp - 1800 AND $end_timestamp`
- Using `$start_datetime` / `$end_datetime` (those are for traces, not logs)
- Forgetting `GLOBAL IN` (not plain `IN`) on the resource fingerprint subquery
- Adding a resource CTE when there is no resource attribute filter

## Workflow

1. **Understand the ask**: What metric/data does the user want? (e.g., error log count, log volume per service, largest payloads)
2. **Clarify signal**: If the request mentions spans, latency, or duration, redirect to the traces skill.
3. **Pick the panel type**: Timeseries, Value, or Table.
4. **Build the query** following the mandatory patterns from the reference doc.
5. **Validate** using the checklist at the bottom of the reference doc.
