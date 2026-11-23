---
name: signoz-investigating-alerts
description: >
  Diagnose why a SigNoz alert fired by correlating the alert's own signal
  with neighbor signals (error rate, latency, throughput, CPU/memory),
  traces, and logs around the fire window, and rank likely causes.
  Make sure to use this skill whenever the user asks "why did this alert
  fire", "what caused alert X", "investigate this alert", "RCA for the
  alert that paged me", "what's wrong with [service]" in the context of
  a recent fire, or otherwise asks for a root-cause analysis of a
  firing or recently-fired alert. Read-only; does not modify any
  alert or notification.
argument-hint: <alert name or rule id> [time window]
---

# Alert Investigate

Diagnose why a SigNoz alert fired. The skill correlates the alert's own
signal with neighbor signals around the fire window, and surfaces a
ranked list of likely causes with supporting evidence. It is the
companion to `signoz-explaining-alerts`: explain decodes the rule
statically; investigate diagnoses a specific incident.

## Prerequisites

This skill calls SigNoz MCP server tools heavily (`signoz_get_alert`,
`signoz_get_alert_history`, `signoz_execute_builder_query`,
`signoz_query_metrics`, `signoz_search_traces`, `signoz_search_logs`,
`signoz_get_trace_details`, etc.). Before running the workflow,
confirm the `signoz_*` tools are available. If they are not, the
SigNoz MCP server is not installed or configured; run `signoz-mcp-setup` first
to initialize or repair the MCP connection.

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
  `signoz_update_alert` directly.
- Run a free-form ad-hoc investigation without an alert as the anchor →
  `signoz-generating-queries`.

## Required inputs

| Input | Required | Source if missing |
|---|---|---|
| Alert identifier (rule ID or name) | yes | `$ARGUMENTS[0]` or recent context |
| Time window | no | default to most recent fire from `signoz_get_alert_history` |

If the alert name is fuzzy, this skill is **best-effort** (read-only):
1. Resolve the name as Step 1 describes and pick the closest match.
2. State the interpretation: "Investigating fire of 'High Error Rate -
   Checkout' (id 42) at 14:32 UTC. If you meant a different alert or
   fire, tell me."
3. Proceed.

If the complete history (Step 1 says when it is complete) has no firing
transition in the queried lookback window, **stop**: there is no fire window to
investigate. Respond with:
> "No firing events were returned for alert '[name]' in the last 7d, so
> there is no fire window to investigate. Use `signoz-explaining-alerts` to
> walk through the rule, or check whether the alert is enabled."

Never shorten this to "has not fired": retention or a rule recreated under a new
ID can empty a complete history. If the history is incomplete, say it could
not be fully read and give any fire count as "at least N". Report firing history, current
`state`, `disabled`, and delivery (no alert tool returns it) as separate facts.

## Workflow

The investigation runs in three tiers with strict early-stop gates.
Tier 1 always runs. Tier 2 runs only if tier 1 confirms a real fire.
Tier 3 runs only if tier 2 surfaces correlated anomalies. Skipping the
gates pulls hundreds of unnecessary traces and logs on quiet alerts.

### Step 1: Resolve alert + fire window (Tier 0)

1. If no rule id was given, call `signoz_list_alert_rules` with `filter`
   set to one distinctive word of the name (a bare word matches name,
   description, and labels, ignoring case), following `pagination.nextOffset`
   while `pagination.hasMore` is true. List unfiltered when no match is close.
2. Call `signoz_get_alert` for the full rule config, needed to know
   what query, threshold, and resource scope the alert evaluated. Read
   `signoz://alert/instructions` before interpreting its thresholds, units,
   evaluation, and `limit`/`order`, unless already read in this
   conversation. If the client cannot read it, work from the fields as
   returned and say which one you could not interpret.
