---
description: Write optimised ClickHouse queries for SigNoz logs or building dashboard panels based on logs
---

# Writing ClickHouse Queries for SigNoz Logs Dashboards

Read [clickhouse-logs-reference.md](./clickhouse-logs-reference.md) for full schema and query reference before writing any query. It covers:

- All table schemas (`distributed_logs_v2`, `distributed_logs_v2_resource`)
- The mandatory resource filter CTE pattern and timestamp bucketing
- Attribute access syntax (map access, indexed columns, resource attributes)
- Dashboard panel query templates (timeseries, value, table)
- Real-world query examples (log counts, error rates, payload auditing)
- The **critical timestamp difference** vs traces (nanoseconds, different variables)

## Workflow

1. **Understand the ask**: What metric/data does the user want? (e.g., error log count, log volume per service, largest payloads)
2. **Pick the panel type**: Timeseries (time-series chart), Value (single number), or Table (rows).
3. **Build the query** following the mandatory patterns from the reference doc.
4. **Validate** the query uses all required optimizations (resource CTE if needed, `ts_bucket_start`, nanosecond timestamp variables, indexed columns).
