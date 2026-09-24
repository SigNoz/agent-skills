---
name: signoz-creating-dashboards
description: >
  Create a new SigNoz dashboard from a natural-language intent: import a
  curated template (PostgreSQL, Redis, JVM, k8s, hostmetrics, APM, LLM,
  etc.) when one fits, or build a custom dashboard from scratch with
  metric / trace / log panels. Make sure to use this skill whenever the
  user says "create a dashboard for…", "set up monitoring for…",
  "build me a dashboard…", "I need observability for…", "import a
  dashboard template", or asks to track / visualize a service, database,
  cluster, or AI/LLM platform, even if they don't explicitly say
  "dashboard". Also use it when someone wants to "monitor", "watch", or
  "see metrics for" a technology and the natural answer is a dashboard.
argument-hint: <natural-language dashboard intent>
---

# Create a SigNoz dashboard

Use the SigNoz MCP tools throughout. If they are unavailable, use
`signoz-mcp-setup`; do not replace them with raw HTTP calls.

## Scope

Use this skill for a new dashboard or template import. Hand changes to an
existing dashboard to `signoz-modifying-dashboards`, explanations to
`signoz-explaining-dashboards`, and one-off exploration to
`signoz-generating-queries`.

Dashboard writes require the dashboard goal, target technology or service,
resource scope, and any user-selected variable scope. Discover exact metrics
and attributes when possible. Ask only for choices that discovery cannot
resolve.

## Workflow

### 1. Check for an existing dashboard

If the user supplies a dashboard `id`, call `signoz_get_dashboard` with it
first; the list below cannot find system dashboards. Keep the returned
`source` as returned. To base a new dashboard on it, read its definition as
reference and continue with a separate create. Never update, patch, or delete
a non-user source.

Otherwise, call `signoz_list_dashboards` with a distinctive `filter` when
available and `limit=50`, following `offset` pagination until `total` is
covered before concluding that no match exists. A later-page error blocks the
write. The v2 list excludes system dashboards.
It may contain user and integration dashboards; only `source=user` dashboards
are mutable. Compare names, descriptions, and tags by real domain relevance.

If a likely duplicate exists, show its name, canonical `id`, source, and update
time. For a `source=user` match, ask whether to modify it, create another, or
stop; if modification is chosen, hand off the canonical `id` and intent to
`signoz-modifying-dashboards`. For an integration match, explain that it is
immutable and ask whether to create another or stop. Dashboard tools use `id`;
never send `uuid`.

### 2. Prefer a matching template

Call `signoz_list_dashboard_templates`. If one template clearly matches, state
which one and continue. If several match, offer the small relevant set. If none
matches, build a custom dashboard.

Before `signoz_import_dashboard`, probe a few representative signals:

- metrics: `signoz_list_metrics`, then `signoz_query_metrics` for exact metrics;
- traces: `signoz_aggregate_traces` with `aggregation=count`;
- logs: `signoz_aggregate_logs` with `aggregation=count`;
- variables: `signoz_get_field_keys` and `signoz_get_field_values`.

If all representative signals are absent, explain that the imported dashboard
will show no data and ask whether to continue. If some are absent, identify
them and let the user decide. Import with the catalog `path`; do not fetch or
recreate template JSON yourself.

If import fails, surface the error and offer either a custom build from the same
validated signals or a stop. Do not retry silently or create a fabricated
replacement payload without telling the user the import failed.

### 3. Discover data for a custom dashboard

Confirm exact metric names, types, temporality, units, and populated resource
attributes. Prefer known resource predicates such as `service.name` and
`k8s.cluster.name`; discover unfamiliar fields before using them. Trust live
field discovery over examples or semantic-convention guesses.

If no intended signal has data, explain the result and ask whether to create a
dashboard that will remain empty until ingestion starts.

### 4. Read the authoritative resources

Before authoring a custom payload, read:

- `signoz://dashboard/instructions`
- `signoz://dashboard/widgets-instructions`
- `signoz://dashboard/widgets-examples`
- `signoz://dashboard/query-builder-example`
- `signoz://dashboard/examples` when a complete create payload helps

Read signal-specific resources only as needed: `signoz://metrics-aggregation-guide`,
`signoz://traces/query-builder-guide`, `signoz://logs/query-builder-guide`,
`signoz://promql/instructions`, or the relevant dashboard ClickHouse resources.
These resources and tool schemas are authoritative. Do not duplicate their
full schemas in the skill or infer fields from old dashboard JSON.

For translating a Perses panel query into an execution dry-run, read
[references/dashboard-to-query-builder-v5.md](references/dashboard-to-query-builder-v5.md).

### 5. Build only the v6 Perses shape

