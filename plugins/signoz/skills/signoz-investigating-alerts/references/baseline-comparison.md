# Baseline Comparison Templates

## Contents

- Window selection
- Builder query template (`signoz:signoz_execute_builder_query`)
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

## Builder query template (`signoz:signoz_execute_builder_query`)

For each neighbor signal, run the same builder query twice — once per
window. The only thing that changes is `start` / `end`.

Pseudo-shape (the actual MCP tool input shape is in the SigNoz MCP
docs, but the conceptual fields):

```jsonc
{
  "compositeQuery": {
    "queryType": "builder",
    "panelType": "graph",
    "queries": [
      {
        "type": "builder_query",
        "spec": {
          "name": "A",
          "signal": "<traces|logs|metrics>",
          "aggregations": [ /* per neighbor-signals.md */ ],
          "filter": { "expression": "<resource attribute filter from the alert>" },
          "groupBy": [ /* mirror the alert's groupBy when relevant */ ]
        }
      }
    ]
  },
  "start": "<window start, RFC3339 UTC>",
  "end":   "<window end, RFC3339 UTC>"
}
```

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
  query: signoz:signoz_execute_builder_query — p99(durationNano) on
         service.name = checkout, fire window 14:32-14:40 UTC vs
         baseline 14:32-14:40 UTC (24h prior)
```

The agent should embed these in the "Likely causes — Evidence"
sections of the final structured output. The query line lets the user
re-run the comparison without rebuilding the parameters.

## When the baseline is invalid

Skip baseline comparison and call out the limitation if:

- The baseline window overlaps with another firing of the same alert
  (`signoz:signoz_get_alert_history` shows a fire in the baseline window).
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

- `signoz:signoz_search_traces` with the resource filter + `hasError = true`.
  Cap at 20. Group by `name` (operation) and surface the top 3 by
  count with one representative `trace_id` each.
- `signoz:signoz_search_logs` with the resource filter +
  `severity_text IN ('ERROR', 'FATAL')`. Cap at 20 most recent. Group
  by message pattern (or `exception.type`) and surface the top 3.
- For deep drill on one trace, `signoz:signoz_get_trace_details(trace_id)`
  extracts span-level attributes (DB statement, peer service, status
  code) — useful when the operation name alone doesn't identify the
  failing call.
