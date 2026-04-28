# Alert Rule JSON Schema Reference

Reference for building SigNoz alert rules via `signoz_create_alert`. The MCP
server also exposes `signoz://alert/instructions` and
`signoz://alert/examples` resources — read those for additional context.

---

## Root Structure

```json
{
  "alert": "string (required — descriptive alert name)",
  "alertType": "METRIC_BASED_ALERT | LOGS_BASED_ALERT | TRACES_BASED_ALERT | EXCEPTIONS_BASED_ALERT",
  "ruleType": "threshold_rule | promql_rule | anomaly_rule",
  "condition": { ... },
  "description": "string (optional)",
  "labels": { "severity": "info | warning | critical", ... },
  "annotations": { "description": "...", "summary": "..." },
  "disabled": false,
  "preferredChannels": ["channel-name"],
  "evaluation": { ... },
  "notificationSettings": { ... }
}
```

**Auto-applied defaults (omit these — the server sets them):**
- `version` → "v5"
- `schemaVersion` → "v2alpha1"
- `source` → "mcp"
- `labels.severity` → "warning" (if not set)
- `annotations` → default templates with `{{$value}}` and `{{$threshold}}`

---

## Alert Types and Signals

| alertType | signal (in builder query) | Use for |
|-----------|--------------------------|---------|
| METRIC_BASED_ALERT | metrics | CPU, memory, request rate, latency metrics |
| LOGS_BASED_ALERT | logs | Log patterns, error counts, log volume |
| TRACES_BASED_ALERT | traces | Span latency, error rates, throughput |
| EXCEPTIONS_BASED_ALERT | (clickhouse_sql) | Exception counts, stack traces |

**Constraint:** The `signal` field in builder queries must match the
`alertType`. Using `signal: "logs"` with `METRIC_BASED_ALERT` will fail
validation.

---

## Rule Types

| ruleType | Description | Constraints |
|----------|-------------|-------------|
| threshold_rule | Static threshold comparison | Works with all alert types |
| promql_rule | PromQL expression evaluation | Requires `queryType: "promql"` |
| anomaly_rule | Seasonal anomaly detection (Z-score) | Only with METRIC_BASED_ALERT |

---

## Condition Object (required)

```json
{
  "condition": {
    "compositeQuery": { ... },
    "selectedQueryName": "A",
    "thresholds": { ... },
    "alertOnAbsent": false,
    "absentFor": 0,
    "algorithm": "zscore",
    "seasonality": "daily"
  }
}
```

- `compositeQuery` — **required**, the query definition
- `selectedQueryName` — which query/formula triggers the alert (auto-defaults
  to first query name if omitted)
- `thresholds` — **required** (unless `alertOnAbsent: true`)
- `alertOnAbsent` / `absentFor` — alert when no data is received for N ms
- `algorithm` / `seasonality` — only for `anomaly_rule`

---

## Composite Query (required)

```json
{
  "compositeQuery": {
    "queryType": "builder",
    "panelType": "graph",
    "unit": "percent",
    "queries": [ ... ]
  }
}
```

- `queryType` — "builder" | "promql" | "clickhouse_sql"
- `panelType` — always "graph" for alerts (auto-set)
- `unit` — Y-axis unit for value formatting: `percent`, `ms`, `s`, `ns`,
  `bytes`, `kbytes`, `mbytes`, `gbytes`, `reqps`, `ops`, `cps`
- `queries` — array of query objects (at least one required)

---

## Query Objects

### Builder Query (metrics)

```json
{
  "type": "builder_query",
  "spec": {
    "name": "A",
    "signal": "metrics",
    "stepInterval": 60,
    "aggregations": [
      {
        "metricName": "system.cpu.utilization",
        "timeAggregation": "avg",
        "spaceAggregation": "avg"
      }
    ],
    "filter": { "expression": "host.name = 'prod-1'" },
    "groupBy": [
      { "name": "host.name", "fieldContext": "resource", "fieldDataType": "string" }
    ],
    "having": { "expression": "" }
  }
}
```

**Metrics aggregation fields:**
- `metricName` — the OTel metric name (e.g., `system.cpu.utilization`)
- `timeAggregation` — avg, sum, rate, min, max, count, count_distinct, increase
- `spaceAggregation` — avg, sum, min, max, count, p50, p75, p90, p95, p99

### Builder Query (logs / traces)

```json
{
  "type": "builder_query",
  "spec": {
    "name": "A",
    "signal": "logs",
    "aggregations": [
      { "expression": "count()" }
    ],
    "filter": { "expression": "severity_text IN ('ERROR', 'FATAL')" },
    "groupBy": [
      { "name": "service.name", "fieldContext": "resource", "fieldDataType": "string" }
    ],
    "having": { "expression": "" }
  }
}
```

