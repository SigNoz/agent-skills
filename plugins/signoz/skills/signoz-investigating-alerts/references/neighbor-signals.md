# Neighbor Signals Lookup

For each resource type the alert is scoped to, this table lists the
neighbor signals to pull during Tier 2 (fire-window vs baseline
comparison). Pull every signal in the row; rank by absolute deviation
from baseline.

The MCP server's "always prefer resource attributes" guideline applies
to all of these queries — use the same resource-attribute filter as
the alert itself.

## Service-level scope (`service.name = X`)

The alert filters or groups by a service. Neighbor signals describe
the service's health from the perspective of its callers and its
runtime.

| Signal | Source | Aggregation | Why it matters |
|---|---|---|---|
| Error rate (traces) | traces | `count(hasError = true) * 100 / count()` grouped by service | A sympathetic move here usually points at downstream / upstream cascades. |
| p95 latency | traces | `p95(durationNano)` filtered to entry spans | Latency moving with errors → resource saturation or downstream slowness. Latency without errors → queue/buffer fill. |
| p99 latency | traces | `p99(durationNano)` | Catches tail-only regressions invisible to p95. |
| Throughput (RPS) | traces | `rate(count())` | Drops mean upstream stopped sending. Spikes mean retry storms or load shifts. |
| Dependency error rate | traces | `count(hasError = true)` filtered to outbound spans, grouped by `db.name` / `peer.service` / target host | Surfaces which downstream the service is failing on. |
| Container CPU (if available) | metrics | `system.cpu.utilization` or `container.cpu.utilization` filtered to the same service | Saturation explains latency/error correlation; flat CPU + errors implies a non-resource cause. |
| Container memory | metrics | `system.memory.usage` / `container.memory.usage` | OOM context, leak detection. |
| Pod restarts (if k8s) | metrics | `k8s.pod.phase` transitions or `kube_pod_container_status_restarts_total` rate | Restarts during the fire window strongly bias toward "infrastructure caused this". |

## Host / VM scope (`host.name = X`)

The alert is on a single host or set of hosts. Neighbor signals are
infrastructure-level.

| Signal | Source | Aggregation | Why it matters |
|---|---|---|---|
| CPU utilization | metrics | `system.cpu.utilization` time-avg space-avg | Already may be the alert metric — pull anyway to see how peak relates to threshold. |
| Memory pressure | metrics | `system.memory.utilization` or free pages | OOM and swap activity. |
| Disk I/O wait | metrics | `system.disk.io_time` or iowait equivalent | Disk saturation often masquerades as CPU pressure. |
| Network I/O | metrics | `system.network.io` | Network saturation or NIC errors. |
| Load average | metrics | `system.cpu.load_average.1m` | Catches contention not visible in raw CPU%. |
| Service-level signals on this host | traces | filter by `host.name = X` and aggregate by service | Identifies which service workload caused the host pressure. |

## K8s namespace / pod scope

The alert is scoped to a k8s namespace, deployment, or pod set.

| Signal | Source | Aggregation | Why it matters |
|---|---|---|---|
| Pod restart count | metrics | restarts in fire window vs baseline | Crash loops dominate every other signal — surface first. |
| CPU vs requests/limits | metrics | `container.cpu.utilization` divided by limit | Throttling shows up here even when raw CPU% looks healthy. |
| Memory vs limit | metrics | `container.memory.usage / container.memory.limit` | OOMKilled is the most common k8s failure. |
| Node pressure | metrics | `kube_node_status_condition` for pressure conditions | Node-level resource exhaustion bleeds into all pods scheduled there. |
| Recent rollout | metrics | check for `k8s.deployment.replicas_updated` change in window | Rollout overlapping with fire is the strongest single signal of cause. |
| Service-level signals (errors / latency) | traces | scoped to the k8s workload | The application-layer view of the same problem. |

## Generic (no resource scope identified)

If the alert has no resource filter (e.g., a global error-log alert
without groupBy), Tier 2 is weaker. Pull:

| Signal | Source | Aggregation |
|---|---|---|
| Top services by error rate | traces | `count(hasError = true)` grouped by `service.name`, top 10 |
| Top services by error log volume | logs | `count()` filtered to `severity_text IN ('ERROR','FATAL')`, grouped by `service.name`, top 10 |

This identifies which service drove the global signal, then re-run
Tier 2 against that service's row from the table above.

## Selection rules

1. **Pick the row that matches the alert's most specific resource
   filter.** If the alert filters on both `k8s.namespace.name` and
   `service.name`, prefer the k8s row plus `service.name` cross-cuts.
2. **Skip a signal if the data is not available.** Don't fabricate
   queries against metrics that don't exist — call `signoz:signoz_list_metrics`
   to verify metric names before querying.
3. **Cap signal pulls at 6 queries per tier** to keep context bounded.
   Pick the most informative for the alert's signal type.
