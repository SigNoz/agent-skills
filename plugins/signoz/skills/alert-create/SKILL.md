---
name: alert-create
description: >
  Trigger when the user wants to create a new alert rule, set up monitoring
  alerts, or get notified about threshold breaches. Includes requests like
  "alert me when error rate exceeds 5%", "create an alert for high latency",
  "set up a notification when CPU usage is high", "monitor my service for
  errors", "notify me if log volume spikes".
---

# Alert Create

## When to use

Use this skill when the user asks to:
- Create, set up, or configure a new alert rule
- Get alerted or notified when a metric crosses a threshold
- Monitor a signal (metrics, logs, traces) for anomalies or threshold breaches
- "Alert me when...", "Notify me if...", "Set up monitoring for..."

Do NOT use when:
- User wants to modify an existing alert → `alert_modify`
- User wants to understand what an alert monitors → `alert-explain-what`
- User wants to check alert status or history → use `signoz_list_alerts` /
  `signoz_get_alert_history` directly
- User wants to create a dashboard → `dashboard-create`
- User wants to query data without alerting → `query-generate`

## Instructions

### Step 1: Check for duplicate alerts

Call `signoz_list_alerts` to see what alert rules already exist. **Paginate
through all pages** — check `pagination.hasMore` in the response. If `hasMore`
is true, call again with `offset` set to `pagination.nextOffset` and repeat
until all pages are exhausted. Only after checking every page can you conclude
no similar alert exists.

If a similar alert exists, tell the user and offer to create a new one anyway
or modify the existing one instead.

### Step 2: Determine the alert parameters

Extract from the user's natural language request:

1. **What to monitor** — the signal and condition:
   - Metric (CPU, memory, latency, request rate, error rate)
   - Log pattern (error count, specific log messages)
   - Trace behavior (latency percentiles, error spans)
2. **Threshold** — when to fire:
   - The numeric value and comparison (above 80%, below 100 req/s)
   - Whether to use multiple severity levels (warning + critical)
3. **Scope** — what to filter on:
   - Service name, environment, host, namespace
   - Specific attributes or patterns
4. **Notification** — where to send:
   - Notification channels (Slack, PagerDuty, email)

If the user's request is vague on any critical parameter, ask for clarification.
At minimum you need: what signal to monitor, what threshold triggers the alert,
and what severity.

### Step 3: Discover available data

Before building the alert rule JSON:

- If the user mentions a metric name you're unsure about, call
  `signoz_list_metrics` to verify the exact metric name.
- If the user mentions attributes for filters or groupBy, call
  `signoz_get_field_keys` to discover available fields.
- If the user mentions a specific service or host, call
  `signoz_get_field_values` to verify the exact value.

### Step 4: Build the alert rule JSON

Read `schema-reference.md` in this skill directory for the complete alert rule
JSON structure, field descriptions, and validation rules.

**Map the user's request to alert configuration:**

| User says | alertType | signal |
|-----------|-----------|--------|
| metric, CPU, memory, latency, request rate | METRIC_BASED_ALERT | metrics |
| log, error logs, log volume, log pattern | LOGS_BASED_ALERT | logs |
| trace, span, latency p99, slow requests | TRACES_BASED_ALERT | traces |
| exception, stack trace, crash | EXCEPTIONS_BASED_ALERT | (clickhouse_sql) |

**Map the comparison to threshold codes:**

| User says | op code |
|-----------|---------|
| above, exceeds, greater than, more than, over | "1" (above) |
| below, drops below, less than, under | "2" (below) |
| equals, exactly | "3" (equal) |
| not equal, differs from | "4" (not_equal) |

**Map the evaluation window to matchType:**

| User says | matchType code |
|-----------|----------------|
| at least once, any time (default) | "1" (at_least_once) |
| consistently, all the time | "2" (all_the_times) |
| on average | "3" (on_average) |
| in total, cumulative | "4" (in_total) |
| last value, most recent | "5" (last) |

**Build the JSON following these rules:**
- Use `ruleType: "threshold_rule"` for static thresholds (most common)
- Use `ruleType: "promql_rule"` only if the user provides a PromQL expression
- Use `ruleType: "anomaly_rule"` only if the user explicitly asks for anomaly
  detection (requires METRIC_BASED_ALERT)
- For metrics aggregations, use the object format with `metricName`,
  `timeAggregation`, `spaceAggregation`
- For logs/traces aggregations, use the expression format:
  `{"expression": "count()"}` or `{"expression": "p99(durationNano)"}`
- For formulas (e.g., error rate = errors / total * 100), use multiple
  `builder_query` entries plus a `builder_formula` entry, and set
  `selectedQueryName` to the formula name (e.g., "F1")
- Always set `labels.severity` to match the highest threshold level
- Write meaningful `annotations.description` using template variables:
  `{{$value}}`, `{{$threshold}}`, `{{$labels.key}}`
- Use OTel attribute names: `service.name`, `host.name`,
  `deployment.environment.name`

### Step 5: Handle notification channels

**If the user explicitly names a channel** (e.g., "send to slack-alerts"),
include it directly in the threshold's `channels` array.

**If the user does not specify channels:**
1. Call `signoz_create_alert` without channels first — the MCP server will
   return available channel names in the error response.
2. Present the list to the user and let them choose.
3. Retry with their selection.

