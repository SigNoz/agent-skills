---
name: signoz-reducing-telemetry-cost
description: >
  Investigate and reduce SigNoz telemetry ingestion cost and metric
  cardinality across metrics, logs, and traces. Find what drives SigNoz
  spend (via the Cost Meter), which metrics have runaway or unbounded
  label cardinality, and safe, dashboard-, alert-, and Infra-page-aware
  ways to cut volume. Make sure to use this skill whenever the user asks
  "why is my SigNoz bill so high", "what's driving my ingestion cost",
  "reduce telemetry volume", "which metrics cost the most", "cardinality
  health check", or "what can I safely drop" — or otherwise asks about
  telemetry spend, ingestion volume, or metric cardinality, even if they
  don't say "cost" or "optimize" explicitly.
argument-hint: <investigation focus, such as metrics cost or cardinality health>
---

## Prerequisites

This skill calls SigNoz MCP server tools heavily (`signoz_list_metrics`,
`signoz_get_field_keys`, `signoz_execute_builder_query`,
`signoz_get_top_metrics`, `signoz_check_metric_usage`, `signoz_check_metric_cardinality`,
`signoz_aggregate_logs`, `signoz_aggregate_traces`, `signoz_search_logs`,
`signoz_list_alert_rules`, `signoz_get_alert`, `signoz_get_service_top_operations`). Before
running the workflow, confirm the `signoz_*` tools are available. If they are not, the SigNoz
MCP server is not installed or configured — run `signoz-mcp-setup` first. The whole
investigation is grounded in these queries; without the server there is nothing to analyze.

Read both reference files before drawing conclusions:
- `references/otel-attribute-cardinality.md` — classify any metric label you encounter.
- `references/infra-do-not-drop.md` — the metrics that power the built-in Infrastructure page
  **and the APM/Services page** (span-derived `signoz_*` RED metrics); never present these as
  "safe to drop" even when usage shows them unused.

## Workflow

Always start with the Cost Meter snapshot (Step 1). For a full cost investigation, run the
metrics, logs, and traces steps for every signal with data, ordered by current cost contribution
(primary, secondary, tertiary). Finish with the report (Step 5).

### Step 1: Cost Meter snapshot

Establish the cross-signal cost picture first. Always call `signoz_list_metrics` with
`source: "meter"`; treat its returned metric names, types, temporalities, and units as the live
source of truth because the meter set evolves. Then query each relevant discovered metric with
`signoz_execute_builder_query` (`source: "meter"`, `requestType: "time_series"`,
`stepInterval: 3600`, the discovered `temporality`, and `timeAggregation: "sum"`) — see
`references/cost-meter-queries.md` for the full tool-argument template. Sum complete hourly
buckets and exclude every datapoint marked `partial: true`. Do **not** use
`signoz_query_metrics` for Cost Meter totals or grouped total attribution.
Report only values returned by successful queries. If a query fails or returns no usable values
after the MCP tools are available, show the intended query and say that the total could not be
computed; never invent a total. If the tools are unavailable, follow the prerequisite instead.

For a rolling 7-day window (`end` = now, `start` = end − 7 days), get the per-signal totals
(span size, log size, metric datapoints), then compute and report:

- **Ask for retention before weighting cost.** Price scales with retention tier, and traces,
  logs, and metrics can each be retained for a different period — so ask the user for their
  currently configured retention for each of the three signals before ranking which one costs
  more. This is a factual input needed to weight cost accurately, not a suggestion to change
  retention (that guardrail still applies below). If the user doesn't know, ask them to check
  their SigNoz plan/retention settings.

  | Traces / logs retention | $/GB |
  |---|---|
  | 15 days | 0.3 |
  | 30 days | 0.4 |
  | 90 days | 0.6 |
  | 180 days | 0.8 |
  | 1 year | 1.4 |

  | Metrics retention | $/M samples |
  |---|---|
  | 1 month | 0.1 |
  | 3 months | 0.12 |
  | 6 months | 0.15 |
  | 13 months | 0.18 |

