# Dashboard JSON to Query Builder v5

<!-- Keep this file byte-identical in both dashboard skills. -->

Saved dashboard/editor JSON and `signoz_execute_builder_query` use different
contracts. Use the current tool schema to decide what MCP accepts and the
required Query Builder resources to build supported fields. This file only maps
the contract boundary; never pass widget JSON to the execution tool.

## Lossless gate

Inventory every result-affecting field, including disabled dependencies. If a
field has no exact equivalent in the current MCP tool schema, do not omit it and
claim validation. Name the gap and write only after the user explicitly accepts
an unvalidated panel. Treat Builder `functions` as unsupported unless the tool
schema exposes them. `legend` may remain saved-only.

## Translate one panel

Saved panels persist no time range. Build the complete outer `query` with
absolute `start` / `end` as JSON integer Unix-ms (for example, the last hour),
request type, composite queries, format options, and representative variable
values; omitted bounds fail with `missing start or end timestamp`.
Start every dry-run with the shortest representative window likely to contain
data, usually the last 30-60 minutes; never use the panel's display range by reflex.
If empty, widen according to signal cadence and report the exact windows tested
rather than concluding telemetry is absent. A dry-run validates execution only
for that window, not correctness across every dashboard range. A PromQL range
selector looks backward from each evaluation timestamp: widening outer `start` /
`end` adds evaluations rather than "covering" a long selector, and long selectors
such as `[12h]` remain costly even with short outer bounds.

On a timeout, never resend the identical payload. Shrink the window, coarsen the
type-appropriate interval when available (PromQL `step`; Builder
`stepInterval`; ClickHouse has no equivalent), or reduce query cost first.

Dashboard request types are: graph/bar/histogram -> `time_series`;
table/pie/value -> `scalar`; trace -> `trace`; list -> `raw`. These are the only
execution values; never invent `aggregate`, `table`, or `timeseries`. MCP
dashboard writes validate `panelTypes` against
graph/value/table/list/bar/pie/histogram only; never author a new trace panel.
Use a list panel with raw trace rows instead; keep `trace` -> `trace` only when
executing an existing saved panel.

Put every dependency in one `compositeQuery.queries` array: `queryData[]` ->
`builder_query`; `queryFormulas[]` -> sibling `builder_formula`;
`queryTraceOperator[]` -> sibling `builder_trace_operator`.

For each `builder_query`:

- `queryName` -> `name`; `dataSource` -> `signal`.
- Use `filter.expression`, or convert `filters.items[]` and `filters.op` exactly.
  Saved operators use underscore enums (`NOT_IN`); execution expressions use
  SQL-ish forms (`NOT IN`). Translate, never mix representations, and keep both
  forms semantically aligned when saved JSON contains both. Never send `filters`.
- Saved `groupBy[].key/dataType/type` -> execution
  `name/fieldDataType/fieldContext`; set `signal` from the field or enclosing
  query. For "by <dimension>", `name` is the actual attribute key and never
  empty; omit `groupBy` when ungrouped. Send no dashboard aliases.
- `selectColumns[]` -> `selectFields[]`: `name` from `name` or `key`,
  `fieldDataType` from `fieldDataType` or `dataType`, `fieldContext` from
  `fieldContext` or `type`, plus `signal`. Send only canonical metadata.
- Every builder query needs a positive `limit` and non-empty ordering. Raw/list
  requests and trace-signal `requestType: trace` default to 100. An intentional
  smaller positive list `pageSize` may override it; scalar and time-series
  standalone queries default to 100. Every query referenced by a formula uses
  10000 because SigNoz limits each component before formula evaluation; raise
  an existing smaller value unless it intentionally selects top N before the
  formula. Preserve other positive saved limits; otherwise apply the relevant
  default. For bounds, inspect every formula expression, including formulas
  with `disabled: true`, and follow formula references until all base
  `builder_query` leaves are found. This dependency walk does not establish
  deterministic formula-to-formula evaluation order; validate the complete
  translated payload. Raw and trace-request traces use
  timestamp desc; raw logs add id desc; aggregate logs/traces use the primary
  aggregation desc. For those signals, map editor
  `{columnName,order}` -> v5 `{key:{name:columnName},direction:order}`. A saved
  metric query orders by its primary aggregation in editor `orderBy`, but its
  v5 `order` key is `__result`; preserve the direction while making that
  special-case translation.
- Preserve schema-supported fields such as `disabled`, `source`, and
  `stepInterval`; map `offset` only for raw/trace requests.
- Metrics: emit one V5 aggregation from `aggregations[0]`, falling back to
  `aggregateAttribute.key/temporality` and top-level time/space aggregation;
  include `reduceTo` for table/pie/value.
- Logs/traces: split function calls inside combined `aggregations[].expression`
  values into separate V5 aggregations, preserve aliases, default to `count()`
  only when none exists, and omit for raw requests.
- Preserve `having.expression`. The frontend drops a non-empty saved HAVING
  clause array: never execute that array or claim an expression probe validates
  it; warn that the saved panel may ignore it.

Formula: set `spec.name` from `queryName`, preserve `expression`/`disabled` and
supported `legend`; require/copy positive result `limit` (default 100) and map
non-empty `orderBy` to v5 `order` (default `__result desc`). Keep its referenced
base queries at 10000 so they are not independently truncated before evaluation,
including base-query leaves reached through a disabled formula expression.

Trace operator: emit a raw-preserved `builder_trace_operator` with `name` from
`queryName`, `expression`, applicable mappings above, and trace V5 aggregations
(`count()` for a count panel; omit for raw). Never coerce it to `builder_query`,
copy dashboard aliases, or invent `signal`, `filter`, `functions`, or `disabled`.

## PromQL and ClickHouse panels

These bypass the Builder crosswalk, but their execution envelopes are fixed. Saved
widgets use `query.promql[]` / `query.clickhouse_sql[]` with `queryType`; never
copy those arrays under execution `compositeQuery`.
Map each saved `query.promql[]` item to one `compositeQuery.queries[]` entry:
`{"type": "promql", "spec": {"name": "A", "query": "<promql>"}}`. Optional
spec fields are `disabled`, `step`, `stats`, and `legend`. The type is exactly
`promql`, never `promql_query`.
Map each saved `query.clickhouse_sql[]` item to one `compositeQuery.queries[]`
entry: `{"type": "clickhouse_sql", "spec": {"name": "A", "query": "<sql>"}}`;
optional spec fields are `disabled` and `legend`.
Always set `requestType` with the Builder panel mapping above. The server's
`time_series` default when PromQL omits it is fallback only; ClickHouse has no
default. Substitute representative literals for `$var` in dry-runs only; saved
panels keep `$var`. Read `signoz://promql/instructions` for selector syntax and
the matching `signoz://dashboard/clickhouse-*` resources for ClickHouse schema.

## Saved payload invariant

Dashboard writes keep editor aliases: `queryName`, `dataSource`, `filters`,
positive `limit`, `pageSize`, non-empty `orderBy`, `selectColumns`, clause-array HAVING,
`queryTraceOperator`, and `groupBy[].key/dataType/type`. Canonical names belong
only in `signoz_execute_builder_query`.
