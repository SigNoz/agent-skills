# ClickHouse Logs Query Reference for SigNoz

All tables live in the `signoz_logs` database.

---

## Table Schemas

### distributed_logs_v2 (Primary Logs Table)

```sql
(
    `timestamp` UInt64 CODEC(DoubleDelta, LZ4),          -- nanoseconds since epoch
    `ts_bucket_start` UInt64 CODEC(DoubleDelta, LZ4),    -- 30-minute bucket start (seconds)
    `observed_timestamp` UInt64 CODEC(DoubleDelta, LZ4),
    `id` String CODEC(ZSTD(1)),                           -- KSUID for pagination/sorting
    `trace_id` String CODEC(ZSTD(1)),
    `span_id` String CODEC(ZSTD(1)),
    `trace_flags` UInt32,
    `severity_text` LowCardinality(String) CODEC(ZSTD(1)),
    `severity_number` UInt8,
    `body` String CODEC(ZSTD(2)),
    `attributes_string` Map(LowCardinality(String), String) CODEC(ZSTD(1)),
    `attributes_number` Map(LowCardinality(String), Float64) CODEC(ZSTD(1)),
    `attributes_bool` Map(LowCardinality(String), Bool) CODEC(ZSTD(1)),
    `resources_string` Map(LowCardinality(String), String) CODEC(ZSTD(1)),  -- deprecated
    `resource` JSON(max_dynamic_paths = 100) CODEC(ZSTD(1)),
    `scope_name` String CODEC(ZSTD(1)),
    `scope_version` String CODEC(ZSTD(1)),
    `scope_string` Map(LowCardinality(String), String) CODEC(ZSTD(1))
)
```

### distributed_logs_v2_resource (Resource Lookup Table)

Used in the resource filter CTE pattern for efficient filtering by resource attributes.

```sql
(
    `labels` String CODEC(ZSTD(5)),
    `fingerprint` String CODEC(ZSTD(1)),
    `seen_at_ts_bucket_start` Int64 CODEC(Delta(8), ZSTD(1))
)
```

---

## Mandatory Optimization Patterns

### 1. Resource Filter CTE

**Always** use a CTE to pre-filter resource fingerprints when filtering by resource attributes (service.name, environment, k8s.cluster.name, etc.). Do not add this if no resource attribute filter is required.

```sql
WITH __resource_filter AS (
    SELECT fingerprint
    FROM signoz_logs.distributed_logs_v2_resource
    WHERE (simpleJSONExtractString(labels, 'service.name') = 'myservice')
    AND seen_at_ts_bucket_start BETWEEN $start_timestamp - 1800 AND $end_timestamp
)
SELECT ...
FROM signoz_logs.distributed_logs_v2
WHERE resource_fingerprint GLOBAL IN __resource_filter
    AND ...
```

- Multiple resource filters: chain with `AND` in the CTE `WHERE` clause.
- Use `simpleJSONExtractString(labels, '<key>')` to extract resource attribute values in the CTE.
- Examples of resource attributes: `service.name`, `host.name`, `k8s.cluster.name`, `k8s.deployment.name`, `cloud.provider`.

### 2. Timestamp Bucketing

**Always** include both the nanosecond timestamp filter AND the `ts_bucket_start` filter.

```sql
WHERE timestamp >= $start_timestamp_nano AND timestamp <= $end_timestamp_nano
  AND ts_bucket_start BETWEEN $start_timestamp - 1800 AND $end_timestamp
```

- `$start_timestamp_nano` / `$end_timestamp_nano` — nanosecond precision, filters the `timestamp` column.
- `$start_timestamp` / `$end_timestamp` — seconds precision, filters the `ts_bucket_start` column.
- The `- 1800` is required because `ts_bucket_start` is rounded down to 30-minute intervals.

### 3. Use Indexed (Selected) Columns Over Map Access

When an attribute has been promoted to a selected (indexed) field, a dedicated materialized column is created:

| Instead of | Use |
|---|---|
| `attributes_string['method']` | `attribute_string_method` |
| `attributes_number['response.time']` | `attribute_number_response$$time` |
| `attributes_bool['is_error']` | `attribute_bool_is_error` |

**Naming convention**: prefix with `attribute_<dataType>_`, replace `.` with `$$` for dotted attribute names.

An `_exists` variant is also created: `attribute_string_method_exists Bool` — use this to check existence of an indexed attribute.

### 4. Use GLOBAL IN for Resource Fingerprint Subquery

Always use `GLOBAL IN`, not plain `IN`:

```sql
WHERE resource_fingerprint GLOBAL IN __resource_filter
```

---

## Attribute Access Syntax

### Resource attributes in SELECT / GROUP BY
```sql
resource.service.name::String
resource.k8s.cluster.name::String
```

### Resource attributes in WHERE (via CTE)
```sql
simpleJSONExtractString(labels, 'service.name') = 'myservice'
```

