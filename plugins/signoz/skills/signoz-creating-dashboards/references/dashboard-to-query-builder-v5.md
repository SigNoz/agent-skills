# Dashboard JSON to Query Builder v5

Saved dashboard JSON and `signoz_execute_builder_query` deliberately use
different contracts. Read the current tool schema first; it is authoritative.
Use this reference for the known dashboard-to-execution conversions, but never
send a field that the current schema does not accept.

## Contents

- [Safety gate](#safety-gate)
- [Query envelopes](#query-envelopes)
- [Trace operators](#trace-operators)
- [Structured-field conversions](#structured-field-conversions)
  - [Filters](#filters)
  - [Grouping and selected fields](#grouping-and-selected-fields)
  - [Limit and order](#limit-and-order)
  - [HAVING](#having)
  - [Aggregations](#aggregations)
- [Saved payload invariant](#saved-payload-invariant)

## Safety gate

Before executing a panel, inventory every active `builder.queryData[]`,
`builder.queryFormulas[]`, and `builder.queryTraceOperator[]` field.

- If an execution-affecting field has no equivalent in the current tool schema,
  stop before the dry-run and name the unsupported field. Do not omit it and call
  the resulting query validated. Only continue to create the dashboard if the
  user explicitly accepts that this panel remains unvalidated; report that
  limitation in the final result.
- `legend` is display metadata. Keep it in saved dashboard JSON. If the current
  execution schema omits it, it may be omitted from the dry-run without making
  the data query lossy.
- At the time this reference was written, the MCP execution schema did not
  expose Builder `functions`, or formula `order` and `limit`. Re-check rather
  than assuming this is still true. These fields affect results and therefore
  trigger the safety gate while unsupported.

## Query envelopes

Build the complete outer `query` object required by the current
`signoz_execute_builder_query` schema. Put every active base query and formula
from one panel into the same `compositeQuery.queries` array so formulas can
resolve their referenced names.

For every dashboard `builder.queryData[]` entry, emit a `builder_query`
envelope and translate:

| Dashboard field | Execution field |
|---|---|
| `queryName` | `name` |
| `dataSource` | `signal` |
| `filters` / `filter` | `filter.expression` |
| `pageSize` / `limit` | `limit` |
| `orderBy` | `order` |
| `selectColumns` | `selectFields` |
| `groupBy` | `groupBy` with canonical telemetry fields |
| existing HAVING expression object | `having.expression` |
| non-empty dashboard HAVING clause array | no parity mapping; apply the safety gate |

Preserve supported fields such as `disabled`, `stepInterval`, `offset`,
`source`, and `aggregations` in their current execution-schema shape.

For every dashboard `builder.queryFormulas[]` entry, emit a sibling
`builder_formula` envelope, never a `builder_query`:

- `queryName` -> `name`; preserve `expression` and `disabled`.
- `orderBy[]` -> `order[]` and preserve `limit` only when the current formula
  schema accepts them. Otherwise apply the safety gate.
- Keep formula names such as `F1` unchanged so expressions still resolve.

## Trace operators

For every dashboard `builder.queryTraceOperator[]` entry, emit a sibling
`builder_trace_operator` envelope in the same `compositeQuery.queries` array as
the base queries it references. The current MCP server preserves this
less-common envelope's `spec` as raw JSON and forwards it byte-for-byte; do not
coerce it into `builder_query` or add `builder_query` zero-value fields.

Follow the frontend conversion exactly:

- Set `type: "builder_trace_operator"`, `spec.name` from `queryName`, and
  preserve `expression` (use `""` only when the saved value is absent).
- Map positive `stepInterval`; map `limit` (falling back to `pageSize` only for
  table/list panels); map `offset` only for raw/trace request types; map
  `orderBy[]` to canonical `order[]`; and preserve non-empty `legend`.
- Map `groupBy[]` with `name` from `key`, `fieldDataType` from `dataType`, and
  `fieldContext` from `type`, preserving any saved `description`, `unit`,
  `signal`, and `materialized` values. Map `selectColumns[]` to `selectFields[]`
  with `name` (falling back to `key`), `fieldDataType`, `fieldContext`, and
  `signal`.
- For a raw request omit `aggregations`. Otherwise use trace aggregations:
  split saved aggregation expressions into V5 `{expression, alias?}` entries,
  or use `count()` when the saved trace operator has no aggregation, matching
  the frontend converter.
- Apply the HAVING rules below. Do not copy dashboard aliases such as
  `queryName`, `dataSource`, `pageSize`, `orderBy`, or `selectColumns` into the
  execution spec. The frontend mapping also does not add `signal`, `filter`,
  `functions`, or `disabled` to a trace-operator spec; if any otherwise-dropped
  field is non-empty and execution-affecting, apply the safety gate.

Minimal shape:

```json
{
  "type": "builder_trace_operator",
  "spec": {
    "name": "T1",
    "expression": "A => B",
    "aggregations": [{"expression": "count()"}]
  }
}
```

## Structured-field conversions

### Filters

If non-empty `filter.expression` already exists, use it. Otherwise convert
`filters.items[]` into an equivalent Query Builder expression, preserving each
key, operator, typed value or variable, grouping, and the `filters.op`
relationship. Do not send `filters` to the execution tool. If an operator or
nested shape cannot be represented exactly, apply the safety gate rather than
running an unfiltered query.

### Grouping and selected fields

For each `groupBy[]` field emit only:

```json
{"name":"service.name","fieldDataType":"string","fieldContext":"resource","signal":"traces"}
```

Map `key` -> `name`, `dataType` -> `fieldDataType`, and `type` ->
`fieldContext`; set `signal` to the enclosing query signal.

For each `selectColumns[]` field emit `selectFields[]` with `name` (falling back
to saved `key` only when necessary), `fieldDataType`, `fieldContext`, and
`signal`. Do not send `selectColumns`, or dashboard `key`/`dataType`/`type`
aliases inside `groupBy` or `selectFields`. The canonical `order[].key` wrapper
below is unrelated and required.

### Limit and order

For table and list panels, execution `limit` is saved `limit` when non-zero,
otherwise saved `pageSize`. For other panel types use saved `limit` only.

Convert each saved order:

```text
{columnName, order} -> {key: {name: columnName}, direction: order}
```

Never send `pageSize` or `orderBy` to the execution tool.

### HAVING

Preserve an existing `{expression: "..."}` object. An empty dashboard HAVING
array may be omitted. A **non-empty** dashboard array of
`{columnName, op, value}` clauses has no parity mapping today: the frontend V5
converter drops arrays when it executes the saved panel. Do not convert the
array to an expression and claim that probe validates the saved dashboard.

You may run a manually constructed `having.expression` probe as a diagnostic of
the intended condition, but label it explicitly as non-parity evidence. It does
not clear the safety gate. Before creating the dashboard, stop or obtain the
user's explicit acceptance that the panel remains unvalidated, and warn that
the saved panel may ignore its HAVING clauses at runtime. Never pass a clause
array to `signoz_execute_builder_query`.

### Aggregations

- Metrics: emit V5 metric aggregation objects. Preserve current `aggregations`
  entries; for legacy dashboard fields, construct the aggregation from
  `aggregateAttribute.key`, `temporality`, `timeAggregation`,
  `spaceAggregation`, and panel-appropriate `reduceTo`.
- Logs and traces: emit one V5 aggregation per function expression and preserve
  its alias. Split legacy combined expressions rather than sending several
  functions as one expression. Default to `count()` only when the saved query
  truly has no aggregation.
- Raw requests omit aggregations when required by the current schema.

## Saved payload invariant

The payload sent to `signoz_create_dashboard` remains dashboard/editor JSON.
Keep `queryName`, `dataSource`, `filters`, `pageSize`, `orderBy`,
`selectColumns`, dashboard HAVING clauses, `queryTraceOperator`, and `groupBy`
fields such as `key`/`dataType`/`type`. Execution-only names belong only in
`signoz_execute_builder_query`.
