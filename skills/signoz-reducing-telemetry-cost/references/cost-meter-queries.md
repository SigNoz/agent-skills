# Cost Meter query templates

## Contents
- Why `signoz_execute_builder_query` (not `signoz_query_metrics`) for totals
- Discover meter metrics
- Per-signal total (template)
- Breakdown by environment / service
- Converting and reconciling the numbers

## Why `signoz_execute_builder_query` (not `signoz_query_metrics`) for totals

Cost Meter data lives in the metrics store under `source: "meter"`. Query it with
`signoz_execute_builder_query` and an explicit `timeAggregation: "sum"`.

Do **not** use `signoz_query_metrics` for Cost Meter totals. Use
`signoz_execute_builder_query`, which honors the explicit raw builder `sum` required for these
meter metrics.

## Discover meter metrics

Always call `signoz_list_metrics` with `source: "meter"` before querying. Treat its returned
metric names, types, temporalities, and units as the live source of truth; the meter set evolves.
Select the discovered size, datapoint, or record-count metric that matches the requested signal.
Names such as `signoz.meter.log.size` and `signoz.meter.span.count` are examples, not an
exhaustive table. Do not query an example name that discovery did not return. Copy the selected
metric's returned `temporality` into the raw builder aggregation.

## Per-signal total (template)

Call `signoz_execute_builder_query` once per discovered meter metric. Replace
`<discovered_meter_metric_name>` with the live name returned by `signoz_list_metrics`; replace
the example `start` and `end` integers with the requested range in Unix milliseconds.

```json
{
  "query": {
    "schemaVersion": "v1",
    "start": 1751932800000,
    "end": 1752537600000,
    "requestType": "time_series",
    "compositeQuery": {
      "queries": [
        {
          "type": "builder_query",
          "spec": {
            "name": "A",
            "signal": "metrics",
            "source": "meter",
            "stepInterval": 3600,
            "limit": 100,
            "order": [
              {"key": {"name": "__result"}, "direction": "desc"}
            ],
            "aggregations": [
              {
                "metricName": "<discovered_meter_metric_name>",
                "temporality": "<discovered_temporality>",
                "timeAggregation": "sum",
                "spaceAggregation": "sum"
              }
            ],
            "disabled": false
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

The 100-group bound ranks groups across the whole requested window. A group
with a short-lived local spike can fall outside the returned top N; narrow the
window or choose a deliberate positive override when that matters. Query Range
uses `order`; `orderBy` is only for dashboard editor payloads.

Meter buckets are hourly, so keep `stepInterval: 3600`. Sum all complete hourly values across
every returned series, excluding datapoints with `partial: true`; they are incomplete edge
buckets. Use the unit returned by discovery when labeling or converting the total.

## Breakdown by environment / service

Call `signoz_get_field_keys` with `signal: "metrics"` and `source: "meter"` before grouping.
Use only a returned key and losslessly copy its `name`, `fieldDataType`, `fieldContext`, and
`signal`; raw builder queries do not reliably infer an omitted or ambiguous field descriptor.
Add the complete returned field to the same spec:

```json
"groupBy": [
  {
    "name": "<returned_field_name>",
    "fieldDataType": "<returned_field_data_type>",
    "fieldContext": "<returned_field_context>",
    "signal": "<returned_signal>"
  }
]
```

## Converting and reconciling the numbers

- GB divisor = 1,000,000,000 (`1e9`). "M samples" divisor = 1,000,000 (`1e6`).
- A grouped sum can differ from the ungrouped total. Use the ungrouped total for absolute cost
  figures; use grouped values only for percentages and ranking.
