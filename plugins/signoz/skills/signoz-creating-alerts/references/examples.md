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
5. Reads `signoz://alert/instructions` and `signoz://alert/examples` and
   adapts the `metric_threshold_single` example: `METRIC_BASED_ALERT`,
   `threshold_rule`, filter `service.name = 'checkout'`, two tiers named
   `warning` and `critical` (`above`, `on_average`) with targets 80 and 90,
   `targetUnit: "percent"`, and `compositeQuery.unit: "percentunit"` because
   the metric is a 0 to 1 ratio. The query sets `timeAggregation` and
   `spaceAggregation` explicitly and carries no `limit` or `order`. Each
   fired alert carries the severity of its tier, so the rule needs no
   `labels.severity` for that.
6. Dry-run via `signoz_execute_builder_query` over last 1h, with the
   display bounds the query tool expects but the persisted rule omits:
   returns data, 0 of the returned points breached (clean baseline).
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
4. Adapts the `traces_error_rate_formula` example to count requests: query
   A counts entry spans with `has_error = true` (`service.name = 'payments'
   AND has_error = true AND (isEntryPoint = true OR isRoot = true)`), query
   B counts all entry spans for the same service, both `disabled: true`,
   formula F1 = `A * 100 / B`, `selectedQueryName: "F1"`. One threshold tier
   named `critical` with a bare target 5, `op: "above"`,
   `matchType: "at_least_once"` (catch any breach), and
   `compositeQuery.unit: "percent"`: the formula already emits percent, so
   the tier sets no `targetUnit`.
5. No channel was named, so it reuses a fully paginated same-operation
   `signoz_list_notification_channels` result, or calls it through
   `pagination.hasMore=false`; the user picks `slack-payments`. If none fits,
   it offers `signoz_create_notification_channel` with user-provided config.
6. Dry-run on last 1h: payments error rate hovered around 0.3%, 0 of the
   returned points breached. Clean, not too tight.
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
3. Adapts the `logs_threshold` example: `LOGS_BASED_ALERT`, `count()` over
   `severity_text IN ('ERROR', 'FATAL')`, grouped by the resource key
   `service.name`, threshold 1000 with no `targetUnit`, `evalWindow: 1m0s`,
   `matchType: "at_least_once"` (catch any minute that breaches). No `limit`
   or `order` on the grouped query: with them SigNoz would evaluate only the
   top-N services and a quiet service that suddenly spikes could be ranked
   out of the evaluated set.
4. No channel was named, so it reuses a fully paginated same-operation
   `signoz_list_notification_channels` result, or calls it through
   `pagination.hasMore=false`; the user picks a Slack channel. If none fits,
   it offers `signoz_create_notification_channel` with user-provided config.
5. Dry-run: returned per-service counts, max in last 1h was 87, so 0 of the
   returned points breached. The dry-run's display `limit` bounds how many services
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
3. Adapts the `metric_anomaly` example: `anomaly_rule`,
   `seasonality=daily`, the anomaly function with `z_score_threshold: 3`,
   and a rolling `evalWindow: "24h"` with `frequency: "3h"`. One threshold
   tier named `warning`: `op:
   "above"`, `target: 3` (3 standard deviations above the forecast),
   `matchType: "at_least_once"`, empty `targetUnit`. A request about drops
   would use `op: "below"` with `target: -3`, and one about either direction
   `op: "outside_bounds"` with `target: 3`.
4. No channel was named, so it reuses a fully paginated same-operation
   `signoz_list_notification_channels` result, or calls it through
   `pagination.hasMore=false`; the user picks `slack-api`, which goes in the
   tier's `channels`. If none fits, it offers
   `signoz_create_notification_channel` with user-provided config.
5. Dry-run validates query returns data. Skip breach-count for
   anomaly alerts.
6. Preview emphasizes that the threshold is in standard deviations, not raw
   latency. Save, report.
