# Baseline Comparison Templates

## Contents

- Window selection
- Builder query template (`signoz_execute_builder_query`)
- Computing the delta
- Surfacing the comparison
- When the baseline is invalid
- Logs / traces drill-down (Tier 3)

Tier 2 of the investigation pairs each neighbor-signal query against a
fire-window query and a baseline-window query, then computes a delta.
This file shows how to format those calls cleanly via the SigNoz MCP
tools.

## Window selection

Given a fire that started at `T_fire_start` and lasted `D` minutes:

- **Fire window**: `[T_fire_start - 5m, T_fire_start + D + 5m]`. The
  ±5m buffer catches lead-in / cool-down behavior the threshold
  evaluation may have missed.
- **Baseline window**: `[T_fire_start - 24h - 5m, T_fire_start - 24h + D + 5m]`.
  Same hour, previous day, same duration.
- If the alert has been firing for > 4 hours, expand the baseline to a
  rolling 7-day median over the same time-of-day to avoid biasing
  against another fire on the prior day.

State both window timestamps in **UTC absolute** in the output, plus a
relative description ("24h before fire").

## Builder query template (`signoz_execute_builder_query`)

For each neighbor signal, run the same builder query twice, once per
window. The only thing that changes is `start` / `end`.

Take the full request shape from the MCP server:
`signoz://traces/query-builder-guide` has a complete time-series request
for p99 request latency, and `signoz://query-builder/examples` has one
request per query type. The tool's input schema describes the outer
fields; `formatOptions` and `variables` are optional. If the client cannot
read those resources, start from this minimal request for p99 request
latency, set `start` and `end` to each comparison window, and adapt the
`spec` to the signal:

```json
{
  "query": {
    "start": 1756386047000,
    "end": 1756387847000,
    "requestType": "time_series",
    "compositeQuery": {
      "queries": [
        {
          "type": "builder_query",
          "spec": {
            "name": "A",
            "signal": "traces",
            "stepInterval": 60,
            "filter": { "expression": "service.name = 'checkout' AND (isEntryPoint = true OR isRoot = true)" },
            "aggregations": [ { "expression": "p99(duration_nano)" } ]
          }
        }
      ]
    }
  }
}
```

`start` and `end` are Unix milliseconds; `stepInterval` is seconds. A
service's requests are its entry spans, which the filter above selects.
Without `isEntryPoint = true OR isRoot = true` the query covers every span
the service records; label that result span-level.

Keep the same positive limit and Query Builder v5 `order` in the fire and
baseline requests. In a query you write for Tier 2, set them on standalone
queries and formula results only, and leave `limit` unset on every query a
formula references. For time series, the limit ranks groups over the whole
window, so a short-lived local spike can be outside the top N. Dashboard
`orderBy` is not valid in this execution payload.

A stored formula alert is the exception: first replay its component limits
exactly as stored. If any formula input carries a limit, run a second
fire/baseline comparison with that input's limit and order removed; SigNoz
applies an input's limit before the formula runs, so independent top-N
inputs can hide the group that should have fired. Find inputs by inspecting
every formula expression, including formulas with `disabled: true`, and
following formula references to all `builder_query` leaves. This dependency
walk changes only the comparison bounds; it does not prove deterministic
formula-to-formula evaluation order.

## Computing the delta

For each signal, after running both windows:

```text
delta_pct = (fire_value - baseline_value) / max(baseline_value, epsilon) * 100
```

- Use the **peak** of the fire window when the alert direction is
  "above" (op `above`, or the legacy code `"1"`), and the **trough** when
  the direction is "below" (op `below`, or `"2"`). For the baseline use the
  **mean** in either case to get a stable reference.
- Name each statistic for what it is. The peak of a per-step p99 series is
  the highest step's p99, and the mean of that series is a mean of step
  p99s; neither is the window's p99, so do not report either as "p99
  latency" without saying which it is.
- Use `epsilon = max(baseline_value * 0.01, signal-specific floor)` to
  avoid divide-by-zero on metrics that idle at 0 (e.g., error rate).
- Clamp `delta_pct` for display at ±10000%; beyond that the absolute
  values matter more than the ratio.

## Surfacing the comparison

In the Tier 2 output for each signal, present:

```
- p99 latency, peak 1m step: 4.1s vs 320ms baseline mean of 1m steps (+1180%)
  query: signoz_execute_builder_query, p99(duration_nano) on
         service.name = checkout entry spans, 60s steps, fire window
         14:32-14:40 UTC vs baseline 14:32-14:40 UTC (24h prior)
```

The agent should embed these in the "Likely causes - Evidence"
sections of the final structured output. The query line lets the user
re-run the comparison without rebuilding the parameters.

## When the baseline is invalid

Skip baseline comparison and call out the limitation if:

- The baseline window overlaps with another firing of the same alert
  (`signoz_get_alert_history` shows a fire in the baseline window).
  In that case use a 7-day median or the user's confirmed
  known-healthy window.
- The service was deployed within 24h before the baseline window;
  the baseline reflects pre-deploy behavior. Note this and either
  use a median or explicitly state "no good baseline available".
- The alert is `anomaly_rule` (Z-score). The rule already encodes a
  baseline; pulling another comparison usually adds noise. Skip Tier
  2's per-signal baselines and instead focus Tier 3 on the fire window
  alone.

## Logs / traces drill-down (Tier 3)

Tier 3 does not require a baseline: the question is "what happened",
not "what changed". Run a single fire-window query for each:

- `signoz_search_traces` with the resource filter + `has_error = true`.
  Cap at 20. Group the sample by `name` (operation) and `status_message`, and
  surface the top 3 with one representative `trace_id` each.
- `signoz_search_logs` with the resource filter +
  `severity_text IN ('ERROR', 'FATAL')`. Cap at 20 most recent. Group
  by message pattern (or `exception.type`) and surface the top 3.
- For deep drill on one trace, pass the search row's `trace_id` to
  `signoz_get_trace_details` as `traceId`, with no time window. Use its
  span attributes (DB statement, peer service, status code) when the
  operation name alone doesn't identify the failing call.
