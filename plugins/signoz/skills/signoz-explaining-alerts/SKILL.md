---
name: signoz-explaining-alerts
description: >
  Describe what an existing SigNoz alert rule does in plain language —
  the signal it watches, the threshold and evaluation behavior, the
  notification routing, and a one-line fire-frequency summary so the user
  knows whether the alert has been active. Make sure to use this skill
  whenever the user asks "what does this alert do", "explain alert X",
  "walk me through this rule", "how does my [Y] alert work", "is this
  alert configured correctly", or otherwise asks for an interpretation
  of an existing alert's configuration. Static explanation only — for
  diagnosing a specific firing incident, use `signoz-investigating-alerts`.
argument-hint: <alert name or rule id>
---

# Alert Explain

Decode an existing SigNoz alert's configuration into a plain-language
explanation. The skill is read-only and stays focused on the rule
itself: what it watches, when it fires, where it notifies. A single
line of fire-frequency data is included to ground the explanation, but
this skill does **not** investigate any specific fire — that is
`signoz-investigating-alerts`'s job.

## Prerequisites

This skill calls SigNoz MCP server tools (`signoz:signoz_get_alert`,
`signoz:signoz_list_alert_rules`, `signoz:signoz_get_alert_history`). Before running
the workflow, confirm the `signoz:signoz_*` tools are available. If they are
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
- Create a new alert → `signoz-creating-alerts`.
- Diagnose why an alert fired or correlate signals around a fire window
  → `signoz-investigating-alerts`.
- Modify an existing alert → call `signoz:signoz_update_alert` directly.

## Required inputs

| Input | Required | Source if missing |
|---|---|---|
| Alert identifier (rule ID or name) | yes | `$ARGUMENTS`, recent context, or fuzzy match |

If the input is missing or ambiguous, this skill is **best-effort** (not
strict — read-only operations are cheap to recover from):

1. Call `signoz:signoz_list_alert_rules`, paginate through every page, and find
   the closest name match.
2. State the interpretation in the response:
   "Interpreting your request as alert 'High Error Rate — Checkout' (id 42).
   If you meant a different one, tell me the name or id."
3. Proceed with the explanation. The user can correct after.

## Workflow

### Step 1: Resolve the alert

If the user provided a numeric id, skip to Step 2. Otherwise:

1. Call `signoz:signoz_list_alert_rules` and **paginate every page** —
   `pagination.hasMore` is true until the full list is walked.
2. Match by name (case-insensitive substring). If multiple match,
   present the candidates and ask which one (interactive) or pick the
   closest and flag the assumption (autonomous).

### Step 2: Fetch the full configuration

Call `signoz:signoz_get_alert` with the rule id. This is **mandatory** — the
list response does not include the full condition / thresholds /
notification settings, and explanations based on the name alone are
guesses.

### Step 3: Pull a one-line fire-frequency summary

Call `signoz:signoz_get_alert_history` for the rule with a 7-day lookback. From
the response, derive a single line:

> Fired N times in the last 7d (last fire: <relative-time>).

If the alert never fired in the window, say so explicitly:
"Has not fired in the last 7d." If the alert is disabled, mention that
and skip the history line.

This single line grounds the explanation. Do **not** drill into specific
fires here — that's `signoz-investigating-alerts`.

### Step 4: Build the explanation

The single most useful thing for the user is a tight summary. Lead
with a **TL;DR that directly answers the question they asked**, not a
generic alert summary. The TL;DR is the only thing some users will
read — burying their answer under a fixed template forces them to
scroll for what they wanted in the first place.

Match the TL;DR shape to the user's question:

- **"What does this alert do?" / "Explain X"** — describe what fires:
  > **TL;DR**: Fires when `<condition>` for `<scope>`, notifies
  > `<channel>`. `<fire-frequency line>`.

- **"Is it configured correctly?" / "Audit this" / "Anything I should
  change?"** — lead with the **verdict and the top 1–3 changes**, not
  the description of what fires:
  > **TL;DR**: Mostly well-configured, but recommend: (1) add
  > `alertOnAbsent` — currently a crashed service stays silent; (2)
  > fix annotation template `{{$topic}}` → `{{$labels.topic}}` (won't
  > interpolate); (3) split critical to PagerDuty (both tiers
  > currently route to Slack). `<fire-frequency line>`.

- **"How does X work?" / "Explain the count guard"** — answer the
  mechanism in 1–2 sentences before any framing:
  > **TL;DR**: The count guard is a `having: count() > 50` clause on
  > query A — any 1-minute bucket with ≤50 spans is dropped before
  > evaluation, so low-traffic minutes can't fire the alert.

