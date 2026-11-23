---
name: signoz-creating-alerts
description: >
  Create a new SigNoz alert rule from a natural-language intent: threshold,
  anomaly, log-volume, error-rate, latency, or absent-data alerts across
  metrics, logs, traces, and exceptions. Make sure to use this skill whenever
  the user says "alert me when…", "notify me if…", "set up monitoring for…",
  "page me on…", "create an alert for…", or asks for a new alert/notification
  rule, even if they don't say the word "alert" explicitly. Also use it when
  someone asks to be notified about error rates, latency spikes, log volume,
  CPU/memory pressure, or anomalous behavior on a service or host.
argument-hint: <natural-language alert intent>
---

# Alert Create

Build a SigNoz alert from natural-language intent. Autonomous agents and
interactive clients follow the same flow.

## Prerequisites

This skill calls SigNoz MCP tools (`signoz_create_alert`,
`signoz_list_alert_rules`, `signoz_get_field_keys`, etc.). Confirm they are
available; otherwise run `signoz-mcp-setup`. Never fall back to raw HTTP or
fabricate alert configs.

## When to use

Use this skill when the user wants to:
- Create, set up, or configure a new alert rule.
- Get paged or notified when a metric, log volume, latency, or error rate
  crosses a threshold.
- Detect anomalous behavior on a service, host, or signal.
- Catch silent data loss ("alert if data stops arriving from X").

Do NOT use when the user wants to:
- Understand what an existing alert monitors → `signoz-explaining-alerts`.
- Diagnose why an existing alert fired → `signoz-investigating-alerts`.
- Modify thresholds, queries, or routing on an existing alert → call
  `signoz_update_alert` directly.

## Required inputs (strict)

Alert creation writes to a shared system. Enforce this strict input contract;
guesses create noisy alerts on the wrong service:

| Input | Required | Source if missing |
|---|---|---|
| Alert intent (NL goal) | yes | `$ARGUMENTS` or recent user turn |
| Resource attribute filter (e.g. `service.name`, `k8s.namespace.name`, `host.name`) | yes | discover via `signoz_get_field_keys` + `signoz_get_field_values` |
| Threshold value(s) | threshold / PromQL rules | derive a sensible default and surface in the preview; never substitute one for an absent-only request |
| Severity | inferred from intent | resolve with *Severity defaults* in Step 5 |
| Notification routing | yes | direct: verified channel display name(s); policy: confirmation that an existing org policy matches this rule |

If a required input is missing and undiscoverable, **stop before any write**
and ask through the host's supported clarification UI. Include:

- **What is missing**: name it concretely (e.g. "which resource-attribute
  filter to use").
- **Candidate lists** from discovery: concrete values per attribute, e.g.:
  `service.name` → `frontend`, `checkout`, `payments`;
  `host.name` → `prod-api-1`, `prod-db-1`.
- **Free-form input** so the user can name an unsurfaced value.

In autonomous mode, escalate or use upstream context; never call
`signoz_create_alert` with a guessed value.

## Workflow

### Step 1: Parse intent and check what's missing

Extract from the user's request:
1. **What to monitor**: signal type (metrics / logs / traces / exceptions)
   and the specific condition (CPU, error rate, p99 latency, log count, ...).
2. **Resource scope**: which service, host, namespace, or environment.
3. **Threshold**: numeric value and comparison ("above 80%", "below 100/s").
4. **Severity**: note any severity the user names and any urgency cue
   ("page me", "just FYI"). Step 5 resolves the final value.
5. **Routing**: direct channel name(s), or an explicit request to use a
   confirmed existing org notification policy.

Pick `alertType` from the signal the query reads; the `signoz_create_alert`
input schema lists the accepted values. CPU, memory, latency histograms, and
request rate are metrics; log lines, log volume, and log patterns are logs;
span latency, slow requests, and span errors are traces; exceptions, stack
traces, and crashes are exceptions, queried with `clickhouse_sql`. The SigNoz
alert UI can edit those four types today. Newer types it does not surface
yet, such as `AI_TRACES_BASED_ALERT` for LLM and AI-agent span telemetry, are
also accepted. Use one only when the user names it or no other type fits, and
say that the UI has no editor for it.

If resource scope is missing, run discovery (Step 2). If still missing after
discovery, stop and ask the user (see *Required inputs* above).

### Step 2: Discover resource attributes and metric names

When the user does not name a service / host / namespace, the SigNoz MCP
guideline applies: **always prefer a resource-attribute filter**. Discover
candidates instead of guessing:

1. Call `signoz_get_field_keys` with `fieldContext=resource` to enumerate
   resource attributes for the chosen signal.
2. Call `signoz_get_field_values` for the most likely attribute (typically
   `service.name`, then `host.name`, then `k8s.namespace.name`) to get
   concrete values.
3. If the user mentioned a metric by name, call `signoz_list_metrics` with a
   search term to verify the exact OTel metric name. A wrong name saves a
   rule whose query returns no data.

Surface the candidates in your clarification request; do not pick one.

### Step 3: Check for duplicate alerts

Once the scope is resolved, check for existing alerts before probing data or
authoring a new config: both are wasted work if the user wants to update an
existing rule instead.

Call `signoz_list_alert_rules` with a `filter` on the scope (the service,
host, or namespace name) and page the matches to the end. The filter reads
a rule's name, description, and labels, not its query, so when none of the
matches is a duplicate, list again without the filter and page to the end
before concluding there is none. `signoz_list_alerts` returns only current alert instances and
misses rules that are not firing. Check for existing rules that match the
user's intent (same signal + same scope + similar threshold). If a likely
duplicate exists, surface it and ask whether to create a new one anyway,
modify the existing one (out of scope here: use `signoz_update_alert`), or
cancel.

### Step 4: Probe data existence for the chosen filter (fail fast)

Before authoring any alert config, confirm the **specific combination** the
alert will watch (metric × service × any other filter) actually emits data.
The most common silent failure is "metric exists in the catalog *and* the
service exists in the catalog, but the service doesn't emit that metric";
each piece checks out in isolation, the alert saves successfully, and its
threshold silently never fires.

Run a single probe over the last 1 hour using the same filter the alert
will use, but with the simplest aggregation that confirms data exists:

- **Metrics**: use `signoz_query_metrics` with the concrete `metricName` and
  the alert's `filter`. It fills aggregation defaults and reports them; a
  saved rule gets none, so keep the reported `timeAggregation` and
  `spaceAggregation` for Step 5. Metrics do **not** accept expression
  aggregations such as `count()` or filter-only probes.
- **Logs**: call `signoz_aggregate_logs` with `aggregations: "count()"` and
  the alert filter.
- **Traces**: call `signoz_aggregate_traces` with `aggregations: "count()"` and
  the alert filter.

Inspect the result:

- **Probe returns rows** → proceed to Step 5.
- **Probe returns empty** → STOP before building any config. Ask the user
  (see *Required inputs* above), describing what was missing and offering
  concrete recovery:
  - Service doesn't emit the metric → call
    `signoz_get_field_values signal=metrics name=service.name metricName=<metric>`
    to list the services that *do* emit it; let the user pick a different
    service or a different metric.
  - Wrong attribute name (`service` instead of `service.name`) → suggest
    the semantic-convention name and re-probe.
  - Service emits the metric but not in the expected time range → widen
    the probe window once (e.g. last 24h) before declaring no-data.

**Exception: log-based crash / panic / OOMKilled / FATAL alerts.** These
intentionally have zero matches in a healthy system. The probe will
return empty by design. Do not stop; instead, surface the zero-match
result and ask the user to confirm before save. Treat this exception
narrowly: it applies to "alert me when bad thing happens" log queries,
not to alerts that depend on continuous data flow.

### Step 5: Build the alert config

Read these MCP resources before composing the payload, unless already read
for this same alert:

1. `signoz://alert/instructions` and `signoz://alert/examples`, for every
   rule: the rule shape, the fields SigNoz requires, threshold, evaluation,
   and unit rules, anomaly scoring, and a complete payload per pattern.
2. `signoz://promql/instructions`, before writing the query of a
   `promql_rule`.
3. `signoz://dashboard/clickhouse-schema-for-logs`,
   `signoz://dashboard/clickhouse-schema-for-traces`, or
   `signoz://dashboard/clickhouse-schema-for-metrics`, for the signal a
   `clickhouse_sql` rule reads; `signoz://alert/examples` holds no SQL. They
   describe dashboard widgets, so take only table and column names from them.
4. `signoz://ai/query-builder-guide`, for an `AI_TRACES_BASED_ALERT`.

If the client cannot read `signoz://` resources, find a rule of the same
`ruleType` and query type with `signoz_list_alert_rules`, fetch it with
`signoz_get_alert`, and copy its shape without the server-populated fields
(`id`, `state`, `createdAt`, `updatedAt`, `createdBy`, `updatedBy`, `webUrl`).

The guide and the `signoz_create_alert` input schema list the required
fields, so this skill does not repeat them. SigNoz rejects an unknown key at
the top level or in `condition`: never send retired fields such as
`condition.algorithm` or top-level `preferredChannels`.

Every rule requires `condition.thresholds` with at least one tier, so
`alertOnAbsent` cannot be the sole trigger. For an exact absent-only request, stop before any write and
offer a combined threshold + absence rule only with explicit approval.

For most user intents, the config is one of a small number of patterns:

| Pattern | Example intents |
|---|---|
| Threshold on a metric, a log count, or a trace count or p-tile | "alert when CPU > 80%", "more than N error logs/min", "p99 span duration > 2s on checkout" |
| Error-rate formula (A/B*100): see "Common query shapes" below | "error rate > 5%" |
| Anomaly detection (Z-score) | "alert me on anomalous traffic" |
| Combined threshold + absence (only after approval) | "alert if data stops arriving" |
| ClickHouse SQL alert: take tables and columns from the schema resource read above | non-trivial joins, custom aggregations the builder cannot express |
| PromQL alert: delegate to `signoz-generating-queries` for the query, then return here | when user already has PromQL |

**Threshold `op` and `matchType`.** Use the canonical words the guide lists
(`equal`, not `equals`). An anomaly tier compares a signed score, negative
on a drop: use `above` with target 3 for spikes, `below` with target -3 for
drops, and `outside_bounds` with target 3 when the request covers both
directions. Leave `targetUnit` empty on an anomaly tier and pass the same
deviation as the anomaly function's `z_score_threshold`.

**Conventions this skill writes into the payload (and surfaces in the
preview):**
- `evalWindow: 5m0s`, `frequency: 1m0s`: change only if the intent implies
  a slower or faster cadence.
- `matchType`: `on_average` (the window average) for CPU / memory / latency,
  `at_least_once` (any point in the window) for error counts / error rates.
  The others: `all_the_times` (every point), `in_total` (the window sum),
  and `last` (the most recent point).

**Severity defaults.** Resolve each threshold tier's severity in this order:

1. Take the first matching row below (no cue needed), or `warning` if none.
2. A user cue overrides the default. A named severity ("critical", "warning
   at 80%") wins over an urgency cue. "Page me", "wake me up", or "urgent"
   sets `critical`. "Just FYI", "no paging", or "low priority" lowers the
   default one tier (`critical` to `warning`, `warning` to `info`, `info`
   stays `info`). A cue tied to one threshold ("page me at 90%") applies
   only to that tier. Ask when urgency cues conflict on the same tier.
3. Name each threshold tier by its severity. Each fired alert carries
   `severity` and `threshold.name` equal to the tier that fired. A static
   `labels.severity` does not change that: SigNoz drops rule labels named
   `severity` or `threshold.name` from fired alerts. The alert-rule list
   reads severity from that label only, so set it only when the user asks
   for the list to show a severity, with the value they name. The Step 8
   preview states each tier's severity and why.

| Alert intent | Default severity |
|---|---|
| Any single crash event: OOMKilled / CrashLoopBackOff / panic / FATAL log line | critical |
| Service down / no-data on a production service | critical |
| SLO burn rate | 14.4× or more: critical; 6× to under 14.4×: warning; under 6× (e.g. ticket-level 1×): info |
| Error rate with a threshold above 1% | critical |
| Error log or exception volume above a count threshold | warning |
| Latency degradation (p95/p99 above target) | warning |
| CPU / memory / disk pressure | warning |
| Request-rate / traffic anomaly | warning |

Example: "alert me when checkout error rate goes above 2%" is `critical`
(error-rate row); the same request with "just FYI" is `warning`.

**Attribute names**: use exact keys returned by `signoz_get_field_keys`; when
available they are usually OTel names such as `service.name`, not `service`.

**Annotation templates**: include moving values; on-call sees the notification,
not the config:

- `summary`: single-line headline. Include the resource scope and the
  numeric value: `"checkoutservice error rate {{$value}}% above 3%"`.
- `description`: longer message. Include `{{$value}}`, `{{$threshold}}`,
  the groupBy values, and a sentence on what to do or where to look. Write a
  groupBy value as `{{$labels.<key>}}` with the key's dots as underscores
  (`service.name` becomes `{{$labels.service_name}}`). For count-based
  alerts include the count explicitly: `"{{$value}} crash log lines in the
  last 5 minutes from service {{$labels.service_name}}"`.

#### Common query shapes: conventions

`signoz://alert/examples` has the JSON for each builder and PromQL pattern.
The conventions that don't live in the schema:

- **Service requests from traces:** a service's requests are its entry
  spans. For a request count, rate, error rate, or latency, add
  `AND (isEntryPoint = true OR isRoot = true)` to every trace query in the
  rule; without it the query covers every span the service records and a
  request with nested spans counts more than once. When the user wants every
  span, leave the filter out and call the result span-level in the preview.
  The span metrics `signoz_calls_total` and `signoz_latency` count every
  span too; say so when a rule uses them for a request rate.
- **Error-rate formula:** set `disabled: true` on the component queries A
  and B so only the formula F1 renders in the alert chart and notification;
  three series confuse the on-call engineer reading it.
- **p99 latency:** the query emits nanoseconds, but express the threshold in
  the user's unit (for example `target: 2`, `targetUnit: "s"`) and set
  `compositeQuery.unit: "ns"`; SigNoz converts the target to that unit during
  evaluation. A 0 to 1 ratio metric with a percent target takes
  `compositeQuery.unit: "percentunit"` and `targetUnit: "percent"`.
- **Low-traffic percentile guard:** list the percentile first and `count()`
  second in the percentile query's `aggregations`, put `count() > N` in its
  `having.expression`, and set `stepInterval` to the requested bucket
  size (for example, `60` for “per minute”). Do not invent comparison operators
  inside a formula such as `A * (B >= N)`.
- **Log volume spike:** prefer `groupBy: service.name` over a hard
  filter when the user said "any service": groupBy provides the
  scoping AND keeps the notification useful per-service.

### Step 6: Dry-run the full query and validate the threshold

Step 4 confirmed data flows. Step 6 does two things:

1. **Validate query shape.** Run the queries exactly as the rule will store
   them (`groupBy`, formulas, disabled component queries, every aggregation
   field): Step 4's probe tools fill defaults a saved rule does not get.
   SigNoz saves a rule whose query errors or returns no data at evaluation
   (a metrics query without `timeAggregation`, a wrong metric name, a
   mismatched aggregation). Fix any error before (2).
   `disabled: true` on formula component queries (A, B in `A * 100 / B`) is
   the *recommended* pattern, not a failure (see Step 5).
2. **Calibrate the threshold.** Given the validated query, how many
   returned points breach the proposed threshold in the last hour?

Run the full primary query (or formula) over the last hour:
- Call `signoz_execute_builder_query` with `query` set to `{start, end,
  requestType: "time_series", compositeQuery: {queries:
  <condition.compositeQuery.queries>}}`: the rule's own query envelopes,
  unchanged, without `queryType`, `panelType`, or `unit`. Set `start` / `end`
  to absolute JSON integer Unix-ms (e.g. now−3600000 → now); the rule itself
  stores no time bounds.
- Do not dry-run with `signoz_query_metrics`, `signoz_aggregate_logs`, or
  `signoz_aggregate_traces`: each builds its own query, and
  `signoz_query_metrics` fills aggregation defaults a saved rule does not
  get, so a pass there does not show the saved query runs.
- Keep alert PromQL fully literal: no `$var`, `$__rate_interval`, or other
  dashboard variable is evaluated.
- For intent grouped by a dimension, each `groupBy[].name` is the
  exact Step 2 key (e.g. `k8s.pod.name`), never empty. Omit `groupBy` otherwise.

**Omit `limit` and `order` from every query in the persisted rule**, builder
queries, formula inputs, and formula results alike. On a grouped alert query
they cap evaluation to the top-N series ranked over the whole evaluation
window: a group with a short-lived spike can be ranked out, and a `below`
alert ordered descending can exclude every breaching series. Set them
only when top-N alerting is the explicit intent ("alert on the five busiest
hosts"), using Query Builder v5 wire `order`, never dashboard `orderBy`.

The dry-run is different: `signoz_execute_builder_query` inserts a display
`limit` and `order` on each standalone query and formula result that omits
them, and names them in a result note. Leave `limit` unset on every query a
formula references: SigNoz applies an input's limit before the formula runs
and drops the other series. The dry-run returns at most `limit` groups, so a
breach count from it covers the returned groups only; when the groupBy can
exceed that bound, say so in the preview rather than reporting it as complete.

Compute how many returned points breached the proposed threshold.
Surface in the preview as **"N of M returned points breached in the last 1h"**.
Do not report breached points as fires. A fire depends on the evaluation
window and `matchType`; only `signoz_get_alert_history` transitions count fires.
A 1h window is too short to grade most alerts: only the upper extreme
is actionable:
   - **N is large (e.g. > 30)** → likely alert storm. Surface and
     recommend tightening or adding hysteresis (`recoveryTarget`).
   - **N = 0** → expected for a healthy system; do not nudge the user
     to loosen. Only flag if the user said they'd expect the alert
     firing right now (e.g. during an active incident).
   - **N is small and non-zero** → report the count; the user decides
     whether the threshold is right. One hour can't distinguish "tuned
     well" from "barely caught a transient".
3. **Exceptions:**
   - **Anomaly alerts**: execute the underlying metric query without the
     anomaly `functions` transform to verify its shape and data, then skip the
     breach count (Z-scores aren't directly comparable to raw values). Be
     explicit that this validates the base query, not anomaly scoring.
   - **Log-based crash / panic / OOMKilled / FATAL alerts**: these
     intentionally have zero matches in a healthy system. Step 4 has
     already surfaced the zero-match result and obtained user confirmation;
     skip the breach count.

If Step 4 was somehow skipped (e.g. a downstream skill is invoking this
flow mid-stream), the no-data stop rule and its crash-log exception apply
here too: empty result → stop and ask the user (see *Required inputs* above).
While its query returns no series, a saved rule can fire only a nodata alert,
and only when `alertOnAbsent` is set.

### Step 7: Resolve notification routing

Choose direct or org-policy routing after dry-run and final severity. A missing
channel does not authorize policy routing.

For a confirmed existing org policy, set
`notificationSettings.usePolicy: true`, preserve the confirmed matcher labels
and threshold tier, and omit threshold channels. This skill does not create
policies. If the policy or match criteria are not confirmed, stop and ask. A
policy that matches `severity` needs no static label: each alert carries the
`severity` of the tier that fired (Step 5), so name the tier to match.

For direct routing, reuse a fully paginated same-operation channel result or
page `signoz_list_notification_channels` to the end. Match and route by
`displayName`, not the machine `name`; show `displayName` and `kind` when
asking the user to pick. Offer creation only from user-provided config and
never create automatically. Ask whether the user wants a test notification
and send `test: true` only if they agree. On `PERMISSION_DENIED`, use an
admin-created channel or a short-lived minimum-role credential from the host's
secret store. If routing remains unresolved, stop and ask.

Before composing `config` for `signoz_create_notification_channel` or
`signoz_update_notification_channel`, read
`signoz://notification-channel/examples`: every provider kind, each kind's
`config.spec` fields, and a worked payload per kind. If the client cannot
read it, start from the minimal example in the tool description and correct
from the error SigNoz returns.

Put exact returned display names in each threshold's `channels`, anomaly
rules included: with direct routing SigNoz rejects a tier with no channels
and a channel name that does not exist. With `usePolicy: true`, omit tier
`channels`; a name supplied there can still fail validation.

#### Updating or handling secret-bearing channel config

`signoz_update_notification_channel` replaces the whole `config`; its
description gives the get-then-replace steps. Preserve credentials and the
effective `sendResolved` without echoing them.

If a requested test fails after a successful write, report mutation and test
status separately. On a post-write auth error with `mutationCommitted: true`,
retain the id and inspect after authentication; do not replay mutation or test.
Transport success does not prove final provider delivery.

Slack webhook URLs, PagerDuty integration keys, and similar tokens are
secrets. When the user supplies one inline:

- **Do not echo it.** Never include the value in chat output, previews,
  confirmations, summaries, or the `<navigation_suggestions>` payload. Name
  the channel by `displayName` only ("Slack channel `Platform Alerts` created").
- **Do not stash it in clarification context.** Leave it out of the
  clarification `message`, `discovered_context`, and any other field the host
  may persist for resume; call it "the webhook you just provided".
- **One pass only.** Pass it directly to
  `signoz_create_notification_channel`. After a failure, ask the user to
  re-paste rather than echoing what they sent.
- **"How do I set up a Slack channel?" is a docs question.** Answer with the
  docs flow (the SigNoz UI's Notification Channels page) and do not solicit
  the secret in chat. Prefer the UI path when the user seems uncertain about
  exposing the token.

### Step 8: Preview the prepared config

Emit a one-paragraph plain-language summary of what will be created, with no
raw JSON dump: what fires, on what scope, at what threshold, and where it
routes. Step 6's dry-run catches query-shape errors; reading JSON does not.

> **Summary**: This alert fires when [condition] for [resource scope],
> evaluated every [frequency] over the last [window]. Severity: [tier],
> because [table row or user cue]. Thresholds:
> warning at X, critical at Y. Notifications route through [direct channels / confirmed org policy]. Dry-run on
> the last hour: N of M returned points breached.

### Step 9: Save and report

1. Call `signoz_create_alert` with the config from Step 8.
2. **Name collision**: if `signoz_create_alert` returns a duplicate-name
   error, **do not** suffix-append or call `signoz_update_alert`. Stop, tell
   the user the existing alert blocked creation, and offer a different name
   or a change to the existing alert (out of scope for this skill).
3. On success, report:
   - The alert ID and name.
   - What it watches, at what threshold, and at what severity.
   - How notifications route (direct channels or the confirmed org policy).
   - The dry-run summary ("N of M returned points breached in last 1h").

## Guardrails

- **Strict inputs over guessing** Resource attribute and notification routing
  are required. Policy routing needs a confirmed existing match.
- **Finish the duplicate check** Page the filtered `signoz_list_alert_rules`
  matches, then the unfiltered list, before concluding none exists (Step 3).
- **Dry-run is mandatory** Complete Steps 4 and 6 before
  `signoz_create_alert`; a rule on a query with no data gives false confidence.
- **Compose the full payload** SigNoz fills in almost nothing. Supply every
  field the Step 5 guide and the tool schema require, including each metrics
  query's `timeAggregation`.
- **No `limit` or `order` on persisted alert queries** They cap a grouped
  alert to its top-N series (Step 6).
- **Match `alertType` to the query signal** SigNoz evaluates the query
  whatever `alertType` says and builds the fired alert's related logs or
  traces link from it, so a mismatch saves and links to the wrong explorer.
- **Anomaly rules are metrics-only** An `anomaly_rule` takes
  `METRIC_BASED_ALERT` and a builder metrics query.
- **Routing must be confirmed.** Direct routes put exact returned
  `displayName` values in per-threshold `channels`, for every rule type.
  Confirmed policy routes set `notificationSettings.usePolicy` and omit them.
- **Never echo channel secrets.** Apply the Step 7 secret rules to every
  output, preview, and clarification payload.

## Examples

Four canonical alert flows (multi-severity metric threshold, error-rate
formula, log-volume groupBy, and anomaly detection) live in
[`references/examples.md`](references/examples.md). To author PromQL or test
a query before wrapping it in an alert, use `signoz-generating-queries`.
