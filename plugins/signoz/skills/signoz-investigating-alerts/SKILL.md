---
name: signoz-investigating-alerts
description: >
  Diagnose why a SigNoz alert fired by correlating the alert's own signal
  with neighbor signals (error rate, latency, throughput, CPU/memory),
  traces, and logs around the fire window — and rank likely causes.
  Make sure to use this skill whenever the user asks "why did this alert
  fire", "what caused alert X", "investigate this alert", "RCA for the
  alert that paged me", "what's wrong with [service]" in the context of
  a recent fire, or otherwise asks for a root-cause analysis of a
  firing or recently-fired alert. Read-only — does not modify any
  alert or notification.
argument-hint: <alert name or rule id> [time window]
---

# Alert Investigate

Diagnose why a SigNoz alert fired. The skill correlates the alert's own
signal with neighbor signals around the fire window, and surfaces a
ranked list of likely causes with supporting evidence. It is the
companion to `signoz-explaining-alerts` — explain decodes the rule
statically; investigate diagnoses a specific incident.

## Prerequisites

This skill calls SigNoz MCP server tools heavily (`signoz:signoz_get_alert`,
`signoz:signoz_get_alert_history`, `signoz:signoz_execute_builder_query`,
`signoz:signoz_query_metrics`, `signoz:signoz_search_traces`, `signoz:signoz_search_logs`,
`signoz:signoz_get_trace_details`, etc.). Before running the workflow,
confirm the `signoz:signoz_*` tools are available. If they are not, the
SigNoz MCP server is not installed or configured — stop and direct
the user to set it up: <https://signoz.io/docs/ai/signoz-mcp-server/>.
The investigation depends on correlating multiple MCP queries; without
the server there is no way to ground the analysis.

## When to use

Use this skill when the user wants to:
- Understand why a specific alert fired.
- Find the root cause of a recent incident triggered by an alert.
- Correlate the alert's signal with related metrics, traces, and logs.
- Distinguish "real signal" fires from flapping or threshold-mistuning.

Do NOT use when the user wants to:
- Understand what an alert is configured to monitor → `signoz-explaining-alerts`.
- Create a new alert → `signoz-creating-alerts`.
- Modify an alert (raise threshold, add hysteresis) → call
  `signoz:signoz_update_alert` directly.
- Run a free-form ad-hoc investigation without an alert as the anchor →
  `signoz-generating-queries`.

## Required inputs

| Input | Required | Source if missing |
|---|---|---|
| Alert identifier (rule ID or name) | yes | `$ARGUMENTS[0]` or recent context |
| Time window | no | default to most recent fire from `signoz:signoz_get_alert_history` |

If the alert name is fuzzy, this skill is **best-effort** (read-only):
1. Call `signoz:signoz_list_alert_rules`, paginate, fuzzy-match the name.
2. State the interpretation: "Investigating fire of 'High Error Rate —
   Checkout' (id 42) at 14:32 UTC. If you meant a different alert or
   fire, tell me."
3. Proceed.

If the alert has never fired in the lookback window, **stop**: there is
nothing to investigate. Respond with:
> "Alert '[name]' has not fired in the last 7d, so there is no fire
> window to investigate. Use `signoz-explaining-alerts` to walk through
> the rule, or check whether the alert is enabled."

## Workflow

The investigation runs in three tiers with strict early-stop gates.
Tier 1 always runs. Tier 2 runs only if tier 1 confirms a real fire.
Tier 3 runs only if tier 2 surfaces correlated anomalies. Skipping the
gates produces hundreds of unnecessary trace/log queries on quiet
alerts.

### Step 1: Resolve alert + fire window (Tier 0)

1. Resolve the alert id via `signoz:signoz_list_alert_rules` (paginated) if
   not given.
2. Call `signoz:signoz_get_alert` for the full rule config — needed to know
   what query, threshold, and resource scope the alert evaluated.
3. Call `signoz:signoz_get_alert_history` with a 7d lookback. From the
   response:
   - **Pick the fire window**. Default to the most recent fire. If the
     user passed an explicit time window via `$ARGUMENTS[1]`, honor it.
   - **Note the fire pattern**:
     - `one-off` → single fire with a long quiet period before/after.
     - `sustained` → fires that stayed firing for ≥ 1 evaluation cycle.
     - `flapping` → ≥ 3 fires within a 1h window, alternating fire/resolve.
     - `recurring` → fires at regular intervals (cron-like, e.g., every hour).
   - The pattern tells you what to expect from tiers 2/3.

