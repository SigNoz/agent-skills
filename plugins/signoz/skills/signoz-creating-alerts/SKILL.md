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

Build a SigNoz alert from a user's natural-language intent. The skill targets
two consumers: an autonomous AI SRE agent that runs without a human in the
loop, and a human at a Claude Code / Codex / Cursor prompt. Both go through
the same flow — the human just gets a chance to intervene at the preview step.

## Prerequisites

This skill calls SigNoz MCP server tools (`signoz:signoz_create_alert`,
`signoz:signoz_list_alerts`, `signoz:signoz_get_field_keys`, etc.). Before running the
workflow, confirm the `signoz:signoz_*` tools are available. If they are not,
the SigNoz MCP server is not installed or configured — stop and direct
the user to set it up:
<https://signoz.io/docs/ai/signoz-mcp-server/>. Do not try to fall back
to raw HTTP calls or fabricate alert configs without the MCP tools.

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
  `signoz:signoz_update_alert` directly.

## Required inputs (strict)

Alert creation is a write operation against a shared system. Guessing here
creates noisy alerts on the wrong service that someone else has to clean up.
The skill enforces a strict input contract:

| Input | Required | Source if missing |
|---|---|---|
| Alert intent (NL goal) | yes | `$ARGUMENTS` or recent user turn |
| Resource attribute filter (e.g. `service.name`, `k8s.namespace.name`, `host.name`) | yes | discover via `signoz:signoz_get_field_keys` + `signoz:signoz_get_field_values` |
| Threshold value(s) | inferred from intent | derive a sensible default and surface in the preview |
| Severity | inferred from intent | default `warning`; promote to `critical` only if user said "page", "wake up", "critical" |
| Notification channel | yes | `signoz:signoz_list_notification_channels` + offer "create new" |

If a required input is missing and cannot be discovered, emit a structured
`needs_input` block and stop **before** calling any write tool:

```text
needs_input:
  missing:
    - resource_attribute_filter: "no service or host specified — pick one"
  candidates:
    service.name: ["frontend", "checkout", "payments", "inventory"]
    host.name: ["prod-api-1", "prod-api-2", "prod-db-1"]
```

In interactive mode, the human picks from candidates. In autonomous mode, the
caller fills the gap from upstream context or escalates. Either way, do not
proceed to `signoz:signoz_create_alert` with a guessed value.

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
discovery, emit `needs_input` and stop.

### Step 2: Discover resource attributes and metric names

When the user does not name a service / host / namespace, the SigNoz MCP
guideline applies: **always prefer a resource-attribute filter**. Discover
candidates instead of guessing:

1. Call `signoz:signoz_get_field_keys` with `fieldContext=resource` to enumerate
   resource attributes for the chosen signal.
2. Call `signoz:signoz_get_field_values` for the most likely attribute (typically
   `service.name`, then `host.name`, then `k8s.namespace.name`) to get
   concrete values.
3. If the user mentioned a metric by name, call `signoz:signoz_list_metrics` with a
   search term to verify the exact OTel metric name. Wrong names create
   alerts that never fire.

Surface the candidates in the `needs_input` block. Do not pick one.

### Step 2.5: Probe data existence for the chosen filter (fail fast)

Before authoring any alert config, confirm the **specific combination** the
alert will watch (metric × service × any other filter) actually emits data.
The most common silent failure is "metric exists in the catalog *and* the
service exists in the catalog, but the service doesn't emit that metric"
— each piece checks out in isolation, the alert saves successfully, and it
silently never fires.

Run a single probe over the last 1 hour using the same filter the alert
will use, but with the simplest aggregation that confirms data exists:

- **Metrics**: `signoz:signoz_query_metrics` (PromQL) or `signoz:signoz_execute_builder_query`
  with `count()` (or `count_distinct(service.name)` if scope-discovering).
- **Logs**: `signoz:signoz_aggregate_logs` with `count()` over the filter.
- **Traces**: `signoz:signoz_aggregate_traces` with `count()` over the filter.