Create with `schemaVersion: "v6"`, `generateName: true`, tags, and `spec`.
Set the visible title and description in `spec.display`. Let the server derive
the immutable machine name; do not set top-level `name` on create.

Panels and layout have this relationship:

- `spec.panels` is a map keyed by a stable panel id.
- Each panel value is a Perses `Panel` envelope selected from the resources.
- `spec.layouts` is an array of `Grid` envelopes.
- Every grid item lives in `spec.layouts[n].spec.items` and links with
  `content.$ref: "#/spec/panels/<panel-id>"`.
- Every panel has exactly one non-overlapping grid item. Use a 12-column grid.

Do not persist legacy `widgets`, `layout`, `panelMap`, `panelTypes`,
`queryData`, `selectedLogFields`, or `selectedTracesFields`. Do not translate a
legacy fixture by retaining both shapes.

Every query panel has exactly one entry in `spec.queries`. Use a direct query
plugin for one query. Use one `signoz/CompositeQuery` entry when multiple base
queries or a formula must be combined. A computed result normally has disabled
metric inputs and one enabled formula; an enabled metric may instead depend on
disabled metric inputs. PromQL and ClickHouse SQL are also valid where the
panel and resources allow them.

For prose, headings, or instructions, use `signoz/TextPanel` with mode
`markdown` and a non-null empty `queries: []`. It is intentionally
queryless: skip discovery and query dry-run for that panel. Do not invent row
panels. For named sections, add a separate `Grid` entry to `spec.layouts` with
its own `spec.display.title`; use text panels for prose within a section.

For volume over time or how parts add up to a total, use
`signoz/AreaChartPanel` with one `time_series` query. Stack only additive
values such as counts or bytes (percent stacking shows each series' share);
keep latency, percentiles, and ratios on `signoz/TimeSeriesPanel`, because a
stacked total of them is meaningless. Take the stack and fill fields from
`signoz://dashboard/widgets-instructions`.

### 6. Variables and layout

Prefer a `ListVariable` with `signoz/DynamicVariable` for live attribute values.
Use `signoz/CustomVariable` for a fixed list and `TextVariable` for free-form
input. Before inserting `$variable` into queries, show the planned panels and
ask whether it applies to all or a selected subset.

Use the resource defaults for variable shape. Typical layout choices are:

- KPI values: height 2-3, widths 3 or 4;
- side-by-side charts: width 6 each, height 6-8;
- tables and dense timeseries: width 12;
- every row starts at or below the previous row's `y + height`.

### 7. Validate queries before writing

Translate each query-bearing panel to a raw `signoz_execute_builder_query`
request using the reference guide. Use representative literals for dashboard
variables only in dry-runs; preserve `$variable` in the saved dashboard.

Skip queryless text panels. For each query panel, validate the complete active
query, including formulas and trace operators. Do not claim a stripped query
validated unsupported fields. If the executor cannot represent an authored
semantic, surface the validation gap before saving.

Every builder query and formula uses a positive `limit` and non-empty Query
Builder v5 `order`. Raw lists and trace requests default to 100 ordered by
timestamp descending; raw logs add `id` descending for stable ties. Aggregate
queries use 100 ordered by their primary aggregation, formula outputs use 100
ordered by `__result`, and every base query referenced by a formula uses 10000
because its limit applies before formula evaluation. This field is `order`, not
dashboard `orderBy`. Narrow filters or grouping if 10000 can truncate inputs.
Keep these bounded specs unchanged in the dry-run and saved Perses query.

### 8. Preview, create, and verify

Preview the title, scope, variables, panel titles/types, grid arrangement, and
probe/dry-run results. Reuse this prepared payload; do not repeat unchanged
discovery or authorization reads.

Call `signoz_create_dashboard` once. Report the returned canonical `id`, title,
panel count, variables, and any validation limitation. If the response is
ambiguous or fails, do not replay automatically.

## Defaults

- Services: request rate, error rate, p50/p95/p99 latency, and throughput.
- Infrastructure: utilization, saturation, errors/restarts, and throughput.
- Prefer per-second rate for active counters and deliberate `increase` for
  low-volume interval totals. Keep gauges absolute.
- Group per-service panels by the discovered `service.name`; remove the group
  when the dashboard is fixed to one service.
- Add legends for grouped series using the exact group-by names.

## Guardrails

- Preserve user intent and discovered tenant names; examples are illustrative.
- Never claim a template import or create succeeded unless the tool returned
  success.
- Do not modify a duplicate from this skill; hand it off.
- Never send legacy dashboard fields or the `uuid` alias.

## Additional examples

Read [references/examples.md](references/examples.md) when a worked workflow is
useful. Treat any legacy payload in old transcripts or fixtures as input to
replace, not as a saveable contract.