### Step 2: Tier 1 — what fired and how hard

This tier always runs. It establishes the fire is real (vs. transient
threshold tickle or flap) and quantifies the magnitude.

1. Re-run the alert's primary query over a window centered on the fire
   start: `[fire_start - 30m, fire_start + 30m]`.
   - Use `signoz:signoz_execute_builder_query` for builder/formula alerts.
   - Use `signoz:signoz_query_metrics` for PromQL alerts.
2. Compute:
   - **Peak value** during the fire window.
   - **Threshold breach magnitude**: `(peak - threshold) / threshold *
     100` for "above" alerts, inverted for "below".
   - **Fire duration**: how long the breach lasted.
   - **Pre-fire baseline**: average value in the 30m before fire start.
3. **Early-stop gate**: if the breach magnitude is < 10% over the
   threshold AND the fire duration is < 1 evaluation window, classify
   as "marginal fire" — the alert may be too sensitive. Skip tiers 2
   and 3 and go to Step 5 with a single hypothesis: "threshold may be
   too tight, recommend tuning."

### Step 3: Tier 2 — neighbor signals vs baseline

Run only if Tier 1 confirms a real breach. Pull related signals for the
same resource scope as the alert and compare the fire window to a
baseline window.

1. **Pick a baseline window**. Use the same hour, previous day
   (`fire_start - 24h, fire_start - 24h + fire_duration`). If the
   alert fired during a known-anomalous time (deploy, weekly job),
   note it in the output but still proceed.

2. **Look up neighbor signals** for the alert's resource type. See
   `references/neighbor-signals.md` for the lookup table. Common cases:
   - **Service-level alert** (`service.name = X`): pull error rate,
     p95/p99 latency, request throughput, dependency error rates if
     trace data is available.
   - **Host / VM alert** (`host.name = X`): CPU, memory, disk I/O,
     network I/O.
   - **K8s pod / namespace alert**: pod restarts, container CPU/memory
     limits, node pressure, recent rollouts.

3. For each neighbor signal:
   - Query both windows (fire + baseline) via
     `signoz:signoz_execute_builder_query` or `signoz:signoz_query_metrics`.
   - Compute the delta (% change in fire window vs baseline).
   - Rank by absolute delta.

4. **Early-stop gate**: if no neighbor signal shows ≥ 25% deviation
   from baseline, classify as "isolated fire — the alert's own signal
   moved but nothing else did." This is unusual and worth surfacing.
   Skip Tier 3 and go to Step 5 with hypotheses focused on the alert's
   own query (likely causes: data source change, instrumentation
   change, downstream silent failure that only shows in this metric).

### Step 4: Tier 3 — traces and logs at the fire window

Run only if Tier 2 found correlated neighbor anomalies. Drill into
specific failing operations.

1. **Traces** (if the alert is service-scoped and traces are
   available):
   - Call `signoz:signoz_search_traces` for the fire window with filter:
     `service.name = <scope>` AND `hasError = true`. Cap at top 20.
   - Group results by `name` (operation) and `error_message`. Surface
     the top 3 by frequency with a representative trace ID for each.
   - Optionally call `signoz:signoz_get_trace_details` on one representative
     to extract specific span attributes (DB statement, downstream URL,
     status code).

2. **Logs** for the fire window:
   - Call `signoz:signoz_search_logs` with filter:
     `<scope_filter>` AND `severity_text IN ('ERROR', 'FATAL')`. Cap
     at top 20 most recent.
   - Group by `body` pattern (or `exception.type` if present). Surface
     the top 3 distinct messages with counts.

3. Cross-reference: do the traces and logs point at the same
   downstream service, dependency, or code path? If so, that becomes
   the leading hypothesis.

See `references/baseline-comparison.md` for query templates that pair
fire-window and baseline-window calls cleanly.

### Step 5: Build the structured output

Use this exact section order. Lead with a TL;DR — engineers under
pressure scan the top first and stop reading once they have what
they need. Compression plus proof: every claim cites the MCP query
that produced it; no generic "check logs / verify connectivity"
filler.

**1. TL;DR** — one or two sentences, no more. Leading hypothesis,
overall confidence, blast radius, and the single most useful next
action. Example:
> "checkoutservice error rate hit 12.4% (threshold 5%) for 8m at
> 14:32 UTC — most likely cause is payments-api timing out
> (high confidence). Open trace `7af3a09b…` to see the failing call."