**Common aggregation expressions:**
- `count()` — count of items
- `avg(fieldName)` — average
- `sum(fieldName)` — sum
- `min(fieldName)` / `max(fieldName)`
- `p50(fieldName)` / `p75(fieldName)` / `p90(fieldName)` / `p95(fieldName)` /
  `p99(fieldName)`
- `count_distinct(fieldName)` — unique values
- `rate(fieldName)` — rate of change

**Traces-specific fields:** `durationNano` (span duration in nanoseconds),
`name` (operation name), `hasError`, `statusCode`

### PromQL Query

```json
{
  "type": "builder_query",
  "spec": {
    "name": "A",
    "query": "sum(rate(signoz_calls_total{status_code='STATUS_CODE_ERROR'}[5m])) / sum(rate(signoz_calls_total[5m])) * 100",
    "legend": "",
    "disabled": false
  }
}
```

### ClickHouse SQL Query

```json
{
  "type": "builder_query",
  "spec": {
    "name": "A",
    "query": "SELECT toStartOfInterval(timestamp, INTERVAL 1 MINUTE) AS ts, count() AS value FROM signoz_traces.distributed_signoz_error_index_v2 WHERE timestamp >= now() - INTERVAL 5 MINUTE AND exceptionType != '' GROUP BY ts ORDER BY ts",
    "legend": "",
    "disabled": false
  }
}
```

### Builder Formula

Combines multiple queries using math expressions:

```json
{
  "type": "builder_formula",
  "spec": {
    "name": "F1",
    "expression": "A * 100 / B"
  }
}
```

- `name` — formula identifier: F1, F2, etc.
- `expression` — references other query names (A, B, C). Supports `+`, `-`,
  `*`, `/`, `abs()`, `sqrt()`, `log()`, `exp()`
- Set `selectedQueryName` to the formula name (e.g., "F1") so the alert
  triggers on the formula result

---

## Filter Expression Syntax

```
# Equality
service.name = 'frontend'

# Comparison
http.status_code >= 500

# Pattern matching
body CONTAINS 'timeout'
body ILIKE '%error%'

# IN operator
severity_text IN ('ERROR', 'WARN', 'FATAL')

# EXISTS
trace_id EXISTS

# Boolean combinations
service.name = 'frontend' AND http.status_code >= 500
(http.status_code >= 400) OR (http.status_code < 200)
```

---

## GroupBy Fields

```json
{
  "name": "service.name",
  "fieldContext": "resource",
  "fieldDataType": "string"
}
```

- `name` — field name (OTel attribute)
- `fieldContext` — "resource" for resource attributes (service.name, host.name,
  k8s.*), or "tag" for span/log attributes
- `fieldDataType` — "string", "int64", "float64", "bool"

---

## Thresholds (required unless alertOnAbsent)

```json
{
  "thresholds": {
    "kind": "basic",
    "spec": [
      {
        "name": "critical",
        "target": 90,
        "targetUnit": "percent",
        "recoveryTarget": null,
        "matchType": "1",
        "op": "1",
        "channels": ["pagerduty-oncall", "slack-alerts"]
      },
      {
        "name": "warning",
        "target": 80,
        "targetUnit": "percent",
        "recoveryTarget": null,
        "matchType": "1",
        "op": "1",
        "channels": ["slack-alerts"]
      }
    ]
  }
}
```

### Threshold Fields

| Field | Type | Description |
|-------|------|-------------|
| name | string | Severity: "critical", "warning", or "info" |
| target | number | Threshold value |
| targetUnit | string | Unit of target (percent, ms, s, ns, bytes, etc.). Auto-converted to compositeQuery.unit during evaluation |
| recoveryTarget | number/null | Value for recovery (null if not needed) |
| matchType | string code | How to evaluate (see table below) |
| op | string code | Comparison operator (see table below) |
| channels | string[] | Notification channel names for this level |

### matchType Codes

| Code | Meaning | Description |
|------|---------|-------------|
| "1" | at_least_once | Fires if threshold breached at any point in eval window |
| "2" | all_the_times | Fires only if breached for the entire eval window |
| "3" | on_average | Fires if the average over eval window breaches threshold |
| "4" | in_total | Fires if the sum over eval window breaches threshold |
| "5" | last | Fires based on the most recent value only |

### op Codes

| Code | Meaning |
|------|---------|
| "1" | above (>) |
| "2" | below (<) |
| "3" | equal (=) |
| "4" | not_equal (!=) |

---

## Evaluation Configuration

```json
{
  "evaluation": {
    "kind": "rolling",
    "spec": {
      "evalWindow": "5m0s",
      "frequency": "1m0s"
    }
  }
}
```

- `evalWindow` — how long the condition must persist: "5m0s", "10m0s",
  "15m0s", "1h0m0s", "4h0m0s", "24h0m0s"