- **"What's the threshold?" / focused config question** — state the
  exact thing they asked about:
  > **TL;DR**: Threshold is **3 standard deviations** (z-score), not
  > a raw rate value. Daily seasonality means the model compares
  > each hour against historical norms for that hour.

Always include the fire-frequency line and `disabled` status if
non-default — those ground every kind of TL;DR. But put the answer to
the user's specific question first.

After the TL;DR, write the explanation in prose, organized into the
four sections below. **Skip any section that has nothing meaningful to
add** — empty severity labels, default notification settings, vanilla
annotations don't deserve a header. Short and skimmable beats
perfunctorily complete; the user is not reading a checklist.

**1. What it watches** — one short paragraph. Combine signal type
(metrics / logs / traces / exceptions), what the query measures, and
scope. Translate the query to operational language; for formulas, name
each sub-query (A, B, …) and state what F1 (or whichever
`selectedQueryName` triggers) computes — e.g. "F1 = A × 100 / B → error
percentage". Decode filter operators (`=` equals, `!=` not equals,
`IN` / `NOT IN`, `LIKE` / `ILIKE`, `CONTAINS`, `REGEXP`, `EXISTS` /
`NOT EXISTS`); enumerate `IN` / `NOT IN` value lists so the user can
verify them. Name each `groupBy` dimension and its practical effect
("fires separately per service" for `service.name`).

For **anomaly rules** (`ruleType: anomaly_rule`), explicitly state that
the threshold is in **standard deviations from the learned pattern, not
the raw value** — this is the most common point of confusion. Include
`algorithm` (zscore), `seasonality` (hourly / daily / weekly), and how
lower/higher targets shift sensitivity (lower → more noise, higher →
only extreme deviations).

**2. When it fires** — one paragraph covering threshold + timing.
Decode the threshold spec into plain English using these mappings:

- `op` codes: `1` above, `2` below, `3` equal, `4` not equal.
- `matchType` codes: `1` at_least_once (any point in window), `2`
  all_the_times (entire window), `3` on_average (window average), `4`
  in_total (window sum), `5` last (most recent point).

State each threshold tier's `name`, `target`, `targetUnit`, and
attached channels. **Always state the threshold in `targetUnit`, not
the native query unit** (e.g. "fires when p99 exceeds 500 ms", not
"…exceeds 500 000 000 ns"). Note `recoveryTarget` if set (hysteresis);
if absent, mention flap risk when the value hovers near the boundary.
Describe timing as "checks every `<frequency>` over the last
`<evalWindow>`", and mention that with `at_least_once` a single-point
breach triggers, while `all_the_times` requires the full window.

**3. Where it notifies** — channels per tier (resolved by name from
`signoz_list_notification_channels` if needed), `notificationSettings.groupBy`
(how notifications are bundled), `renotify` (interval + which states),
`usePolicy` (label-based routing). Skip this section entirely if
notification settings are vanilla and the user already saw the channel
in the TL;DR.

**4. Notable concerns** — flag *only* what's non-default and worth the
user's attention. Don't list every absent field; focus on the
high-leverage ones:

- **`alertOnAbsent` missing** when the signal is critical: silent data
  loss (crashed service, broken instrumentation) won't trigger the
  alert. Always call this out for production-tier rules.
- **`alertOnAbsent: true` but `nodata` not in `renotify.alertStates`**:
  the absent-data fire pages once and then goes silent — easy to miss.
- **Template variable bugs**: `{{$topic}}` won't interpolate; the
  correct form is `{{$labels.topic}}`. Dots in label keys become
  underscores (`service.name` → `{{$labels.service_name}}`).
- **Multiple severity tiers but `labels.severity` missing on the rule**
  — breaks label-based routing policies. Common gap.
- **All tiers route to the same channel** — defeats the point of
  graduated thresholds.
- **High-cardinality `groupBy`** (e.g. `pod.name` × `partition`) →
  notification-storm risk during cluster-wide events.
- **Annotation/description text contradicts `matchType`** (e.g.
  description says "for over 5 minutes" but `matchType=at_least_once`
  fires on first breach within the window).
- **Alert name doesn't match the filter target** (e.g. name says
  "checkout" but filter targets `payments`) — call this out.

If none of these apply, omit the section. Better silent than padded.

If the user asked only "what does this alert do", stop here. The audit
(Step 5) is for "is it configured correctly" / "audit this" /
"anything I should change" requests.

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
- "Want me to investigate the most recent fire?" (→ `signoz-investigating-alerts`)
- "Want me to run the underlying query to see current values?" (→
  `signoz-generating-queries`)
- "Want me to adjust the threshold or add a severity level?" (→
  `signoz:signoz_update_alert` directly — out of scope here)
