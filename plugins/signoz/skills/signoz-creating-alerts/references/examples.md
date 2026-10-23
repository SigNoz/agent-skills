# Examples: `signoz-creating-alerts`

## Contents

- Metric threshold with multi-severity routing
- Error-rate formula alert
- Log-volume threshold with groupBy
- Anomaly detection (z-score)

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
4. Reuses a fully paginated same-operation `signoz_list_notification_channels`
   result, or calls it through `pagination.hasMore=false`; the user picks
   `slack-infra` and `pagerduty-oncall`. If none fits, it offers
   `signoz_create_notification_channel` with user-provided provider config.
5. Builds JSON: `METRIC_BASED_ALERT`, `threshold_rule`,
   `schemaVersion: "v2alpha1"`, `signal=metrics`, two thresholds named
   `warning` and `critical` (`op="above"`, `matchType="on_average"`,
   `targetUnit="percent"`), `labels.severity: critical` (the highest tier;
   direct routing still sends each tier to its own channels by
   `threshold.name`), filter `service.name = 'checkout'`, an explicit
   `evaluation` block (rolling, 5m window, 1m frequency),
   `notificationSettings`, and `panelType: "graph"`. The builder query
   carries no `limit` or `order`.
6. Dry-run via `signoz_execute_builder_query` over last 1h, with the
   display bounds the query tool expects but the persisted rule omits:
   returns data, would have fired 0 times (clean baseline).
7. Emits a one-paragraph plain-language summary, no JSON dump.
8. Calls `signoz_create_alert`. Reports created alert with ID, threshold
   summary, channel routing, and dry-run result.

## Error-rate formula alert

**User:** "Set up an alert when error rate goes above 5% on payments"

**Agent:**
1. Intent parsed: traces, error-rate formula, scope
   `service.name = payments`, threshold 5%. The user gives no severity cue,
   so the error-rate row of *Severity defaults* sets `critical`.
2. `signoz_get_field_keys fieldContext=resource signal=traces` confirms
   `service.name`. `signoz_get_field_values` confirms `payments` exists.
3. No existing payments error-rate alert.
4. Builds formula alert: query A counts spans with `has_error = true` for
   `service.name = 'payments'`, query B counts all spans for the same
   service, formula F1 = `A * 100 / B`, `selectedQueryName: "F1"`,
   one threshold tier named `critical` with target 5,
   `targetUnit: "percent"`, `op: "above"`, `matchType: "at_least_once"`
   (catch any breach), and `labels.severity: critical`.
5. No channel was named, so it reuses a fully paginated same-operation
   `signoz_list_notification_channels` result, or calls it through
   `pagination.hasMore=false`; the user picks `slack-payments`. If none fits,
   it offers `signoz_create_notification_channel` with user-provided config.
6. Dry-run on last 1h: payments error rate hovered around 0.3%, would have
   fired 0 times. Clean, not too tight.
7. Preview states severity `critical` with the error-rate row as the reason.
   Save, report.

## Log-volume threshold with groupBy

**User:** "Notify me if log volume spikes more than 1000 error logs per minute on any service"

**Agent:**
1. Intent parsed: logs, volume threshold, scope = all services (groupBy
   `service.name`), threshold 1000/min. Severity is `warning` from the
   error-log volume row: the alert counts ERROR and FATAL lines and does
   not fire on a single crash event.
2. `signoz_get_field_keys signal=logs fieldContext=resource` confirms
   `service.name` exists; **no service filter required** since the user
   said "any service" → groupBy provides the scoping.
3. Builds: `LOGS_BASED_ALERT`, `signal=logs`,
   `aggregations: [{expression: "count()"}]`,
   `filter: {expression: "severity_text IN ('ERROR', 'FATAL')"}`,
   `groupBy: [{name: "service.name", fieldContext: "resource", fieldDataType: "string"}]`,
   threshold 1000, `targetUnit: ""`, `evalWindow: 1m0s`,
   `matchType: "at_least_once"` (catch any minute that breaches). No `limit`
   or `order` on the grouped query: with them SigNoz would evaluate only the
   top-N services and a quiet service that suddenly spikes could be ranked
   out of the evaluated set.
4. No channel was named, so it reuses a fully paginated same-operation
   `signoz_list_notification_channels` result, or calls it through
   `pagination.hasMore=false`; the user picks a Slack channel. If none fits,
   it offers `signoz_create_notification_channel` with user-provided config.
5. Dry-run: returned per-service counts, max in last 1h was 87, which would
   have fired 0 times. The dry-run's display `limit` bounds how many services
   came back, so the preview states the count covers the returned services.
6. Preview, save, report.

## Anomaly detection (z-score)

**User:** "Alert me on anomalous request latency for the api gateway"

**Agent:**
1. Intent parsed: metric, anomaly detection, scope
   `service.name = api-gateway`. Anomaly detection requires
   `METRIC_BASED_ALERT` + `anomaly_rule`.
2. `signoz_list_metrics searchText=duration` → finds
   `http.server.request.duration`.
3. Builds the v1 anomaly shape: `anomaly_rule`, `algorithm=standard`
   (z-score based), `seasonality=daily`, top-level `evalWindow` and
   `frequency`, `condition.target: 3` (3 standard deviations), `op: "above"`,
   `matchType: "at_least_once"`; no `schemaVersion`, `thresholds`,
   `evaluation`, or `notificationSettings`.
4. No channel was named, so it reuses a fully paginated same-operation
   `signoz_list_notification_channels` result, or calls it through
   `pagination.hasMore=false`; the user picks `slack-api`. If none fits, it
   offers `signoz_create_notification_channel` with user-provided config.
5. Dry-run validates query returns data. Skip breach-count for
   anomaly alerts.
6. Preview emphasizes that the threshold is in standard deviations, not raw
   latency. Save, report.
