---
name: signoz-creating-alerts
description: >
  Create a new SigNoz alert rule from a natural-language intent — threshold,
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
| Threshold value(s) | inferred from intent | derive a sensible default and surface in the preview |
| Severity | inferred from intent | default `warning`; promote to `critical` only if user said "page", "wake up", "critical" |
| Notification channel | yes | `signoz_list_notification_channels` + offer "create new" |

If a required input is missing and undiscoverable, **stop before any write**
and ask through the host's supported clarification UI.

What to include in the question:

- **What is missing** — name it concretely (e.g. "which resource-attribute
  filter to use").
- **Candidate lists** from discovery — concrete values per attribute, e.g.:
  `service.name` → `frontend`, `checkout`, `payments`;
  `host.name` → `prod-api-1`, `prod-db-1`.
- **Free-form input** so the user can name an unsurfaced value.

In autonomous mode, escalate or use upstream context; never call
`signoz_create_alert` with a guessed value.

## Workflow

### Step 1: Parse intent and check what's missing

Extract from the user's request:
1. **What to monitor** — signal type (metrics / logs / traces / exceptions)
   and the specific condition (CPU, error rate, p99 latency, log count, ...).
2. **Resource scope** — which service, host, namespace, or environment.
3. **Threshold** — numeric value and comparison ("above 80%", "below 100/s").
4. **Severity** — implicit from urgency words ("page" → critical, default
   warning otherwise).
5. **Channel** — explicit channel name if the user provided one.

Map signal phrasing to alert type:

| User says | alertType | signal |
|---|---|---|
| metric, CPU, memory, latency, request rate | METRIC_BASED_ALERT | metrics |
| log, error logs, log volume, log pattern | LOGS_BASED_ALERT | logs |
| trace, span, latency p99, slow requests | TRACES_BASED_ALERT | traces |
| exception, stack trace, crash | EXCEPTIONS_BASED_ALERT | (clickhouse_sql) |

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
   search term to verify the exact OTel metric name. Wrong names create
   alerts that never fire.

Surface the candidates in your clarification request (see *Required
inputs* above). Do not pick one.

### Step 3: Check for duplicate alerts

Once the scope is resolved (either provided by the user or discovered in
Step 2), check for existing alerts before probing data or authoring a
new config — both are wasted work if the user wants to update an
existing rule instead.

Call `signoz_list_alert_rules` and **paginate through every page** —
`pagination.hasMore` is true until you have walked the full list. This lists
*configured* alert rules (the durable state); do not use `signoz_list_alerts`,
which returns currently triggered/active alert instances and will silently
miss rules that are configured but not firing right now. Check for existing
rules that match the user's intent (same signal + same scope + similar
threshold). If a likely duplicate exists, surface it and ask whether to
create a new one anyway, modify the existing one (out of scope here — use
`signoz_update_alert`), or cancel.

### Step 4: Probe data existence for the chosen filter (fail fast)

Before authoring any alert config, confirm the **specific combination** the
alert will watch (metric × service × any other filter) actually emits data.
The most common silent failure is "metric exists in the catalog *and* the
service exists in the catalog, but the service doesn't emit that metric"
— each piece checks out in isolation, the alert saves successfully, and it
silently never fires.

Run a single probe over the last 1 hour using the same filter the alert
will use, but with the simplest aggregation that confirms data exists:

- **Metrics**: use `signoz_query_metrics` with the concrete `metricName` and
  the alert's `filter`; it auto-applies aggregation defaults. If the full v5
  tool is necessary, use a metrics aggregation object containing
  `metricName`, `timeAggregation`, and `spaceAggregation`. Metrics do **not**
  accept expression aggregations such as `count()` or filter-only probes.
- **Logs**: call `signoz_aggregate_logs` with `aggregation: "count"` and the
  alert filter. `count()` is a Query Builder expression, not a helper-tool
  argument.
- **Traces**: call `signoz_aggregate_traces` with `aggregation: "count"` and
  the alert filter. Do not pass `aggregation: "count()"`.

Inspect the result:

- **Probe returns rows** → proceed to Step 5.
- **Probe returns empty** → STOP. Do not build an alert config the user
  will then be asked to throw away. Stop and ask the user (see *Required
  inputs* above), describing what was missing and offering concrete
  recovery:
  - Service doesn't emit the metric → call
    `signoz_get_field_values signal=metrics name=service.name metricName=<metric>`
    to list the services that *do* emit it; let the user pick a different
    service or a different metric.
  - Wrong attribute name (`service` instead of `service.name`) → suggest
    the semantic-convention name and re-probe.
  - Service emits the metric but not in the expected time range → widen
    the probe window once (e.g. last 24h) before declaring no-data.

**Exception — log-based crash / panic / OOMKilled / FATAL alerts.** These
intentionally have zero matches in a healthy system. The probe will
return empty by design. Do not stop; instead, surface the zero-match
result and ask the user to confirm before save. Treat this exception
narrowly: it applies to "alert me when bad thing happens" log queries,
not to alerts that depend on continuous data flow.

This cheap probe catches no-data before the user reviews an alert that cannot
fire.

### Step 5: Build the alert config

The MCP server is the source of truth for the alert JSON schema, threshold
codes, and validation rules. Read the `signoz://alert/instructions` and
`signoz://alert/examples` MCP resources for the canonical, version-current
shape.

Threshold/PromQL `condition.thresholds` requires `kind` (use `"basic"`) and
non-empty `spec[]`, except when `alertOnAbsent` is the sole trigger. Anomaly
rules omit it.

For most user intents, the config is one of a small number of patterns:

| Pattern | Example intents |
|---|---|
| Single-metric threshold | "alert when CPU > 80%", "p99 latency > 2s" |
| Log volume threshold | "more than N error logs/min" |
| Trace-based count or p-tile | "p99 span duration > 2s on checkout" |
| Error-rate formula (A/B*100) — see "Common query shapes" below | "error rate > 5%" |
| Anomaly detection (Z-score) | "alert me on anomalous traffic" |
| Absent-data alert | "alert if data stops arriving" |
| ClickHouse SQL alert — author SQL using the schema in `signoz://alert/examples` | non-trivial joins, custom aggregations the builder cannot express |
| PromQL alert — delegate to `signoz-generating-queries` for the query, then return here | when user already has PromQL |

**Threshold `op` and `matchType` values.** Prefer readable words; symbols and
legacy numeric codes are accepted but discouraged. Valid `op` words are
`above`, `below`, `equal`, `not_equal`,
`above_or_equal`, `below_or_equal`, and `outside_bounds`; `equals` is invalid.
Use `above` for anomaly rules: their absolute score covers spikes and drops.

| Comparison | `op` | Evaluation behavior | `matchType` |
|---|---|---|---|
| above / exceeds / > | `"above"` | breach at any point | `"at_least_once"` |
| below / under / < | `"below"` | breach for entire window | `"all_the_times"` |
| equal / = | `"equal"` | average breaches | `"on_average"` |
| not equal / != | `"not_equal"` | sum breaches | `"in_total"` |
|  |  | last value breaches | `"last"` |

**Defaults the skill applies (and surfaces in the preview):**
- `evalWindow: 5m0s`, `frequency: 1m0s` — change only if the intent implies
  a slower or faster cadence.
- `matchType: "on_average"` for CPU / memory / latency — smooths
  transient spikes.
- `matchType: "at_least_once"` for error counts / error rates —
  catches any breach.

**Severity defaults — derive intrinsic urgency, not just wording.** An explicit
cue overrides this table ("just FYI" → demote; "page me" → promote).

| Alert intent | Default severity |
|---|---|
| Pod crash / OOMKilled / CrashLoopBackOff / panic / FATAL log signals | critical |
| Service down / no-data on a production service | critical |
| Error rate above any non-trivial threshold (>1%) | critical |
| Error logs / exception spikes | warning |
| Latency degradation (p95/p99 above target) | warning |
| CPU / memory / disk pressure | warning |
| Request-rate / traffic anomaly | warning |
| SLO budget burn (info-level burn rate) | info / warning |

When the user's intent is ambiguous on severity (no urgency cue, no
clearly-critical condition), default to `warning` and surface the choice
in the preview so they can adjust.