3. Call `signoz_get_alert_history` with `timeRange: "7d"` and
   `order: "desc"`; omit `state` so the timeline includes firing and inactive
   transitions. While the completeness note reports more results, fetch the
   next page exactly as the note says. The history is complete only when the
   note says all matching results were returned (`hasMore=false`). A note
   that the tool could not count the rows, a failed call, or a pagination
   stopped early means incomplete history, even with no `nextCursor`.
   For "resolved" / "recovered", filter on `inactive`; `recovering` is a
   transient keep-firing state, not resolution.
   Pattern analysis needs the complete transition set. Rows are emitted per
   label-group `fingerprint`; do not interleave them. From the response:
   - **Build rule-wide incident windows** from distinct rows where
     `overallStateChanged: true`: an `overallState: "firing"` transition opens
     an incident; the next `overallState: "inactive"` closes it. Deduplicate
     matching timestamps and sort by `unixMilli` ascending before pairing.
     Default to the most recent incident unless `$ARGUMENTS[1]` selects another.
   - **Partition affected series by `fingerprint`** and retain each row's
     `labels`; they name the service, host, or other group that fired. Use
     only `stateChanged: true` rows to decide when that group fired and
     resolved, and which group should scope Tier 1–3 queries.
   - **Note the fire pattern** from rule-wide transitions or one named fingerprint:
     - `one-off` → single fire with a long quiet period before/after.
     - `sustained` → fires that stayed firing for ≥ 1 evaluation cycle.
     - `flapping` → ≥ 3 fires within a 1h window, alternating fire/resolve.
     - `recurring` → fires at regular intervals (cron-like, e.g., every hour).
   - Never infer flapping from different fingerprints. The pattern guides tiers 2/3.

### Step 2: Tier 1 (what fired and how hard)

This tier always runs. It establishes the fire is real (vs. transient
threshold tickle or flap) and quantifies the magnitude.

1. Read `signoz://query-builder/examples` before turning the stored query
   into a `signoz_execute_builder_query` request, and the guide for its
   kind when the grammar is unfamiliar: `signoz://traces/query-builder-guide`,
   `signoz://logs/query-builder-guide`, `signoz://metrics-aggregation-guide`,
   `signoz://promql/instructions`, or `signoz://ai/query-builder-guide`. If
   the client cannot read them, send `query` as `{start, end, requestType:
   "time_series", compositeQuery: {queries: <the rule's
   condition.compositeQuery.queries>}}` with Unix-ms bounds.
