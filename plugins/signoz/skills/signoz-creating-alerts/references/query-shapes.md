# Common alert query shapes — `signoz-creating-alerts`

Three JSON patterns cover most non-trivial alerts. The
`signoz://alert/examples` MCP resource is the authoritative source —
these are pedagogical illustrations of the same shapes.

## Error rate (formula)

Two component queries + a formula. Component queries A and B carry
`disabled: true` so only the formula F1 renders in the alert chart;
the raw counts are intermediate, not the alert signal.

```json
{
  "queries": [
    { "type": "builder_query", "spec": { "name": "A", "signal": "traces",
        "disabled": true,
        "aggregations": [{ "expression": "count()" }],
        "filter": { "expression": "hasError = true" } } },
    { "type": "builder_query", "spec": { "name": "B", "signal": "traces",
        "disabled": true,
        "aggregations": [{ "expression": "count()" }],
        "filter": { "expression": "" } } },
    { "type": "builder_formula",
      "spec": { "name": "F1", "expression": "A * 100 / B" } }
  ],
  "selectedQueryName": "F1"
}
```

## p99 latency by service

Single trace query with `groupBy` for per-service breakdown. Threshold
target is in **nanoseconds** (2s → 2000000000), `targetUnit: "ns"`.

```json
{
  "queries": [
    { "type": "builder_query", "spec": { "name": "A", "signal": "traces",
        "aggregations": [{ "expression": "p99(durationNano)" }],
        "groupBy": [{ "name": "service.name", "fieldContext": "resource",
                      "fieldDataType": "string" }] } }
  ]
}
```

## Log volume spike

Count of error / fatal logs grouped by service.

```json
{
  "queries": [
    { "type": "builder_query", "spec": { "name": "A", "signal": "logs",
        "aggregations": [{ "expression": "count()" }],
        "filter": { "expression": "severity_text IN ('ERROR', 'FATAL')" },
        "groupBy": [{ "name": "service.name", "fieldContext": "resource",
                      "fieldDataType": "string" }] } }
  ]
}
```

For absent-data, anomaly, PromQL, and ClickHouse SQL alerts, read the
`signoz://alert/examples` MCP resource for current shapes.