### Span/log attributes in WHERE (map access)
```sql
attributes_string['method'] = 'GET'
attributes_number['response.time'] > 1000
attributes_bool['is_error'] = true
```

### Checking attribute existence
```sql
mapContains(attributes_string, 'container_name')
```

### Timestamp display conversion
```sql
fromUnixTimestamp64Nano(timestamp)  -- use in SELECT for human-readable time
toStartOfInterval(fromUnixTimestamp64Nano(timestamp), INTERVAL 1 MINUTE) AS ts
```

---

## SigNoz Dashboard Variables

| Variable | Type | Description |
|---|---|---|
| `$start_timestamp_nano` | UInt64 | Start of selected time range (nanoseconds) |
| `$end_timestamp_nano` | UInt64 | End of selected time range (nanoseconds) |
| `$start_timestamp` | Int64 | Start as Unix timestamp (seconds) |
| `$end_timestamp` | Int64 | End as Unix timestamp (seconds) |

---

## Critical Difference vs Traces

> **Logs timestamps are nanosecond `UInt64`, not `DateTime64`.**

| | Traces | Logs |
|---|---|---|
| Timestamp type | `DateTime64(9)` | `UInt64` (nanoseconds) |
| Time filter variables | `$start_datetime`, `$end_datetime` | `$start_timestamp_nano`, `$end_timestamp_nano` |
| Bucket filter variables | `$start_timestamp`, `$end_timestamp` | `$start_timestamp`, `$end_timestamp` (same) |
| Display conversion | direct | `fromUnixTimestamp64Nano(timestamp)` |
| Main table | `signoz_traces.distributed_signoz_index_v3` | `signoz_logs.distributed_logs_v2` |
| Resource table | `signoz_traces.distributed_traces_v3_resource` | `signoz_logs.distributed_logs_v2_resource` |

---

## Dashboard Panel Query Examples

### Timeseries Panel

Aggregates data over time intervals for chart visualization.

```sql
WITH __resource_filter AS (
    SELECT fingerprint
    FROM signoz_logs.distributed_logs_v2_resource
    WHERE (simpleJSONExtractString(labels, 'service.name') = 'service-name')
    AND seen_at_ts_bucket_start BETWEEN $start_timestamp - 1800 AND $end_timestamp
)
SELECT
    toStartOfInterval(fromUnixTimestamp64Nano(timestamp), INTERVAL 1 MINUTE) AS ts,
    toFloat64(count()) AS value
FROM signoz_logs.distributed_logs_v2
WHERE
    resource_fingerprint GLOBAL IN __resource_filter AND
    timestamp >= $start_timestamp_nano AND timestamp <= $end_timestamp_nano AND
    ts_bucket_start BETWEEN $start_timestamp - 1800 AND $end_timestamp
GROUP BY ts
ORDER BY ts ASC;
```

### Value Panel

Returns a single aggregated number using methods like `avg()`.

```sql
WITH __resource_filter AS (
    SELECT fingerprint
    FROM signoz_logs.distributed_logs_v2_resource
    WHERE (simpleJSONExtractString(labels, 'service.name') = 'myservice')
    AND seen_at_ts_bucket_start BETWEEN $start_timestamp - 1800 AND $end_timestamp
)
SELECT
    avg(value) AS value
FROM (
    SELECT
        toStartOfInterval(fromUnixTimestamp64Nano(timestamp), INTERVAL 1 MINUTE) AS ts,
        toFloat64(count()) AS value
    FROM signoz_logs.distributed_logs_v2
    WHERE
        resource_fingerprint GLOBAL IN __resource_filter AND
        timestamp >= $start_timestamp_nano AND timestamp <= $end_timestamp_nano AND
        ts_bucket_start BETWEEN $start_timestamp - 1800 AND $end_timestamp
    GROUP BY ts
    ORDER BY ts ASC
);
```

### Table Panel

```sql
SELECT
    resource.service.name::String AS `service.name`,
    toFloat64(count()) AS value
FROM signoz_logs.distributed_logs_v2
WHERE
    timestamp >= $start_timestamp_nano AND timestamp <= $end_timestamp_nano AND
    ts_bucket_start BETWEEN $start_timestamp - 1800 AND $end_timestamp
GROUP BY `service.name`
ORDER BY value DESC;
```

> Note: only add the resource CTE and `resource_fingerprint GLOBAL IN __resource_filter` when you need to filter on resource attributes. A plain table breakdown by service name does not require it.

---

## Query Examples

### Timeseries — Count per minute grouped by container name

Shows `mapContains` for attribute existence check and attribute in GROUP BY.

```sql
SELECT
    toStartOfInterval(fromUnixTimestamp64Nano(timestamp), INTERVAL 1 MINUTE) AS ts,
    attributes_string['container_name'] AS container_name,
    toFloat64(count()) AS value
FROM signoz_logs.distributed_logs_v2
WHERE
    timestamp >= $start_timestamp_nano AND timestamp <= $end_timestamp_nano AND
    ts_bucket_start BETWEEN $start_timestamp - 1800 AND $end_timestamp AND
    mapContains(attributes_string, 'container_name')
GROUP BY container_name, ts
ORDER BY ts ASC;
```