If no hypothesis reaches medium confidence, the leading line is
"No clear root cause found." rather than a low-confidence guess
dressed up as the answer.

**2. What fired**
The alert (id, name), the fire window (absolute UTC + relative),
peak magnitude ("error rate hit 12.4% vs. 5% threshold — 148% over"),
fire duration, and the fire pattern (`one-off` / `sustained` /
`flapping` / `recurring` / `marginal`).

**3. Investigation trail**
A scannable list of what was checked, with ✅ for confirmed signals
and ❌ for ruled out, each followed by a one-line finding. The point
is that the reader can see what work the AI did and what it found —
this is where trust is earned. Example:
- ✅ Tier 1 — peak error rate 12.4%, fire was real (not marginal).
- ✅ Tier 2 — payments error rate +8900%, p99 +1180%; downstream
  cascade.
- ❌ CPU / memory pressure — flat through the fire window.
- ✅ Tier 3 — 30 error traces all hit payments-api, same message.

**4. Likely causes** (ranked, max 3)
Each cause has three parts:
- **Hypothesis** — one sentence, specific. Bad: "service is unhealthy".
  Good: "checkout is timing out on calls to payments-api".
- **Evidence** — the supporting numbers from tiers 1/2/3, with the
  underlying query inline so the user can re-run it. State the
  neighbor signal, the delta vs baseline, the trace/log pattern that
  supports it.
- **Confidence** — `high` requires ≥2 of: temporal precedence,
  topology / dependency edge, shared service or entity, correlated
  metric/log/trace evidence, recent deploy or config change.
  `medium` is one tier's evidence with at least one of those
  signals. `low` is a single signal moved with no corroboration —
  in that case label it a "co-occurring signal," not a cause.

If only Tier 1 ran (marginal fire / no neighbor anomalies), output
fewer hypotheses with `low` confidence and explicitly call out the
limitation.

**5. Ruled out**
Short but explicit. List candidates the evidence eliminated and the
one-line reason why. Skip the section if there's nothing meaningful
to rule out — but if you considered something and dropped it, say so
here so the user doesn't waste time re-checking it.

**6. Suggested next steps**
Action items the user can take. Be concrete and use SigNoz-native
handles so the user can act immediately:
- Specific trace, dashboard, or alert to open
  (e.g., "open trace `7af3a09b…` in the SigNoz UI").
- Specific query to run with `signoz-generating-queries` — paste
  the exact filter and time window.
- "Tune this alert" if the fire was marginal — name the field
  (`matchType`, `target`, `recoveryTarget`) and the change to make
  via `signoz:signoz_update_alert`.
- "Open an incident" or "page the owning team" if the cause is
  cross-service.

