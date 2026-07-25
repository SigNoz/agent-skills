# `signoz-creating-dashboards` — eval coverage

This document describes the eval suite for the `signoz-creating-dashboards` skill. The suite verifies behaviour across the full surface of the create-dashboard workflow: duplicate detection, template import, no-data gating, custom builds across all three signals (metrics / traces / logs), panel-type shape correctness, variable handling, and scope-boundary handoffs.

Evals live at:

```
plugins/signoz/skills/signoz-creating-dashboards/evals/evals.json
```

Dashboards use the **Perses schema (`schemaVersion: "v6"`)**: panels are a map, layouts are Grid envelopes, panel type is a plugin `kind`, and the v2 API is the authoritative validator.

## How the suite was built

1. **Mapped the skill surface** from `SKILL.md`, the core dashboard resources,
   `signoz://promql/instructions`, the metrics/traces/logs Query Builder guides,
   and the six exact ClickHouse resources: `clickhouse-schema-for-metrics`,
   `clickhouse-metrics-example`, `clickhouse-schema-for-traces`,
   `clickhouse-traces-example`, `clickhouse-schema-for-logs`, and
   `clickhouse-logs-example` under `signoz://dashboard/`.
2. **Verified template-catalog claims** against [SigNoz/dashboards](https://github.com/SigNoz/dashboards) — every template reference in the evals points to a real file.
3. **Verified data assumptions** against the live SigNoz instance via the MCP server (`signoz_list_dashboards`, `signoz_list_metrics`, `signoz_list_services`, `signoz_get_field_keys`, `signoz_get_field_values`, `signoz_aggregate_logs`). Evals that assume "no existing dashboard" were corrected to acknowledge the duplicates that are actually present.
4. **Pairwise duplicate audit** across all evals — removed `custom-build-payment-pipeline` whose unique elements were strict subsets of other evals.
5. **Offline branch fixtures** under `evals/files/` make pagination and prior-turn
   simulations deterministic without depending on a live tenant's ordering.

## Surface covered

### Signals (data sources)

| Signal | Evals |
|---|---|
| metrics | 0, 1, 7, 9, 18, 21 |
| traces | 8, 10, 12, 15, 16, 17, 19, 23 |
| logs | 14, 20, 24 |

### Panel plugin kinds

| Plugin kind | Evals |
|---|---|
| `signoz/TimeSeriesPanel` | 6, 8, 9, 10, 12, 14, 17, 19, 21, 23 |
| `signoz/NumberPanel` (value) | 9, 14, 16 |
| `signoz/TablePanel` | 14, 16, 20, 22, 24 |
| `signoz/ListPanel` | 15, 25 |
| `signoz/BarChartPanel` | 16 |
| `signoz/PieChartPanel` | 8, 16 |
| Grid sections | 6, 16 |
| `signoz/HistogramPanel` | _intentionally uncovered — niche distribution panel_ |

### Workflow paths

| Path | Evals |
|---|---|
| Duplicate found → user picks "create new" → template import success | 0 |
| Duplicate found → user picks "create new" → template import + no-data warning | 1 |
| Duplicate found → user picks "create new" → template import → server failure → fallback | 13 |
| Duplicate found → user picks "modify" → hand off to `signoz-modifying-dashboards` | 11 |
| Duplicate found on a later page → present choices before any write | 18 |
| Broad/ambiguous request → present multiple template options | 2 |
| Vague request → emit `needs_input` / clarify scope | 5 |
| No template match → custom build | 6, 8, 9, 10, 12, 14, 15, 16, 17, 19, 20, 21, 22, 23, 24, 25 |

### Guardrails exercised

| Guardrail | Eval(s) |
|---|---|
| Always paginate `signoz_list_dashboards` before any write | 0, 1, 11, 13, 18 |
| `list_dashboard_templates` before custom build | 6, 7, 8, 9, 10, 14, 15, 16, 17 |
| No-data probe before save | 1, 6, 14 |
| Don't shortcut to a near-neighbour template | 6 |
| Don't skip discovery under incident pressure | 7 |
| Use OTel attribute names (e.g. `service.name`, not `service`) | 9, 10, 16 |
| Builder mode only — no PromQL / underscored span-metric labels | 9 |
| Discover real attribute keys (no invented shorthand) | 7, 8, 10 |
| List panel `selectFields` on both the plugin spec and the query, `name` not `key` | 15 |
| `signoz/NumberPanel` must NOT have `groupBy` | 14, 16 |
| Pie panel must have `groupBy` AND `legend` | 16 |
| Error-rate formula `A*100/B` with `disabled:true` on base queries | 9, 16 |
| `groupBy` uses canonical `name` / `fieldDataType` / `fieldContext` in create payloads and dry-runs alike | 10 |
| Dashboard filters/limits/order/select fields/formulas are saved in canonical execution form | 8, 9, 14, 15, 19, 22, 23, 24, 25 |
| Saved `having.expression` executes as stored — no clause array, no parity gap | 20 |
| Trace operators become raw-preserved sibling `builder_trace_operator` envelopes | 23 |
| Unsupported execution-affecting fields block false-positive dry-run success | 21 |
| Non-default time range for SLO windows (28d) | 9 |
| Variable-application prompt before injecting `$var` into panels | 17 |
| Selected-panel variable wiring and dry-run | 19 |
| `ListVariable` + `signoz/DynamicVariable` shape | 17, 19 |
| No `JSON.stringify` on `spec` / `panels` / `layouts` / `tags` / `variables` | 12 |
| Per-panel required fields, plugin `kind`, and its single query envelope | 12, 14, 15 |
| Envelope: `schemaVersion` v6, no top-level `name`, `spec.display.name` as title, key/value tags | 12 |
| 12-column bounds, no overlapping grid items | 16 |
| Scope boundary — don't call `signoz_update_dashboard` or `signoz_patch_dashboard` from this skill | 11 |
| Surface import failures, don't silently retry | 13 |
| Panels map + `content.$ref` bijection with grid items | 12, 16 |
| Sections are Grid layouts; there is no row panel type and no `panelMap` | 16 |
| Aggregation columns named with `alias`, not `as '...'` inside the expression | 14, 16 |
| Metrics `order` key is the composed `spaceAggregation(timeAggregation(metricName))` | 6 |
| Filters are one `filter.expression` string | 14, 24 |
| Result bounds preserved: 100 standalone, 10000 formula inputs, 100 `__result` formula output | 9, 10, 16, 22 |
| One query per panel — multi-series via `signoz/CompositeQuery` (backend-enforced, not schema-enforced) | 9, 16 |

## Eval-by-eval coverage

| ID | Name | Primary test | Signal | Panel kinds | Key guardrails |
|---:|---|---|---|---|---|
| 0 | `template-with-data-jvm` | Duplicate-check → user picks "create new" → template import succeeds | metrics | (template) | duplicate detection on `spec.display.name`, no-data probe, `signoz_import_dashboard` |
| 1 | `template-no-data-postgres` | Duplicate-check → "create new" → template path emits no-data warning before import | metrics | (template) | no-data probe, user-confirmation gate before import |
| 2 | `broad-request-apm-category` | Ambiguous request — present multiple template options, don't pick silently | (any) | (template) | `list_dashboard_templates` browse, no silent template selection |
| 5 | `needs-input-missing-scope-custom-build` | Vague k8s prompt — agent must clarify scope before any write | (k8s) | n/a | `needs_input` block, no guessing scope |
| 6 | `custom-build-scylladb-no-near-template-shortcut` | No catalog template + don't shortcut to a near-neighbour (jmx/cassandra, mongodb) | metrics | TimeSeries, Grid sections | no-near-neighbour-shortcut, no-data warning, OTel resource attrs, composed metrics order key |
| 7 | `template-kafka-consumer-pressure` | "Don't ask questions, I'm in incident" — agent must still check duplicates + probe | metrics | (template) | discovery + probe under pressure, hand customizations to the modify skill |
| 8 | `custom-build-checkout-funnel-span-attributes` | Span-attribute-driven business KPIs (orders, revenue, card-type) | traces | TimeSeries, Pie | `signoz_get_field_keys signal=traces` discovery, `sum(app.order.amount)`, `fieldContext: attribute` for span attrs |
| 9 | `custom-build-slo-error-budget-formula` | SLO availability + error-budget burn-rate; builder mode only | metrics | TimeSeries, Number | composite-per-panel, error-budget arithmetic, 28d as a viewer instruction, `service.name` dotted |
| 10 | `custom-build-multi-service-user-journey` | Per-hop latency + error rate across multiple services | traces | TimeSeries | service discovery, IN-list `filter.expression`, per-service `groupBy` + legend, composite formula |
| 11 | `duplicate-modify-hands-off` | Existing dashboard + user picks "modify" → handoff | (any) | n/a | scope boundary — no `signoz_update_dashboard` / `signoz_patch_dashboard` here |
| 12 | `shape-check-no-stringify` | Top-level fields are native JSON, every panel has required keys | traces | TimeSeries | `spec` / `panels` / `layouts` not stringified, panel has plugin `kind` + one complete query |
| 13 | `import-failure-falls-back-to-custom` | Duplicate-check → "create new" → template import fails → surface error + fallback | metrics | (template) | no silent retry, no fabricated payload, custom-build fallback or stop |
| 14 | `custom-build-logs-signal-volume-and-errors` | Logs-signal dashboard with severity breakdown | logs | TimeSeries, Number, Table | `signal=logs`, `severity_text` (not `severity`/`level`), Number-panel-no-`groupBy`, aggregation `alias` |
| 15 | `custom-build-list-panel-select-fields` | Recent-error-traces list panel | traces | List | `selectFields` on both plugin and query, `name` not `key`, `raw` query kind |
| 16 | `custom-build-multi-panel-types-mixed` | One dashboard exercising two Grid sections + Number/Pie/Bar/Table | traces | Number, Pie, Bar, Table | sections as Grids, per-kind shape rules, composite error rate, `$ref` bijection, grid bounds |
| 17 | `custom-build-variable-application-prompt` | User asks for `service.name` dropdown; agent stops at panel-scope clarification | traces | TimeSeries | `ListVariable` + `signoz/DynamicVariable`, `spec.name` vs `plugin.spec.name`, ask before injection |
| 18 | `duplicate-dashboard-on-second-page` | Matching dashboard appears only on the second page | metrics | n/a | later-page duplicate detection, offset paging without `nextOffset`, no write before user choice |
| 19 | `custom-build-variable-application-selected-panels` | Follow-up selects two panels and keeps the global panel unfiltered | traces | TimeSeries | targeted `$service_name` wiring, representative-value dry-runs, spec reused verbatim |
| 20 | `custom-build-having-array-validation-gap` | Logs table with a per-group count threshold | logs | Table | `having.expression` not a clause array, dry-run validates the saved panel |
| 21 | `unsupported-builder-function-blocks-lossy-validation` | Current execution schema cannot represent a requested Builder function | metrics | TimeSeries | surface unsupported field; never claim a stripped dry-run passed |
| 22 | `formula-order-limit-bounded-execution` | Top-5 formula bound applied after, not before, the formula | traces | Table | formula `limit`/`order`, 10000 on inputs, no `orderBy` anywhere |
| 23 | `trace-operator-sibling-envelope-contract` | Trace operator as a composite member | traces | TimeSeries | `builder_trace_operator` sibling, no coercion to `builder_query` |
| 24 | `saved-not-in-to-execution-not-in` | Logs table excluding checkout and frontend services | logs | Table | discover the log-side service field; one `filter.expression` with `NOT IN`; non-empty groupBy `name`; short absolute Unix-ms dry-run window |
| 25 | `custom-build-raw-log-stable-order` | 20 newest ERROR logs with stable ordering | logs | List | `raw` query kind, `limit` + two-key `order`, `selectFields` |

## Intentionally uncovered

| Surface | Reason |
|---|---|
| `signoz/HistogramPanel` | Niche distribution panel; low-risk shape |
| PromQL panels | Supported via `signoz://promql/instructions`; no dedicated creation eval yet |
| Raw ClickHouse SQL panels | Supported via the signal-specific MCP resources and `signoz-writing-clickhouse-queries`; no dedicated creation eval yet |
| `signoz/QueryVariable` and `TextVariable` | `signoz/DynamicVariable` is the recommended default per `signoz://dashboard/instructions`; evals 17 and 19 cover the recommended path |
| Threshold and unit formatting | Edge feature — failure mode is cosmetic, not data-correctness |

## Updating the suite

When changing evals:

1. Run a JSON validation (`python3 -c "import json; json.load(open('evals.json'))"`).
2. If an eval references the live SigNoz instance (existing dashboards, metric names, services, span attributes), re-verify against the MCP server before committing — instance state drifts.
3. If a referenced dashboard template is added/removed in [SigNoz/dashboards](https://github.com/SigNoz/dashboards), update the eval that references it (see commit `e2e3683` for the precedent — `custom-build-scylladb` enumerates the database templates explicitly).
4. Run a duplicate audit when adding evals — every eval should test at least one guardrail no other eval covers.
