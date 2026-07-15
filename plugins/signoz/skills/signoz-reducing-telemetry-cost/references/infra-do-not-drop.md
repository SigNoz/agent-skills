# Infra-page "do-not-drop" metrics — the safety guard

## Contents
- The rule (Infra page uses built-in queries, not dashboards)
- Hosts view — families
- Kubernetes view — enumerated names + workload/volume/namespace/cluster families
- APM / Services page — span-derived `signoz_*` RED metrics
- Required attributes and page metadata (resolution / filtering)
- Why the do-not-drop list matters
- Caveat / discrepancy to keep in mind

The SigNoz **Infrastructure** page (Hosts and Kubernetes views) queries these metrics
via **built-in queries, not dashboards** — and fails silently when the data is missing.
So `signoz_check_metric_usage` will report them as having **no dashboards/alerts**, yet
dropping them **breaks the Infra page.** This list is the authoritative exception to the
"unused ⇒ drop candidate" rule.

**Rule:** if a drop candidate matches anything below, do NOT present it as "safe to
drop." Present it as **"Infra-page dependency — dropping breaks the Hosts/Kubernetes
view; confirm you don't use that view before dropping."** This overrides the empty
usage-check result.

Bias intentionally conservative (family-level) — over-protecting a metric costs a little
saving; under-protecting silently breaks a product page.

## Hosts view — families (treat whole prefix as load-bearing)
- `system.cpu.*` (incl. `system.cpu.load_average.1m/5m/15m`)
- `system.memory.*`
- `system.disk.*`
- `system.network.*`
- `system.filesystem.*`
- `system.paging.*`
- `system.processes.*`
- `host.cpu.usage` (used for host entity validation)

Exact `system.*` names are NOT enumerated in SigNoz docs — definitive list lives in the
frontend Hosts query builders. Family-level protection is the safe default; refine from
frontend source only if a user needs to drop a specific `system.*` metric.

## Kubernetes view — enumerated names (from k8s-metrics.mdx, high confidence)
Entity resolution (critical — missing = entities don't resolve / click errors):
- `k8s.pod.cpu.usage`, `k8s.node.cpu.usage`
Pods: `k8s.pod.cpu.usage`, `k8s.pod.cpu_request_utilization`, `k8s.pod.cpu_limit_utilization`,
  `k8s.pod.memory_request_utilization`, `k8s.pod.memory_limit_utilization`, `k8s.pod.memory.usage`,
  `k8s.pod.uptime`, `k8s.pod.status_reason`
Containers: `container.cpu.usage`, `container.uptime`,
  `k8s.container.cpu_request_utilization`, `k8s.container.cpu_limit_utilization`,
  `k8s.container.memory_request_utilization`, `k8s.container.memory_limit_utilization`
Nodes: `k8s.node.cpu.usage`, `k8s.node.condition`, `k8s.node.uptime`
The Workload (Deployments/StatefulSets/DaemonSets/Jobs/ReplicaSets), Volumes, Namespaces, and
Clusters tabs each render from their own metric families — `k8s.replicaset.*`, `k8s.deployment.*`,
`k8s.volume.*`, and the rest listed below are all load-bearing for those tabs.

**Families safe to treat whole** (family-level protection is the safe default; exact names in
`k8s-metrics.mdx`):
`k8s.pod.*`, `k8s.container.*`, `k8s.node.*`, `container.*`, `k8s.deployment.*`,
`k8s.replicaset.*`, `k8s.statefulset.*`, `k8s.daemonset.*`, `k8s.job.*`, `k8s.cronjob.*`,
`k8s.hpa.*`, `k8s.volume.*`, `k8s.namespace.*`, `k8s.cluster.*`

## APM / Services page — powered exclusively by span-derived `signoz_*` RED metrics
The SigNoz APM / Services pages are built from span-derived RED metrics that the
`signozspanmetrics` collector processor generates from the traces pipeline — not from any user
dashboard.

The Services list and service-detail charts (rate, error %, p50/p90/p99 latency, apdex, DB
calls, external calls) query ONLY these span-derived metrics:
- `signoz_calls_total`
- `signoz_latency_bucket`, `signoz_latency_count`, `signoz_latency_sum`
- `signoz_db_latency_count`, `signoz_db_latency_sum`
- `signoz_external_call_latency_count`, `signoz_external_call_latency_sum`
- dotted variants (`signoz_latency.bucket`, …) when `dotMetricsEnabled` is on — same data.

**Handling in the skill:**
- These already fall under the internal-`signoz_`/`signoz.` exclusion → never in the drop
  candidate list. Keep it that way; if a user asks about them, explain they power the APM
  page (do not drop).
- **OTel-native `http.server.*` / `rpc.*` metrics do NOT back the APM page in SigNoz.** Treat
  them as ordinary metrics — normal usage-check applies; if unused and not in a dashboard/alert
  they are genuinely droppable (histograms: trim buckets rather than hard-drop). No special APM
  protection.
- **Trace-layer dependency:** because these RED metrics are generated from spans, trace sampling
  limits the built-in APM/Services metrics to retained traces. Absolute request counts and rates
  undercount real traffic; latency trends and error spikes may remain useful. Never recommend
  trace sampling as a cost-reduction lever.
  Targeted SDK exclusions and Collector filters also remove those operations from APM, so state
  that impact before recommending them. Dropping the `signoz_*` metrics themselves breaks APM
  entirely. Treat that as a separate lever.

## Required attributes and page metadata (not metrics)
- Hosts: `host.name` (required — missing = host not clickable), `host.id` (fallback)
- Kubernetes entity resolution: each entity's `.uid` + `.name` —
  `k8s.pod.uid`/`k8s.pod.name`,
  `k8s.node.uid`/`k8s.node.name`, `k8s.deployment.name`, `k8s.namespace.name`,
  `k8s.statefulset.name`, `k8s.daemonset.name`, `k8s.job.name`, `k8s.cronjob.name`,
  and `k8s.container.name`. Container rows use `k8s.pod.uid` + `k8s.container.name`, not
  `container.id`.
  Missing UID → clicking the entity raises an internal error.
- Kubernetes page metadata: keep `k8s.pod.start_time` (Pod Age) and `k8s.pod.ip` on Pod metrics;
  keep `k8s.volume.type` on volume metrics.

## Why the do-not-drop list matters
`signoz_check_metric_usage` does a real dashboard/alert lookup, so it correctly reports these
metrics as referenced by no dashboard and no alert. That is exactly the trap: the Infra page
queries them directly rather than through a dashboard, so "no usage" does **not** mean "safe to
drop." Top-volume `k8s.*` metrics like `k8s.node.condition` and the `k8s.container.*_utilization`
family are common offenders — frequently the single biggest metric-volume contributors, and
exactly what a naive drop pass would remove first.

## Caveat / discrepancy to keep in mind
SigNoz docs write some resolution metrics as `pod.cpu.usage` / `host.cpu.usage` (no `k8s.` /
`system.` prefix) while the Kubernetes metrics reference uses the `k8s.*` form. When matching by
exact name, allow both prefix forms.

_Source: SigNoz Infrastructure Monitoring docs (Kubernetes metric names are authoritative). The
exact Hosts `system.*` names live in the frontend Hosts query builders; family-level protection
is the safe default._