- "Want me to create a related alert for [gap noticed]?" (→
  `signoz-creating-alerts`)

## Guardrails

- **Fetch before explaining.** Always call `signoz:signoz_get_alert`. Do not
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
  exist, walk every page of `signoz:signoz_list_alert_rules`.
- **SigNoz evaluation model.** SigNoz uses `evalWindow` + `frequency`
  + `matchType`, not Prometheus-style `for` durations. Don't describe
  the evaluation model in Prometheus terms.
- **Stay in scope.** Investigation of a specific fire window belongs
  to `signoz-investigating-alerts`. Modifications belong to
  `signoz:signoz_update_alert`.

## Examples

**User:** "Explain my checkout error rate alert"

**Agent:**
1. `signoz:signoz_list_alert_rules` (paginated) → finds "High Error Rate —
   Checkout" id 42.
2. `signoz:signoz_get_alert id=42` → traces formula (A errored spans / B
   total spans × 100), single critical threshold at 5%, `op=1`,
   `matchType=1`, channel `pagerduty-oncall`.
3. `signoz:signoz_get_alert_history id=42 lookback=7d` → fired 3 times,
   last fire 2h ago.
4. Replies:

   > **TL;DR**: Fires when checkout error rate (errored spans / total
   > spans) exceeds 5% at any point in the last 5 min, pages
   > `pagerduty-oncall`. Fired 3 times in the last 7d (last 2h ago).
   >
   > **What it watches** — traces from `service.name = 'checkout'`.
   > Query A counts spans with `hasError = true`, query B counts all
   > spans, F1 = A × 100 / B is the error percentage; the alert
   > triggers on F1.
   >
   > **When it fires** — `op=above`, `matchType=at_least_once`, target
   > 5%. Checks every 1 min over the last 5 min — a single elevated
   > minute fires it.
   >
   > **Notable** — no `recoveryTarget` (could flap near 5%); no
   > `alertOnAbsent` (a checkout outage that drops traffic to zero
   > won't trigger this rule).

5. Offers: "Want me to investigate the fire from 2h ago?"

---

**User:** "Explain alert rule 17 — is it well configured?"

**Agent:**
1. `signoz:signoz_get_alert id=17` → metrics, `system.cpu.utilization`,
   two thresholds (warning 80%, critical 90%), `matchType=3` on_average,
   filter `deployment.environment.name = 'production'`, groupBy
   `host.name`.
2. `signoz:signoz_get_alert_history id=17` → has not fired in last 7d.
3. The user asked "is it well configured?" — the TL;DR leads with the
   **verdict**, not a generic description. Then explanation + full
   audit:

   > **TL;DR**: Mostly well-configured (dual-threshold + `on_average`
   > is the right call for CPU), but two gaps to fix: (1) no
   > `alertOnAbsent` — a crashed agent silently stops reporting and
   > this rule won't catch it; (2) annotations are default — a
   > runbook URL would help on-call. Has not fired in the last 7d
   > (could mean production is healthy or thresholds too loose).
   >
   > **What it watches** — `system.cpu.utilization` on
   > `deployment.environment.name = 'production'`, grouped by
   > `host.name` (fires per host).
   >
   > **When it fires** — `op=above`, `matchType=on_average`, two tiers
   > (warning 80%, critical 90%) over a 5-min window. Short spikes
   > don't fire — smoothing is correct for CPU.
   >
   > **Notable concerns** — same as TL;DR fixes above; nothing else
   > non-default.

4. Offers next steps.

---

**User:** "Help me understand this anomaly detection alert" (alert id 88)

**Agent:**
1. `signoz:signoz_get_alert id=88` → `ruleType: anomaly_rule`,
   `algorithm=zscore`, `seasonality=daily`, target 3, metric
   `http.server.request.duration`, scope `service.name = 'api-gateway'`.
2. History: fired 1 time in last 7d.
3. Replies:

   > **TL;DR**: Fires when api-gateway request latency deviates by more
   > than **3 standard deviations** (not raw latency, not a fixed value)
   > from its learned daily pattern. Fired once in the last 7d.
   >
   > **What it watches** — `http.server.request.duration` for
   > `service.name = 'api-gateway'`, evaluated as a Z-score anomaly
   > with **daily seasonality** — the model learns the typical pattern
   > for each hour of day, so peak-hour latency won't false-trigger if
   > it matches the historical norm for that hour.
   >
   > **When it fires** — when |Z-score| > 3, i.e. the value is more
   > than 3 standard deviations away from the expected pattern. Lower
   > target → more sensitive (more noise); higher → only extreme
   > deviations. The threshold is **not** in seconds or milliseconds.

4. Offers to investigate the recent fire.