Inspect the result:

- **Probe returns rows** → proceed to Step 3.
- **Probe returns empty** → STOP. Do not build an alert config the user
  will then be asked to throw away. Emit a `needs_input` block describing
  what was missing and offer concrete recovery:
  - Service doesn't emit the metric → call
    `signoz:signoz_get_field_values signal=metrics name=service.name metricName=<metric>`
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

This probe is cheap (one query, ~100ms), and catching the no-data case
early avoids the worst UX failure mode of this skill — the user reading
through a fully-authored JSON payload and only then learning the alert
can never fire.

### Step 3: Check for duplicate alerts

Call `signoz:signoz_list_alerts` and **paginate through every page** —
`pagination.hasMore` is true until you have walked the full list. Check for
existing alerts that match the user's intent (same signal + same scope +
similar threshold). If a likely duplicate exists, surface it and ask whether
to create a new one anyway, modify the existing one (out of scope here — use
`signoz:signoz_update_alert`), or cancel.

### Step 4: Build the alert config

The MCP server is the source of truth for the alert JSON schema, threshold
codes, and validation rules. Read the `signoz://alert/instructions` and
`signoz://alert/examples` MCP resources for the canonical, version-current
shape. Do not transcribe schema text into this skill — it will rot out of
sync with the server.

For most user intents, the config is one of a small number of patterns:

| Pattern | Where to author | Example intents |
|---|---|---|
| Single-metric threshold | inline (this skill) | "alert when CPU > 80%", "p99 latency > 2s" |
| Log volume threshold | inline | "more than N error logs/min" |
| Trace-based count or p-tile | inline | "p99 span duration > 2s on checkout" |
| Error-rate formula (A/B*100) | inline (see "Common query shapes" below) | "error rate > 5%" |
| Anomaly detection (Z-score) | inline, but only with `METRIC_BASED_ALERT` | "alert me on anomalous traffic" |
| Absent-data alert | inline | "alert if data stops arriving" |
| ClickHouse SQL alert | inline (this skill) — author the SQL directly using the schema in `signoz://alert/examples` | non-trivial joins, custom aggregations the builder cannot express |
| PromQL alert | delegate to `signoz-generating-queries` for the PromQL, then return here | when user already has PromQL |

**Threshold `op` and `matchType` values.** v2alpha1 accepts the
human-readable strings (`"above"`, `"on_average"`); the legacy numeric
codes (`"1"`, `"3"`) are also accepted but harder to read in the UI. Prefer
the words. **Anomaly rules only support `op: "above"`** — the engine
already treats z-score breaches as two-sided when the threshold is
positive, so `"above_or_below"` is rejected and unnecessary.

| Comparison | `op` | Evaluation behavior | `matchType` |
|---|---|---|---|
| above / exceeds / > | `"above"` | breach at any point | `"at_least_once"` |
| below / under / < | `"below"` | breach for entire window | `"all_the_times"` |
| equal / = | `"equals"` | average breaches | `"on_average"` |
| not equal / != | `"not_equals"` | sum breaches | `"in_total"` |
|  |  | last value breaches | `"last"` |

**Defaults the skill applies (and surfaces in the preview):**
- `evalWindow: 5m0s`, `frequency: 1m0s` — change only if the intent implies
  a slower or faster cadence.
- `matchType: "3"` (on_average) for CPU / memory / latency — smooths
  transient spikes.
- `matchType: "1"` (at_least_once) for error counts / error rates — catches
  any breach.

