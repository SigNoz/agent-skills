# `signoz-creating-dashboards` — eval coverage

This document describes the eval suite for the `signoz-creating-dashboards` skill. The suite verifies behaviour across the full surface of the create-dashboard workflow: duplicate detection, template import, no-data gating, custom builds across all three signals (metrics / traces / logs), panel-type shape correctness, variable handling, and scope-boundary handoffs.

Evals live at:

```
plugins/signoz/skills/signoz-creating-dashboards/evals/evals.json
```

## How the suite was built

1. **Mapped the skill surface** from `SKILL.md`, the SigNoz dashboard MCP resources (`signoz://dashboard/instructions`, `widgets-instructions`, `widgets-examples`, `query-builder-example`, `traces/query-builder-guide`, `clickhouse-{schema,example}-for-{metrics,traces,logs}`), and the SigNoz repo (`frontend/src/constants/queryBuilder.ts` for the panel-type enum).
2. **Verified template-catalog claims** against [SigNoz/dashboards](https://github.com/SigNoz/dashboards) — every template reference in the evals points to a real file.
3. **Verified data assumptions** against the live SigNoz instance via the MCP server (`signoz_list_dashboards`, `signoz_list_metrics`, `signoz_list_services`, `signoz_get_field_keys`, `signoz_get_field_values`, `signoz_aggregate_logs`). Evals that assume "no existing dashboard" were corrected to acknowledge the duplicates that are actually present.
4. **Pairwise duplicate audit** across all evals — removed `custom-build-payment-pipeline` whose unique elements were strict subsets of other evals.

## Surface covered

### Signals (data sources)

| Signal | Evals |
|---|---|
| metrics | 0, 1, 7, 9 |
| traces | 8, 10, 12, 15, 16 |
| logs | 14 |

### Panel types (from `PANEL_TYPES` enum in `frontend/src/constants/queryBuilder.ts`)

| Panel type | Evals |
|---|---|
| graph (timeseries) | 7, 9, 10, 12, 14, 17 |
| value | 9, 14, 16 |
| table | 14, 16 |
| list | 15 |
| bar | 16 |
| pie | 16 |
| row (section header) | 16 |
| histogram | _intentionally uncovered — niche distribution panel_ |

### Workflow paths

| Path | Evals |
|---|---|
| Duplicate found → user picks "create new" → template import success | 0 |
| Duplicate found → user picks "create new" → template import + no-data warning | 1 |
| Duplicate found → user picks "create new" → template import → server failure → fallback | 13 |
| Duplicate found → user picks "modify" → hand off to `signoz-modifying-dashboards` | 11 |
| Broad/ambiguous request → present multiple template options | 2 |
| Vague request → emit `needs_input` / clarify scope | 5 |
| No template match → custom build | 6, 7, 8, 9, 10, 12, 14, 15, 16, 17 |

### Guardrails exercised

| Guardrail | Eval(s) |
|---|---|
| Always paginate `signoz_list_dashboards` before any write | 0, 1, 11, 13 |
| `list_dashboard_templates` before custom build | 6, 7, 8, 9, 10, 14, 15, 16, 17 |
| No-data probe before save | 1, 6, 14 |
| Don't shortcut to a near-neighbour template | 6 |
| Don't skip discovery under incident pressure | 7 |
| Use OTel attribute names (e.g. `service.name`, not `service`) | 9, 10, 16 |
| Builder mode only — no PromQL / underscored span-metric labels | 9 |
| Discover real attribute keys (no invented shorthand) | 7, 8, 10 |
| `selectColumns` shape correctness on list panels (frontend-crash safety) | 15 |
| Value panel must NOT have `groupBy` | 14, 16 |
| Pie panel must have `groupBy` AND `legend` | 16 |
| Error-rate formula `A*100/B` with `disabled:true` on base queries | 9, 16 |
| Non-default time range for SLO windows (28d) | 9 |
| Variable-application prompt before injecting `$var` into panels | 17 |
| `DYNAMIC` variable shape (`DynamicVariablesAttribute` / `DynamicVariablesSource`) | 17 |
| No `JSON.stringify` on `layout` / `widgets` / `variables` | 12 |
| Per-widget required fields (`id`, `panelTypes`, `title`, `query`, `selectedLogFields`, `selectedTracesFields`, `thresholds`, `contextLinks`) | 12, 14, 15 |
| Scope boundary — don't call `signoz_update_dashboard` from this skill | 11 |
| Surface import failures, don't silently retry | 13 |

## Eval-by-eval coverage

| ID | Name | Primary test | Signal | Panel types | Key guardrails |
|---:|---|---|---|---|---|
| 0 | `template-with-data-jvm` | Duplicate-check → user picks "create new" → template import succeeds | metrics | (template) | duplicate detection, no-data probe, `signoz_import_dashboard` |
| 1 | `template-no-data-postgres` | Duplicate-check → "create new" → template path emits no-data warning before import | metrics | (template) | no-data probe, user-confirmation gate before import |
| 2 | `broad-request-apm-category` | Ambiguous request — present multiple template options, don't pick silently | (any) | (template) | `list_dashboard_templates` browse, no silent template selection |
| 5 | `needs-input-missing-scope-custom-build` | Vague k8s prompt — agent must clarify scope before any write | (k8s) | n/a | `needs_input` block, no guessing scope |
| 6 | `custom-build-scylladb-no-near-template-shortcut` | No catalog template + don't shortcut to a near-neighbour (jmx/cassandra, mongodb) | metrics | graph | no-near-neighbour-shortcut, no-data warning, OTel resource attrs |
| 7 | `custom-build-kafka-consumer-pressure` | "Don't ask questions, I'm in incident" — agent must still discover + probe | metrics | graph | discovery + probe under pressure, real attribute keys (e.g. `client-id`), reject invented shorthand |
| 8 | `custom-build-checkout-funnel-span-attributes` | Span-attribute-driven business KPIs (orders, revenue, card-type) | traces | graph, pie | `signoz_get_field_keys signal=traces` discovery, `signoz_aggregate_traces` (not metrics), `sum(app.order.amount)`, span-tag groupBy |
| 9 | `custom-build-slo-error-budget-formula` | SLO availability + error-budget burn-rate; builder mode only | metrics | graph, value | error-rate formula, non-default 28d time range, `service.name` (dotted, resource), no PromQL |
| 10 | `custom-build-multi-service-user-journey` | Per-hop latency + error rate across multiple services | traces | graph | `service.name` discovery (`signoz_list_services` / `signoz_get_field_values`), IN-list filter, per-service `groupBy=service.name`, error-rate formula |
| 11 | `duplicate-modify-hands-off` | Existing dashboard + user picks "modify" → handoff | (any) | n/a | scope boundary — no `signoz_update_dashboard` from this skill |
| 12 | `shape-check-no-stringify` | Top-level fields are native JSON, every widget has required keys | traces | graph | `layout` / `widgets` / `variables` not stringified, query has `queryType` + `builder` + `promql` + `clickhouse_sql` sub-keys |
| 13 | `import-failure-falls-back-to-custom` | Duplicate-check → "create new" → template import fails → surface error + fallback | metrics | (template) | no silent retry, no fabricated payload, custom-build fallback or stop |
| 14 | `custom-build-logs-signal-volume-and-errors` | Logs-signal dashboard with severity breakdown | logs | graph, value, table | `dataSource=logs`, `severity_text` (not `severity`/`level`), value-no-`groupBy`, `selectedLogFields` per widget |
| 15 | `custom-build-list-panel-selectColumns-required` | Recent-error-traces list panel | traces | list | `selectColumns` uses `name` not `key`, each entry has `fieldContext` + `signal`, `orderBy` + `pageSize` set, no `groupBy` on lists |
| 16 | `custom-build-multi-panel-types-mixed` | One dashboard exercising row + value + pie + bar + table | traces | row, value, pie, bar, table | per-panel-type shape rules (value-no-`groupBy`, pie-needs-legend, bar-not-graph, table-`as`-aliases), formula with `disabled:true`, KPI-row layout |
| 17 | `custom-build-variable-application-prompt` | User asks for `service.name` dropdown; one panel is intentionally global | traces | graph | `DYNAMIC` variable shape, ask-which-panels-before-injection, don't over-filter the global panel |

## Intentionally uncovered

| Surface | Reason |
|---|---|
| `histogram` panel | Niche distribution panel; low-risk shape |
| PromQL widgets | Skill explicitly forbids PromQL in builder mode (eval 9 tests the negative); not a primary user path for this skill |
| Raw ClickHouse SQL panels | Owned by sibling skill `signoz-writing-clickhouse-queries`; out of scope per `SKILL.md` |
| `CUSTOM` / `TEXTBOX` / `QUERY` variable types | `DYNAMIC` is the recommended default per `signoz://dashboard/instructions`; eval 17 covers the recommended path |
| Threshold formats (`Text` / `Background`) | Edge feature — failure mode is cosmetic, not data-correctness |

## Updating the suite

When changing evals:

1. Run a JSON validation (`python3 -c "import json; json.load(open('evals.json'))"`).
2. If an eval references the live SigNoz instance (existing dashboards, metric names, services, span attributes), re-verify against the MCP server before committing — instance state drifts.
3. If a referenced dashboard template is added/removed in [SigNoz/dashboards](https://github.com/SigNoz/dashboards), update the eval that references it (see commit `e2e3683` for the precedent — `custom-build-scylladb` enumerates the database templates explicitly).
4. Run a duplicate audit when adding evals — every eval should test at least one guardrail no other eval covers.