- **Primary cost driver.** The signal with the highest *dollar* weight, using each signal's own
  retention-matched rate from the tables above (orientation only; never quote the resulting
  dollar figure to the user — it's for ranking signals against each other, not a cost estimate).
  This picks by cost, not by raw volume.
- **Bytes per record.** span.size ÷ span.count and log.size ÷ log.count — tells you whether a
  signal is a payload-size problem or a volume problem.

Then break the primary signal down by environment and service. First call
`signoz_get_field_keys` with `signal: "metrics"` and `source: "meter"`; use only keys it returns
and copy each key's `name`, `fieldDataType`, `fieldContext`, and `signal` into the raw
builder `groupBy` without translating or dropping fields. Run the same meter query with that
complete `groupBy` and report the top
~10 per group with their share. If a non-prod environment (`staging`, `dev`, `test`, `qa`,
`sandbox`, `preview`, `uat`, …) is > 40% of volume, recommend Ingestion Limits on that key
before any signal-level change: https://signoz.io/docs/ingestion/signoz-cloud/keys/

### Step 2: Metrics

Run when the Cost Meter shows metric data, ordered by its cost contribution, or when the user
explicitly asks about metric cost or cardinality.

**2a. Rank by volume — `signoz_get_top_metrics`.** Returns the top 100 metrics by ingested
samples with percentages pre-computed and `totalValue` sample counts (pass `start`/`end`). This
is the volume-ranked worklist. Histogram metrics (`.bucket` suffix) are usually the top
contributors — each bucket boundary is a separate sample per scrape.

**2b. Check usage — `signoz_check_metric_usage`.** Pass the top metric names (batch of ≤ 50 per
call). Returns `{ dashboards, alerts, error }` per metric. A metric is a drop candidate only when
its `error` is empty **and** both `dashboards` and `alerts` are empty. If `error` is non-empty the
lookup is incomplete (a timeout, or an older SigNoz that lacks the endpoint) and the returned
lists are unreliable — never treat that metric as unused; mark it **Needs one check first** (verify
its usage manually). A clean lookup with both lists empty is a drop candidate — except the guard
below.

> **Do-not-drop guard (mandatory).** Before calling any empty-usage metric a "safe drop", check
> it against `references/infra-do-not-drop.md`. The Infrastructure page (Hosts / Kubernetes)
> queries `system.*` and many `k8s.*` / `container.*` metrics through built-in queries — *not*
> dashboards — so usage-check reports them empty even though dropping them breaks that page. If
> a candidate matches the do-not-drop set, present it as **"Infra-page dependency — breaks the
> Hosts/Kubernetes view; confirm you don't use that view before dropping,"** never as "safe to
> drop." This overrides the empty usage result. Also exclude internal `signoz_` / `signoz.`
> metrics (auto-generated RED metrics that power the APM page, not customer-controlled).

**2c. Inspect cardinality — `signoz_check_metric_cardinality`.** Run this for metrics that are
not drop candidates and for any drop candidate the user chooses to retain. Cardinality analysis
adds no value for a metric the user has agreed to drop. The tool returns attribute keys sorted
highest-cardinality first, each with `valueCount` and sample `values`. Classify each with
`references/otel-attribute-cardinality.md`:

- **UNBOUNDED** (`url.full`, `http.target`, `db.query.text`, `client.port`, `trace.id`,
  `exception.stacktrace`, …) — grow without ceiling; flag regardless of current count.
- **ACCUMULATING** (`container.id`, `k8s.pod.uid`, `k8s.pod.name`, `k8s.pod.start_time`) —
  `valueCount` reflects historical pod churn, not active series; explain the distinction.
- **HIGH but bounded** (`valueCount` ≳ 100) — check whether dashboards/alerts actually filter on
  that label before recommending aggregation.

> **Infra identity override (mandatory).** For a metric protected by
> `references/infra-do-not-drop.md`, preserve the identity attributes and page metadata used by
> that metric's Infra entity/view. Do not aggregate or remove entity UID/name attributes when they
> resolve that entity. Keep `k8s.pod.start_time` on Pod metrics because the Pods page uses it for
> Pod Age. This overrides the generic ACCUMULATING fixes in the cardinality reference.

To reduce cardinality use the `metricstransform` processor's `aggregate_labels` action to *merge*
series (samples are the billable cost, so merging is what actually cuts it) — not the `transform`
processor's `delete_key`, which leaves the same sample count and creates colliding series. If a
label is essential to the metric's identity, drop the whole metric or fix it at the SDK instead.
For histograms, reducing bucket boundaries cuts samples with little P99 impact. Docs:
https://signoz.io/docs/userguide/drop-metrics/ ·
https://signoz.io/docs/metrics-management/dropping-metric-labels/

**2d. Review the collection interval.** For a high-volume metric that must be kept, identify how
it is produced and its current interval before recommending a change. A longer interval reduces
ingested datapoints but also lowers time resolution, so preserve the resolution required by its
dashboards and alerts. Use the source's own control: a receiver `collection_interval` for
Collector-generated metrics, the scrape interval for Prometheus-scraped metrics, or
`OTEL_METRIC_EXPORT_INTERVAL` for SDK push metrics when that SDK supports it. Verify the exact
setting name against the source's own documentation before stating it (see the verification
guardrail below). Never recommend switching a metric between delta and cumulative temporality;
changing temporality for the same metric can break SigNoz queries.

