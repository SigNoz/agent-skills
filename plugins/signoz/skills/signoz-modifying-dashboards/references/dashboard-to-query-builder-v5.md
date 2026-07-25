# Dashboard JSON to Query Builder v5

<!-- Keep this file byte-identical in both dashboard skills. -->

A panel saves each query as the same Query Builder v5 spec that
`signoz_execute_builder_query` executes, so a dry-run is an envelope change and
never a rename: lift the saved spec verbatim and wrap it. This file only maps
that envelope; never pass panel JSON to the execution tool.

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

The query envelope's `kind` is the outer `requestType`, unchanged:
graph/bar/histogram panels save `time_series`; table/pie/value save `scalar`;
list saves `raw`; an existing trace panel saves `trace`. These are the only
execution values; never invent `aggregate`, `table`, or `timeseries`. There is
no trace panel plugin to author — use `signoz/ListPanel` with raw trace rows.

Put every dependency in one `compositeQuery.queries` array. A panel holds
exactly one query envelope, and its plugin `kind` picks the execution `type`
while `plugin.spec` becomes that entry's `spec`, unchanged:
`signoz/BuilderQuery` -> `builder_query`; `signoz/Formula` ->
`builder_formula`; `signoz/TraceOperator` -> `builder_trace_operator`.
A `signoz/CompositeQuery` already holds `{type, spec}` members — lift its
`spec.queries` into `compositeQuery.queries` as-is.

Bounds and ordering are part of the saved spec, so execute what the panel
stores rather than re-deriving it, and author them when you build the panel:

- Every builder query needs a positive `limit` and non-empty ordering. Raw/list
  requests and trace-signal `requestType: trace` default to 100. An intentional
  smaller positive list bound may override it; scalar and time-series
  standalone queries default to 100. Every query referenced by a formula uses
  10000 because SigNoz limits each component before formula evaluation; raise
  an existing smaller value unless it intentionally selects top N before the
  formula. Preserve other positive saved limits; otherwise apply the relevant
  default. For bounds, inspect every formula expression, including formulas
  with `disabled: true`, and follow formula references until all base
  `builder_query` leaves are found. This dependency walk does not establish
  deterministic formula-to-formula evaluation order; validate the complete
  payload. Raw and trace-request traces use timestamp desc; raw logs add id
  desc; aggregate logs/traces use the primary aggregation desc. A metrics
  `order` key is the composed `spaceAggregation(timeAggregation(metricName))`
  expression — the bare metric name is rejected, while `__result` and groupBy
  keys are accepted; a formula orders by `__result`.
- Time-series top-N ranks groups over the whole window and can omit a
  short-lived local spike. Narrow filters or grouping if formula-input
  cardinality can exceed 10000.
- A formula's inputs are commonly `disabled: true` so only the computed series
  renders. Keep them, keep them disabled, and dry-run the whole composite
  rather than one member.
- Metrics aggregations carry `metricName` / `temporality` / `timeAggregation` /
  `spaceAggregation`, plus `reduceTo` for table/pie/value. Logs and traces use
  separate `{expression}` aggregations named with `alias`, never one combined
  expression string. Both execute as saved, as do `having.expression` and
  `functions`.

## PromQL and ClickHouse panels

These bypass the Builder crosswalk, but their execution envelopes are fixed.
Map a `signoz/PromQLQuery` panel to one `compositeQuery.queries[]` entry:
`{"type": "promql", "spec": {"name": "A", "query": "<promql>"}}`. Optional
spec fields are `disabled`, `step`, `stats`, and `legend`. The type is exactly
`promql`, never `promql_query`.
Map a `signoz/ClickHouseSQL` panel to one `compositeQuery.queries[]`
entry: `{"type": "clickhouse_sql", "spec": {"name": "A", "query": "<sql>"}}`;
optional spec fields are `disabled` and `legend`.
Always set `requestType` from the query envelope's `kind`. The server's
`time_series` default when PromQL omits it is fallback only; ClickHouse has no
default. Substitute representative literals for `$var` in dry-runs only; saved
panels keep `$var`. Read `signoz://promql/instructions` for selector syntax and
the matching `signoz://dashboard/clickhouse-*` resources for ClickHouse schema.

## Saved payload invariant

Dashboard writes save the canonical names: `name`, `signal`,
`filter.expression`, `selectFields`, `groupBy` with
`name`/`fieldDataType`/`fieldContext`, `order`, and `limit`. The editor aliases
`queryName`, `dataSource`, `filters.items`, `pageSize`, `orderBy`,
`selectColumns`, clause-array `having`, and `queryTraceOperator` belong to
neither tool and are rejected.
