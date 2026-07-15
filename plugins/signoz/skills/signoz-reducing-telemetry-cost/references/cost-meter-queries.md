# Cost Meter query templates

## Contents
- Why `signoz_execute_builder_query` (not `signoz_query_metrics`) for totals
- Meter metrics
- Per-signal total (template)
- Breakdown by environment / service
- Converting and reconciling the numbers

## Why `signoz_execute_builder_query` (not `signoz_query_metrics`) for totals

Cost Meter data lives in the metrics store under `source: "meter"`. Query it with
`signoz_execute_builder_query` and an explicit `timeAggregation: "sum"`.

Do **not** use `signoz_query_metrics` for Cost Meter totals. Use
`signoz_execute_builder_query`, which honors the explicit raw builder `sum` required for these
meter metrics.

## Meter metrics

| metricName | unit | signal |
|---|---|---|
| `signoz.meter.span.size` | bytes → GB | traces volume (cost) |
| `signoz.meter.log.size` | bytes → GB | logs volume (cost) |
| `signoz.meter.metric.datapoint.count` | samples | metrics volume (cost) |
| `signoz.meter.span.count` | count | span count (context only, not cost) |
| `signoz.meter.log.count` | count | log record count (context only, not cost) |

## Per-signal total (template)

Call `signoz_execute_builder_query` once per meter metric with `start`/`end` in unix ms
(only `metricName` changes):

```json
{
  "schemaVersion": "v1",
  "start": <start_ms>, "end": <end_ms>,
  "requestType": "time_series",
  "compositeQuery": { "queries": [ { "type": "builder_query", "spec": {
    "name": "A", "signal": "metrics", "source": "meter", "stepInterval": 86400,
    "aggregations": [ { "metricName": "signoz.meter.span.size",
                        "timeAggregation": "sum", "spaceAggregation": "sum" } ],
    "disabled": false
  } } ] }
}
```

Sum all values across every series/time-bucket in the response, excluding datapoints with
`partial: true`; they are incomplete edge buckets.

## Breakdown by environment / service

Add a `groupBy` to the same spec:

```json
"groupBy": [ { "name": "deployment.environment" } ]
```
or
```json
"groupBy": [ { "name": "service.name" } ]
```

## Converting and reconciling the numbers

- GB divisor = 1,000,000,000 (`1e9`). "M samples" divisor = 1,000,000 (`1e6`).
- A grouped sum can differ from the ungrouped total. Use the ungrouped total for absolute cost
  figures; use grouped values only for percentages and ranking.