### Step 3: Logs

Run when the Cost Meter shows log data, ordered by its cost contribution, or when the user
explicitly asks about log cost.

**3a. Total + attribution decides the path.**
- Total log GB (the absolute cost figure): use `signoz_execute_builder_query` with the discovered
  meter metric whose live unit and meaning represent log bytes, summed as in Step 1.
- Attribution: run the **same meter query grouped by `service.name`**. This returns one group per
  service plus an unset/empty-`service.name` group for logs with no attribution. Compute the ratio
  entirely from THIS grouped result so numerator and denominator share one basis — a grouped sum can
  differ from the ungrouped total, so never divide the grouped attributed sum by the ungrouped
  total:
  - attributed GB = sum of the groups with a non-empty `service.name`.
  - grouped total = sum of *all* groups (including the empty one).
  - **Attribution % = attributed ÷ grouped total.**
- This is a hard branch:
  - **≥ 10% → Path A (service mode).**
  - **< 10% → Path B (namespace mode).** Logs come from an infra forwarder (Fluent Bit /
    Fluentd / Vector), not OTel SDKs, so `service.name` isn't set. Path B is a less common
    setup — sanity-check its numbers.

**3b. Analyze the selected attribution path and identify candidate fixes.** The fixes in this
step are candidates only. Complete the alert check in Step 3c before recommending any log-volume
reduction, including a source log-level change.

**Path A — service mode (≥ 10%).** Get the severity mix with `signoz_aggregate_logs`,
`aggregation: count`, `groupBy: "service.name,severity_text"`. Classify severities — REDUCIBLE =
INFO, INFORMATION, DEBUG, TRACE, VERBOSE; HIGH-SIGNAL = ERROR, FATAL, CRITICAL, WARN, WARNING.
For each top service by GB:
- Reducible-dominant + own service code → candidate: raise the log level to WARN (stops
  generation at source). `LOG_LEVEL=WARN` is a common convention, not a universal one — confirm
  the actual variable, config key, or logger-config call the service's language/framework uses
  before naming it (see the verification guardrail below).
