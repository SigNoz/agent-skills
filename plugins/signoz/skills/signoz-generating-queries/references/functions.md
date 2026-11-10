# Functions and window comparison

Read this when the user compares a window with an earlier one (week over
week, day over day, before and after a deploy), or asks for a series that is
smoothed, has no gaps, has spikes capped, shows the change per step, or shows
a running total.

## Where functions go

`functions` is a list of `{name, args}` objects; each arg is
`{"value": <number>}`. SigNoz applies them in order, after the aggregation and
before any formula. Three tools take the list as their `functions` parameter:
`signoz_query_metrics` (it applies to query A), `signoz_aggregate_logs`, and
`signoz_aggregate_traces`. `formulaQueries` items on `signoz_query_metrics`
take no functions. In `signoz_execute_builder_query`, `functions` goes on the
`spec` of each `builder_query`.

On a scalar request (`requestType: "scalar"`):

- `signoz_aggregate_logs` and `signoz_aggregate_traces`: only `timeShift` has
  an effect. SigNoz skips the other functions; set
  `requestType: "time_series"` to use them.
- `signoz_query_metrics`: the functions run on each series before `reduceTo`.

## Compare a window with an earlier one

`timeShift` reads the window that many seconds earlier and returns its points
on the current window's timestamps. The number is positive: `3600` is one hour
back, `86400` one day, `604800` one week.

Pick the shape from the question:

- **Two numbers or two series to read side by side:** call the same tool
  twice with the same arguments, once without `timeShift` and once with
  `functions: [{"name": "timeShift", "args": [{"value": 604800}]}]`. Both
  results have the same timestamps, so compare them point by point. On a
  scalar request the second call returns last week's value for the same
  window.
- **The difference or the ratio in one result:** use
  `signoz_execute_builder_query` with two builder queries that differ only in
  `functions`, and a `builder_formula`. Use `A - B` for the change and
  `(A - B) / B * 100` for the change in percent.

Error logs in the last hour against the same hour last week, as the change per
15-minute step (tool arguments for `signoz_execute_builder_query`):

```json
{
  "query": {
    "schemaVersion": "v1",
    "start": 1794285480000,
    "end": 1794289080000,
    "requestType": "time_series",
    "compositeQuery": {
      "queries": [
        {
          "type": "builder_query",
          "spec": {
            "name": "A",
            "signal": "logs",
            "stepInterval": 900,
            "aggregations": [{ "expression": "count()" }],
            "filter": { "expression": "severity_text = 'ERROR'" }
          }
        },
        {
          "type": "builder_query",
          "spec": {
            "name": "B",
            "signal": "logs",
            "stepInterval": 900,
            "aggregations": [{ "expression": "count()" }],
            "filter": { "expression": "severity_text = 'ERROR'" },
            "functions": [{ "name": "timeShift", "args": [{ "value": 604800 }] }]
          }
        },
        {
          "type": "builder_formula",
          "spec": {
            "name": "F1",
            "expression": "A - B",
            "limit": 100,
            "order": [{ "key": { "name": "__result" }, "direction": "desc" }]
          }
        }
      ]
    },
    "formatOptions": { "formatTableResultForUI": false, "fillGaps": false },
    "variables": {}
  }
}
```

- Leave `limit` unset on A and B, because SigNoz applies an input's limit
  before the formula runs.
- Give A and B the same filter, `groupBy`, and `stepInterval`, so the formula
  pairs matching series at matching timestamps.
- The first and last steps of a window are often partial (`"partial": true`),
  in both queries. Compare full steps, or say that the edges are partial.
- Report both windows in absolute UTC, for example "10:00 to 11:00 UTC on
  2026-11-10 against the same hour on 2026-11-03".

## Other functions

| Function | Args | What it does | Use it for |
|---|---|---|---|
| `cutOffMin`, `cutOffMax` | threshold | Removes the points below or above the threshold. | Hiding idle hosts from a chart. |
| `clampMin`, `clampMax` | threshold | Sets the points below or above the threshold to the threshold. | Capping spikes without hiding them. |
| `runningDiff` | none | Replaces each point with the change from the point before, and drops the first point. | A gauge as change per step, such as disk usage as bytes written per step. Add `clampMin` with `0` after it to remove the negative step that a reset gives. |
| `cumulativeSum` | none | Replaces each point with the sum of all points up to it. The total starts again with each window. | A running total of errors in the window. |
| `ewma3`, `ewma5`, `ewma7` | optional alpha | Exponentially weighted average; the default alpha is 0.5, 0.333, or 0.25. A higher alpha follows the raw series more closely. | Smoothing a noisy trend. |
| `median3`, `median5`, `median7` | none | Median of the 3, 5, or 7 points around each point. A spike that lasts one step disappears. | Removing one-step spikes from a trend. |
| `fillZero` | none | Adds a zero at each step with no data. | Counts of sparse events, such as failed requests. |
| `absolute`, `log2`, `log10` | none | Transform each value. Zero and negative values have no logarithm. | Series with very different sizes on one chart. |

`anomaly` is for anomaly alert rules; see `signoz-creating-alerts`.