**Attribute names** — use exact keys returned by `signoz_get_field_keys`; when
available they are usually OTel names such as `service.name`, not `service`.

**Annotation templates** — include moving values; on-call sees the notification,
not the config:

- `summary` — single-line headline. Include the resource scope and the
  numeric value: `"checkoutservice error rate {{$value}}% above 3%"`.
- `description` — longer message. Include `{{$value}}`, `{{$threshold}}`,
  the groupBy values (e.g. `{{$labels.service_name}}`), and a sentence on
  what to do or where to look. For count-based alerts include the count
  explicitly: `"{{$value}} crash log lines in the last 5 minutes from
  service {{$labels.service_name}}"`.

Use `{{$value}}` for the breaching value, `{{$threshold}}` for the target,
and `{{$labels.<key>}}` for groupBy values (note SigNoz substitutes the
dotted attribute name with underscores: `service.name` → `service_name`).

#### Common query shapes — conventions

Read `signoz://alert/examples` for the authoritative JSON of all
patterns (error rate, p99 latency, log volume, absent-data, anomaly,
PromQL, ClickHouse SQL). The conventions that don't live in the
schema:

- **Error-rate formula:** set `disabled: true` on the component
  queries A and B so only the formula F1 renders in the alert chart
  and notification. The raw counts are intermediate, not the alert
  signal — forgetting this clutters the preview with three series and
  confuses the on-call engineer reading the notification.
- **p99 latency:** the query emits nanoseconds, but express the threshold in
  the user's unit (for example `target: 2`, `targetUnit: "s"`); SigNoz converts
  it during evaluation.
- **Low-traffic percentile guard:** put `count() > N` in the percentile
  query's `having.expression` and set `stepInterval` to the requested bucket
  size (for example, `60` for “per minute”). Do not invent comparison operators
  inside a formula such as `A * (B >= N)`.
- **Log volume spike:** prefer `groupBy: service.name` over a hard
  filter when the user said "any service" — groupBy provides the
  scoping AND keeps the notification useful per-service.

### Step 6: Dry-run the full query and validate the threshold

Step 4 confirmed data flows. Step 6 does two things:

1. **Validate query shape.** Run the full builder spec (with
   `groupBy`, formulas, disabled component queries, and non-string
   filters) — Step 4's bare `count()` probe doesn't exercise these.
   The create-alert schema accepts queries that error at evaluation
   (numeric `groupBy`, unquoted bool filter, mismatched aggregation).
   Any HTTP 5xx or "filter type mismatch" = fix the config before
   proceeding to (2). `disabled: true` on formula component queries
   (A, B in `A * 100 / B`) is the *recommended* pattern, not a failure
   — see Step 5.
2. **Calibrate the threshold.** Given the validated query, would the
   alert have fired a sensible number of times in the last hour?

Run the full primary query (or formula) over the last hour:
- `signoz_execute_builder_query` for **all** builder, formula,
  and PromQL queries — set `compositeQuery.queries[].type` to
  `builder_query` / `builder_formula` / `promql` as appropriate. Alert PromQL
  specs carry only `name` / `query` / `legend` / `disabled`; dry-run execution
  PromQL specs may also carry `step` / `stats`. Still omit builder-only
  `stepInterval`.
  Put the string in `spec.query`, read
  `signoz://promql/instructions` for the UTF-8 quoted-selector form
  SigNoz requires (`{"metric.name.with.dots"}` — not the underscored
  or bare-dotted forms), and keep alert PromQL fully literal: no `$var`,
  `$__rate_interval`, or other dashboard variable is evaluated.
- Alert specs omit time bounds, but this dry-run cannot: set outer-query
  `start` / `end` to absolute JSON integer Unix-ms (e.g. now−3600000 → now),
  or `signoz_execute_builder_query` fails with `missing start or end timestamp`.
- For intent grouped by a dimension, each execution `groupBy[].name` is the
  exact Step 2 key (e.g. `k8s.pod.name`), never empty. Omit `groupBy` otherwise.
- `signoz_aggregate_logs` / `signoz_aggregate_traces`
  when those fit better.
