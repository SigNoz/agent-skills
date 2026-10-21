# ClickHouse Logs Query Reference for SigNoz

## Contents

- Table Schemas (`distributed_logs_v2`, `distributed_logs_v2_resource`)
- Which Body Column Holds the Text (legacy `body` vs JSON `body_v2`: feature
  flags over direct HTTP, SQL probe over MCP, ranges that cross the cut-over)
- Mandatory Optimization Patterns
  - Resource Filter CTE
  - Timestamp Bucketing
  - Use Indexed (Selected) Columns Over Map Access
  - Use GLOBAL IN for Resource Fingerprint Subquery
  - Complete GROUP BY Projections
  - Body Text Search: Engaging Skip Indexes (predicate engagement,
    anti-patterns, OR-of-LIKE, hyphens/punctuation, EXPLAIN, type traps)
- JSON Body (`body_v2`): typed `message` sub-column, dynamic paths with
  `dynamicElement`, path skip index, type collisions, absent paths and
  negative operators, arrays, whole-document search, GROUP BY on a path,
  porting legacy `JSONExtract*(body, ...)`, `body_promoted`
- Attribute Access Syntax (resource attributes, span/log attributes,
  existence checks, timestamp conversion)
- SigNoz Dashboard Variables
- Dashboard Panel Query Examples (timeseries, table)
- Query Examples (per-minute counts, filtered counts, top-N audit)
- Query Examples: JSON Body (level per minute, top users by a nested path,
  p95 of a numeric path, message search value panel, array of objects)
- Query Optimization Checklist

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
    `body` String CODEC(ZSTD(2)),                         -- legacy text body; written empty on JSON-body orgs
    `body_v2` JSON(max_dynamic_paths = 0, message String) CODEC(ZSTD(1)),  -- JSON body; `message` is a typed String sub-column
    `body_promoted` JSON CODEC(ZSTD(1)),                   -- reserved; the query path does not read it
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

Skip indexes on the body columns (all `GRANULARITY 1`):

```sql
INDEX body_index_v2_token       lower(body)              TYPE tokenbf_v1(10000, 2, 0)
INDEX body_index_v2_ngram       lower(body)              TYPE ngrambf_v1(4, 15000, 3, 0)
INDEX body_v2_string_token_idx  lower(toString(body_v2)) TYPE tokenbf_v1(10000, 2, 0)
INDEX body_v2_string_ngram_idx  lower(toString(body_v2)) TYPE ngrambf_v1(4, 15000, 3, 0)
INDEX body_v2_paths_token_idx   JSONAllPaths(body_v2)    TYPE tokenbf_v1(10000, 2, 0)
INDEX body_v2_paths_ngram_idx   JSONAllPaths(body_v2)    TYPE ngrambf_v1(4, 15000, 3, 0)
```

`body_v2.message` has no skip index of its own. Legacy tenants that predate the
JSON body migration have no `body_v2` column at all.

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

## Which Body Column Holds the Text

SigNoz tenants store the log body in one of three ways. Decide the mode before
writing any body predicate, because a query against the wrong column returns no
rows or fails.

| Tenant mode | `body` | `body_v2` | Query the body through |
|---|---|---|---|
| Legacy (predates the JSON body migration) | populated | column absent | `body` |
| Dual ingestion | populated | populated | `body`; `body_v2` is available |
| JSON body (SigNoz Cloud accounts created from May 2026 on `in2`, `eu2`, `us2`) | written empty | populated | `body_v2` |

Two detection paths exist, chosen by what the agent can reach:

- Feature flags (Path 1) when the agent calls the SigNoz HTTP API directly
  with an API key or a session, for example to build dashboard JSON or to
  send `query_range` requests itself.
- The SQL probe (Path 2) for any agent on the SigNoz MCP server: Claude Code,
  another coding agent, or an agent running inside SigNoz. The MCP server has
  no feature-flag tool, so the probe runs through `signoz_execute_builder_query`.
  An in-product agent whose host already supplies the resolved flags should
  use those and skip the probe.

If the user names the tenant mode or pastes a schema, use that instead.

### Path 1: feature flags (direct HTTP access)

`GET /api/v2/features` returns every feature flag with its value resolved for
the caller's org. Authenticate with the `SIGNOZ-API-KEY` header or a logged-in
session. Two flags decide the body column:

```sh
curl -s -H "SIGNOZ-API-KEY: $SIGNOZ_API_KEY" "$SIGNOZ_URL/api/v2/features" \
  | jq '.data[] | select(.name == "use_json_body" or .name == "json_body_dual_ingestion")
        | {name, resolvedValue}'
```

| `use_json_body` | `json_body_dual_ingestion` | Mode |
|---|---|---|
| `true` | any | JSON body |
| `false` | `true` | Dual ingestion |
| `false` | `false` | Legacy |

`use_json_body` is the switch the SigNoz query builder consults. With it on,
`body.*` filters resolve to `body_v2` and a bare `body` search targets
`body_v2.message`, so a custom SQL panel that follows the flag stays consistent
with the Logs Explorer on the same tenant.

### Path 2: SQL probe (any agent on the MCP server, or no API access)

Run this through `signoz_execute_builder_query` or `POST /api/v5/query_range`
as a `clickhouse_sql` envelope with `requestType: "scalar"` and a `start`/`end`
window covering the last 15 minutes (see "Running the SQL" in SKILL.md). The
backend fills the `$` variables from `start` and `end`.

```sql
SELECT countIf(body != '') AS legacy_body_rows,
       countIf(body_v2.message != '') AS json_message_rows
FROM signoz_logs.distributed_logs_v2
WHERE timestamp >= $start_timestamp_nano AND timestamp <= $end_timestamp_nano
  AND ts_bucket_start BETWEEN $start_timestamp - 1800 AND $end_timestamp
```

| Result | Mode |
|---|---|
| Error `Code: 47` (unknown identifier `body_v2`) | Legacy; the column does not exist |
| `legacy_body_rows > 0` and `json_message_rows > 0` | Dual ingestion |
| `legacy_body_rows = 0` and `json_message_rows > 0` | JSON body |
| Both `0` | No logs in the window; widen it or ask the user |

`SELECT name, type FROM system.columns WHERE database = 'signoz_logs' AND
table = 'distributed_logs_v2' AND name LIKE 'body%'` answers the column
question directly, but the ClickHouse user behind a managed tenant may lack
access to `system.columns`. The count probe works on every tenant.

### Panels whose range crosses the cut-over

A flag flip does not rewrite history. On a tenant that moved to JSON bodies,
rows ingested before the move keep their text in `body` and later rows in
`body_v2`. Run the count probe over the panel's own range when the range
starts before the move, and read text across both columns with
`if(body != '', body, toString(body_v2))`. That expression engages no skip
index, so reserve it for the crossing range and use the single-column
patterns otherwise.

When the mode is JSON body, every body pattern in this file that mentions
`body` must be written against `body_v2` as described in "JSON Body
(`body_v2`)". `JSONExtractString(body, ...)` and `lower(body) LIKE ...` return
nothing on such a tenant because `body` is empty.

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

- `$start_timestamp_nano` / `$end_timestamp_nano`: nanosecond precision, filters the `timestamp` column.
- `$start_timestamp` / `$end_timestamp`: seconds precision, filters the `ts_bucket_start` column.
- The `- 1800` is required because `ts_bucket_start` is rounded down to 30-minute intervals.

### 3. Use Indexed (Selected) Columns Over Map Access

When an attribute has been promoted to a selected (indexed) field, a dedicated materialized column is created:

| Instead of | Use |
|---|---|
| `attributes_string['method']` | `attribute_string_method` |
| `attributes_number['response.time']` | `attribute_number_response$$time` |
| `attributes_bool['is_error']` | `attribute_bool_is_error` |

**Naming convention**: prefix with `attribute_<dataType>_`, replace `.` with `$$` for dotted attribute names.

An `_exists` variant is also created: `attribute_string_method_exists Bool`: use this to check existence of an indexed attribute.

### 4. Use GLOBAL IN for Resource Fingerprint Subquery

Always use `GLOBAL IN`, not plain `IN`:

```sql
WHERE resource_fingerprint GLOBAL IN __resource_filter
```

Plain `IN` or `JOIN` with a distributed table in its subquery fails when
`distributed_product_mode='deny'`. Prefer the time-bounded fingerprint
`GLOBAL IN` pattern above, then a local table in the subquery. Do not default to
`GLOBAL JOIN`: it broadcasts the RHS to every shard and is safe only when that
dataset is demonstrably small and bounded.

### 5. Complete GROUP BY Projections

Every non-aggregated `SELECT` expression must appear in `GROUP BY`, including
computed expressions: `SELECT JSONExtractString(body, 'kind') AS kind, count() ... GROUP BY kind`.

