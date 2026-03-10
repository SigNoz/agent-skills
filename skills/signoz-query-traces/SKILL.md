---
name: signoz-query-traces
description: Write optimised ClickHouse queries for SigNoz traces or building dashboards based on traces. Use this skill whenever the user asks to query SigNoz traces, build a trace-based dashboard panel, analyse span counts, latency, error rates, duration distributions, or trace attributes — even if they don't mention ClickHouse. If the request could be logs or traces, prefer this skill when the user mentions spans, latency, duration, p99, or HTTP/DB operations. For log-line queries (severity, body text, log volume), use the logs skill instead.
---

# Writing ClickHouse Queries for SigNoz Traces Dashboards

Read [clickhouse-traces-reference.md](./clickhouse-traces-reference.md) for full schema and query reference before writing any query. It covers:

- All table schemas (`distributed_signoz_index_v3`, `distributed_traces_v3_resource`, `distributed_signoz_error_index_v2`, etc.)
- The mandatory resource filter CTE pattern and timestamp bucketing
- Attribute access syntax (standard, indexed, resource)
- Dashboard panel query templates (timeseries, value, table)
- Real-world query examples (span counts, error rates, latency, event extraction)

## Quick Reference

| Panel type | Returns | Use when |
|---|---|---|
| Timeseries | rows of `(ts, value)` | chart over time |
| Value | single `value` | stat/counter widget |
| Table | rows of labelled columns | breakdown by dimension |

**Key variables** — traces use DateTime64:
- `$start_datetime` / `$end_datetime` — filter `timestamp` (DateTime64(9))
- `$start_timestamp` / `$end_timestamp` — filter `ts_bucket_start` (seconds)

**Top anti-patterns to avoid:**
- Missing `ts_bucket_start BETWEEN $start_timestamp - 1800 AND $end_timestamp`
- Using `$start_timestamp_nano` / `$end_timestamp_nano` (those are for logs, not traces)
- Using `resources_string['service.name']` instead of `resource_string_service$$name`
- Forgetting `GLOBAL IN` (not plain `IN`) on the resource fingerprint subquery
- Adding a resource CTE when there is no resource attribute filter

## Workflow

1. **Understand the ask**: What metric/data does the user want? (e.g., error rate, latency, span count)
2. **Clarify signal**: If the request mentions log lines, severity text, or log body, redirect to the logs skill.
3. **Pick the panel type**: Timeseries, Value, or Table.
4. **Build the query** following the mandatory patterns from the reference doc.
5. **Validate** using the checklist at the bottom of the reference doc.