- `signoz_query_metrics` when the alert query targets a single
  known metric by `metricName` — the tool auto-applies aggregation
  defaults and accepts `filter`, `groupBy`, and `formula` alongside.
  PromQL is not supported here; use `signoz_execute_builder_query`
  for that.

For every persisted alert and dry-run, each `builder_query` and
`builder_formula` spec must include a positive `limit` plus a non-empty Query
Builder v5 `order`. Standalone queries and formula results use `limit: 100`.
Every `builder_query` referenced by a formula uses `limit: 10000`, because
SigNoz limits each component before formula evaluation; independently ranking
the top 100 numerator and denominator groups can silently prevent an alert from
firing. Find those inputs from every formula expression, including formulas
with `disabled: true`, following formula references until all `builder_query`
leaves are found. This dependency walk determines bounds only; it does not
guarantee formula-to-formula evaluation order, so dry-run the complete composite
payload. Use `__result desc` for metrics/formulas and the primary aggregation
desc for logs/traces. This field is `order`, not dashboard editor `orderBy`.
Preserve the fields when copying the validated query into the alert. If expected
formula-input cardinality can exceed 10000, narrow the filters/grouping and tell
the user completeness cannot otherwise be guaranteed.

Compute how many evaluation points breached the proposed threshold.
Surface in the preview as **"would have fired N times in the last 1h"**.
A 1h window is too short to grade most alerts — only the upper extreme
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
   - **Anomaly alerts** — execute the underlying metric query without the
     anomaly `functions` transform to verify its shape and data, then skip the
     breach count (Z-scores aren't directly comparable to raw values). Be
     explicit that this validates the base query, not anomaly scoring.
   - **Log-based crash / panic / OOMKilled / FATAL alerts** — these
     intentionally have zero matches in a healthy system. Step 4 has
     already surfaced the zero-match result and obtained user confirmation;
     skip the breach count.

If Step 4 was somehow skipped (e.g. a downstream skill is invoking this
flow mid-stream), the no-data stop rule applies here too: empty result →
stop and ask the user (see *Required inputs* above) instead of saving an
alert that will never fire.

### Step 7: Resolve notification channels

Resolve at least one channel after dry-run and final severity; otherwise the
alert saves but never notifies.

1. Call `signoz_list_notification_channels` and follow
   `pagination.nextOffset` while `pagination.hasMore` is true.
2. If the user named a channel ("send to slack-infra"), use it if it exists;
   if not, fall through.
3. Otherwise present the user with two options:
   - **Pick from existing** — list channels with their type (Slack, PagerDuty,
     email, webhook) so the user can choose.
   - **Create new inline** — call `signoz_create_notification_channel` with
     channel parameters the user provides (name, type, type-specific config
     like Slack webhook URL or PagerDuty integration key).
4. If neither path resolves a channel, stop and ask the user for a
   notification channel (see *Required inputs* above).

Channel creation is admin-gated. On `PERMISSION_DENIED`, have an admin create it
out of band or configure a dedicated, short-lived minimum-role credential via
the host's environment/secret store; never request an elevated key in chat or
tracked config.

Place the resolved channel according to the rule schema:

- `threshold_rule` / `promql_rule` (v2alpha1): attach direct-routing channels
  to each `condition.thresholds.spec[N].channels` array — typically warning →
  Slack only, critical → Slack + PagerDuty. When `alertOnAbsent` is the sole
  trigger and thresholds are omitted, put fallback channels in top-level
  `preferredChannels`.
- `anomaly_rule` (v1): thresholds are forbidden, so put channel names in the
  top-level `preferredChannels` array.

Never put a chosen anomaly or absent-only channel in a nonexistent thresholds
block, or substitute `preferredChannels` for per-tier multi-severity routing.

#### Handling secret-bearing channel config

Slack webhook URLs, PagerDuty integration keys, and similar webhook tokens
are secrets. When the user supplies them inline, treat them as opaque
inputs and follow these rules:

- **Do not echo the secret back.** Never include the webhook URL,
  integration key, or any password-like token in chat output, previews,
  confirmation messages, summaries, or the `<navigation_suggestions>`
  payload. Refer to the channel by its `name` only ("Slack channel
  `slack-infra` created") and omit the value entirely.
- **Do not stash secrets in clarification context.** If you need to ask the
  user a follow-up question after they pasted a secret, do not include
  the secret value in the clarification `message`, `discovered_context`,
  or any other field that the host may persist for resume. Refer to it
  symbolically (e.g. "the webhook you just provided").
- **One-pass only.** Pass the secret directly to
  `signoz_create_notification_channel` and do not retain it in any
  intermediate prose. After the create call succeeds, refer to the
  channel by name; after a failure, ask the user to re-paste rather than
  echoing what they sent.
- **If the user instead asks "how do I set up a Slack channel?"** — that
  is a docs question, not a create-channel request. Answer with the docs
  flow (the SigNoz UI's Notification Channels page) and do not solicit
  the secret in chat at all. Prefer the UI path when the user seems
  uncertain about exposing the token.

### Step 8: Preview the prepared config

Emit a one-paragraph plain-language summary of what will be created —
no raw JSON dump. The user-facing facts (what fires, on what scope, at
what threshold, where it routes) are captured by the summary; clicking
through the JSON does not catch query-shape errors (Step 6's dry-run
does).

> **Summary**: This alert fires when [condition] for [resource scope],
> evaluated every [frequency] over the last [window]. Thresholds:
> warning at X, critical at Y. Notifications go to [channels]. Dry-run on
> the last hour: would have fired N times.

### Step 9: Save and report

1. Call `signoz_create_alert` with the config from Step 8.
2. **Name collision** — if `signoz_create_alert` returns a duplicate-name
   error, **do not** suffix-append or call `signoz_update_alert`. Stop and
   tell the user the existing alert blocked creation; offer to use a
   different name or modify the existing alert (which is out of scope for
   this skill).
3. On success, report:
   - The alert ID and name.
   - What it watches and at what threshold.
   - Which channels are wired up.
   - The dry-run summary ("would have fired N times in last 1h").

## Guardrails

- **Strict inputs over guessing** Resource attribute and channel are required;
  if missing, stop and ask rather than guessing a service.
- **Always paginate `signoz_list_alert_rules`** Stopping at page 1 misses
  duplicates and produces noise.
- **Dry-run is mandatory** Complete Steps 4 and 6 before
  `signoz_create_alert`; a never-firing alert creates false confidence.
- **Threshold operators use canonical words** Prefer valid words, never
  `equals`. Numeric codes (`"1"`–`"7"`)
  are accepted but discouraged — same goes for `matchType`
  (`"on_average"` / `"at_least_once"`, not `"3"` / `"1"`).
- **Signal must match alertType** `signal: "logs"` requires
  `LOGS_BASED_ALERT`. Mismatches fail validation.
- **Anomaly rules are metrics-only** `anomaly_rule` + non-metric alertType
  is rejected.
- **Channels must exist and use the rule's routing field.** Use exact names
  from `signoz_list_notification_channels`; put them in per-threshold
  `channels` for threshold/PromQL rules, or top-level `preferredChannels` for
  anomaly and absent-only threshold/PromQL rules without thresholds.
- **Never echo channel secrets.** Slack webhook URLs, PagerDuty integration
  keys, and similar webhook tokens are secrets. Pass them to
  `signoz_create_notification_channel` once and never repeat the
  value in chat output, previews, confirmations, summaries, clarification
  payloads, or navigation suggestions. Refer to the channel by name only
  after creation; ask the user to re-paste on failure rather than
  reproducing what they sent.

## Examples

Four canonical alert flows — multi-severity metric threshold,
error-rate formula, log-volume groupBy, anomaly detection — live in
[`references/examples.md`](references/examples.md).

## Additional resources

- `signoz://alert/instructions` and `signoz://alert/examples` MCP resources
  — full alert config JSON schema, threshold codes, filter expression
  syntax, and version-current pattern examples. Always preferred over any
  transcribed copy.
- `signoz-generating-queries` skill — for authoring PromQL or testing queries
  before wrapping them in an alert.
