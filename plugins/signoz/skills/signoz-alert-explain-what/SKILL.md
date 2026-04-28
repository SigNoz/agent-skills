---
name: signoz-alert-explain-what
description: >
  Trigger when the user wants to understand, interpret, or get an overview of an
  existing alert rule. Includes requests like "explain this alert", "what does
  my error rate alert monitor", "walk me through this alert's configuration",
  "is this alert configured correctly", "help me understand this alert rule".
---

# Alert Explain What

## When to use

Use this skill when the user asks to:
- Understand, explain, or interpret an existing alert rule
- Know what an alert monitors, when it fires, and how it evaluates
- Assess whether an alert's configuration is reasonable or well-tuned
- Understand the queries, thresholds, or notification routing on an alert

Do NOT use when:
- User wants to create a new alert → `signoz-alert-create`
- User wants to modify an existing alert → `alert_modify`
- User wants to query data without an alert context → `signoz-query-generate`

## Instructions

### Step 1: Identify the target alert

Determine which alert the user wants explained. If the user provides a rule
name, ID, or it is clear from context (e.g., auto-context providing an alert
resource), use that.

If the target alert is ambiguous:
1. Call `signoz_list_alerts` to list existing alerts. **Paginate through all
   pages** — check `pagination.hasMore` in the response. If `hasMore` is true,
   call again with `offset` set to `pagination.nextOffset` and repeat until all
   pages are exhausted. Never stop at the first page.
2. Present matching candidates to the user and ask which one to explain.

### Step 2: Fetch the full alert configuration

Call `signoz_get_alert` with the rule ID. This is **mandatory** — you need the
complete JSON to explain the alert accurately. Never guess based on the alert
name alone.

### Step 3: Build the explanation

Structure your explanation in this order:

**1. Overview** — One paragraph summarizing the alert's purpose in plain
language: what signal it watches (metrics, logs, traces), what condition
triggers it, and what severity it carries. Include:
- Whether the alert is **enabled or disabled** (`disabled` field)
- The current **state** if present: `firing` (condition is actively breached),
  `inactive` (enabled but not breaching), or `disabled`
- When it was created and last updated (`createAt`, `updateAt`) and by whom
  (`createBy`, `updateBy`) — mention briefly so the user knows the alert's age
  and last maintainer

**2. Query breakdown** — Explain what the alert actually measures. Decode the
query configuration into plain operational language:

- **Builder queries**: Explain the signal, aggregation, filters, and groupBy.
  For metrics, name the metric and the time/space aggregations. For logs/traces,
  explain the aggregation expression (e.g., "counts log lines matching...").
- **Formula queries**: When the alert uses multiple `builder_query` entries plus
  a `builder_formula`, explain each sub-query (A, B, ...) separately, then
  explain what the formula computes and why. Identify which query or formula is
  the `selectedQueryName` — that is what the alert actually triggers on.
- **PromQL queries**: Translate the PromQL expression into plain English.
- **ClickHouse SQL queries**: Translate the SQL intent into plain English.

For filters, translate the filter expression into readable form. Common
operators: `=` (equals), `!=` (not equals), `IN` / `NOT IN` (set membership),
`EXISTS` / `NOT EXISTS` (field presence), `LIKE` / `ILIKE` (pattern match),
`CONTAINS` (substring), `REGEXP` (regex). When filters use `NOT IN` with an
explicit value list, enumerate the excluded values so the user can verify the
list is complete and intentional.

For groupBy fields, explain what dimension the alert evaluates independently
(e.g., "fires separately per service" if groupBy includes `service.name`).
Note the `fieldContext` if present — `resource` attributes (e.g.,
`service.name`) come from the OTel resource descriptor and identify the
emitting process, while `attribute`/`tag` fields come from individual
spans or log records.

**3. Threshold and firing condition** — Decode the threshold configuration:

- Translate `op` codes into words: "1" = above, "2" = below, "3" = equal,
  "4" = not equal.
- Translate `matchType` codes into words: "1" = fires if breached at any point
  in the evaluation window (at least once), "2" = fires only if breached for
  the entire window (all the time), "3" = fires if the average over the window
  breaches (on average), "4" = fires if the cumulative total breaches (in
  total), "5" = fires based on the most recent value only (last).
- If multiple thresholds exist (e.g., warning at 80%, critical at 90%), explain
  each level, its target value, and which notification channels are attached to
  each.
- If `recoveryTarget` is set, explain the recovery condition (the value the
  metric must return to before the alert resolves). If `recoveryTarget` is
  absent, note there is no hysteresis — the alert resolves as soon as the value
  drops back below (or above, for "below" alerts) the threshold, which can
  cause flapping if the value hovers near the boundary.
