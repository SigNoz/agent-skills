# Duplicate log copies

Read this when a service sends logs over OTLP and its container or host output is also collected
from files or stdout. The same records then arrive twice and are billed twice. Stopping either
copy is a candidate only after every check below.

## Confirm the duplicate

Match each OTLP service to the collected container or process that runs it (the same name, or the
pod's service label); the OTLP copy may carry no container attributes and the file copy may carry
no `service.name`. Compare their hourly record counts over the same window, then match a sample of
records by timestamp and message; do not treat similar counts alone as proof of a duplicate.

## Check both copies before stopping one

- **Fields only one copy carries.** List them for both copies. The file copy often has k8s
  resource attributes (such as `k8s.deployment.name`), file-path attributes, and parsed fields.
  The OTLP copy often has `trace_id` and `span_id`, which link logs to traces, plus SDK resource
  attributes. For the copy you would stop, check every query on those fields:
  - Alerts: every log alert, as in Step 3c.
  - Dashboards: `signoz_list_dashboards`, raising `offset` by `limit` until you reach `total`,
    then `signoz_get_dashboard` on every one. Read every panel query, including PromQL and
    ClickHouse SQL panels and dashboard variables.
  - Saved views: `signoz_list_views` with `source: "logs"`, following `pagination.nextOffset`
    while `pagination.hasMore` is true, then `signoz_get_view` on every one.

  A query that filters, groups, or aggregates on such a field breaks when that copy stops, even
  if it names no service or container. Mark it **Will break alert coverage** or **Will break
  dashboards** and name it. Stopping the OTLP copy also loses the link from those logs to their
  traces; say so.
- **Records only one copy has.** Count them and their severities. Crash output and runtime errors
  can reach stdout without passing through the SDK. If the copy you would stop has records at WARN
  or higher that the other copy lacks, keep that copy or keep those records.

## Choose and size

Stop the copy whose checks found nothing that depends on it. When both copies pass, prefer keeping
the OTLP copy and stopping file collection for those pods, which is SigNoz's guidance for
SDK-instrumented pods. Size the change as the stopped copy's bytes only. When the Cost Meter can't
separate the two copies, measure both with the same byte estimate over the same window and apply
the stopped copy's share of that estimate to the Cost Meter total.

## Where to stop it

- SigNoz k8s-infra file collection: exclude the pods or containers with the
  `presets.logsCollection.blacklist` values, or turn collection off for those pods. Docs:
  https://signoz.io/docs/opentelemetry-collection-agents/k8s/k8s-infra/configure-k8s-infra/
- Another file or stdout collector: its own exclude setting, checked against its documentation.
- The OTLP copy: the SDK's or log bridge's documented setting, checked against its documentation.
