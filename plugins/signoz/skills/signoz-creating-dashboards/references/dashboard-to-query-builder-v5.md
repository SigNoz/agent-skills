# Perses dashboard query to Query Builder v5 execution

## Contents

- [Purpose](#purpose)
- [Authoritative resources](#authoritative-resources)
- [Persisted dashboard shape](#persisted-dashboard-shape)
- [Queryless text panels](#queryless-text-panels)
- [Find the one panel query](#find-the-one-panel-query)
- [Translate query plugins](#translate-query-plugins)
- [Builder query mapping](#builder-query-mapping)
- [Formula mapping](#formula-mapping)
- [Bounds and ordering](#bounds-and-ordering)
- [Trace operator mapping](#trace-operator-mapping)
- [PromQL and ClickHouse mapping](#promql-and-clickhouse-mapping)
- [Variables](#variables)
- [Request envelope](#request-envelope)
- [Validation gaps](#validation-gaps)
- [Save discipline](#save-discipline)
- [Checklist](#checklist)

## Purpose

Perses dashboard panels and `signoz_execute_builder_query` use related but
different representations. Persist the Perses panel unchanged. Build a separate
Query Builder v5 execution request only to validate its query.

This guide is a translation checklist, not a schema copy. Tool schemas and MCP
resources remain authoritative.

## Authoritative resources

Read these before translating:

1. `signoz://dashboard/instructions`
2. `signoz://dashboard/widgets-instructions`
3. `signoz://dashboard/widgets-examples`
4. `signoz://dashboard/query-builder-example`
5. The relevant logs, traces, metrics, PromQL, or ClickHouse resource

If a resource and this guide differ, follow the resource.

## Persisted dashboard shape

A v6 dashboard keeps panels in `spec.panels`, a map keyed by panel id.

Each rendered panel has one Grid item in
`spec.layouts[n].spec.items`. The link is:

`content.$ref: "#/spec/panels/<panel-id>"`

Patch a panel at `/spec/panels/<panel-id>`. Patch its position at
`/spec/layouts/<layout-index>/spec/items/<item-index>`.

Do not create or retain legacy `widgets`, `layout`, `panelMap`,
`panelTypes`, `queryData`, `selectedLogFields`, or
`selectedTracesFields`.

## Queryless text panels

A `signoz/TextPanel` is intentionally queryless.

It must use mode `markdown` or `text` and a non-null empty `queries: []`.
Do not invent an execution query for it. Skip discovery and dry-run for that
panel.

Every other supported query panel has exactly one entry in
`panel.spec.queries`.

## Find the one panel query

Read `spec.panels[panelId].spec.queries[0]`.

That entry may directly contain a query plugin or a
`signoz/CompositeQuery`. A composite query still counts as the panel's one
query; its internal entries become sibling execution envelopes.

Never append a second item to `panel.spec.queries`.

## Translate query plugins

Translate only the query plugin content. Do not send the Perses panel display,
layout, links, visual plugin configuration, or dashboard metadata to the
executor.

Keep the persisted plugin unchanged. The execution request is temporary.

A direct query plugin becomes one execution query envelope. A
`signoz/CompositeQuery` becomes its ordered internal query/formula/operator
entries under `compositeQuery.queries`.

Preserve names, enabled/disabled state, legends, limits, order, filters,
aggregations, and plugin-specific semantics that the execution schema supports.

## Builder query mapping

Map a Perses `signoz/BuilderQuery` to a Query Builder v5
`builder_query` envelope.

The execution spec uses canonical fields:

- `name`
- `signal`
- `source` when applicable
- `stepInterval`
- `aggregations`
- `filter: {expression}`
- `groupBy`
- `having: {expression}`
- `limit`
- `order`
- `legend`
- `disabled`

Group-by entries use `name`, `fieldContext`, `fieldDataType`, and
`signal`. Do not translate them back to old dashboard keys such as `key`,
`type`, or `dataType`.

Use the aggregation guide for metric temporality and valid aggregation pairs.
Use exact discovered metric and field names.

For raw log/trace lists, preserve canonical `selectFields`, limit, and order.
Do not reintroduce editor-only `selectColumns`, `pageSize`, or `orderBy`
unless the current resource explicitly presents them as input to translate.

## Formula mapping

Map a Perses formula to a `builder_formula` envelope. Preserve:

- `name`
- numeric `expression`
- `legend`
- `limit`
- `order`
- `disabled`

A common computed-series pattern has disabled metric inputs and one enabled
formula. An enabled metric output may also depend on disabled metric inputs.
Keep the authored topology.

Do not put comparisons into a numeric formula. Do not silently remove formula
fields merely to make validation pass.

## Bounds and ordering

Bounds and ordering are part of the persisted spec; execute what the panel
stores. Every builder query and formula needs a positive `limit` and non-empty
`order`. Raw/list and trace requests default to 100; raw traces order by
timestamp descending and raw logs add `id` descending. Aggregate logs/traces
order by their primary aggregation. Metrics use the composed aggregation name
or `__result`; formulas use `__result`.

Formula inputs use 10000 because SigNoz limits each component before formula
evaluation. Follow every formula reference, including disabled formulas, to
all base builder-query leaves. Preserve an intentional smaller pre-formula top
N. Narrow filters or grouping if cardinality may exceed 10000. Keep disabled
inputs and dry-run the complete composite.

## Trace operator mapping

Map each trace relationship plugin to a `builder_trace_operator` envelope in
the same composite execution request as the referenced trace queries.

Preserve the operator expression and query names. Do not validate only the base
queries and claim the relationship was tested.

## PromQL and ClickHouse mapping

Map PromQL and ClickHouse plugins to the exact envelope type required by the
current executor schema. Preserve query text byte-for-byte except for
representative dashboard-variable substitution in the temporary dry-run.

Read `signoz://promql/instructions` for dotted OpenTelemetry metric names.
Read the relevant ClickHouse schema and example resources before authoring SQL.

Do not save the execution envelope into the dashboard.

## Variables

The executor does not expand dashboard variables.

For a dry-run, replace each `$variable` with one representative discovered
literal. Preserve the original variable reference in the Perses panel.

Record which values were substituted so the validation result is interpretable.
Do not wire a new variable into panels until the user chooses all panels or a
specific subset.

## Request envelope

Call `signoz_execute_builder_query` with the mandatory tool wrapper:

`{searchContext: "<original request>", query: {schemaVersion, start, end, requestType, compositeQuery, formatOptions, variables}}`

The object inside `query` is the execution payload. Use absolute JSON integer
Unix-millisecond `start` and `end`, the appropriate `requestType`, and the
translated sibling entries under `query.compositeQuery.queries`.

Do not pass the execution payload directly as the tool arguments, and do not
add another `query` or `compositeQuery` wrapper inside `query`.

## Validation gaps

If the executor schema cannot represent a persisted query field, do not delete
that field and call the reduced request equivalent.

Explain the exact unsupported semantic. The user may choose whether to save
despite the gap.

Do not pass a persisted HAVING array to an execution field that expects
`having.expression`, or claim one validates the other, unless the current MCP
resource explicitly defines the translation.

## Save discipline

After a successful dry-run, save or patch the original Perses query, not the
temporary execution request.

For full dashboard replacement, preserve all unchanged authored fields and
strip only known server-populated fields. For targeted changes, prefer
`signoz_patch_dashboard`.

Do not replay a write after an ambiguous failure.

## Checklist

- The dashboard is v6 Perses.
- The panel exists in `spec.panels`.
- Its Grid item references `#/spec/panels/<id>`.
- A TextPanel has `queries: []` and no dry-run.
- Every query panel has exactly one panel query entry.
- Composite internals became sibling execution envelopes.
- Metric/field names came from discovery.
- Dashboard variables were substituted only in the dry-run.
- Absolute integer millisecond bounds were used.
- No legacy dashboard fields entered the saved payload.
- Unsupported semantics were surfaced rather than stripped.
- The persisted Perses query remained unchanged after translation.