- **Unit handling**: The `targetUnit` is the unit the user set the threshold
  in (e.g., "ms"). The query may produce values in a different native unit
  (e.g., nanoseconds for `durationNano`). SigNoz converts the query output to
  `targetUnit` before comparing against `target`. Always state the threshold
  in the `targetUnit` (e.g., "fires when p90 latency exceeds 500 ms"), not
  in the query's native unit. If `targetUnit` is absent, the threshold is
  compared against the raw query output.

**4. Evaluation timing** — Explain the evaluation configuration:
- `evalWindow` — how far back the query looks each time it evaluates
- `frequency` — how often the alert runs
- Explain the practical implication: "The alert checks every [frequency] using
  the last [evalWindow] of data, so a spike that lasts less than [evalWindow]
  could still trigger it depending on the matchType."

**5. Absent-data behavior** — If `alertOnAbsent` is true, explain that the
alert fires when no data is received for the configured `absentFor` duration.
The `absentFor` value is in **minutes**. If `alertOnAbsent` is false or
absent, note that the alert only fires on threshold breaches — silent data
loss (e.g., a crashed service or broken instrumentation) will not be detected
by this alert.

**6. Notification routing** — Explain:
- `preferredChannels` and per-threshold `channels` — where notifications go
  for each severity level
- `notificationSettings.groupBy` — how notifications are grouped to reduce
  noise
- `notificationSettings.renotify` — whether re-notification is enabled, at
  what interval, and for which alert states
- `notificationSettings.usePolicy` — whether routing policies based on labels
  are active
- If `notificationSettings` is absent, note that default notification behavior
  applies (no grouping customization, no re-notification, no label-based
  routing policies)

**7. Labels and annotations** — Explain:
- `labels.severity` and any custom labels (team, service, environment) — note
  that labels drive routing when `usePolicy` is true
- `annotations.description` — the alert message template. Point out template
  variables like `{{$value}}`, `{{$threshold}}`, `{{$labels.key}}` and what
  they resolve to

**8. Rule type context** — Note the rule type and its implications:
- `threshold_rule` — standard static threshold comparison
- `promql_rule` — evaluates a PromQL expression
- `anomaly_rule` — uses Z-score seasonal anomaly detection. Explain the
  `algorithm` (zscore), `seasonality` (hourly/daily/weekly), and that the
  threshold represents standard deviations from the expected pattern

### Step 4: Assess the configuration (if asked)

Only provide a "is this reasonable?" assessment if the user asks for it or the
question implies it. When assessing, evaluate:

- **Threshold calibration**: Is the threshold value appropriate for the signal?
  Consider the service's criticality and traffic volume.
- **matchType fit**: Is the matchType appropriate? `at_least_once` is sensitive
  (catches transient spikes), `all_the_times` is conservative (requires
  sustained breach), `on_average` smooths out noise. Note trade-offs.
- **Evaluation window vs frequency**: A very short eval window with
  `at_least_once` can be noisy. A very long one can be slow to detect issues.
- **Multi-severity**: Does the alert have both warning and critical thresholds?
  Single-severity alerts miss the opportunity for graduated response.
- **Notification routing**: Are critical alerts going to high-urgency channels
  (PagerDuty) and warnings to lower-urgency ones (Slack)?
- **Missing runbook**: If `annotations` lacks a runbook link, suggest adding
  one.
- **Missing description**: If the description or annotations are empty/default,
  suggest adding meaningful context.
- **Absent-data monitoring**: For critical signals, if `alertOnAbsent` is false,
  note that silent data loss won't be detected.
- **GroupBy considerations**: High-cardinality groupBy fields can produce many
  independent alert series — flag if this might cause notification storms.
- **Filter completeness**: For `IN` / `NOT IN` filters with explicit value
  lists, check whether the list looks complete and intentional. Flag values
  that seem out of place (e.g., a redirect code in an "error" exclusion list)
  or values that are missing (e.g., excluding 200 but not 204).

### Step 5: Offer next steps

After the explanation, offer actionable follow-ups:
- "Want me to check recent firing history for this alert?" (→
  `signoz_get_alert_history`)
- "Want me to run the underlying query to see current values?"
  (→ `signoz-query-generate`)
- "Want me to adjust the threshold or add another severity level?"
  (→ `alert_modify`)
- "Want me to create a related alert for [gap you noticed]?"
  (→ `signoz-alert-create`)

## Guardrails

- **Fetch before explaining**: Always call `signoz_get_alert` to get the full
  configuration. Never explain based on the alert name or listing alone.