**If no suitable channel exists**, tell the user they need to create one first
in SigNoz settings before the alert can notify them. The alert will still be
created and will evaluate, but won't send notifications.

### Step 6: Create the alert

Call `signoz_create_alert` with the built JSON. The MCP server auto-applies
these defaults if omitted:
- `version` → "v5"
- `schemaVersion` → "v2alpha1"
- `evaluation` → rolling, 5-minute window, 1-minute frequency
- `notificationSettings` → re-notification disabled, 30-minute interval
- `panelType` → "graph"
- `selectedQueryName` → first query name
- `labels.severity` → "warning" (if not set)

### Step 7: Report the result

Tell the user what was created:
- Alert name and what it monitors
- Threshold values and severity levels
- Which notification channels are configured
- Evaluation window and frequency

Offer to adjust: "Want me to change the threshold, add another severity level,
or configure notification channels?"

## Guardrails

- **No blind creation**: Always confirm the alert configuration with the user
  before calling `signoz_create_alert`. Summarize: "I'll create an alert named
  '[name]' that fires when [condition] for [evaluation window]. Sound good?"
- **No duplicate alerts**: Always call `signoz_list_alerts` first and paginate
  through all pages before concluding no similar alert exists.
- **Signal must match alertType**: `signal: "metrics"` requires
  `alertType: "METRIC_BASED_ALERT"`, `signal: "logs"` requires
  `LOGS_BASED_ALERT`, `signal: "traces"` requires `TRACES_BASED_ALERT`.
- **No metric guessing**: If unsure what metrics are available, call
  `signoz_list_metrics`. Wrong metric names create alerts that never fire.
- **No channel guessing**: If the user doesn't name a channel, do not guess.
  Follow the channel discovery flow in Step 5.
- **OTel attribute names**: Always use OpenTelemetry semantic conventions for
  filter and groupBy fields. Use `service.name` not `service`, `host.name` not
  `host`, `deployment.environment.name` not `env`.
- **Threshold codes, not words**: The `op` and `matchType` fields use numeric
  string codes ("1", "2", etc.), not descriptive strings. Refer to the mapping
  tables in Step 4.
- **Anomaly rules are metrics-only**: `ruleType: "anomaly_rule"` can only be
  used with `alertType: "METRIC_BASED_ALERT"`.
- **Formula alerts need selectedQueryName**: When using formulas, set
  `selectedQueryName` to the formula name (e.g., "F1"), not a data query name.
- **Scope boundary**: This skill creates new alert rules. Modifications to
  existing alerts belong to `alert_modify`.

## Examples

**User:** "Alert me when CPU usage goes above 80%"

**Agent:**
1. Calls `signoz_list_alerts` — no existing CPU alert.
2. Calls `signoz_list_metrics` with `searchText: "cpu"` — finds
   `system.cpu.utilization`.
3. Confirms: "I'll create an alert named 'High CPU Usage' that fires when
   average CPU utilization exceeds 80% (warning) or 90% (critical), evaluated
   every minute over a 5-minute window, grouped by host. Sound good?"
4. User confirms.
5. Builds alert JSON with `alertType: "METRIC_BASED_ALERT"`,
   `ruleType: "threshold_rule"`, two threshold levels.
6. Calls `signoz_create_alert` — fails with channel list.
7. Presents channels to user, user picks "slack-infra".
8. Retries with `channels: ["slack-infra"]`.
9. Reports: "Created 'High CPU Usage' alert with warning at 80% and critical
   at 90%. Notifications go to slack-infra. Want to adjust anything?"

---

**User:** "Set up an alert for high error rate on the checkout service — notify
PagerDuty if it's above 5%"

**Agent:**
1. Calls `signoz_list_alerts` — no existing error rate alert for checkout.
2. Builds a formula-based alert: query A counts error traces
   (`hasError = true`), query B counts total traces, formula F1 = `A * 100 / B`.
3. Confirms: "I'll create 'Checkout Error Rate High' that fires when the error
   rate for the checkout service exceeds 5%. Uses traces signal with a formula.
   Notifications to pagerduty-oncall. OK?"
4. User confirms.
5. Calls `signoz_create_alert` with the formula alert JSON, filter
   `service.name = 'checkout'`, `selectedQueryName: "F1"`.
6. Reports what was created.

---

**User:** "Notify me if there are more than 100 error logs per minute"

**Agent:**
1. Calls `signoz_list_alerts` — no existing error log alert.
2. Confirms: "I'll create 'High Error Log Volume' that fires when error/fatal
   log count exceeds 100 in any 5-minute window, grouped by service. Sound
   good?"
3. Builds alert: `alertType: "LOGS_BASED_ALERT"`, filter
   `severity_text IN ('ERROR', 'FATAL')`, aggregation `count()`.
4. Calls `signoz_create_alert`.
5. Reports and offers channel configuration.

---

**User:** "Create an alert for p99 latency above 2 seconds on any service"

**Agent:**
1. Calls `signoz_list_alerts` — no existing latency alert.
2. Confirms: "I'll create 'High P99 Latency' that fires when p99 span
   duration exceeds 2 seconds, grouped by service and operation. Sound good?"
3. Builds alert: `alertType: "TRACES_BASED_ALERT"`,
   aggregation `p99(durationNano)`, target `2000000000` with `targetUnit: "ns"`.
4. Calls `signoz_create_alert`.
5. Reports and offers to add notification channels.