- Reducible-dominant + third-party library → candidate: Collector filter on
  `instrumentation_scope.name`
  (read the scope from a `signoz_search_logs` sample's `scope_name`).
- No source access → candidate: Collector filter on `severity_text` matching **only the reducible
  set** (INFO/DEBUG/TRACE) — never a range that also catches WARN+.
- High-signal-dominant (WARN/ERROR > 50%) → the logs are worth keeping; a high error rate may be
  a real problem — flag it separately, do not recommend filtering it away.

> **Service severity guard.** The candidate fixes above (`LOG_LEVEL=WARN`, or a Collector filter
> scoped to INFO/DEBUG only) preserve WARN+ by construction, so the severity mix does not block
> them; Step 3c still determines whether an alert depends on the records. The guard applies only
> to actions that would *also* drop high-signal logs: a **blanket service drop**, or a
> `severity_text` filter whose range includes WARN/ERROR/FATAL/CRITICAL. Before recommending one
> of those, compute high-signal %
> = (all HIGH-SIGNAL severities — ERROR, FATAL, CRITICAL, WARN, **and WARNING** — matched
> case-insensitively) ÷ service total. **If it is > 1% (or a non-trivial absolute count), do not
> take the blanket action** — keep the reduction scoped to INFO/DEBUG and flag the errors as a real
> signal.

**Path B — namespace mode (< 10%).**
- Top namespaces: `signoz_aggregate_logs`, `count`,
  `groupBy: "k8s.namespace.name,deployment.environment"`, order by count desc, limit ~10. Use a
  **24h** window (7-day namespace scans time out on large tenants; count is the proxy — the Cost
  Meter has no namespace dimension).
- Severity per namespace: `signoz_aggregate_logs`, `count`,
  `groupBy: "k8s.namespace.name,severity_text"`.
- Samples: `signoz_search_logs`, `filter: "k8s.namespace.name = '<ns>'"`, small limit; read
  `body`, `severity_text`, `scope_name`.

> **Namespace severity guard.** high-signal % = (all HIGH-SIGNAL severities — ERROR, FATAL,
> CRITICAL, WARN, **and WARNING** — matched case-insensitively) ÷ namespace
> total. **If it is > 1% (or a non-trivial absolute count), do not consider dropping or
> filtering the whole namespace.** Scope the filter to the specific noisy pattern (a log
> category, a `severity_text` match, or a component). Never drop a namespace that carries active
> errors. Only namespaces that are essentially all INFO/DEBUG are wholesale-filter candidates,
> subject to Step 3c.

- Empty `severity_text` on samples → the forwarder ships raw lines unparsed; the fix is a
  json/regex parser in the OTel Collector log pipeline (without it, severity filtering is
  impossible).
- `k8s.event.*` logs are often high-volume / low-value → droppable if not alerted on.

**3c. Log alerts, dashboards, and saved views — check before any log-reduction recommendation.**
`signoz_list_alert_rules`, **paginating through every page** (follow `pagination.nextOffset`
until `pagination.hasMore` is false — do not stop at the first page, or an alert on a later page
is missed and a filter looks safe when it isn't). Keep `alertType == "LOGS_BASED_ALERT"`. For
each, `signoz_get_alert(id)` and read `condition.compositeQuery.queries[].spec.filter.expression`
+ `groupBy` to see which service / severity / namespace it guards. Check every query the alert's
condition depends on, not just the one that looks related (see the formula-dependency guardrail
below). If a filter would blind an alert, mark it **Will break alert coverage** and name the
alert. Then check dashboards and saved views the same way (see the dashboard/view coverage
guardrail below). Docs: https://signoz.io/docs/logs-management/guides/drop-logs/

### Step 4: Traces

Run when the Cost Meter shows span data, ordered by its cost contribution, or when the user
explicitly asks about span cost.

**4a. Global operation-name view — read this first.** `signoz_aggregate_traces`,
`aggregation: count`, `groupBy: "name"`, `orderBy: "count() desc"`, limit 20, **no service
filter**. This surfaces auto-instrumentation noise (health checks, SQL, cache, sidecars) across
all services at once.

**4b. Cost per service + ops per service.** Span GB by service: use
`signoz_execute_builder_query` with the discovered meter metric whose live unit and meaning
represent span bytes, summed as in Step 1 and grouped by the `service.name` field returned by
`signoz_get_field_keys` (copying its `name`, `fieldDataType`, `fieldContext`, and `signal`).
Compute each service's % against the **grouped total (sum of all service groups from this same
query)**, not a top-N sum and not the separately-fetched ungrouped total — keep numerator and
denominator on one grouped basis. For each top-3
service by GB, get its dominant operations with `signoz_get_service_top_operations` (or
`signoz_aggregate_traces` with `service: "<svc>"` + `groupBy: "name"`). The op breakdown is
top-3 for brevity, but the error-rate check (4c) and the APM guard below apply to **every**
service you consider reducing.

**4c. Error rate per service.** `signoz_aggregate_traces`, `count`, `groupBy: "service.name"`
(total), then again with `error: true`. Error rate = errors ÷ total, per service.

**4d. Trace alerts, dashboards, and saved views.** `signoz_list_alert_rules`, **paginating
through every page** (follow `pagination.nextOffset` until `pagination.hasMore` is false). Keep
`alertType == "TRACES_BASED_ALERT"`; `signoz_get_alert(id)` for what each guards. Check every
query the alert's condition depends on, not just the one that looks related (see the
formula-dependency guardrail below). Then check dashboards and saved views the same way (see the
dashboard/view coverage guardrail below).

**Classify the dominant operations.**
- Common noise candidates: health/liveness (`/health`, `/ping`, `/ready`,
  `grpc.health.v1.Health/Check`); proxy/sidecar (`envoy.*`, `istio.*`, `linkerd.*`). Treat these as
  candidates, not automatically safe removals; the APM guard below still applies.