### 6. Body Text Search: Engaging Skip Indexes

The `body` column has two skip indexes, **both on `lower(body)`**:

```sql
INDEX body_index_v2_token  lower(body) TYPE tokenbf_v1(10000, 2, 0)   GRANULARITY 1,
INDEX body_index_v2_ngram  lower(body) TYPE ngrambf_v1(4, 15000, 3, 0) GRANULARITY 1
```

ClickHouse compares predicate ASTs to the index expression **literally**. A predicate must reference `lower(body)` to engage either index; `hasToken(body, …)` and `body LIKE '%x%'` prune nothing.

#### Predicate engagement

| Predicate | tokenbf | ngrambf | Notes |
|---|:-:|:-:|---|
| `hasToken(lower(body), 'tok')` | yes | no | Whole-token check; best for distinctive single words. |
| `lower(body) = 'literal'` | yes | yes | Exact equality. |
| `lower(body) LIKE '%substr%'` | no | yes | Substring must be ≥ 4 chars (ngrambf `N=4`). |
| `lower(body) LIKE '%a%b%'` | no | yes | n-grams of each substring ANDed, more selective. |
| `lower(body) ILIKE '%x%'` | no | sometimes | Prefer the explicit `lower(body) LIKE '%x%'` form. |
| `position(body, 'x') > 0` | no | no | Always rewrite to `lower(body) LIKE`. |
| `positionCaseInsensitive(body, 'X') > 0` | no | no | Biggest trap: engages neither even with `lower(body)` index. |
| `match(lower(body), 'regex')` | no | partial | Only literal substrings inside the regex are usable. |

#### Anti-patterns to rewrite

| Replace | With |
|---|---|
| `positionCaseInsensitive(body, 'Foo')` | `lower(body) LIKE '%foo%'` |
| `position(body, 'foo') > 0` | `lower(body) LIKE '%foo%'` |
| `body LIKE '%Foo%'` | `lower(body) LIKE '%foo%'` |
| `hasToken(body, 'foo')` | `hasToken(lower(body), 'foo')` |

Lowercase the literal (the index value is lowercase). Escape `%` and `_` in the literal; pass other characters (hyphens, dots, parens, colons) through as-is.

#### OR-of-LIKE: add a common AND-prefix

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

Pick the AND-prefix in this order: (1) most distinctive single token via `hasToken`, (2) two ANDed `hasToken` calls, (3) distinctive shared substring via `LIKE`. Avoid common words like `the`, `user`, `error`: high false-positive rate on the bloom filter.

#### Hyphens and punctuation split tokens

`tokenbf` only stores `[A-Za-z0-9_]+` runs. Anything else (hyphens, dots, slashes, quotes, parens, colons) is a token boundary. So:

- `hasToken(lower(body), 'settlement-requested')` fails with `Code: 36, BAD_ARGUMENTS`
  (`Needle must not contain whitespace or separator characters`).
- Use `hasToken(lower(body), 'settlement') AND hasToken(lower(body), 'requested')`, or
- Use `lower(body) LIKE '%settlement-requested%'` (ngrambf handles punctuation).

#### Verify with `EXPLAIN indexes=1`

```sql
EXPLAIN indexes=1
<your query>;
```

Each `Skip` block under `ReadFromMergeTree` shows `Granules: kept/total`. For both `body_index_v2_token` and `body_index_v2_ngram`, kept should be `<` total. The `Combined` block is what feeds the actual scan; that's the number to drive down.

Failure modes:
- `Granules: 195/195` means the predicate doesn't match the index expression, or the chosen token is too common.
- `Skip` block missing: predicate engages no skip index at all.

`tokenbf_v1(10000, …)` is small and saturates at high cardinality; `ngrambf_v1(4, 15000, …)` is the workhorse. If tokenbf looks idle even with a correct `hasToken(lower(body), …)`, lean on `lower(body) LIKE` rather than chasing tokenbf pruning the filter size won't deliver.

#### Type traps in body-search queries

- `toUnixTimestamp64Nano(now())` → `Code: 43, ILLEGAL_TYPE_OF_ARGUMENT`. Use `now64()` (or `toDateTime64(now(), 9)`). SigNoz dashboard macros like `$start_timestamp_nano` resolve to literal integers and sidestep this.
- `max(fromUnixTimestamp64Nano(timestamp))` converts every row before aggregating. Use `fromUnixTimestamp64Nano(max(timestamp))`: `max` once on cheap UInt64, convert once at the end.