- `frequency` — how often to evaluate: "1m0s", "5m0s"
- Auto-generated with defaults (5m0s window, 1m0s frequency) if omitted

---

## Notification Settings

```json
{
  "notificationSettings": {
    "groupBy": ["service.name"],
    "renotify": {
      "enabled": true,
      "interval": "4h0m0s",
      "alertStates": ["firing", "nodata"]
    },
    "usePolicy": true
  }
}
```

- `groupBy` — fields to group notifications by (reduces noise)
- `renotify` — re-send alerts at interval for specified states
- `usePolicy` — enable routing policy matching based on labels
- Auto-generated with defaults (re-notification disabled, 30m interval) if
  omitted

---

## Labels & Annotations

### Labels

```json
{
  "labels": {
    "severity": "critical",
    "team": "backend",
    "service": "checkout",
    "environment": "production"
  }
}
```

- `severity` — **required** (auto-defaults to "warning"): "info", "warning",
  or "critical"
- Additional labels enable routing policies when `usePolicy: true`

### Annotations (Template Variables)

```json
{
  "annotations": {
    "description": "CPU usage is {{$value}}% on host {{$labels.host_name}}, exceeding threshold of {{$threshold}}%",
    "summary": "High CPU usage detected",
    "runbook": "https://wiki.example.com/runbooks/high-cpu"
  }
}
```

- `{{$value}}` — current metric value
- `{{$threshold}}` — threshold that was breached
- `{{$labels.key}}` — label values (dots in attribute names become underscores:
  `service.name` → `{{$labels.service_name}}`)

---

## Anomaly Detection (ruleType: anomaly_rule)

Only works with `METRIC_BASED_ALERT`. Uses Z-score seasonal decomposition.

```json
{
  "ruleType": "anomaly_rule",
  "condition": {
    "algorithm": "zscore",
    "seasonality": "daily",
    "thresholds": {
      "kind": "basic",
      "spec": [
        {
          "name": "warning",
          "target": 3,
          "op": "1",
          "matchType": "1"
        }
      ]
    }
  }
}
```

- `algorithm` — only "zscore" is supported
- `seasonality` — "hourly", "daily", or "weekly"
- `target` — Z-score threshold (e.g., 3 for 3 standard deviations)

---

## Absent Data Alerts

Alert when no data is received:

```json
{
  "condition": {
    "alertOnAbsent": true,
    "absentFor": 300000
  }
}
```

- `alertOnAbsent` — enable absent-data alerting
- `absentFor` — duration in milliseconds (300000 = 5 minutes)
- When `alertOnAbsent: true`, thresholds are optional

---

## Common Alert Patterns

### Error Rate (Formula)

Two queries + formula: A = error count, B = total count, F1 = A * 100 / B

```json
{
  "queries": [
    {
      "type": "builder_query",
      "spec": {
        "name": "A",
        "signal": "traces",
        "aggregations": [{ "expression": "count()" }],
        "filter": { "expression": "hasError = true" }
      }
    },
    {
      "type": "builder_query",
      "spec": {
        "name": "B",
        "signal": "traces",
        "aggregations": [{ "expression": "count()" }],
        "filter": { "expression": "" }
      }
    },
    {
      "type": "builder_formula",
      "spec": { "name": "F1", "expression": "A * 100 / B" }
    }
  ],
  "selectedQueryName": "F1"
}
```

### Latency P99

```json
{
  "queries": [
    {
      "type": "builder_query",
      "spec": {
        "name": "A",
        "signal": "traces",
        "aggregations": [{ "expression": "p99(durationNano)" }],
        "groupBy": [
          { "name": "service.name", "fieldContext": "resource", "fieldDataType": "string" }
        ]
      }
    }
  ]
}
```

Target value should be in nanoseconds (2 seconds = 2000000000ns). Set
`targetUnit: "ns"` on the threshold.

### Log Volume Spike

```json
{
  "queries": [
    {
      "type": "builder_query",
      "spec": {
        "name": "A",
        "signal": "logs",
        "aggregations": [{ "expression": "count()" }],
        "filter": { "expression": "severity_text IN ('ERROR', 'FATAL')" },
        "groupBy": [
          { "name": "service.name", "fieldContext": "resource", "fieldDataType": "string" }
        ]
      }
    }
  ]
}
```

---

## Validation Rules

The MCP server validates these constraints:
- `alert` — cannot be empty
- `alertType` — must be one of the 4 valid types
- `ruleType` — must be one of the 3 valid types
- `condition.compositeQuery` — required
- `condition.compositeQuery.queryType` — required
- `condition.compositeQuery.queries` — at least one query
- Builder query `signal` must match `alertType`
- `anomaly_rule` only works with `METRIC_BASED_ALERT`
- `promql_rule` requires `queryType: "promql"`
- Channel names must match exactly from `signoz_list_notification_channels`