Do not pad with generic advice ("verify connectivity", "check
dashboards") — that's noise during an active incident.

## Out of scope (v1)

- **Deployment / config-change correlation** — SigNoz MCP does not
  expose a deployments tool; do not fabricate one. If the user
  mentions a recent deploy, surface it as context but don't claim it
  caused the fire without the signal evidence.
- **Cross-service blast-radius walking** — investigating downstream
  callers of the alert's service. Out of scope to keep context
  bounded.
- **Long-horizon historical baselines** — Tier 2 compares to one
  prior-day window, not to weekly/monthly seasonality. If the user
  says "is this normal for a Friday afternoon", suggest an anomaly
  alert (`signoz-creating-alerts` with `anomaly_rule`).

## Guardrails

- **Three-tier early-stop is mandatory.** Skipping the gates pulls
  hundreds of traces/logs on quiet alerts and explodes context. The
  gates are not optional optimizations.
- **Anchor every claim to an MCP query result.** No speculation. If
  evidence is missing, lower confidence and say so.
- **Show the supporting query** with each hypothesis so the user can
  reproduce and dig deeper.
- **Compression plus proof.** TL;DR is one or two sentences max; the
  full report is a triage card, not a postmortem. Engineers under
  pressure should be able to skim the top and act. Every section
  earns its place by adding evidence the user couldn't already see
  in the alert payload.
- **Correlation ≠ causation.** Label something a cause only when at
  least two of the following converge: temporal precedence (signal
  moved before symptom), topology / dependency edge, shared service
  or entity, correlated metric/log/trace evidence, or a recent
  deploy/config change. A single time-aligned anomaly is a
  "co-occurring signal," not a cause — say so explicitly.
- **Don't restate the alert or recommend the obvious.** "Check
  logs", "verify connectivity", "investigate dashboards" — the
  reader of this output already knows they need to. Replace generic
  suggestions with specific queries, traces, or filters they can run
  immediately.
- **No fabricated identifiers.** Trace IDs, span names, alert rule
  IDs, channel names, deploy IDs — every identifier in the output
  must come from a real MCP response. Don't invent placeholders that
  look plausible.
- **Honest uncertainty wins.** If no hypothesis reaches medium
  confidence, the answer is "No clear root cause found — here's
  what we checked and what's ruled out." Do not promote a
  low-confidence guess to the leading hypothesis just to sound
  useful. False positives waste active incident time more than false
  negatives.
- **Prefer resource-attribute filters** in every drill-down query.
  This is the SigNoz MCP guideline and it directly affects query
  speed at scale.
- **Do not modify any alert.** Investigate is read-only. If the user
  says "and tighten this alert", surface that as a next-step
  recommendation; do not call `signoz:signoz_update_alert`.
- **Stay in scope.** Static rule explanation belongs to
  `signoz-explaining-alerts`. Cause analysis without an alert anchor
  belongs to `signoz-generating-queries`.
- **Time zones.** Always state fire windows in UTC alongside relative
  time ("14:32 UTC, 2h ago") so autonomous and interactive consumers
  agree on the window.

## Examples

**User:** "Why did the checkout error rate alert fire?"

**Agent:**
1. Resolves alert: "High Error Rate — Checkout" (id 42).
2. `signoz:signoz_get_alert_history` → most recent fire 2h ago at 14:32 UTC,
   sustained for 8m, single fire (not flapping).
3. **Tier 1**: re-runs error-rate formula over `[14:02, 15:02]`. Peak
   error rate 12.4% (vs 5% threshold — 148% over). Pre-fire baseline
   0.3%. Real fire, not marginal.
4. **Tier 2**: pulls neighbor signals for `service.name = checkout`:
   - p99 latency: 4.1s vs 320ms baseline (+1180%).
   - Throughput: -42% (drop).
   - Downstream `payments` error rate: 18% vs 0.2% baseline (+8900%).
   - CPU/memory: flat (no resource pressure).
5. **Tier 3**: traces for `service.name = checkout, hasError = true`
   in the fire window — top operation `POST /checkout/submit`, top
   error message "context deadline exceeded calling payments-api".
   30 traces, all hitting the same downstream URL. Logs show
   matching "payments client timeout" lines, 142 occurrences.
6. **Output**:

   > **TL;DR**: checkoutservice error rate hit 12.4% (threshold 5%)
   > for 8m at 14:32 UTC. Most likely cause: payments-api timing out
   > (high confidence — converging trace + log + neighbor evidence).
   > Open trace `7af3a09b…` to see the failing call.

   - **What fired**: alert 42 fired 2h ago at 14:32 UTC, sustained
     8m. Error rate peaked at 12.4% (148% over threshold).
   - **Investigation trail**:
     - ✅ Tier 1 — peak 12.4% vs 5% threshold, pre-fire baseline 0.3%.
       Real fire.
     - ✅ Tier 2 — payments error rate +8900%, p99 latency +1180%,
       throughput −42%.
     - ❌ CPU / memory pressure on checkout — flat.
     - ✅ Tier 3 — 30 error traces all hit payments-api with
       `context deadline exceeded`; 142 matching timeout logs.
   - **Likely causes** (high confidence): payments service errors
     cascading into checkout. Evidence converges across topology
     (checkout → payments edge), temporal precedence (payments
     errors lead checkout p99), and shared entity (every error
     trace targets the payments-api URL).
   - **Ruled out**: checkout-side resource pressure (CPU/memory
     flat); upstream traffic spike (throughput dropped, didn't
     spike).
   - **Next steps**: open trace `7af3a09b…` in the SigNoz UI; if
     payments has its own alert, run `signoz-explaining-alerts` on
     it, otherwise `signoz-generating-queries` for payments error
     rate over the last 4h.

---

**User:** "Investigate the flapping CPU alert on prod-api-3"

**Agent:**
1. Resolves alert (id 88, host.name = prod-api-3).
2. History: 7 fires in last 1h, alternating fire/resolve every 8-12
   minutes — flapping pattern.
3. **Tier 1**: peak 84% (threshold 80%, only 5% over). Each fire
   lasted 2-4 minutes. Marginal — the value hovered near threshold.
   `matchType = at_least_once` made each blip trigger.
4. Early-stop kicks in. Skip tiers 2/3.
5. **Output**:

   > **TL;DR**: alert 88 has been flapping on `prod-api-3` — 7 fires
   > in the last 1h, each 2–4m, all within 5% of the 80% threshold.
   > No clear root cause; this is threshold tuning, not an incident.
   > Switch `matchType` to `on_average` or add hysteresis to stop
   > the noise.

   - **What fired**: alert 88, host `prod-api-3`, fire pattern
     `flapping`. 7 fires in the last 1h, each 2–4m. Peak 84% (5%
     over the 80% threshold).
   - **Investigation trail**:
     - ✅ Tier 1 — every fire was within 5% of threshold; duration
       short; baseline already at 70–75%. Marginal fire — early-stop
       triggered, Tier 2/3 skipped.
   - **Likely causes** (low / co-occurring signal only): threshold
     tuned too tight or `matchType` is too sensitive. Evidence:
     every fire was within 5% of threshold; baseline already runs
     at 70–75%. Not promoted to a "cause" — single signal, no
     corroboration.
   - **Ruled out**: real CPU saturation incident (peaks too small
     and short-lived; baseline already near threshold).
   - **Next steps**: change `matchType` to `on_average` (smooths
     transient spikes) OR raise threshold to 85% with hysteresis
     (`recoveryTarget: 75`). Use `signoz:signoz_update_alert` to apply.

---

**User:** "RCA for the log volume alert that fired last night"

**Agent:**
1. Resolves alert: "Error Log Volume Spike" (id 14, no service
   filter — groupBy `service.name`).
2. History: fired at 03:12 UTC, sustained 22m, broke down by service
   in the alert annotations: `service.name = inventory` was the
   firing series.
3. **Tier 1**: re-runs log count for inventory in fire window. Peak
   3,400 errors/min vs 1,000/min threshold (240% over). Pre-fire
   baseline 12/min. Real, large fire.
4. **Tier 2**: neighbor signals for `service.name = inventory`:
   - Request error rate: +600%.
   - p99 latency: +30% (mild).
   - CPU: -80% (collapsed). Memory: -60%.
   - Pod restarts (k8s): 4 in fire window.
5. **Tier 3**: logs for inventory in fire window. Top message: "OOMKilled
   restarting" (1,200 occurrences). Top trace error: graceful-shutdown
   exceptions.
6. **Output**:

   > **TL;DR**: log volume alert 14 fired at 03:12 UTC for
   > `service.name = inventory`, sustained 22m at 240% over threshold.
   > Most likely cause: inventory pods OOM-killed and restarted 4
   > times (high confidence). Check container memory limits for the
   > inventory deployment.

   - **What fired**: alert 14 fired at 03:12 UTC for service
     `inventory`, sustained 22m, 240% over threshold.
   - **Investigation trail**:
     - ✅ Tier 1 — peak 3,400 errors/min vs 1,000/min threshold;
       pre-fire baseline 12/min. Real fire.
     - ✅ Tier 2 — request error rate +600%; CPU/memory collapsed
       (−80%/−60%); 4 pod restarts in window.
     - ❌ p99 latency — only +30%, not a latency-driven incident.
     - ✅ Tier 3 — top log message "OOMKilled restarting" (1,200
       occurrences); top trace error: graceful-shutdown exceptions.
   - **Likely causes** (high confidence): inventory pods OOM-killed
     and restarted 4 times during the window. Evidence converges
     across topology (single service), temporal precedence (memory
     fell to zero before error spike), shared entity (all log lines
     from `service.name = inventory`), and a single coherent
     pattern (OOM → restart → graceful-shutdown noise).
   - **Ruled out**: a true application error-rate change (errors
     are restart noise, not request-path failures); upstream
     traffic surge (throughput unchanged).
   - **Next steps**: check container memory limits for inventory
     pods; review recent deploys; consider whether the alert should
     exclude restart-related error patterns or whether the
     underlying OOM is the real concern.

## Additional resources

- `references/neighbor-signals.md` — lookup table mapping resource type
  (service / host / k8s) to the neighbor signals to pull in Tier 2.
- `references/baseline-comparison.md` — query templates that pair
  fire-window and baseline-window calls cleanly, including how to
  format `signoz:signoz_execute_builder_query` for both.
- `signoz-explaining-alerts` skill — to decode the rule before
  investigating, if the user is unfamiliar with what the alert
  monitors.
- `signoz-generating-queries` skill — for ad-hoc follow-up queries on the same
  resource scope.
