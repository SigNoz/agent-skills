---
name: signoz-alert-explain
description: >
  Describe what an existing SigNoz alert rule does in plain language —
  the signal it watches, the threshold and evaluation behavior, the
  notification routing, and a one-line fire-frequency summary so the user
  knows whether the alert has been active. Make sure to use this skill
  whenever the user asks "what does this alert do", "explain alert X",
  "walk me through this rule", "how does my [Y] alert work", "is this
  alert configured correctly", or otherwise asks for an interpretation
  of an existing alert's configuration. Static explanation only — for
  diagnosing a specific firing incident, use `signoz-alert-investigate`.
argument-hint: <alert name or rule id>
---

# Alert Explain

Decode an existing SigNoz alert's configuration into a plain-language
explanation. The skill is read-only and stays focused on the rule
itself: what it watches, when it fires, where it notifies. A single
line of fire-frequency data is included to ground the explanation, but
this skill does **not** investigate any specific fire — that is
`signoz-alert-investigate`'s job.

## Prerequisites

This skill calls SigNoz MCP server tools (`signoz_get_alert`,
`signoz_list_alert_rules`, `signoz_get_alert_history`). Before running
the workflow, confirm the `signoz_*` tools are available. If they are
not, the SigNoz MCP server is not installed or configured — stop and
direct the user to set it up:
<https://signoz.io/docs/ai/signoz-mcp-server/>. Do not guess at alert
configuration from the rule name alone.

## When to use

Use this skill when the user wants to:
- Understand or interpret an existing alert rule.
- Confirm what signal an alert watches and at what threshold.
- Audit whether an alert is reasonably configured.
- Translate raw alert JSON into operational language.

Do NOT use when the user wants to:
- Create a new alert → `signoz-alert-create`.
- Diagnose why an alert fired or correlate signals around a fire window
  → `signoz-alert-investigate`.
- Modify an existing alert → call `signoz_update_alert` directly.
- Run an ad-hoc query → `signoz-query-generate`.

## Required inputs

| Input | Required | Source if missing |
|---|---|---|
| Alert identifier (rule ID or name) | yes | `$ARGUMENTS`, recent context, or fuzzy match |

If the input is missing or ambiguous, this skill is **best-effort** (not
strict — read-only operations are cheap to recover from):

1. Call `signoz_list_alert_rules`, paginate through every page, and find
   the closest name match.
2. State the interpretation in the response:
   "Interpreting your request as alert 'High Error Rate — Checkout' (id 42).
   If you meant a different one, tell me the name or id."
3. Proceed with the explanation. The user can correct after.

## Workflow

### Step 1: Resolve the alert

If the user provided a numeric id, skip to Step 2. Otherwise:

1. Call `signoz_list_alert_rules` and **paginate every page** —
   `pagination.hasMore` is true until the full list is walked.
2. Match by name (case-insensitive substring). If multiple match,
   present the candidates and ask which one (interactive) or pick the
   closest and flag the assumption (autonomous).

### Step 2: Fetch the full configuration

Call `signoz_get_alert` with the rule id. This is **mandatory** — the
list response does not include the full condition / thresholds /
notification settings, and explanations based on the name alone are
guesses.

### Step 3: Pull a one-line fire-frequency summary

Call `signoz_get_alert_history` for the rule with a 7-day lookback. From
the response, derive a single line:

> Fired N times in the last 7d (last fire: <relative-time>).

If the alert never fired in the window, say so explicitly:
"Has not fired in the last 7d." If the alert is disabled, mention that
and skip the history line.

This single line grounds the explanation. Do **not** drill into specific
fires here — that's `alert-investigate`.

### Step 4: Build the structured explanation

Use this exact section order. Skip a section if there's nothing
meaningful to say (e.g., omit the Anomaly section unless `ruleType` is
`anomaly_rule`).

**1. Overview** — one paragraph:
- Signal type (metrics / logs / traces / exceptions) and what it watches.
- Severity (`labels.severity`).
- State: enabled vs `disabled`; if SigNoz returns a current state
  (`firing`, `inactive`), include it.
- The one-line fire-frequency summary from Step 3.
- A short audit trail: created/updated timestamps and authors
  (`createAt`, `updateAt`, `createBy`, `updateBy`) so the user knows
  the alert's age and last maintainer.

**2. Query breakdown** — translate the query into operational language.
The shape depends on `compositeQuery.queryType`:

- **Builder (metrics)** — name the metric, time aggregation, space
  aggregation, filter, and groupBy. Example: "Measures
  `system.cpu.utilization`, averaged over time, averaged across CPU
  cores, filtered to `deployment.environment.name = 'production'`,
  grouped by `host.name`."
- **Builder (logs / traces)** — explain the aggregation expression
  (e.g., "counts log lines matching..."), filter, and groupBy. For
  traces, note `durationNano` (nanoseconds) when the unit conversion
  matters.
