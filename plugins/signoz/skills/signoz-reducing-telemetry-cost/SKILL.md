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
  don't say "cost" or "optimize" explicitly. Do NOT use for building
  dashboards or ad-hoc data queries — use signoz-generating-queries.
argument-hint: [investigation focus, e.g. "metrics cost" or "cardinality health"]
---

# Reduce Telemetry Cost

Find what is driving SigNoz ingestion cost and cardinality, and return safe, specific ways to
reduce it. The skill reads the Cost Meter to identify the primary cost driver across metrics,
logs, and traces, drills into that signal, and produces a prioritized action list where every
recommendation carries a safety status — is it safe to drop, or would it break a dashboard,
an alert, or a built-in SigNoz page. It is the companion to `signoz-generating-queries`: that
runs ad-hoc queries; this runs a structured cost/cardinality investigation.

## Prerequisites

This skill calls SigNoz MCP server tools heavily (`signoz_execute_builder_query`,
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

## When to use

Use this skill when the user wants to:
- Understand what is driving their SigNoz ingestion cost or bill.
- Find high-cardinality, unbounded, or accumulating metric labels.
- Get safe recommendations to reduce telemetry volume across metrics, logs, or traces.

Do NOT use when the user wants to:
- Build or edit a dashboard → `signoz-creating-dashboards`.
- Run a free-form ad-hoc query → `signoz-generating-queries`.

## Workflow

Always start with the Cost Meter snapshot (Step 1) — it names the primary cost driver. Then run
the step for that signal (metrics, logs, or traces). Finish with the report (Step 5).

### Step 1: Cost Meter snapshot

Establish the cross-signal cost picture first. Query the Cost Meter with
`signoz_execute_builder_query` (`source: "meter"`, `timeAggregation: "sum"`) — see
`references/cost-meter-queries.md` for the exact template, the meter metric names, and the
unit divisors. Do **not** use `signoz_query_metrics` for these totals; it forces an `increase`
aggregation that undercounts the billing figure by ~6%.

For a rolling 7-day window (`end` = now, `start` = end − 7 days), get the per-signal totals
(span size, log size, metric datapoints), then compute and report:

- **Week-over-week.** Repeat the queries for the prior 7-day window. A ratio > 1.5× is a
  **spike** — that signal is the primary driver regardless of absolute volume. 1.1–1.5× is
  rising; < 0.9× is falling.
- **Primary cost driver.** The signal with the highest *dollar* weight — traces/logs at
  $0.30/GB, metrics at $0.10/M samples (orientation only; never quote dollar savings). This
  picks by cost, not by raw volume.
- **Bytes per record.** span.size ÷ span.count and log.size ÷ log.count — tells you whether a
  signal is a payload-size problem or a volume problem.

Then break the primary signal down by `deployment.environment` and by `service.name` (same
meter query with a `groupBy`; template in the reference). Report the top ~10 per group with
their share. If a non-prod environment (`staging`, `dev`, `test`, `qa`, `sandbox`, `preview`,
`uat`, …) is > 40% of volume, recommend Ingestion Limits on that key before any signal-level
change: https://signoz.io/docs/ingestion/signoz-cloud/keys/

### Step 2: Metrics

Run when metrics are the primary driver, or when the user asks about metric cost or cardinality.
Three tools, in order.

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

**2c. Inspect cardinality — `signoz_check_metric_cardinality`.** Only for metrics that are **in
use** (unused metrics are drop candidates — cardinality adds nothing). Returns attribute keys
sorted highest-cardinality first, each with `valueCount` and sample `values`. Classify each with
`references/otel-attribute-cardinality.md`:

- **UNBOUNDED** (`url.full`, `http.target`, `db.query.text`, `client.port`, `trace.id`,
  `exception.stacktrace`, …) — grow without ceiling; flag regardless of current count.
- **ACCUMULATING** (`container.id`, `k8s.pod.uid`, `k8s.pod.name`, `k8s.pod.start_time`) —
  `valueCount` reflects historical pod churn, not active series; explain the distinction.
- **HIGH but bounded** (`valueCount` ≳ 100) — check whether dashboards/alerts actually filter on
  that label before recommending aggregation.

To reduce cardinality use the `metricstransform` processor's `aggregate_labels` action to *merge*
series (samples are the billable cost, so merging is what actually cuts it) — not the `transform`
processor's `delete_key`, which leaves the same sample count and creates colliding series. If a
label is essential to the metric's identity, drop the whole metric or fix it at the SDK instead.
For histograms, reducing bucket boundaries cuts samples with little P99 impact. Docs:
https://signoz.io/docs/userguide/drop-metrics/ ·
https://signoz.io/docs/metrics-management/dropping-metric-labels/

### Step 3: Logs

Run when logs are the primary driver, or when the user asks about log cost.

**3a. Total + attribution decides the path.**
- Total log GB (the absolute cost figure): `signoz_execute_builder_query`, `source: "meter"`,
  `signoz.meter.log.size`, sum (as in Step 1).
- Attribution: run the **same meter query grouped by `service.name`**. This returns one group per
  service plus an unset/empty-`service.name` group for logs with no attribution. Compute the ratio
  entirely from THIS grouped result so numerator and denominator share one basis — a grouped sum can
  differ from the ungrouped total by ~5%, so never divide the grouped attributed sum by the
  ungrouped total:
  - attributed GB = sum of the groups with a non-empty `service.name`.
  - grouped total = sum of *all* groups (including the empty one).
  - **Attribution % = attributed ÷ grouped total.**
- This is a hard branch:
  - **≥ 10% → Path A (service mode).**
  - **< 10% → Path B (namespace mode).** Logs come from an infra forwarder (Fluent Bit /
    Fluentd / Vector), not OTel SDKs, so `service.name` isn't set. Path B is a less common
    setup — sanity-check its numbers.

**Path A — service mode (≥ 10%).** Get the severity mix with `signoz_aggregate_logs`,
`aggregation: count`, `groupBy: "service.name,severity_text"`. Classify severities — REDUCIBLE =
INFO, INFORMATION, DEBUG, TRACE, VERBOSE; HIGH-SIGNAL = ERROR, FATAL, CRITICAL, WARN, WARNING.
For each top service by GB:
- Reducible-dominant + own service code → set `LOG_LEVEL=WARN` (stops generation at source).
- Reducible-dominant + third-party library → Collector filter on `instrumentation_scope.name`
  (read the scope from a `signoz_search_logs` sample's `scope_name`).
- No source access → Collector filter on `severity_text` matching **only the reducible set**
  (INFO/DEBUG/TRACE) — never a range that also catches WARN+.
- High-signal-dominant (WARN/ERROR > 50%) → the logs are worth keeping; a high error rate may be
  a real problem — flag it separately, do not recommend filtering it away.

> **Service severity guard.** The fixes above (`LOG_LEVEL=WARN`, or a Collector filter scoped to
> INFO/DEBUG only) preserve WARN+ by construction, so they are safe first-line actions **regardless
> of the service's error rate** — recommend them freely. The guard applies only to actions that
> would *also* drop high-signal logs: a **blanket service drop**, or a `severity_text` filter whose
> range includes WARN/ERROR/FATAL/CRITICAL. Before recommending one of those, compute high-signal %
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
> total. **If it is > 1% (or a non-trivial absolute count), do not recommend dropping or
> filtering the whole namespace.** Scope the filter to the specific noisy pattern (a log
> category, a `severity_text` match, or a component). Never drop a namespace that carries active
> errors. Only namespaces that are essentially all INFO/DEBUG are safe to filter wholesale.

- Empty `severity_text` on samples → the forwarder ships raw lines unparsed; the fix is a
  json/regex parser in the OTel Collector log pipeline (without it, severity filtering is
  impossible).
- `k8s.event.*` logs are often high-volume / low-value → droppable if not alerted on.

**3c. Log alerts — check before any filter recommendation.** `signoz_list_alert_rules`,
**paginating through every page** (follow `pagination.nextOffset` until `pagination.hasMore` is
false — do not stop at the first page, or an alert on a later page is missed and a filter looks
safe when it isn't). Keep `alertType == "LOGS_BASED_ALERT"`. For each, `signoz_get_alert(id)` and read
`condition.compositeQuery.queries[].spec.filter.expression` + `groupBy` to see which service /
severity / namespace it guards. If a filter would blind an alert, mark it **Will break alert
coverage** and name the alert. Docs: https://signoz.io/docs/logs-management/guides/drop-logs/

### Step 4: Traces

Run when spans are the primary driver, or when the user asks about span cost.

**4a. Global operation-name view — read this first.** `signoz_aggregate_traces`,
`aggregation: count`, `groupBy: "name"`, `orderBy: "count() desc"`, limit 20, **no service
filter**. This surfaces auto-instrumentation noise (health checks, SQL, cache, sidecars) across
all services at once.

**4b. Cost per service + ops per service.** Span GB by service: `signoz_execute_builder_query`,
`source: "meter"`, `signoz.meter.span.size`, sum, `groupBy: [{ "name": "service.name" }]`.
Compute each service's % against the **grouped total (sum of all service groups from this same
query)**, not a top-N sum and not the separately-fetched ungrouped total — keep numerator and
denominator on one grouped basis. For each top-3
service by GB, get its dominant operations with `signoz_get_service_top_operations` (or
`signoz_aggregate_traces` with `service: "<svc>"` + `groupBy: "name"`). The op breakdown is
top-3 for brevity, but the error-rate gate (4c) and the APM guard below apply to **every**
service you consider reducing.

**4c. Error rate per service.** `signoz_aggregate_traces`, `count`, `groupBy: "service.name"`
(total), then again with `error: true`. Error rate = errors ÷ total, per service.

**4d. Trace alerts.** `signoz_list_alert_rules`, **paginating through every page** (follow
`pagination.nextOffset` until `pagination.hasMore` is false). Keep
`alertType == "TRACES_BASED_ALERT"`; `signoz_get_alert(id)` for what each guards. Name any
trace-based alert before suggesting sampling.

**Classify the dominant operations.**
- Known-safe to pre-filter (near-zero diagnostic value): health/liveness (`/health`, `/ping`,
  `/ready`, `grpc.health.v1.Health/Check`); proxy/sidecar (`envoy.*`, `istio.*`, `linkerd.*`).
- Research before concluding — do not assume: SQL fragments (the language decides the library:
  Java → JDBC, Python → SQLAlchemy, Node → pg/mysql2/sequelize, .NET → EF/Dapper); cache commands
  (HMGET/GET/SET… → ioredis, redis-py, Jedis, go-redis…); unfamiliar gRPC methods. Search first;
  if still unidentified after searching, say so.

**Fix layer.** Prefer SDK/env disable (`OTEL_INSTRUMENTATION_*_ENABLED=false`) — stops
generation at source. Else a Collector filter on the operation name. Sampling is **not** the fix
for known-noise ops — the data still reaches the Collector before the drop.

> **Error-rate sampling gates.** > 10% error rate → do **not** suggest sampling; errors must be
> investigated first, sampling would hide the signal — flag it as a real problem. < 2% → sampling
> is safe *only if* the other conditions below also hold. 2–10% → investigate before sampling.

> **Span → APM guard.** The SigNoz APM/Services page is built from span-derived `signoz_*` RED
> metrics generated by the `signozspanmetrics` processor on the traces pipeline (see
> `references/infra-do-not-drop.md`). Head-sampling or dropping spans **upstream** of that
> processor degrades the APM page (skews rate/latency/error). Prefer **tail-sampling downstream**
> of the processor. State this before recommending any span-volume reduction.

**Tail sampling is an optional lever, not a default fix.** Raise it only when structural fixes
are exhausted (noisy ops already filtered/SDK-disabled), volume is genuinely high, and the
dominant ops are real application traffic. Never when volume is explained by fixable issues,
error rate > 10%, or trace-based alerts exist. State the tradeoffs (misses rare errors, harder
debugging, more Collector overhead). If traces look structurally healthy, say so first, then
offer tail sampling as a voluntary lever — never as a remedy for a problem that doesn't exist.
Docs: https://signoz.io/docs/traces-management/guides/drop-spans/

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

Then the detail: what generates the cost and why (grounded in what was actually observed), and
what to do about it in priority order. Priority depends on the signal:
- **Metrics:** drop unused metrics first (complete saving, zero dashboard impact) → fix UNBOUNDED
  labels → fix ACCUMULATING labels → trim histogram buckets → reduce HIGH-but-bounded labels.
  Never the Infra/APM do-not-drop set.
- **Logs:** fix reducible volume at source (`LOG_LEVEL=WARN`) → scope-filter the noisy INFO/DEBUG
  pattern (never blanket-filter a service or namespace carrying active ERROR/WARN > 1%) → add a
  parser where severity is unparsed. Flag high-error services as real problems, not volume.
- **Traces:** investigate errors first (never sample a service with > 10% error rate) →
  SDK-disable / pre-filter known-noise ops → only then consider tail-sampling downstream, and
  only if healthy and genuinely high volume.

Keep it conversational — a prioritized triage list, not a formatted report with headers and
tables. If the signal investigated is not the primary driver, say which is larger and by how
much, and ask whether to look at that one too.

## Guardrails

- **Never declare a drop or filter "safe" on a partial check.** Paginate
  `signoz_list_alert_rules` fully (through `pagination.hasMore`) before ruling out alert impact,
  and treat a non-empty `error` from `signoz_check_metric_usage` as *unknown* usage (needs a
  manual check) — not as "unused." An incomplete lookup is not a green light.
- **Volume = GB from the Cost Meter** (`signoz.meter.span.size`, `signoz.meter.log.size`) or
  samples (`signoz.meter.metric.datapoint.count`). Never cite span/log record counts as volume.
- **Cost totals via `signoz_execute_builder_query`** with `timeAggregation: sum` — never
  `signoz_query_metrics`, which undercounts by ~6%.
- **Never present an Infra-page or APM metric as safe to drop** (see
  `references/infra-do-not-drop.md`), even when usage-check shows no dashboards or alerts.
- **Logs:** never recommend dropping/filtering a whole service or namespace that carries active
  ERROR/WARN (> 1% high-signal, or a non-trivial absolute count) — scope the filter to the noisy
  pattern. Fix order: at source (`LOG_LEVEL=WARN`) → Collector scope filter
  (`instrumentation_scope.name`) → `severity_text` filter.
- **Logs attribution is a hard threshold:** ≥ 10% → Path A; < 10% → Path B. Compute it.
- **Traces:** error-rate gates are hard thresholds — > 10% → never suggest sampling (flag errors
  first); < 2% → sampling only if other conditions hold. Sampling upstream of `signozspanmetrics`
  degrades the APM page — tail-sample downstream. Name any trace-based alert before suggesting
  sampling. Tail sampling is a lever, never a fix for a non-problem or for noise.
- **UNBOUNDED and IDENTIFIER labels are always worth flagging** — the problem is trajectory, not
  just current count.
- **Never suggest changing retention. Never estimate dollar savings.** Never call a dashboard or
  alert unused/noisy/redundant — report counts only.
- **Anchor claims to query results.** If a signal has no Cost Meter data, say so — do not
  substitute count-based proxies. Don't re-list metrics already shown in the breakdown; metrics
  outside the top ~20 by volume are individually negligible.

## Additional resources

- `references/cost-meter-queries.md` — `signoz_execute_builder_query` meter templates, metric
  names, unit divisors, and the grouped-vs-ungrouped caveat.
- `references/infra-do-not-drop.md` — the metrics behind the built-in Infrastructure and
  APM/Services pages that must never be recommended for dropping.
- `references/otel-attribute-cardinality.md` — reference for classifying metric labels
  (UNBOUNDED / ACCUMULATING / BOUNDED / IDENTIFIER).
- `signoz-generating-queries` skill — for the ad-hoc follow-up queries this investigation points to.