**Severity defaults — derive from the intrinsic urgency of the alert, not
just the user's words.** The user saying "alert me" doesn't force `warning`
when the condition itself describes a critical event. Use this table; an
explicit user cue overrides it ("just FYI" → demote, "page me" / "wake me
up" → promote).

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

**OTel attribute names** — always use semantic conventions:
`service.name`, `host.name`, `k8s.namespace.name`,
`deployment.environment.name`. Never `service`, `host`, or `env`.

**Annotation templates** — the on-call engineer sees the notification, not
the alert config. A notification that says "Pod crash detected" with no
service name, no count, and no value is nearly useless at 3am. Always
include the moving values:

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

#### Common query shapes

Three patterns cover most non-trivial alerts. The MCP resources above carry
the full schema; these are quick references for the query block only.

**Error rate** — two queries + formula `A * 100 / B`. **Set
`disabled: true` on the component queries A and B** so only the formula
F1 renders in the alert chart and notification — the raw counts are
intermediate, not the alert signal. Forgetting this clutters the alert
preview with three series and confuses the on-call engineer reading the
notification.

```json
{
  "queries": [
    { "type": "builder_query", "spec": { "name": "A", "signal": "traces",
        "disabled": true,
        "aggregations": [{ "expression": "count()" }],
        "filter": { "expression": "hasError = true" } } },
    { "type": "builder_query", "spec": { "name": "B", "signal": "traces",
        "disabled": true,
        "aggregations": [{ "expression": "count()" }],
        "filter": { "expression": "" } } },
    { "type": "builder_formula",
      "spec": { "name": "F1", "expression": "A * 100 / B" } }
  ],
  "selectedQueryName": "F1"
}
```

**p99 latency** — single trace query with `groupBy` for per-service
breakdown. Threshold target is in **nanoseconds** (2s → 2000000000),
`targetUnit: "ns"`:

```json
{
  "queries": [
    { "type": "builder_query", "spec": { "name": "A", "signal": "traces",
        "aggregations": [{ "expression": "p99(durationNano)" }],
        "groupBy": [{ "name": "service.name", "fieldContext": "resource",
                      "fieldDataType": "string" }] } }
  ]
}
```

**Log volume spike** — count of error/fatal logs grouped by service:

```json
{
  "queries": [
    { "type": "builder_query", "spec": { "name": "A", "signal": "logs",
        "aggregations": [{ "expression": "count()" }],
        "filter": { "expression": "severity_text IN ('ERROR', 'FATAL')" },
        "groupBy": [{ "name": "service.name", "fieldContext": "resource",
                      "fieldDataType": "string" }] } }
  ]
}
```

For absent-data, anomaly, PromQL, and ClickHouse SQL alerts, read the
`signoz://alert/examples` MCP resource for current shapes.

### Step 5: Resolve notification channels

The skill **must** resolve at least one channel before save. An alert with no
channels saves successfully and silently never notifies anyone — the second
most common silent failure after bad queries.

1. Call `signoz:signoz_list_notification_channels` to enumerate existing channels.
2. If the user named a channel ("send to slack-infra"), use it if it exists;
   if not, fall through.
3. Otherwise present the user with two options:
   - **Pick from existing** — list channels with their type (Slack, PagerDuty,
     email, webhook) so the user can choose.
   - **Create new inline** — call `signoz:signoz_create_notification_channel` with
     channel parameters the user provides (name, type, type-specific config
     like Slack webhook URL or PagerDuty integration key).
4. If neither path resolves a channel, emit
   `needs_input: notification_channel` and stop.

For multi-severity alerts, attach channels per threshold:
`thresholds.spec[N].channels` is an array — typically warning → Slack only,
critical → Slack + PagerDuty.

### Step 6: Validate the threshold (would-have-fired count)

Step 2.5 already confirmed the underlying data exists. Step 6 is about
the *threshold* — given the full proposed query (including formulas,
groupBy, and unit conversions) and the proposed threshold, would this
alert have fired a sensible number of times in the last hour?

1. Run the alert's full primary query (or formula) over the last hour using:
   - `signoz:signoz_execute_builder_query` for builder/formula queries.
   - `signoz:signoz_query_metrics` for PromQL queries.
   - `signoz:signoz_aggregate_logs` / `signoz:signoz_aggregate_traces` if those fit better.
2. Compute how many evaluation points in the last hour breached the
   proposed threshold. Surface this in the preview as
   **"would have fired N times in the last 1h"**:
   - **N = 0** → the threshold may be too loose or the gating too strict.
     Mention this so the user can adjust if intent was tighter.
   - **N is large (e.g. > 30)** → likely alert storm. Surface and
     recommend tightening or adding hysteresis (`recoveryTarget`).
   - **N is small and non-zero** → calibrated; proceed.
3. **Exceptions:**
   - **Anomaly alerts** — skip the breach count entirely (Z-scores aren't
     directly comparable to raw values). Step 2.5 already verified the
     underlying metric × service has data; nothing more to validate here.
   - **Log-based crash / panic / OOMKilled / FATAL alerts** — these
     intentionally have zero matches in a healthy system. Step 2.5 has
     already surfaced the zero-match result and obtained user confirmation;
     skip the breach count.

If Step 2.5 was somehow skipped (e.g. a downstream skill is invoking this
flow mid-stream), the no-data stop rule applies here too: empty result →
emit `needs_input` instead of saving an alert that will never fire.

### Step 7: Preview the prepared config

Emit a fenced JSON code block containing the exact payload that will be sent
to `signoz:signoz_create_alert`, plus a one-paragraph plain-language summary:

```json
{
  "alert": "<name>",
  "alertType": "...",
  "ruleType": "...",
  "condition": { ... },
  "labels": { "severity": "..." },
  "annotations": { "description": "...", "summary": "..." },
  "evaluation": { ... },
  "preferredChannels": ["..."]
}
```

> **Summary**: This alert fires when [condition] for [resource scope],
> evaluated every [frequency] over the last [window]. Thresholds:
> warning at X, critical at Y. Notifications go to [channels]. Dry-run on
> the last hour: would have fired N times.

In autonomous mode the consumer proceeds. In interactive mode the human can
intervene before Step 8.

### Step 8: Save and report

1. Call `signoz:signoz_create_alert` with the JSON payload from Step 7.
2. **Name collision** — if `signoz:signoz_create_alert` returns a duplicate-name
   error, **do not** suffix-append or call `signoz:signoz_update_alert`. Stop and
   tell the user the existing alert blocked creation; offer to use a
   different name or modify the existing alert (which is out of scope for
   this skill).
3. On success, report:
   - The alert ID and name.
   - What it watches and at what threshold.
   - Which channels are wired up.
   - The dry-run summary ("would have fired N times in last 1h").
   - Two follow-up offers: "Want to test the query live with `signoz-generating-queries`?"
     and "Want me to add a runbook URL to the annotations?"

## Guardrails

- **Strict inputs over guessing.** Resource attribute and channel are
  required. If missing, emit `needs_input` and stop. Creating an alert on
  a guessed service is harder to undo than asking.
- **Always paginate `signoz:signoz_list_alerts`.** Stopping at page 1 misses
  duplicates and produces noise.
- **Dry-run is mandatory.** Saving an alert whose query returns no data is
  a silent failure mode and must be prevented.
- **No duplicate updates.** Name collision → error and stop. Do not
  silently update an existing alert from a "create" skill.
- **OTel attribute names only.** `service.name` not `service`.
- **Threshold codes are strings, not words.** `op: "1"` not `op: "above"`.
- **Signal must match alertType.** `signal: "logs"` requires
  `LOGS_BASED_ALERT`. Mismatches fail validation.
- **Anomaly rules are metrics-only.** `anomaly_rule` + non-metric alertType
  is rejected.
- **Channels must exist.** Use names from `signoz:signoz_list_notification_channels`
  exactly, or create the channel inline first.
- **Scope boundary.** This skill only creates new rules. Modifications use
  `signoz:signoz_update_alert` directly.

## Examples

**User:** "Alert me when CPU usage on the checkout service goes above 80%, page me at 90%"

**Agent:**
1. Intent parsed: metric, CPU, scope `service.name = checkout`,
   thresholds 80% (warning) / 90% (critical), severity bumped to critical
   on the higher level because "page me" was used.
2. `signoz:signoz_list_metrics searchText=cpu` → confirms `system.cpu.utilization`.
3. `signoz:signoz_list_alerts` (paginated) → no existing CPU alert for checkout.
4. `signoz:signoz_list_notification_channels` → presents existing channels;
   user picks `slack-infra` for warning and `pagerduty-oncall` for critical.
5. Builds JSON: `METRIC_BASED_ALERT`, `threshold_rule`,
   `signal=metrics`, two thresholds (`op="1"`, `matchType="3"` on_average,
   `targetUnit="percent"`), filter `service.name = 'checkout'`.
6. Dry-run via `signoz:signoz_execute_builder_query` over last 1h: returns data,
   would have fired 0 times (clean baseline).
7. Emits JSON preview + summary.
8. Calls `signoz:signoz_create_alert`. Reports created alert with ID, threshold
   summary, channel routing, and dry-run result.

---

**User:** "Set up an alert when error rate goes above 5% on payments"

**Agent:**
1. Intent parsed: traces, error-rate formula, scope
   `service.name = payments`, threshold 5%, severity default warning.
2. `signoz:signoz_get_field_keys fieldContext=resource signal=traces` confirms
   `service.name`. `signoz:signoz_get_field_values` confirms `payments` exists.
3. No existing payments error-rate alert.
4. Builds formula alert: query A counts spans with `hasError = true` for
   `service.name = 'payments'`, query B counts all spans for the same
   service, formula F1 = `A * 100 / B`, `selectedQueryName: "F1"`,
   threshold target 5, `targetUnit: "percent"`, `op: "1"`, `matchType: "1"`
   (catch any breach).
5. Channel: user picks `slack-payments`.
6. Dry-run on last 1h: payments error rate hovered around 0.3%, would have
   fired 0 times. Clean — not too tight.
7. Preview, save, report.

---

**User:** "Notify me if log volume spikes more than 1000 error logs per minute on any service"

**Agent:**
1. Intent parsed: logs, volume threshold, scope = all services (groupBy
   `service.name`), threshold 1000/min, severity warning.
2. `signoz:signoz_get_field_keys signal=logs fieldContext=resource` confirms
   `service.name` exists; **no service filter required** since the user
   said "any service" → groupBy provides the scoping.
3. Builds: `LOGS_BASED_ALERT`, `signal=logs`,
   `aggregations: [{expression: "count()"}]`,
   `filter: {expression: "severity_text IN ('ERROR', 'FATAL')"}`,
   `groupBy: [{name: "service.name", fieldContext: "resource", fieldDataType: "string"}]`,
   threshold 1000, `targetUnit: ""`, `evalWindow: 1m0s`,
   `matchType: "1"` (catch any minute that breaches).
4. Channels: user picks slack channel.
5. Dry-run: returned per-service counts, max in last 1h was 87 — would
   have fired 0 times. Within reasonable headroom.
6. Preview, save, report.

---

**User:** "Alert me on anomalous request latency for the api gateway"

**Agent:**
1. Intent parsed: metric, anomaly detection, scope
   `service.name = api-gateway`. Anomaly detection requires
   `METRIC_BASED_ALERT` + `anomaly_rule`.
2. `signoz:signoz_list_metrics searchText=duration` → finds
   `http.server.request.duration`.
3. Builds: `anomaly_rule`, `algorithm=zscore`, `seasonality=daily`,
   threshold target 3 (3 standard deviations), `op: "1"`, `matchType: "1"`.
4. Channel: user picks slack-api.
5. Dry-run validates query returns data. Skip breach-count for
   anomaly alerts.
6. Preview emphasizes that the threshold is in standard deviations, not raw
   latency. Save, report.

## Additional resources

- `signoz://alert/instructions` and `signoz://alert/examples` MCP resources
  — full alert config JSON schema, threshold codes, filter expression
  syntax, and version-current pattern examples. Always preferred over any
  transcribed copy.
- `signoz-generating-queries` skill — for authoring PromQL or testing queries
  before wrapping them in an alert.