- Research before concluding — do not assume: SQL fragments (the language decides the library:
  Java → JDBC, Python → SQLAlchemy, Node → pg/mysql2/sequelize, .NET → EF/Dapper); cache commands
  (HMGET/GET/SET… → ioredis, redis-py, Jedis, go-redis…); unfamiliar gRPC methods. Search first;
  if still unidentified after searching, say so.

**Fix layer.** For a confirmed noise operation, prefer the deployed SDK or instrumentation
library's documented disable/exclusion control so generation stops at source. Identify the
language and library before naming a setting; Java, Python, Node.js, and .NET use different
controls. Verify the exact env var, config key, or code snippet against that library's own
documentation before stating it (see the verification guardrail below) — do not name a setting
from memory alone. If no SDK control exists, use a Collector filter on the operation name.

> **Span → APM guard (mandatory).** Never recommend or configure head, probabilistic, tail, or
> any other trace sampling as a cost-reduction lever. When a user asks for sampling, state both
> effects: the built-in APM/Services metrics cover only retained traces, so absolute request counts
> and rates undercount real traffic; latency trends and error spikes may remain useful, but the APM
> page no longer represents all requests. This limited usefulness does not make sampling an allowed
> lever, and processor placement is not an exception.
>
> Use SDK exclusions and Collector filters for confirmed noise. State that the removed operation
> will disappear from APM before giving a configuration.
Docs: https://signoz.io/docs/traces-management/guides/drop-spans/

**4e. Span attribute and event size — only when bytes-per-span is unusually high.** Run this only
when Step 1's bytes-per-record check (`span.size ÷ span.count`) flags a service as a payload-size
problem, not a volume problem. Sample its spans with `signoz_search_traces`, identify which
attributes or events are driving the size, and report them with their approximate size
contribution — do not assert they're noise. Ask the user directly whether each large attribute or
event is operationally necessary before recommending anything; usefulness here is contextual, not
something to judge unilaterally. The same posture applies to attributes carrying real diagnostic
content (`db.query.text`, `url.full`, `exception.stacktrace`, correlation IDs like
`user.id`/`request.id`) — size alone doesn't make them noise. If the user confirms one isn't
needed, use the `attributes` processor (`action: delete`) for span attributes, or the filter
processor's `traces.spanevent` OTTL context for span events specifically — the `transform`
processor cannot target individual events.

### Step 5: Report what you found

Lead with a **TL;DR** — concise, no headers, two parts:
1. **Cost orientation** — which signal is the primary driver, how much, and what generates it
   (name the service, environment, or metric). If several things together dominate, name them
   with individual shares and combined impact.
2. **Prioritized action list** — every actionable finding in priority order, each with its
   status inline: **Safe to implement** / **Needs one check first** (state what) / **Will break
   dashboards** (name them) / **Will break alert coverage** (name the alert) / **Infra-page
   dependency** (breaks the Hosts/K8s view). For metric drops, include the volume % so the
   reader knows the cost impact.

After the TL;DR, add only evidence or context that was not already stated. Rank the actions using
the decision order in Steps 2–4, but state each finding and guardrail once instead of repeating
the action list or the per-signal playbooks.

Keep it conversational — a prioritized triage list, not a formatted report with headers and
tables. Cover every signal with Cost Meter data in that single list; do not ask whether to inspect
a signal the workflow already analyzed.

## Guardrails

- **Never declare a drop or filter "safe" on a partial check.** Paginate
  `signoz_list_alert_rules` fully (through `pagination.hasMore`) before ruling out alert impact,
  and treat a non-empty `error` from `signoz_check_metric_usage` as *unknown* usage (needs a
  manual check) — not as "unused." An incomplete lookup is not a green light.
- **Check every query an alert's condition depends on, not just the one that looks related.**
  This applies to both log and trace alerts. An alert can combine two or more queries in a
  formula (e.g., an error rate computed as errors ÷ total calls) or use a single query with no
  filter at all (e.g., counting any log record to track instance liveness). A volume-reduction
  recommendation can shift or trip such an alert even when it only touches data that looks
  unrelated to what the alert is nominally about — dropping non-error spans changes the "total
  calls" denominator of an error-rate formula just as much as dropping error spans would, and
  dropping DEBUG logs can undercount instances a replica-count alert expects to see from every
  record regardless of severity. When reading `condition.compositeQuery` in Step 3c or 4d,
  identify every query the condition depends on and check whether the proposed change affects
  any of them, not only the one whose filter matches the category being reduced.