---

## JSON Body (`body_v2`)

Read this section whenever the tenant is in JSON body mode (see "Which Body
Column Holds the Text") or the user asks for a filter, GROUP BY, or
aggregation on a key inside the log body.

The column type is `JSON(max_dynamic_paths = 0, message String)`. Two
consequences drive every pattern below:

- `message` is a typed sub-column. `body_v2.message` is a plain `String`
  column: non-nullable, cheap to read, and present on every row. Plain-text
  logs arrive as `{"message": "<text>"}`, and the ingest pipeline promotes
  `msg` and `log` keys into `message`. A row without a message stores `''`.
- `max_dynamic_paths = 0` sends every other key to the JSON shared data. Reading
  a key means decoding shared data for that row, so a filter on a key is more
  expensive than a filter on `message`, and `toString(body_v2)` rebuilds the
  whole document for every row it touches.

### Access syntax

| Need | Expression | Result type |
|---|---|---|
| Message text | `body_v2.message` | `String` |
| Any other key, typed | ``dynamicElement(body_v2.`level`, 'String')`` | `Nullable(String)` |
| Nested key | ``dynamicElement(body_v2.`user.name`, 'String')`` | `Nullable(String)` |
| Integer key | ``dynamicElement(body_v2.`user.id`, 'Int64')`` | `Nullable(Int64)` |
| Float key | ``dynamicElement(body_v2.`latency`, 'Float64')`` | `Nullable(Float64)` |
| Bool key | ``dynamicElement(body_v2.`ok`, 'Bool')`` | `Nullable(Bool)` |
| Array of strings | ``dynamicElement(body_v2.`tags`, 'Array(Nullable(String))')`` | `Array(Nullable(String))` |
| Array of objects | ``dynamicElement(body_v2.`items`, 'Array(JSON(max_dynamic_types=16, max_dynamic_paths=0))')`` | `Array(JSON(...))` |
| Whole document as text | `toString(body_v2)` | `String` |
| Keys present in the row | `JSONAllPaths(body_v2)` | `Array(String)` |

Rules:

- Quote the path with backticks and write nested keys with dots inside the
  backticks: `` body_v2.`user.name` ``. This is the same path as
  `body_v2.user.name`; the backticked form also survives keys that contain
  hyphens or other punctuation.
- A bare `` body_v2.`level` `` is `Dynamic`. It compares against a string
  literal, but ClickHouse rejects it as a GROUP BY key (`Code: 44,
  ILLEGAL_COLUMN`) and rejects a numeric comparison once the key holds both
  numbers and strings (`Code: 386, NO_COMMON_TYPE`), so a panel that works
  today breaks when one differently typed row arrives. Always wrap it in
  `dynamicElement(..., '<type>')`.
- The type string must match the stored type exactly. `dynamicElement` returns
  `NULL` (or an empty array) on a mismatch instead of erroring. Discover types
  with ``SELECT dynamicType(body_v2.`key`) AS t, count() FROM ... GROUP BY t``
  over a short window, or read `signoz_metadata.distributed_field_keys` where
  `signal = 'logs' AND field_context = 'body'` (columns `field_name`,
  `field_data_type`, `last_seen`).
- Arrays of objects carry the JSON parameters in their type string. At the top
  level it is `Array(JSON(max_dynamic_types=16, max_dynamic_paths=0))`; one
  level deeper it is `Array(JSON(max_dynamic_types=8, max_dynamic_paths=0))`.
  Copy the string that `dynamicType` returns; a wrong parameter yields an empty
  array and silently matches nothing.

### Path skip index: pair every key filter with `has(JSONAllPaths(body_v2), '<key>')`

`dynamicElement(...) = 'x'` on its own engages no skip index. Adding
`has(JSONAllPaths(body_v2), 'level')` engages `body_v2_paths_token_idx` and
`body_v2_paths_ngram_idx`, which prune every granule where no row carries that
key. This mirrors what the SigNoz query builder emits for every positive
operator. Use the key path exactly as `JSONAllPaths` reports it (nested keys
are dotted, arrays of objects report the array key only, e.g. `items`).

```sql
WHERE has(JSONAllPaths(body_v2), 'level')
  AND dynamicElement(body_v2.`level`, 'String') = 'error'
```

The index only helps for keys that are absent from most rows. A key present on
every row keeps every granule, which is harmless.

### Numeric keys: handle Int64 and Float64 collisions

JSON stores `20` as `Int64` and `20.5` as `Float64`, so one key commonly holds
both types across rows. ``dynamicElement(body_v2.`latency`, 'Float64') > 30``
skips every integer row. Coalesce both types:

```sql
coalesce(
    dynamicElement(body_v2.`latency`, 'Float64'),
    toFloat64(dynamicElement(body_v2.`latency`, 'Int64'))
) AS latency
```

Do the same for string keys that sometimes arrive as numbers (`status` as
`200` and `"200"`): coalesce the `String` element with
`toString(dynamicElement(..., 'Int64'))`.

### Absent keys: NULL semantics and negative operators

- Exists: ``dynamicElement(body_v2.`key`, 'String') IS NOT NULL``.
- Not exists: `` body_v2.`key` IS NULL ``.
- For `message`, existence is `body_v2.message != ''`; the sub-column is never
  NULL.
- Negative operators drop absent rows. `dynamicElement(..., 'String') != 'x'`
  evaluates to NULL for rows without the key, and NULL never passes a
  `WHERE`. When "not equal" should include rows without the key, wrap the
  element: ``assumeNotNull(dynamicElement(body_v2.`key`, 'String')) != 'x'``.
  The same applies to `NOT LIKE`, `NOT IN`, and `NOT BETWEEN`.

### Arrays

- Scalar arrays: ``has(dynamicElement(body_v2.`tags`, 'Array(Nullable(String))'), 'prod')``,
  or `arrayExists(x -> x LIKE 'prod%', dynamicElement(...))` for pattern
  matches.
- Arrays of objects: `arrayExists` over the typed array, reading each element's
  keys with `dynamicElement` again:

```sql
arrayExists(
    item -> dynamicElement(item.`sku`, 'String') = 'ABC-1',
    dynamicElement(body_v2.`items`, 'Array(JSON(max_dynamic_types=16, max_dynamic_paths=0))')
)
```

  Index lookups (`items[0]`) are not a supported query pattern; SigNoz matches
  any element.

### Whole-document text search

Two skip indexes cover `lower(toString(body_v2))`, so the legacy predicate table
applies once `body` is replaced with `toString(body_v2)`:

| Predicate | tokenbf | ngrambf |
|---|:-:|:-:|
| `hasToken(lower(toString(body_v2)), 'tok')` | yes | no |
| `lower(toString(body_v2)) LIKE '%substr%'` | no | yes |
| `toString(body_v2) LIKE '%x%'` (no `lower`) | no | no |
| `lower(body_v2.message) LIKE '%x%'` | no | no |
| `hasToken(lower(body_v2.message), 'tok')` | no | no |

`toString(body_v2)` rebuilds the document for every row in a kept granule.
SigNoz budgets such a search at one tenth of the rows it allows for a `body`
scan (6M versus 60M rows per shard by default). Apply it in this order:

1. When the text lives in the message, filter on `lower(body_v2.message)`.
   It has no skip index but reads one cheap column, and ClickHouse evaluates
   it in PREWHERE.
2. Add `hasToken(lower(toString(body_v2)), '<rare token>')` beside it only when
   a distinctive token exists; the token index prunes granules and the message
   predicate validates rows.
3. Use `lower(toString(body_v2)) LIKE '%...%'` alone only when the text may sit
   under any key. Keep the window short.

`hasToken` rejects needles with separators (`-`, `.`, `@`, `/`, space) with
`Code: 36`. Split the needle into alphanumeric tokens or use `LIKE`.

### GROUP BY on a body key

Project the typed element and filter on key presence so the NULL group
disappears and the path index engages:

```sql
SELECT dynamicElement(body_v2.`level`, 'String') AS level, toFloat64(count()) AS value
FROM signoz_logs.distributed_logs_v2
WHERE ... AND has(JSONAllPaths(body_v2), 'level')
GROUP BY level
ORDER BY value DESC
```

For a key with mixed types, group on the coalesced expression from the numeric
section, not on the raw `Dynamic` value.

### Porting a legacy body query

| Legacy (`body` String) | JSON body (`body_v2`) |
|---|---|
| `JSONExtractString(body, 'level')` | ``dynamicElement(body_v2.`level`, 'String')`` |
| `JSONExtractInt(body, 'status')` | ``dynamicElement(body_v2.`status`, 'Int64')`` |
| `JSONExtractFloat(body, 'latency')` | the `coalesce` form from the numeric section |
| `JSON_EXISTS(body, '$.user.id')` | `has(JSONAllPaths(body_v2), 'user.id')` |
| `lower(body) LIKE '%x%'` | `lower(body_v2.message) LIKE '%x%'` or `lower(toString(body_v2)) LIKE '%x%'` |
| `hasToken(lower(body), 'x')` | `hasToken(lower(toString(body_v2)), 'x')` |
| `body` in SELECT | `toString(body_v2) AS body` |
| `OCTET_LENGTH(body)` | `OCTET_LENGTH(toString(body_v2))` |

`JSONExtractString(toString(body_v2), 'level')` also works as a mechanical
drop-in, but it pays the document rebuild on every row and engages no index.
Use it only for a one-off check.

### `body_promoted`

The column exists next to `body_v2` and the collector may write promoted paths
into it, but the SigNoz query path does not read it. Do not query
`body_promoted`; reach every key through `body_v2`.

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

### Log body keys (JSON body tenants)
```sql
body_v2.message                                        -- typed String sub-column
dynamicElement(body_v2.`user.name`, 'String')          -- any other key, Nullable
has(JSONAllPaths(body_v2), 'user.name')                -- key present; engages the path index
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
| `$start_timestamp_ms`, `$end_timestamp_ms` | Int64 | Same range in milliseconds |
| `$start_datetime`, `$end_datetime` | DateTime | `toDateTime(<seconds>)`; for traces, never for the logs `timestamp` column |

The same variables are filled from `start` and `end` when the SQL runs through
`POST /api/v5/query_range` or `signoz_execute_builder_query`, so a panel query
can be dry-run unchanged. Dashboard-defined variables travel in the request's
`variables` map and substitute as `$name`, `{{name}}`, or `[[name]]`.

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

### Timeseries: Count per minute grouped by container name

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

### Timeseries: Filtered by service, severity, and attribute

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

### Advanced: Top 10 largest logs for payload auditing

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

## Query Examples: JSON Body

All examples assume a JSON body tenant (see "Which Body Column Holds the
Text"). Each one was run against the `body_v2` schema.

### Timeseries: error-level logs per minute by a body key

```sql
SELECT
    toStartOfInterval(fromUnixTimestamp64Nano(timestamp), INTERVAL 1 MINUTE) AS ts,
    toFloat64(count()) AS value
FROM signoz_logs.distributed_logs_v2
WHERE
    timestamp >= $start_timestamp_nano AND timestamp <= $end_timestamp_nano AND
    ts_bucket_start BETWEEN $start_timestamp - 1800 AND $end_timestamp AND
    has(JSONAllPaths(body_v2), 'level') AND
    dynamicElement(body_v2.`level`, 'String') = 'error'
GROUP BY ts
ORDER BY ts ASC
SETTINGS log_comment = 'signoz-writing-clickhouse-queries skill | YYYY-MM-DD';
```

### Table: top 10 users by log count from a nested key

```sql
SELECT
    dynamicElement(body_v2.`user.name`, 'String') AS user_name,
    toFloat64(count()) AS value
FROM signoz_logs.distributed_logs_v2
WHERE
    timestamp >= $start_timestamp_nano AND timestamp <= $end_timestamp_nano AND
    ts_bucket_start BETWEEN $start_timestamp - 1800 AND $end_timestamp AND
    has(JSONAllPaths(body_v2), 'user.name')
GROUP BY user_name
ORDER BY value DESC
LIMIT 10
SETTINGS log_comment = 'signoz-writing-clickhouse-queries skill | YYYY-MM-DD';
```

### Timeseries: p95 of a numeric body key with mixed Int64/Float64 rows

```sql
SELECT
    toStartOfInterval(fromUnixTimestamp64Nano(timestamp), INTERVAL 1 MINUTE) AS ts,
    quantile(0.95)(coalesce(
        dynamicElement(body_v2.`latency`, 'Float64'),
        toFloat64(dynamicElement(body_v2.`latency`, 'Int64'))
    )) AS value
FROM signoz_logs.distributed_logs_v2
WHERE
    timestamp >= $start_timestamp_nano AND timestamp <= $end_timestamp_nano AND
    ts_bucket_start BETWEEN $start_timestamp - 1800 AND $end_timestamp AND
    has(JSONAllPaths(body_v2), 'latency')
GROUP BY ts
ORDER BY ts ASC
SETTINGS log_comment = 'signoz-writing-clickhouse-queries skill | YYYY-MM-DD';
```

### Value: count of messages containing a phrase, for one service

The token predicate prunes granules through `body_v2_string_token_idx`; the
message predicate validates rows cheaply.

```sql
WITH __resource_filter AS (
    SELECT fingerprint
    FROM signoz_logs.distributed_logs_v2_resource
    WHERE (simpleJSONExtractString(labels, 'service.name') = 'settlements')
    AND seen_at_ts_bucket_start BETWEEN $start_timestamp - 1800 AND $end_timestamp
)
SELECT toFloat64(count()) AS value
FROM signoz_logs.distributed_logs_v2
WHERE
    resource_fingerprint GLOBAL IN __resource_filter AND
    timestamp >= $start_timestamp_nano AND timestamp <= $end_timestamp_nano AND
    ts_bucket_start BETWEEN $start_timestamp - 1800 AND $end_timestamp AND
    hasToken(lower(toString(body_v2)), 'settlement') AND
    lower(body_v2.message) LIKE '%settlement-requested%'
SETTINGS log_comment = 'signoz-writing-clickhouse-queries skill | YYYY-MM-DD';
```

### Value: logs where any item in a body array matches

```sql
SELECT toFloat64(count()) AS value
FROM signoz_logs.distributed_logs_v2
WHERE
    timestamp >= $start_timestamp_nano AND timestamp <= $end_timestamp_nano AND
    ts_bucket_start BETWEEN $start_timestamp - 1800 AND $end_timestamp AND
    has(JSONAllPaths(body_v2), 'items') AND
    arrayExists(
        item -> dynamicElement(item.`sku`, 'String') = 'ABC-1',
        dynamicElement(body_v2.`items`, 'Array(JSON(max_dynamic_types=16, max_dynamic_paths=0))')
    )
SETTINGS log_comment = 'signoz-writing-clickhouse-queries skill | YYYY-MM-DD';
```

---

## Query Optimization Checklist

Before finalizing any query, verify:

- [ ] **Resource filter CTE** is present when filtering by resource attributes (`service.name`, `k8s.*`, etc.)
- [ ] Do **not** add the resource CTE if no resource attribute filtering is needed
- [ ] **`ts_bucket_start`** filter is included: `BETWEEN $start_timestamp - 1800 AND $end_timestamp`
- [ ] **Nanosecond variables** used for the `timestamp` column: `$start_timestamp_nano` / `$end_timestamp_nano`
- [ ] **`fromUnixTimestamp64Nano(timestamp)`** used in SELECT when displaying timestamps
- [ ] **`GLOBAL IN`** is used (not plain `IN`) for the resource fingerprint subquery
- [ ] Every non-aggregated projection, including computed expressions, appears in `GROUP BY`
- [ ] **Indexed columns** used over map access where the attribute is a selected field
- [ ] **Body column** matches the tenant mode found through the feature flags (direct HTTP) or the SQL probe (MCP): `body` on legacy and dual-ingestion tenants, `body_v2` on JSON body tenants (where `body` is empty)
- [ ] **Body searches** use `lower(body)` (not raw `body`) and `LIKE` (not `position` / `positionCaseInsensitive`); for OR'd patterns, a shared `hasToken` or `LIKE` is ANDed before the OR block
- [ ] **JSON body keys** are read with ``dynamicElement(body_v2.`key`, '<type>')`` (never a bare `` body_v2.`key` `` compared to a literal), and message text with `body_v2.message`
- [ ] **JSON body key filters** carry `has(JSONAllPaths(body_v2), '<key>')` so the path skip index engages
- [ ] **JSON body numeric keys** coalesce `Float64` and `Int64` elements; negative operators wrap the element in `assumeNotNull`
- [ ] **JSON body text search** uses `lower(body_v2.message)` or `lower(toString(body_v2))`, never `toString(body_v2)` without `lower`
- [ ] **`seen_at_ts_bucket_start`** filter is included in the resource CTE
- [ ] For timeseries: results are ordered by `ts ASC`
- [ ] **Table Name**: use `signoz_logs.distributed_logs_v2`, never `signoz_logs.logs`, bare `logs`, or `distributed_logs`
- [ ] If multiple tables are joined, ensure all tables have timestamp and bucket filter applied if applicable.
