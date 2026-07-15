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
an unvalidated panel. Treat Builder `functions` and formula `order`/`limit` as
unsupported unless the tool schema exposes them. `legend` may remain saved-only.

## Translate one panel

Saved panels persist no time range. Build the complete outer `query` with
absolute `start` / `end` as JSON integer Unix-ms (for example, the last hour),
request type, composite queries, format options, and representative variable
values; omitted bounds fail with `missing start or end timestamp`. Dashboard
request types are: graph/bar/histogram -> `time_series`;
table/pie/value -> `scalar`; trace -> `trace`; list -> `raw`. These are the only
values; never invent `aggregate`, `table`, or `timeseries`.

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
- For table/list use `limit`, falling back to `pageSize`; otherwise use `limit`.
  `{columnName,order}` -> `{key:{name:columnName},direction:order}`.
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
supported `legend`; map `orderBy` -> `order` and copy `limit` only when the tool
schema accepts them.

Trace operator: emit a raw-preserved `builder_trace_operator` with `name` from
`queryName`, `expression`, applicable mappings above, and trace V5 aggregations
(`count()` for a count panel; omit for raw). Never coerce it to `builder_query`,
copy dashboard aliases, or invent `signal`, `filter`, `functions`, or `disabled`.

PromQL and ClickHouse bypass this Builder crosswalk; build their current MCP
envelopes from the corresponding resources without dropping fields.

## Saved payload invariant

Dashboard writes keep editor aliases: `queryName`, `dataSource`, `filters`,
`pageSize`, `orderBy`, `selectColumns`, clause-array HAVING,
`queryTraceOperator`, and `groupBy[].key/dataType/type`. Canonical names belong
only in `signoz_execute_builder_query`.
