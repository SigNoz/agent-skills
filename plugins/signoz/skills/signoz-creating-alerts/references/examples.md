# Examples — `signoz-creating-alerts`

Four canonical alert flows: simple metric threshold, error-rate formula,
log-volume groupBy, and anomaly detection.

## Metric threshold with multi-severity routing

**User:** "Alert me when CPU usage on the checkout service goes above 80%, page me at 90%"

**Agent:**
1. Intent parsed: metric, CPU, scope `service.name = checkout`,
   thresholds 80% (warning) / 90% (critical), severity bumped to critical
   on the higher level because "page me" was used.
2. `signoz_list_metrics searchText=cpu` → confirms `system.cpu.utilization`.
3. `signoz_list_alert_rules` (paginated) → no existing CPU alert for checkout.
4. `signoz_list_notification_channels` → presents existing channels;
   user picks `slack-infra` for warning and `pagerduty-oncall` for critical.
5. Builds JSON: `METRIC_BASED_ALERT`, `threshold_rule`,
   `signal=metrics`, two thresholds (`op="above"`,
   `matchType="on_average"`, `targetUnit="percent"`), filter
   `service.name = 'checkout'`.
6. Dry-run via `signoz_execute_builder_query` over last 1h: returns data,
   would have fired 0 times (clean baseline).
7. Emits a one-paragraph plain-language summary — no JSON dump.
8. Calls `signoz_create_alert`. Reports created alert with ID, threshold
   summary, channel routing, and dry-run result.

## Error-rate formula alert

**User:** "Set up an alert when error rate goes above 5% on payments"

**Agent:**
1. Intent parsed: traces, error-rate formula, scope
   `service.name = payments`, threshold 5%, severity default warning.
2. `signoz_get_field_keys fieldContext=resource signal=traces` confirms
   `service.name`. `signoz_get_field_values` confirms `payments` exists.
3. No existing payments error-rate alert.
4. Builds formula alert: query A counts spans with `has_error = true` for
   `service.name = 'payments'`, query B counts all spans for the same
   service, formula F1 = `A * 100 / B`, `selectedQueryName: "F1"`,
   threshold target 5, `targetUnit: "percent"`,
   `op: "above"`, `matchType: "at_least_once"` (catch any breach).
5. Channel: user picks `slack-payments`.
6. Dry-run on last 1h: payments error rate hovered around 0.3%, would have
   fired 0 times. Clean — not too tight.
7. Preview, save, report.

## Log-volume threshold with groupBy

**User:** "Notify me if log volume spikes more than 1000 error logs per minute on any service"

**Agent:**
1. Intent parsed: logs, volume threshold, scope = all services (groupBy
   `service.name`), threshold 1000/min, severity warning.
2. `signoz_get_field_keys signal=logs fieldContext=resource` confirms
   `service.name` exists; **no service filter required** since the user
   said "any service" → groupBy provides the scoping.
3. Builds: `LOGS_BASED_ALERT`, `signal=logs`,
   `aggregations: [{expression: "count()"}]`,
   `filter: {expression: "severity_text IN ('ERROR', 'FATAL')"}`,
   `groupBy: [{name: "service.name", fieldContext: "resource", fieldDataType: "string"}]`,
   threshold 1000, `targetUnit: ""`, `evalWindow: 1m0s`,
   `matchType: "at_least_once"` (catch any minute that breaches).
4. Channels: user picks slack channel.
5. Dry-run: returned per-service counts, max in last 1h was 87 — would
   have fired 0 times. Within reasonable headroom.
6. Preview, save, report.

## Anomaly detection (z-score)

**User:** "Alert me on anomalous request latency for the api gateway"

**Agent:**
1. Intent parsed: metric, anomaly detection, scope
   `service.name = api-gateway`. Anomaly detection requires
   `METRIC_BASED_ALERT` + `anomaly_rule`.
2. `signoz_list_metrics searchText=duration` → finds
   `http.server.request.duration`.
3. Builds: `anomaly_rule`, `algorithm=standard` (z-score based), `seasonality=daily`,
   threshold target 3 (3 standard deviations), `op: "above"`,
   `matchType: "at_least_once"`.
4. Channel: user picks slack-api.
5. Dry-run validates query returns data. Skip breach-count for
   anomaly alerts.
6. Preview emphasizes that the threshold is in standard deviations, not raw
   latency. Save, report.