### Timeseries — Filtered by service, severity, and attribute

Shows combining resource CTE with `severity_text` and attribute map access.

```sql
WITH __resource_filter AS (
    SELECT fingerprint
    FROM signoz_logs.distributed_logs_v2_resource
    WHERE (simpleJSONExtractString(labels, 'service.name') = 'demo')
    AND seen_at_ts_bucket_start BETWEEN $start_timestamp - 1800 AND $end_timestamp
)
SELECT
    toStartOfInterval(fromUnixTimestamp64Nano(timestamp), INTERVAL 1 MINUTE) AS ts,
    toFloat64(count()) AS value
FROM signoz_logs.distributed_logs_v2
WHERE
    resource_fingerprint GLOBAL IN __resource_filter AND
    timestamp >= $start_timestamp_nano AND timestamp <= $end_timestamp_nano AND
    severity_text = 'INFO' AND
    attributes_string['method'] = 'GET' AND
    ts_bucket_start BETWEEN $start_timestamp - 1800 AND $end_timestamp
GROUP BY ts
ORDER BY ts ASC;
```

### Table — Info log count by service name

```sql
SELECT
    resource.service.name::String AS `service.name`,
    toFloat64(count()) AS value
FROM signoz_logs.distributed_logs_v2
WHERE
    timestamp >= $start_timestamp_nano AND timestamp <= $end_timestamp_nano AND
    severity_text = 'INFO' AND
    ts_bucket_start BETWEEN $start_timestamp - 1800 AND $end_timestamp
GROUP BY `service.name`
ORDER BY value DESC;
```

### Timeseries — Log lines per Kubernetes cluster

Shows `resource.k8s.cluster.name::String` with IS NOT NULL guard.

```sql
WITH __resource_filter AS (
    SELECT fingerprint
    FROM signoz_logs.distributed_logs_v2_resource
    WHERE seen_at_ts_bucket_start BETWEEN $start_timestamp - 1800 AND $end_timestamp
)
SELECT
    toStartOfInterval(fromUnixTimestamp64Nano(timestamp), INTERVAL 1 MINUTE) AS ts,
    resource.k8s.cluster.name::String AS k8s_cluster_name,
    toFloat64(count()) AS value
FROM signoz_logs.distributed_logs_v2
WHERE
    resource_fingerprint GLOBAL IN __resource_filter AND
    timestamp >= $start_timestamp_nano AND timestamp <= $end_timestamp_nano AND
    resource.k8s.cluster.name::String IS NOT NULL AND
    ts_bucket_start BETWEEN $start_timestamp - 1800 AND $end_timestamp
GROUP BY k8s_cluster_name, ts
ORDER BY ts ASC;
```

### Advanced — Top 10 largest logs for payload auditing

Calculates per-log byte size from body + all attributes. Keep queries to ≤6 hour windows for this pattern.

```sql
SELECT
    fromUnixTimestamp64Nano(timestamp) AS log_timestamp,
    (OCTET_LENGTH(body) +
     OCTET_LENGTH(toJSONString(attributes_string)) +
     OCTET_LENGTH(toJSONString(attributes_number)) +
     OCTET_LENGTH(toJSONString(attributes_bool))) AS size_bytes,
    id
FROM signoz_logs.distributed_logs_v2
WHERE
    timestamp >= $start_timestamp_nano AND timestamp <= $end_timestamp_nano AND
    ts_bucket_start BETWEEN $start_timestamp - 1800 AND $end_timestamp
ORDER BY size_bytes DESC
LIMIT 10;
```

Use the returned `id` value in the SigNoz Logs Explorer filter `id=<log_id>` to view full log details.

---

## Query Optimization Checklist

Before finalizing any query, verify:

- [ ] **Resource filter CTE** is present when filtering by resource attributes (`service.name`, `k8s.*`, etc.)
- [ ] Do **not** add the resource CTE if no resource attribute filtering is needed
- [ ] **`ts_bucket_start`** filter is included: `BETWEEN $start_timestamp - 1800 AND $end_timestamp`
- [ ] **Nanosecond variables** used for the `timestamp` column: `$start_timestamp_nano` / `$end_timestamp_nano`
- [ ] **`fromUnixTimestamp64Nano(timestamp)`** used in SELECT when displaying timestamps
- [ ] **`GLOBAL IN`** is used (not plain `IN`) for the any subquery
- [ ] **Indexed columns** used over map access where the attribute is a selected field
- [ ] **`seen_at_ts_bucket_start`** filter is included in the resource CTE
- [ ] For timeseries: results are ordered by `ts ASC`
- [ ] **Table Name**: Always use the `distributed_` prefix (`distributed_logs_v2`, not `logs_v2`)
- [ ] If multiple tables are joined, ensure all tables have timestamp and bucket filter applied if applicable.