- **Formula** — explain each sub-query (A, B, ...) separately, then
  the formula expression and what it computes (e.g., "F1 = A * 100 / B
  → error percentage"). State which `selectedQueryName` the alert
  triggers on.
- **PromQL** — translate the expression in plain English.
- **ClickHouse SQL** — translate the SQL intent.

For filters, decode operators: `=` equals, `!=` not equals, `IN` /
`NOT IN` set membership, `EXISTS` / `NOT EXISTS` field presence,
`LIKE` / `ILIKE` pattern match, `CONTAINS` substring, `REGEXP` regex.
For `IN` / `NOT IN` lists, enumerate the values so the user can verify
the list is intentional.

For groupBy, name the dimension and explain the practical effect:
"fires separately per service" if `service.name` is included.

**3. Threshold and firing condition** — decode the threshold spec:

- **`op` codes** → words: "1" above, "2" below, "3" equal, "4" not
  equal.
- **`matchType` codes** → words: "1" at_least_once (breach at any
  point in window), "2" all_the_times (breach for entire window), "3"
  on_average (average over window breaches), "4" in_total (sum over
  window breaches), "5" last (most recent value).
- Each threshold level: `name` (severity), `target`, `targetUnit`, the
  channels attached. If multiple levels, explain each.
- `recoveryTarget` if set → explain hysteresis. If absent, note the
  alert resolves the moment the value drops back across the threshold,
  which can flap if the value hovers near the boundary.
- **Unit handling**: `targetUnit` is the unit the user set the threshold
  in (e.g., "ms"). The query may emit a different native unit (e.g.,
  ns for `durationNano`). SigNoz converts the query output to
  `targetUnit` before comparing. State the threshold in `targetUnit`
  (e.g., "fires when p99 latency exceeds 500 ms"), not in the native
  unit.

**4. Evaluation timing** — explain `evalWindow` and `frequency`:

> The alert checks every `frequency` using the last `evalWindow` of
> data, so a spike that lasts less than `evalWindow` could still
> trigger it depending on `matchType`.

**5. Absent-data behavior** — if `alertOnAbsent: true`, explain that
the alert fires when no data arrives for `absentFor` (in milliseconds —
e.g., `300000` is 5 minutes). If absent or false, note that silent
data loss (crashed service, broken instrumentation) will not trigger
this alert.

**6. Notification routing** — explain:
- `preferredChannels` and per-threshold `channels`: where each severity
  level routes.
- `notificationSettings.groupBy`: how notifications are grouped to
  reduce noise.
- `notificationSettings.renotify`: whether re-notification is on, the
  interval, and which states (`firing`, `nodata`).
- `notificationSettings.usePolicy`: whether label-based routing
  policies apply.
- If `notificationSettings` is absent, default behavior applies: no
  grouping, no re-notification, no label-based routing.

**7. Labels and annotations** — explain `labels.severity` plus any
custom labels (team, service, environment) that drive routing. Decode
`annotations.description` template variables: `{{$value}}` (current
value), `{{$threshold}}` (threshold target), `{{$labels.key}}` (label
value — note dots become underscores: `service.name` →
`{{$labels.service_name}}`).

**8. Rule type context** — note `ruleType` and what it implies:
- `threshold_rule` — static threshold comparison (most common).
- `promql_rule` — PromQL expression evaluated against the metrics
  store.
- `anomaly_rule` — Z-score seasonal anomaly detection. State the
  `algorithm` (zscore), `seasonality` (hourly / daily / weekly), and
  that the threshold is in standard deviations from the expected
  pattern, not raw value. Lower target → more sensitive (more
  noise); higher target → only extreme deviations.

### Step 5: Assess the configuration (only if asked)

The user may ask "is this alert reasonable" alongside the explanation.
Only assess when asked or when the request implies it (audit, review,
"is this configured correctly"). Keep assessment grounded in what's
actually in the config:

- **Threshold calibration** — appropriate for the signal? Consider
  service criticality and traffic.
- **matchType fit** — `at_least_once` is sensitive (catches transients);
  `all_the_times` is conservative; `on_average` smooths noise.
- **Window vs frequency** — short window + `at_least_once` can be noisy.
  Long window can delay detection.
- **Multi-severity** — alerts with both warning and critical thresholds
  enable graduated response. Single-severity alerts miss this.
- **Notification routing** — critical → high-urgency channels (PagerDuty);
  warning → low-urgency (Slack).
- **Missing runbook / description** — if `annotations` are empty or
  default, suggest adding context.
- **Absent-data monitoring** — for critical signals, recommend
  `alertOnAbsent: true` if it isn't set.
- **GroupBy cardinality** — high-cardinality groupBy fields can produce
  many independent alert series; flag potential notification storms.
- **Filter completeness** — for `IN` / `NOT IN` filters with explicit
  value lists, flag values that look out of place or missing values
  that seem expected.
- **Fire frequency vs threshold** — if Step 3 shows the alert fires
  many times a day (>10/day in the 7d window), the threshold is likely
  too tight; if it never fires and the user is asking because they
  expected it to, the threshold may be too loose or the query may be
  wrong.

### Step 6: Offer next steps

End with two or three actionable follow-ups:
- "Want me to investigate the most recent fire?" (→ `signoz-alert-investigate`)
- "Want me to run the underlying query to see current values?" (→
  `signoz-query-generate`)
- "Want me to adjust the threshold or add a severity level?" (→
  `signoz_update_alert` directly — out of scope here)
- "Want me to create a related alert for [gap noticed]?" (→
  `alert-create`)

## Guardrails

- **Fetch before explaining.** Always call `signoz_get_alert`. Do not
  base explanations on the rule name or list response alone.
- **Always pull fire history.** The one-line frequency summary is
  cheap (one MCP call) and grounds the explanation. Skip it only if
  the alert is disabled.
- **Decode, don't dump.** Translate `op`, `matchType`, filter
  expressions, and query JSON into operational language. Show raw JSON
  only if the user asks.
- **Decode every sub-query.** For formula alerts, explain each builder
  query and the formula. Don't gloss over a formula as "error rate" —
  show the user what A, B, and F1 each compute.
- **Anchor to the actual config.** Don't speculate based on the alert
  name. If the name says "checkout" but the filter targets `payments`,
  call that out.
- **No live queries by default.** Do not run the alert's query unless
  the user asks. Explain is about understanding the rule, not
  inspecting current data.
- **Paginate alert listing.** Before concluding an alert does not
  exist, walk every page of `signoz_list_alert_rules`.
- **SigNoz evaluation model.** SigNoz uses `evalWindow` + `frequency`
  + `matchType`, not Prometheus-style `for` durations. Don't describe
  the evaluation model in Prometheus terms.
- **Stay in scope.** Investigation of a specific fire window belongs
  to `signoz-alert-investigate`. Modifications belong to
  `signoz_update_alert`.

## Examples

**User:** "Explain my checkout error rate alert"

**Agent:**
1. `signoz_list_alert_rules` (paginated) → finds "High Error Rate —
   Checkout" with id 42.
2. `signoz_get_alert id=42` → full config (formula alert,
   `alertType=TRACES_BASED_ALERT`, two queries + formula F1, single
   critical threshold at 5%, `op=1`, `matchType=1`).
3. `signoz_get_alert_history id=42 lookback=7d` → fired 3 times in
   last 7d, last fire 2h ago.
4. Builds explanation:
   - **Overview**: traces-based alert, critical severity, currently
     enabled. Fired 3 times in the last 7d (last fire 2h ago). Created
     by alice 2 weeks ago, last updated by bob yesterday.
   - **Query breakdown**: query A counts spans with `hasError = true`
     for `service.name = 'checkout'`. Query B counts all spans for the
     same service. Formula F1 = A * 100 / B → error percentage. The
     alert triggers on F1.
   - **Threshold**: fires when error rate goes above 5% at any point in
     the evaluation window (`at_least_once`). Single critical
     threshold, channel `pagerduty-oncall`.
   - **Evaluation**: checks every 1 min over the last 5 min.
   - **Notification**: pagerduty-oncall on critical; re-notify every
     4h while firing.
5. Offers: "Want me to investigate the fire from 2h ago?"

---

**User:** "Explain alert rule 17 — is it well configured?"

**Agent:**
1. `signoz_get_alert id=17` → metrics-based, `system.cpu.utilization`,
   threshold_rule, two thresholds (warning 80%, critical 90%),
   `matchType=3` on_average, filter
   `deployment.environment.name = 'production'`, groupBy `host.name`.
2. `signoz_get_alert_history id=17` → has not fired in last 7d.
3. Builds explanation, then assesses (since user asked):
   - Dual-threshold setup is good for graduated response.
   - `on_average` is appropriate for CPU — avoids false positives from
     momentary spikes.
   - 0 fires in 7d means the threshold has not been exercised. Could be
     fine (production is healthy) or too loose. If user expected it to
     fire, suggest checking the metric directly with `signoz-query-generate`.
   - Suggests adding `alertOnAbsent: true` so a host that stops
     reporting metrics doesn't slip through silently.
   - Annotations use default templates — suggests adding a runbook URL.
4. Offers next steps.

---

**User:** "Help me understand this anomaly detection alert" (alert id 88)

**Agent:**
1. `signoz_get_alert id=88` →
   `ruleType: anomaly_rule`, `algorithm=zscore`, `seasonality=daily`,
   target 3, metric `http.server.request.duration`, scope
   `service.name = 'api-gateway'`.
2. History: fired 1 time in last 7d.
3. Explanation:
   - **Overview**: metrics-based anomaly detection alert on
     `http.server.request.duration` for api-gateway. Fired once in last
     7d.
   - **Anomaly specifics**: uses Z-score with daily seasonality.
     Instead of a fixed threshold, the alert learns the daily pattern
     of latency and fires when the value deviates by more than 3
     standard deviations from the expected pattern. This adapts to
     traffic patterns — higher latency at peak hours won't false-trigger
     if that's normal.
   - **Threshold interpretation**: target 3 means 3 standard deviations.
     Lower (e.g., 2) → more sensitive, more noise. Higher (e.g., 4) →
     only extreme deviations.
4. Offers to investigate the recent fire.
