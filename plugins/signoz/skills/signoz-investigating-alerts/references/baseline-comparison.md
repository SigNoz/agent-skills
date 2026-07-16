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

For each neighbor signal, run the same builder query twice — once per
window. The only thing that changes is `start` / `end`.

This is a complete tool-argument example for trace p99 latency. Replace the
Unix-millisecond `start` / `end`, treat `stepInterval: 60` as the
window-appropriate seconds placeholder, and adapt the `spec` using the MCP
guide for the chosen signal. Keep the outer `query`, `formatOptions`, and
`variables` fields.

```json
{
  "query": {
    "schemaVersion": "v1",
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
            "disabled": false,
            "stepInterval": 60,
            "limit": 100,
            "order": [
              {"key": {"name": "p99(duration_nano)"}, "direction": "desc"}
            ],
            "having": { "expression": "" },
            "filter": { "expression": "service.name = 'checkout'" },
            "aggregations": [
              { "expression": "p99(duration_nano)" }
            ],
            "groupBy": []
          }
        }
      ]
    },
    "formatOptions": {
      "formatTableResultForUI": false,
      "fillGaps": false
    },
    "variables": {}
  }
}
```

Keep the same positive limit and Query Builder v5 `order` in the fire and
baseline requests. For time series, the limit ranks groups over the whole
window, so a short-lived local spike can be outside the top N. Dashboard
`orderBy` is not valid in this execution payload. For a formula alert, first
replay the stored component limits exactly. If any formula input is below
10000, run a second fire/baseline comparison with that input raised to 10000;
base limits are applied before formula evaluation, so independent top-N inputs
can hide the group that should have fired. Find inputs by inspecting every
formula expression, including formulas with `disabled: true`, and following
formula references to all `builder_query` leaves. This dependency walk changes
only the comparison bounds; it does not prove deterministic formula-to-formula
evaluation order.

## Computing the delta

For each signal, after running both windows:

```text
delta_pct = (fire_value - baseline_value) / max(baseline_value, epsilon) * 100
```

- Use the **peak** of the fire window when the alert direction is
  "above" (op `"1"`), and the **trough** when the direction is "below"
  (op `"2"`). For the baseline use the **mean** in either case to get
  a stable reference.
- Use `epsilon = max(baseline_value * 0.01, signal-specific floor)` to
  avoid divide-by-zero on metrics that idle at 0 (e.g., error rate).
- Clamp `delta_pct` for display at ±10000% — beyond that the absolute
  values matter more than the ratio.

## Surfacing the comparison

In the Tier 2 output for each signal, present:

```
- p99 latency: 4.1s vs 320ms baseline (+1180%)
  query: signoz_execute_builder_query — p99(duration_nano) on
         service.name = checkout, fire window 14:32-14:40 UTC vs
         baseline 14:32-14:40 UTC (24h prior)
```

The agent should embed these in the "Likely causes — Evidence"
sections of the final structured output. The query line lets the user
re-run the comparison without rebuilding the parameters.

## When the baseline is invalid

Skip baseline comparison and call out the limitation if:

- The baseline window overlaps with another firing of the same alert
  (`signoz_get_alert_history` shows a fire in the baseline window).
  In that case use a 7-day median or the user's confirmed
  known-healthy window.
- The service was deployed within 24h before the baseline window —
  the baseline reflects pre-deploy behavior. Note this and either
  use a median or explicitly state "no good baseline available".
- The alert is `anomaly_rule` (Z-score). The rule already encodes a
  baseline; pulling another comparison usually adds noise. Skip Tier
  2's per-signal baselines and instead focus Tier 3 on the fire window
  alone.

## Logs / traces drill-down (Tier 3)

Tier 3 does not require a baseline — the question is "what happened",
not "what changed". Run a single fire-window query for each:

- `signoz_search_traces` with the resource filter + `has_error = true`.
  Cap at 20. Group the sample by `name` (operation) and `status_message`, and
  surface the top 3 with one representative `trace_id` each.
- `signoz_search_logs` with the resource filter +
  `severity_text IN ('ERROR', 'FATAL')`. Cap at 20 most recent. Group
  by message pattern (or `exception.type`) and surface the top 3.
- For deep drill on one trace, map the search row's `trace_id` to the details
  input: `signoz_get_trace_details` with `{ "traceId": "<returned trace_id>",
  "start": "<fire_start_ms>", "end": "<fire_end_ms>" }`.
  It extracts span-level attributes (DB statement, peer service, status code)
  when the operation name alone doesn't identify the failing call.