- **Decode, don't dump**: Translate numeric codes (`op`, `matchType`), filter
  expressions, and query JSON into plain operational language. Never show raw
  threshold codes to the user unless they specifically ask for the raw config.
- **Decode every query**: For formula alerts, explain each sub-query and the
  formula. Do not gloss over the formula as "error rate" — show the user what
  A, B, and F1 each represent.
- **Anchor to actual config**: Base all explanations on the actual alert JSON
  returned by `signoz_get_alert`. Do not speculate about what the alert
  "probably" does based on its name.
- **No live queries by default**: Do not run the alert's underlying query unless
  the user asks. The explain skill is about understanding the configuration,
  not inspecting current data.
- **Paginate alert listing**: When searching for an alert by name, always
  paginate through all pages of `signoz_list_alerts` before concluding an alert
  does not exist.
- **SigNoz evaluation model**: SigNoz alerts use `evalWindow` + `frequency` +
  `matchType`, not Prometheus-style `for` durations or consecutive evaluation
  counts. Do not describe the evaluation model using Prometheus terminology.
- **Scope boundary**: This skill explains existing alert rules. If the user
  wants to change something after your explanation, redirect to `alert_modify`.
  If they want a new alert, redirect to `signoz-alert-create`.

## Examples

**User:** "Explain my checkout error rate alert"

**Agent:**
1. Calls `signoz_list_alerts` (paginates all pages) — finds "High Error Rate -
   Checkout" with ruleId 42.
2. Calls `signoz_get_alert` with ruleId 42 — gets full configuration.
3. Provides structured explanation:
   - **Overview**: "This is a traces-based alert that monitors the error rate of
     your checkout service. It's currently enabled with critical severity."
   - **Query breakdown**: "The alert uses two queries and a formula. Query A
     counts error traces (spans where `hasError = true`) for
     `service.name = 'checkout'`. Query B counts all traces for the same
     service. Formula F1 computes `A * 100 / B` — the error percentage. The
     alert triggers on F1."
   - **Threshold**: "Fires when the error rate goes above 5% at any point in the
     evaluation window (at_least_once). There's a single critical threshold
     with notifications to pagerduty-oncall."
   - **Evaluation**: "Checks every 1 minute using the last 5 minutes of data."
   - **Notification**: "Critical alerts go to pagerduty-oncall. Re-notification
     is enabled every 4 hours while firing."
4. Offers: "Want me to check the recent firing history, or adjust the threshold?"

---

**User:** "What does alert rule 17 monitor? Is it configured well?"

**Agent:**
1. Calls `signoz_get_alert` with ruleId 17 — gets full configuration for
   "High CPU Usage" (metric-based, threshold_rule).
2. Provides explanation:
   - **Overview**: "This is a metrics-based alert monitoring
     `system.cpu.utilization`, grouped by `host.name`."
   - **Query breakdown**: "Measures the average CPU utilization over time (time
     aggregation: avg) averaged across CPU cores (space aggregation: avg),
     filtered to `deployment.environment.name = 'production'`."
   - **Thresholds**: "Two levels — warning at 80% (notifications to
     slack-infra) and critical at 90% (notifications to slack-infra and
     pagerduty-oncall). Both use matchType 'on_average' — the alert fires
     when the average value over the evaluation window breaches the threshold,
     smoothing out transient spikes."
   - **Assessment**: "The dual-threshold setup is good for graduated response.
     Using 'on_average' is appropriate for CPU — it avoids false positives from
     momentary spikes. Consider adding `alertOnAbsent: true` so you get
     notified if a host stops reporting metrics entirely. The annotations are
     using default templates — adding a runbook link would help on-call."
3. Offers next steps.

---

**User:** "Help me understand this anomaly detection alert"

**Agent:**
1. Identifies and fetches the alert configuration.
2. Provides explanation:
   - **Overview**: "This is a metrics-based anomaly detection alert (anomaly_rule)
     monitoring `http.server.request.duration`."
   - **Query breakdown**: Explains the metric, aggregation, and filters.
   - **Anomaly detection specifics**: "This alert uses Z-score anomaly detection
     with daily seasonality. Instead of a fixed threshold, it learns the
     normal daily pattern of your request latency and fires when the value
     deviates by more than 3 standard deviations from the expected value. This
     means it adapts to your service's natural traffic patterns — higher
     latency during peak hours won't trigger false alarms if that's normal."
   - **Threshold interpretation**: "The threshold target of 3 represents
     3 standard deviations. A lower value (e.g., 2) would be more sensitive,
     catching smaller anomalies but potentially more noisy. A higher value
     (e.g., 4) would only fire on extreme deviations."
3. Offers next steps.