- **Check dashboards and saved views too, not just alerts, for log and trace reductions.** For
  metrics, `signoz_check_metric_usage` returns both `dashboards` and `alerts` in a single call.
  No equivalent tool exists for logs or traces, so perform this check manually before marking any
  log-severity or trace-operation reduction "Safe to implement": call `signoz_list_dashboards`
  and `signoz_list_views` (scoped to the affected signal), filter to the ones whose name, tags, or
  description are plausibly related to the affected service or operation, then
  `signoz_get_dashboard` / `signoz_get_view` on those candidates and read their queries —
  including raw PromQL or ClickHouse SQL panels, not just structured builder queries — for any
  reference to the data being reduced. If one depends on it, mark the finding **Will break
  dashboards** (or name the saved view) instead of a clean drop.
- **Volume comes from discovered Cost Meter metrics and their live units:** bytes for span/log
  volume or samples for metric volume. Never cite span/log record counts as volume.
- **Cost totals and grouped total attribution use `signoz_execute_builder_query`** with raw
  `timeAggregation: sum`, hourly `stepInterval: 3600`, and complete datapoints only — never
  `signoz_query_metrics`.
- Every Cost Meter `builder_query` sent through that raw escape hatch includes
  `limit: 100` and Query Builder v5 `order: [{key:{name:"__result"},
  direction:"desc"}]`. This is wire `order`, not dashboard `orderBy`; preserve
  it in grouped queries. The limit ranks groups over the whole window, so call
  out the possibility that a short-lived group falls outside the top N.
- **Never present an Infra-page or APM metric as safe to drop** (see
  `references/infra-do-not-drop.md`), even when usage-check shows no dashboards or alerts.
- **Logs:** never recommend dropping/filtering a whole service or namespace that carries active
  ERROR/WARN (> 1% high-signal, or a non-trivial absolute count) — scope the filter to the noisy
  pattern. Fix order: at source (`LOG_LEVEL=WARN`) → Collector scope filter
  (`instrumentation_scope.name`) → `severity_text` filter.
- **Logs attribution is a hard threshold:** ≥ 10% → Path A; < 10% → Path B. Compute it.
- **Traces:** never recommend or configure head, probabilistic, tail, or any other sampling.
  Sampling limits the built-in APM/Services metrics to retained traces, so absolute request counts
  and rates no longer represent all traffic.
- **UNBOUNDED and IDENTIFIER labels are always worth flagging** — the problem is trajectory, not
  just current count.
- **Never suggest changing retention. Never estimate dollar savings.** Asking the user their
  currently configured retention (Step 1, to weight cost accurately) is required and does not
  violate this guardrail — recommending they change it does. Using retention-matched rates to
  rank signals against each other internally is required — presenting the resulting figure to the
  user as a dollar estimate or savings number is not. Never call a dashboard or alert
  unused/noisy/redundant — report counts only.
- **Anchor claims to query results.** If a signal has no Cost Meter data, say so — do not
  substitute count-based proxies. Don't re-list metrics already shown in the breakdown; metrics
  outside the top ~20 by volume are individually negligible.
- **Verify configuration specifics before stating them as fact.** An env var, config key, flag, or
  code snippet for disabling instrumentation, changing a collection interval, or filtering logs is
  a factual claim about a specific library or the Collector, not something to pattern-match from
  memory. Before naming one, check it against that library's or the Collector's actual
  documentation — WebFetch/WebSearch the official docs, changelog, or repo, or read the matching
  `signoz://` doc resource for SigNoz-side syntax. If it can't be verified, say so explicitly and
  present it as an unconfirmed guess to check, never as a directive to apply.

## Additional resources

- `references/cost-meter-queries.md` — Cost Meter discovery, the full
  `signoz_execute_builder_query` template, unit conversion, and the grouped-vs-ungrouped caveat.
- `references/infra-do-not-drop.md` — the metrics behind the built-in Infrastructure and
  APM/Services pages that must never be recommended for dropping.
- `references/otel-attribute-cardinality.md` — reference for classifying metric labels
  (UNBOUNDED / ACCUMULATING / BOUNDED / IDENTIFIER).
- `signoz-generating-queries` skill — for the ad-hoc follow-up queries this investigation points to.
