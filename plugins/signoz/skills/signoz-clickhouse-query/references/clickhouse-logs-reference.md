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

### 5. Body Text Search — Engaging Skip Indexes

The `body` column has two skip indexes, **both on `lower(body)`**:

```sql
INDEX body_index_v2_token  lower(body) TYPE tokenbf_v1(10000, 2, 0)   GRANULARITY 1,
INDEX body_index_v2_ngram  lower(body) TYPE ngrambf_v1(4, 15000, 3, 0) GRANULARITY 1
```

ClickHouse compares predicate ASTs to the index expression **literally**. A predicate must reference `lower(body)` to engage either index — `hasToken(body, …)` and `body LIKE '%x%'` prune nothing.

#### Predicate engagement

| Predicate | tokenbf | ngrambf | Notes |
|---|:-:|:-:|---|
| `hasToken(lower(body), 'tok')` | yes | no | Whole-token check; best for distinctive single words. |
| `lower(body) = 'literal'` | yes | yes | Exact equality. |
| `lower(body) LIKE '%substr%'` | no | yes | Substring must be ≥ 4 chars (ngrambf `N=4`). |
| `lower(body) LIKE '%a%b%'` | no | yes | n-grams of each substring ANDed — more selective. |
| `lower(body) ILIKE '%x%'` | no | sometimes | Prefer the explicit `lower(body) LIKE '%x%'` form. |
| `position(body, 'x') > 0` | no | no | Always rewrite to `lower(body) LIKE`. |
| `positionCaseInsensitive(body, 'X') > 0` | no | no | Biggest trap — engages neither even with `lower(body)` index. |
| `match(lower(body), 'regex')` | no | partial | Only literal substrings inside the regex are usable. |

#### Anti-patterns to rewrite

| Replace | With |
|---|---|
| `positionCaseInsensitive(body, 'Foo')` | `lower(body) LIKE '%foo%'` |
| `position(body, 'foo') > 0` | `lower(body) LIKE '%foo%'` |
| `body LIKE '%Foo%'` | `lower(body) LIKE '%foo%'` |
| `hasToken(body, 'foo')` | `hasToken(lower(body), 'foo')` |

Lowercase the literal (the index value is lowercase). Escape `%` and `_` in the literal; pass other characters (hyphens, dots, parens, colons) through as-is.

#### OR-of-LIKE — add a common AND-prefix

OR'd `LIKE` patterns weaken ngrambf to nearly nothing: any branch matching keeps the granule. Find a token or substring shared by **all** branches and AND it before the OR block:

```sql
-- BEFORE: ngrambf keeps almost every granule
WHERE lower(body) LIKE '%failed to send foo%'
   OR lower(body) LIKE '%failed to send bar%'
   OR lower(body) LIKE '%failed to send baz%'

-- AFTER: tokenbf + ngrambf both prune; OR is now a per-row validator
WHERE hasToken(lower(body), 'failed')               -- tokenbf engages
  AND lower(body) LIKE '%failed to send%'           -- ngrambf engages
  AND ( lower(body) LIKE '%failed to send foo%'
     OR lower(body) LIKE '%failed to send bar%'
     OR lower(body) LIKE '%failed to send baz%' )
```

Pick the AND-prefix in this order: (1) most distinctive single token via `hasToken`, (2) two ANDed `hasToken` calls, (3) distinctive shared substring via `LIKE`. Avoid common words like `the`, `user`, `error` — high false-positive rate on the bloom filter.

#### Hyphens and punctuation split tokens

`tokenbf` only stores `[A-Za-z0-9_]+` runs. Anything else (hyphens, dots, slashes, quotes, parens, colons) is a token boundary. So:

- `hasToken(lower(body), 'settlement-requested')` matches **nothing** — there is no such token.
- Use `hasToken(lower(body), 'settlement') AND hasToken(lower(body), 'requested')`, or
- Use `lower(body) LIKE '%settlement-requested%'` (ngrambf handles punctuation).

#### Verify with `EXPLAIN indexes=1`

```sql
EXPLAIN indexes=1
<your query>;
```

Each `Skip` block under `ReadFromMergeTree` shows `Granules: kept/total`. For both `body_index_v2_token` and `body_index_v2_ngram`, kept should be `<` total. The `Combined` block is what feeds the actual scan — that's the number to drive down.

Failure modes:
- `Granules: 195/195` — predicate doesn't match the index expression, or the chosen token is too common.
- `Skip` block missing — predicate engages no skip index at all.

`tokenbf_v1(10000, …)` is small and saturates at high cardinality; `ngrambf_v1(4, 15000, …)` is the workhorse. If tokenbf looks idle even with a correct `hasToken(lower(body), …)`, lean on `lower(body) LIKE` rather than chasing tokenbf pruning the filter size won't deliver.

#### Type traps in body-search queries

- `toUnixTimestamp64Nano(now())` → `Code: 43, ILLEGAL_TYPE_OF_ARGUMENT`. Use `now64()` (or `toDateTime64(now(), 9)`). SigNoz dashboard macros like `$start_timestamp_nano` resolve to literal integers and sidestep this.
- `max(fromUnixTimestamp64Nano(timestamp))` converts every row before aggregating. Use `fromUnixTimestamp64Nano(max(timestamp))` — `max` once on cheap UInt64, convert once at the end.

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
- [ ] **Body searches** use `lower(body)` (not raw `body`) and `LIKE` (not `position` / `positionCaseInsensitive`); for OR'd patterns, a shared `hasToken` or `LIKE` is ANDed before the OR block
- [ ] **`seen_at_ts_bucket_start`** filter is included in the resource CTE
- [ ] For timeseries: results are ordered by `ts ASC`
- [ ] **Table Name**: Always use the `distributed_` prefix (`distributed_logs_v2`, not `logs_v2`)
- [ ] If multiple tables are joined, ensure all tables have timestamp and bucket filter applied if applicable.