2. Re-run the alert's stored query (builder, formula, PromQL, or ClickHouse
   envelope) over a window centered on the fire start,
   `[fire_start - 30m, fire_start + 30m]`, for magnitude and context.
   - If the rule carries `limit` and `order` on a grouped query, also run
     it as stored over the evaluation window that fired,
     `[fire_start - evalWindow, fire_start]` (for a cumulative rule, from
     the schedule's last reset). SigNoz ranks the top-N groups over the
     whole requested window, so only this run shows the subset the rule
     evaluated; the centered hour can rank other groups. Record the cap as
     a finding: a breaching group outside the top N was never evaluated,
     and a `below` rule ordered descending can exclude every breaching
     series. The remediation is to update the rule without `limit`/`order`
     unless top-N alerting was the intent.
   - If the stored queries carry no bounds, the alert evaluated every
     series, but `signoz_execute_builder_query` still applies its own display
     `limit`. To check a specific fingerprint from Step 1, add its labels to
     the filter instead of raising the limit; to rank groups, use v5 `order`
     (`__result desc` for metrics/formulas, primary aggregation desc for
     logs/traces), never dashboard `orderBy`, and say when exactly `limit`
     groups came back.
3. Compute:
   - **Extreme value** during the fire window: the peak for an `above`
     rule, the trough for a `below` rule.
   - **Threshold breach magnitude**: `(peak - threshold) / threshold *
     100` for "above" alerts, inverted for "below", with the target
     converted to the series unit. When the target is 0 or the series is an
     anomaly score, report the absolute distance from the target instead.
   - **Fire duration**: the rule's overall firing→inactive interval, or the
     selected fingerprint's interval for a group-scoped investigation. Say which.
   - **Pre-fire baseline**: average value in the 30m before fire start.
4. **Early-stop gate**: if the breach magnitude is < 10% over the
   threshold AND the fire duration is < 1 evaluation window, classify
   as "marginal fire"; the alert may be too sensitive. Skip tiers 2
   and 3 and go to Step 5 with a single hypothesis: "threshold may be
   too tight, recommend tuning." The gate does not apply when no
   percentage could be computed; continue to Tier 2.

### Step 3: Tier 2 (neighbor signals vs baseline)

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
     trace data is available. A service's requests are its entry spans:
     filter these trace queries on `isEntryPoint = true OR isRoot = true`,
     and call a number computed over every span span-level.
   - **Host / VM alert** (`host.name = X`): CPU, memory, disk I/O,
     network I/O.
   - **K8s pod / namespace alert**: pod restarts, container CPU/memory
     limits, node pressure, recent rollouts.
3. For each neighbor signal:
   - Query both windows (fire + baseline) via
     `signoz_execute_builder_query` or `signoz_query_metrics`. Read
     `references/baseline-comparison.md` for the paired request, the delta
     formula, and what to do when the baseline window is unusable.
   - Compute the delta (% change in fire window vs baseline).
   - Rank by absolute delta.
4. **Early-stop gate**: if no neighbor signal shows ≥ 25% deviation
   from baseline, classify as "isolated fire: the alert's own signal
   moved but nothing else did." This is unusual and worth surfacing.
   Skip Tier 3 and go to Step 5 with hypotheses focused on the alert's
   own query (likely causes: data source change, instrumentation
   change, downstream silent failure that only shows in this metric).

### Step 4: Tier 3 (traces and logs at the fire window)

Run only if Tier 2 found correlated neighbor anomalies. Drill into
specific failing operations.

1. **Traces** (if the alert is service-scoped and traces are
   available):
   - Call `signoz_search_traces` for the fire window with filter:
     `service.name = <scope>` AND `has_error = true`. Cap at top 20.
   - Group by `name` and `status_message`. Surface the sample's top 3 with one
     trace ID each; do not call a 20-row sample count full-window frequency.
   - Optionally call `signoz_get_trace_details` for span attributes. Pass the
     search row's `trace_id` as `traceId`; the tool takes no time window,
     because SigNoz locates the trace by its ID.
2. **Logs** for the fire window:
   - Call `signoz_search_logs` with filter:
     `<scope_filter>` AND `severity_text IN ('ERROR', 'FATAL')`. Cap
     at top 20 most recent.
   - Group by `body` pattern (or `exception.type` if present). Surface
     the top 3 distinct messages with their counts in the sample.
3. Cross-reference: do the traces and logs point at the same
   downstream service, dependency, or code path? If so, that becomes
   the leading hypothesis.

### Step 5: Build the structured output

Use this exact section order. Lead with a TL;DR, because engineers
under pressure scan the top first and stop reading once they have what
they need. Every claim cites the MCP query that produced it, with no
generic "check logs / verify connectivity" filler.

**1. TL;DR**: one or two sentences, no more. Leading hypothesis,
overall confidence, blast radius, and the single most useful next
action. Example:
> "checkoutservice error rate hit 12.4% (threshold 5%) for 8m at
> 14:32 UTC; most likely cause is payments-api timing out
> (high confidence). Open trace `7af3a09b…` to see the failing call."

**2. What fired**
The alert (id, name), the fire window (absolute UTC + relative),
peak magnitude ("error rate hit 12.4% vs. 5% threshold, 148% over"),
fire duration, and the fire pattern (`one-off` / `sustained` /
`flapping` / `recurring` / `marginal`).

**3. Investigation trail**
The background the reader needs, then what was checked. Open with history
and context: earlier fires of the same rule in the history you fetched
(how many, when, what pattern), and a recent deploy or config change when
a query result or the user gave evidence of one. Then list each check,
starting with its result in words: "confirmed", "ruled out", or "not
checked" (a query that failed or timed out, with the error), followed by a
one-line finding. Write the result as a word, never as an emoji or symbol:
a host can strip those and the trail must still read correctly.
Example:
- History: third fire of this rule in 7d; the earlier two lasted under 5m.
- Confirmed, Tier 1: peak error rate 12.4%, fire was real (not marginal).
- Confirmed, Tier 2: payments error rate +8900%, p99 +1180%; downstream
  cascade.
- Ruled out, CPU / memory pressure: flat through the fire window.
- Confirmed, Tier 3: all 20 sampled error traces hit payments-api, same
  message.

**4. Likely causes** (ranked, max 3)
Each cause has three parts:
- **Hypothesis**: one sentence, specific. Bad: "service is unhealthy".
  Good: "checkout is timing out on calls to payments-api".
- **Evidence**: the supporting numbers from tiers 1/2/3, with the
  underlying query inline so the user can re-run it. State the
  neighbor signal, the delta vs baseline, the trace/log pattern that
  supports it.
- **Confidence**: `high` requires ≥2 of: temporal precedence,
  topology / dependency edge, shared service or entity, correlated
  metric/log/trace evidence, recent deploy or config change.
  `medium` is one tier's evidence with at least one of those
  signals. `low` is a single signal moved with no corroboration;
  in that case label it a "co-occurring signal," not a cause.

If only Tier 1 ran (marginal fire / no neighbor anomalies), output
fewer hypotheses with `low` confidence and explicitly call out the
limitation.

**5. Ruled out**
List candidates the evidence eliminated, each with a one-line reason, so
the user doesn't re-check them. Skip the section if there is nothing
meaningful to rule out.

**6. Suggested next steps**
Action items the user can take. Be concrete and use SigNoz-native
handles so the user can act immediately:
- Specific trace, dashboard, or alert to open
  (e.g., "open trace `7af3a09b…` in the SigNoz UI").
- Specific query to run with `signoz-generating-queries`: paste
  the exact filter and time window.
- "Tune this alert" if the fire was marginal: name the field
  (`matchType`, `target`, `recoveryTarget`) and the change to make
  via `signoz_update_alert`.
- "Open an incident" or "page the owning team" if the cause is
  cross-service.

**Mirroring as navigation chips.** Mirror up to 3 of these "Suggested
next steps" as host follow-up intents: the most actionable, alert-scoped
ones. Keep the rest in the report prose.

## Out of scope (v1)

- **Deployment / config-change correlation**: SigNoz MCP does not
  expose a deployments tool; do not fabricate one. If the user mentions
  a deploy, or a queried signal shows one (a rollout metric, a changed
  `service.version`), put it in the investigation trail as context; don't
  claim it caused the fire without the signal evidence.
- **Cross-service blast-radius walking**: investigating downstream
  callers of the alert's service. Out of scope to keep context
  bounded.
- **Long-horizon historical baselines**: Tier 2 compares to one
  prior-day window, not to weekly/monthly seasonality. If the user
  says "is this normal for a Friday afternoon", suggest an anomaly
  alert (`signoz-creating-alerts` with `anomaly_rule`).

## Guardrails

- **Three-tier early-stop is mandatory.** Apply both gates on every
  investigation.
- **Anchor every claim to an MCP query result**, and show that query with
  each hypothesis. If evidence is missing, lower confidence and say so.
- **A failed or partial read rules nothing out.** An errored or timed-out query
  is "not checked". Capped trace or log samples support claims only about their
  rows; "none", "all", or a total for the window needs a complete result.
- **Keep it short.** The report is a triage card, not a postmortem: every
  section adds evidence the user couldn't already see in the alert payload.
- **Correlation ≠ causation.** Label something a cause only when at least
  two of the Step 5 confidence signals converge. A single time-aligned
  anomaly is a "co-occurring signal," not a cause; say so explicitly.
- **Don't recommend the obvious.** Replace "check logs" or "verify
  connectivity" with specific queries, traces, or filters the user can run
  immediately.
- **No fabricated identifiers.** Trace IDs, span names, alert rule IDs,
  channel names, deploy IDs: every identifier in the output must come from
  a real MCP response.
- **Report uncertainty honestly.** If no hypothesis reaches medium
  confidence, the answer is "No clear root cause found; here's what we
  checked and what's ruled out." Do not promote a low-confidence guess to
  the leading hypothesis; a false cause costs more incident time than none.
- **Prefer resource-attribute filters** in every drill-down query; they
  directly affect query speed at scale.
- **Do not modify any alert.** Investigate is read-only. If the user
  says "and tighten this alert", surface that as a next-step
  recommendation; do not call `signoz_update_alert`.
- **Time zones.** State fire windows in UTC alongside relative time
  ("14:32 UTC, 2h ago") so every consumer agrees on the window.

## Examples

**User:** "Why did the checkout error rate alert fire?"

**Agent:**
1. Resolves alert: "High Error Rate - Checkout" (id 42).
2. `signoz_get_alert_history` → most recent fire 2h ago at 14:32 UTC,
   sustained for 8m, single fire (not flapping).
3. **Tier 1**: re-runs error-rate formula over `[14:02, 15:02]`. Peak
   error rate 12.4% (vs 5% threshold, 148% over). Pre-fire baseline
   0.3%. Real fire, not marginal.
4. **Tier 2**: pulls neighbor signals for `service.name = checkout`:
   - p99 latency, peak step: 4.1s vs 320ms mean of baseline steps (+1180%).
   - Throughput: -42% (drop).
   - Downstream `payments` error rate: 18% vs 0.2% baseline (+8900%).
   - CPU/memory: flat (no resource pressure).
5. **Tier 3**: traces for `service.name = checkout, has_error = true`
   in the fire window: top operation `POST /checkout/submit`, top
   error message "context deadline exceeded calling payments-api".
   All 20 sampled error traces hit the same downstream URL; 17 of 20
   sampled error logs read "payments client timeout".
6. **Output**:

   > **TL;DR**: checkoutservice error rate hit 12.4% (threshold 5%)
   > for 8m at 14:32 UTC. Most likely cause: payments-api timing out
   > (high confidence; converging trace + log + neighbor evidence).
   > Open trace `7af3a09b…` to see the failing call.

   - **What fired**: alert 42 fired 2h ago at 14:32 UTC, sustained
     8m. Error rate peaked at 12.4% (148% over threshold).
   - **Investigation trail**:
     - History: the only fire of this rule in the last 7d.
     - Confirmed, Tier 1: peak 12.4% vs 5% threshold, pre-fire baseline
       0.3%. Real fire.
     - Confirmed, Tier 2: payments error rate +8900%, p99 latency +1180%,
       throughput −42%.
     - Ruled out, CPU / memory pressure on checkout: flat.
     - Confirmed, Tier 3: all 20 sampled error traces hit payments-api with
       `context deadline exceeded`; 17 of 20 sampled logs are timeouts.
   - **Likely causes** (high confidence): payments service errors
     cascading into checkout. Evidence converges across topology
     (checkout → payments edge), temporal precedence (payments
     errors lead checkout p99), and shared entity (every sampled
     error trace targets the payments-api URL).
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
   minutes: a flapping pattern.
3. **Tier 1**: peak 84% (threshold 80%, only 5% over). Each fire
   lasted 2-4 minutes. Marginal: the value hovered near threshold.
   `matchType = at_least_once` made each blip trigger.
4. Early-stop kicks in. Skip tiers 2/3.
5. **Output**:

   > **TL;DR**: alert 88 has been flapping on `prod-api-3`: 7 fires
   > in the last 1h, each 2–4m, all within 5% of the 80% threshold.
   > No clear root cause; this is threshold tuning, not an incident.
   > Switch `matchType` to `on_average` or add hysteresis to stop
   > the noise.

   - **What fired**: alert 88, host `prod-api-3`, fire pattern
     `flapping`. 7 fires in the last 1h, each 2–4m. Peak 84% (5%
     over the 80% threshold).
   - **Investigation trail**:
     - History: 7 fires in the last 1h, alternating fire and resolve.
     - Confirmed, Tier 1: every fire was within 5% of threshold; duration
       short; baseline already at 70–75%. Marginal fire; early-stop
       triggered, Tier 2/3 skipped.
   - **Likely causes** (low / co-occurring signal only): threshold
     tuned too tight or `matchType` is too sensitive. Evidence:
     every fire was within 5% of threshold; baseline already runs
     at 70–75%. Not promoted to a "cause": single signal, no
     corroboration.
   - **Ruled out**: real CPU saturation incident (peaks too small
     and short-lived; baseline already near threshold).
   - **Next steps**: change `matchType` to `on_average` (smooths
     transient spikes) OR raise threshold to 85% with hysteresis
     (`recoveryTarget: 75`). Use `signoz_update_alert` to apply.

---

**User:** "RCA for the log volume alert that fired last night"

**Agent:**
1. Resolves alert: "Error Log Volume Spike" (id 14, no service
   filter; groupBy `service.name`).
2. History: fired at 03:12 UTC, sustained 22m; the firing row's
   `labels` name `service.name = inventory` as the firing series.
3. **Tier 1**: re-runs log count for inventory in fire window. Peak
   3,400 errors/min vs 1,000/min threshold (240% over). Pre-fire
   baseline 12/min. Real, large fire.
4. **Tier 2**: neighbor signals for `service.name = inventory`:
   - Request error rate: +600%.
   - p99 latency: +30% (mild).
   - CPU: -80% (collapsed). Memory: -60%.
   - Pod restarts (k8s): 4 in fire window.
5. **Tier 3**: logs for inventory in fire window. Top message in the
   20-row sample: "OOMKilled restarting" (14 of 20). Top trace error:
   graceful-shutdown exceptions.
6. **Output**:

   > **TL;DR**: log volume alert 14 fired at 03:12 UTC for
   > `service.name = inventory`, sustained 22m at 240% over threshold.
   > Most likely cause: inventory pods OOM-killed and restarted 4
   > times (high confidence). Check container memory limits for the
   > inventory deployment.

   - **What fired**: alert 14 fired at 03:12 UTC for service
     `inventory`, sustained 22m, 240% over threshold.
   - **Investigation trail**:
     - History: first fire of this rule in the last 7d.
     - Confirmed, Tier 1: peak 3,400 errors/min vs 1,000/min threshold;
       pre-fire baseline 12/min. Real fire.
     - Confirmed, Tier 2: request error rate +600%; CPU/memory collapsed
       (−80%/−60%); 4 pod restarts in window.
     - Ruled out, p99 latency as the driver: only +30%.
     - Confirmed, Tier 3: top sampled log message "OOMKilled restarting"
       (14 of 20); top trace error: graceful-shutdown exceptions.
   - **Likely causes** (high confidence): inventory pods OOM-killed
     and restarted 4 times during the window. Evidence converges
     across topology (single service), temporal precedence (memory
     fell to zero before error spike), shared entity (all log lines
     from `service.name = inventory`), and a single coherent
     pattern (OOM → restart → graceful-shutdown noise).
   - **Ruled out**: upstream traffic surge (throughput unchanged). Not
     ruled out: request-path failures (6 of 20 sampled logs are not
     restarts); count restart vs all error logs to separate them.
   - **Next steps**: check container memory limits for inventory
     pods; review recent deploys; consider whether the alert should
     exclude restart-related error patterns or whether the
     underlying OOM is the real concern.
