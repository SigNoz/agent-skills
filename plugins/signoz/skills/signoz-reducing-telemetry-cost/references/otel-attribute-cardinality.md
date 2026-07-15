# OTel Attribute Cardinality Reference

## Contents
- Profiles (UNBOUNDED, ACCUMULATING, BOUNDED, DEPLOYMENT_DEPENDENT, IDENTIFIER)
- HTTP / Network
- Database
- Messaging / Queues
- RPC / gRPC
- Kubernetes / Infrastructure
- Process / Runtime
- Errors / Exceptions
- Tracing / Correlation IDs
- Cloud / Provider
- Service / SDK
- How to classify an unknown attribute
- Fix reference

Used by the agent to classify any attribute encountered during cardinality analysis.
For each attribute: profile, why it matters, and what to do about it.

## Profiles

- **UNBOUNDED** — grows without ceiling. Every new URL, query, ID, or stack trace creates a new series permanently. These are the most dangerous.
- **ACCUMULATING** — grows with infrastructure churn (pod restarts, deploys). Does not reflect concurrent active series — a metric with 20,000 `k8s.pod.uid` values may only have 50 active pods right now.
- **BOUNDED** — fixed or near-fixed set of values. Safe to keep as a label dimension.
- **DEPLOYMENT_DEPENDENT** — cardinality depends on the deployment scale. Fine at 10 services, dangerous at 500.
- **IDENTIFIER** — always a unique ID per request/event. Should never appear as a metric label. Immediate red flag.

---

## HTTP / Network

| Attribute | Profile | Notes | Fix |
|-----------|---------|-------|-----|
| `url.full` | UNBOUNDED | Full URL including query string and path params. Each unique URL = new series. `/user/123` and `/user/456` are different series. | Aggregate with metricstransform or use `http.route` instead |
| `http.url` | UNBOUNDED | Older convention, same problem as `url.full` | Same |
| `http.target` | UNBOUNDED | URL path + query string. Path params make this unbounded | Use `http.route` (templated path) instead |
| `url.path` | UNBOUNDED | Raw path without query, but still unbounded if path contains IDs | Use `http.route` |
| `url.query` | UNBOUNDED | Query string. Completely unbounded | Drop entirely |
| `http.route` | BOUNDED | Templated route e.g. `/user/{id}`. Fixed set per application | Safe to keep |
| `http.method` | BOUNDED | GET, POST, PUT, DELETE etc. Fixed set | Safe |
| `http.request_method` | BOUNDED | Same as `http.method`, newer convention | Safe |
| `http.status_code` | BOUNDED | 200, 404, 500 etc. Fixed set | Safe |
| `http.response_status_code` | BOUNDED | Same, newer convention | Safe |
| `http.scheme` | BOUNDED | http or https | Safe |
| `http.flavor` | BOUNDED | 1.0, 1.1, 2.0, 3.0 | Safe |
| `network.protocol.version` | BOUNDED | Protocol version, small fixed set | Safe |
| `network.protocol.name` | BOUNDED | http, grpc, etc. | Safe |
| `net.peer.name` | DEPLOYMENT_DEPENDENT | Hostname of remote peer. Fine if calling fixed upstream services, unbounded if calling arbitrary user-supplied hosts | Review actual cardinality |
| `net.peer.port` | UNBOUNDED | Ephemeral client ports are unique per connection (range 32768–60999). Server ports are bounded but client ports are not. | Check if client or server port; drop client ports |
| `net.host.port` | BOUNDED | Server-side listening port. Small fixed set | Safe |
| `client.port` | UNBOUNDED | Client-side ephemeral port. Always unbounded | Drop — no diagnostic value |
| `client.address` | DEPLOYMENT_DEPENDENT | Client IP. Bounded in internal service mesh, unbounded for public-facing APIs | Check cardinality |
| `server.address` | DEPLOYMENT_DEPENDENT | Upstream hostname. Usually bounded | Review |
| `server.port` | BOUNDED | Server-side port. Fixed set | Safe |
| `network.peer.address` | DEPLOYMENT_DEPENDENT | IP of remote peer. Bounded in internal mesh, unbounded externally | Check cardinality |
| `network.local.address` | BOUNDED | Local interface IP. Small fixed set per host | Safe |

---

## Database

| Attribute | Profile | Notes | Fix |
|-----------|---------|-------|-----|
| `db.query.text` | UNBOUNDED | Raw SQL or query string. Every unique query = new series. Parameterized queries with different values = different series | Drop entirely or replace with `db.operation.name` |
| `db.statement` | UNBOUNDED | Older convention for raw query text. Same problem | Drop |
| `db.operation` | BOUNDED | SELECT, INSERT, UPDATE, DELETE etc. | Safe |
| `db.operation.name` | BOUNDED | Same, newer convention | Safe |
| `db.name` | DEPLOYMENT_DEPENDENT | Database name. Usually small fixed set | Safe at low counts |
| `db.sql.table` | DEPLOYMENT_DEPENDENT | Table name. Bounded if schema is fixed | Usually safe |
| `db.collection.name` | DEPLOYMENT_DEPENDENT | Collection/table name | Usually safe |
| `db.system` | BOUNDED | postgresql, mysql, redis, mongodb etc. | Safe |
| `db.redis.database_index` | BOUNDED | Redis DB index 0-15 | Safe |
| `db.cassandra.keyspace` | DEPLOYMENT_DEPENDENT | Keyspace name | Usually safe |
| `db.hbase.namespace` | DEPLOYMENT_DEPENDENT | HBase namespace | Usually safe |
| `db.mongodb.collection` | DEPLOYMENT_DEPENDENT | Collection name | Usually safe |

---

## Messaging / Queues

| Attribute | Profile | Notes | Fix |
|-----------|---------|-------|-----|
| `messaging.message_id` | IDENTIFIER | Unique per message. Should never be a metric label | Drop immediately |
| `messaging.destination.name` | DEPLOYMENT_DEPENDENT | Topic/queue name. Bounded if topics are fixed, unbounded if dynamically created per user/tenant | Check cardinality |
| `messaging.kafka.message_key` | UNBOUNDED | Message key — can be any string | Drop |
| `messaging.kafka.partition` | BOUNDED | Partition number. Fixed per topic | Safe |
| `messaging.kafka.consumer_group` | DEPLOYMENT_DEPENDENT | Consumer group name. Usually bounded | Usually safe |
| `messaging.rabbitmq.routing_key` | DEPLOYMENT_DEPENDENT | Routing key. Bounded if fixed routes, unbounded if dynamic | Check cardinality |
| `messaging.operation` | BOUNDED | publish, receive, process etc. | Safe |
| `messaging.system` | BOUNDED | kafka, rabbitmq, sqs etc. | Safe |

---

## RPC / gRPC

| Attribute | Profile | Notes | Fix |
|-----------|---------|-------|-----|
| `rpc.method` | BOUNDED | gRPC method name. Fixed set per service definition | Safe |
| `rpc.service` | BOUNDED | gRPC service name. Fixed set | Safe |
| `rpc.system` | BOUNDED | grpc, thrift, etc. | Safe |
| `rpc.grpc.status_code` | BOUNDED | 0-16 fixed gRPC status codes | Safe |

---

## Kubernetes / Infrastructure

| Attribute | Profile | Notes | Fix |
|-----------|---------|-------|-----|
| `k8s.pod.uid` | ACCUMULATING | New UID per pod restart. Accumulates over time — 7-day window captures every pod that ever ran, not just current pods | Keep on Infra-page metrics; on unrelated custom metrics, aggregate only after identity and usage review |
| `k8s.pod.name` | ACCUMULATING | Pod names with random suffixes change on every restart/deploy. Same accumulation problem as pod.uid | Keep on Infra-page metrics; apply the generic fix only to unrelated custom metrics |
| `k8s.pod.start_time` | ACCUMULATING | Timestamp of pod start. Unique per pod lifecycle; the Pods page uses it for Pod Age | Keep on Pod Infra metrics; remove from unrelated custom metrics only after usage review |
| `container.id` | ACCUMULATING | Container runtime ID. New per restart; current Infra container identity uses `k8s.pod.uid` + `k8s.container.name` | Aggregate away after usage review |
| `k8s.namespace.name` | BOUNDED | Namespace. Fixed small set in most deployments | Safe |
| `k8s.deployment.name` | BOUNDED | Deployment name. Fixed set | Safe |
| `k8s.statefulset.name` | BOUNDED | StatefulSet name. Fixed set | Safe |
| `k8s.daemonset.name` | BOUNDED | DaemonSet name. Fixed set | Safe |
| `k8s.job.name` | DEPLOYMENT_DEPENDENT | Job names may include timestamps or IDs if dynamically generated | Check cardinality |
| `k8s.cronjob.name` | BOUNDED | CronJob name. Fixed set | Safe |
| `k8s.node.name` | DEPLOYMENT_DEPENDENT | Node name. Bounded by cluster size. Fine at 10 nodes, notable at 1000 | Check actual count |
| `k8s.cluster.name` | BOUNDED | Cluster name. Usually 1-5 values | Safe |
| `k8s.replicaset.name` | ACCUMULATING | Includes hash suffix, changes per deploy | Aggregate away |
| `k8s.container.name` | BOUNDED | Container name within pod spec. Fixed | Safe |

---

## Process / Runtime

| Attribute | Profile | Notes | Fix |
|-----------|---------|-------|-----|
| `process.pid` | UNBOUNDED | Process ID. New per process restart. Unbounded over time | Drop from metrics |
| `process.command_line` | UNBOUNDED | Full command with args. Can contain paths, flags, secrets | Drop entirely |
| `process.command_args` | UNBOUNDED | Array of command arguments | Drop entirely |
| `process.executable.path` | BOUNDED | Executable path. Usually fixed per service | Usually safe |
| `process.executable.name` | BOUNDED | Executable name. Fixed | Safe |
| `process.runtime.name` | BOUNDED | go, python, jvm, dotnet etc. | Safe |
| `process.runtime.version` | DEPLOYMENT_DEPENDENT | Runtime version. Bounded if versions are controlled | Usually safe |
| `process.owner` | BOUNDED | Process owner user. Fixed set | Safe |
| `thread.id` | UNBOUNDED | Thread ID. Unique per thread, changes on restart | Drop from metrics |
| `thread.name` | DEPLOYMENT_DEPENDENT | Thread name. Bounded if thread pool has fixed names, unbounded for request-scoped threads | Check cardinality |

---

## Errors / Exceptions

| Attribute | Profile | Notes | Fix |
|-----------|---------|-------|-----|
| `exception.stacktrace` | UNBOUNDED | Full stack trace as string. Every unique trace = new series. Should never be a metric label | Drop immediately |
| `exception.message` | UNBOUNDED | Error message. Can contain IDs, values, dynamic content | Drop or cap with metricstransform |
| `exception.type` | BOUNDED | Exception class name. Fixed set per application | Safe |
| `error.type` | BOUNDED | Error type/class. Fixed set | Safe |
| `error.stack` | UNBOUNDED | Stack trace. Same as exception.stacktrace | Drop immediately |

---

## Tracing / Correlation IDs (should never appear on metrics)

| Attribute | Profile | Notes | Fix |
|-----------|---------|-------|-----|
| `span.id` | IDENTIFIER | Unique per span. Catastrophic as metric label | Drop immediately |
| `trace.id` | IDENTIFIER | Unique per trace. Catastrophic as metric label | Drop immediately |
| `trace_id` | IDENTIFIER | Same | Drop immediately |
| `span_id` | IDENTIFIER | Same | Drop immediately |
| `request.id` | IDENTIFIER | Unique per request | Drop from metrics |
| `session.id` | IDENTIFIER | Unique per session | Drop from metrics |
| `user.id` | IDENTIFIER | Unique per user. Unbounded as metric label | Drop from metrics |
| `enduser.id` | IDENTIFIER | Same | Drop from metrics |

---

## Cloud / Provider

| Attribute | Profile | Notes | Fix |
|-----------|---------|-------|-----|
| `cloud.provider` | BOUNDED | aws, gcp, azure etc. | Safe |
| `cloud.region` | BOUNDED | us-east-1, eu-west-1 etc. Fixed set | Safe |
| `cloud.availability_zone` | BOUNDED | AZ name. Small fixed set per region | Safe |
| `cloud.account.id` | DEPLOYMENT_DEPENDENT | Account/project ID. Bounded by org structure | Usually safe |
| `cloud.resource_id` | UNBOUNDED | Full ARN or resource path. Includes instance IDs | Drop or restrict |
| `aws.lambda.invoked_arn` | UNBOUNDED | Full ARN with region and account | Drop |
| `faas.instance` | UNBOUNDED | Function instance ID. Unique per cold start | Drop |
| `faas.id` | UNBOUNDED | Function instance identifier | Drop |
| `faas.name` | BOUNDED | Function name. Fixed set | Safe |
| `faas.version` | DEPLOYMENT_DEPENDENT | Function version. Bounded if controlled | Usually safe |

---

## Service / SDK

| Attribute | Profile | Notes | Fix |
|-----------|---------|-------|-----|
| `service.name` | BOUNDED | Service name. Fixed set — this is a required attribute | Safe, keep always |
| `service.version` | DEPLOYMENT_DEPENDENT | Service version. Bounded if versioning is controlled. Can grow if CI deploys unique versions per commit | Check cardinality |
| `service.instance.id` | DEPLOYMENT_DEPENDENT | Instance identifier. Bounded = one per running pod. But if it includes a UUID or timestamp, it becomes ACCUMULATING | Check format — if it contains hyphens/long random strings, treat as ACCUMULATING |
| `service.namespace` | BOUNDED | Logical grouping of services. Fixed | Safe |
| `deployment.environment` | BOUNDED | prod, staging, dev, uat etc. | Safe |
| `telemetry.sdk.name` | BOUNDED | opentelemetry etc. | Safe |
| `telemetry.sdk.version` | BOUNDED | SDK version. Fixed per deployment | Safe |
| `telemetry.sdk.language` | BOUNDED | go, python, java etc. | Safe |

---

## How to classify an unknown attribute

If you encounter an attribute not listed above, reason through these questions:

1. **Can the value be user-supplied, request-scoped, or contain IDs?** → Likely UNBOUNDED. Drop.
2. **Does the value change every time a pod restarts or container is replaced?** → ACCUMULATING. Aggregate away.
3. **Is it a timestamp, UUID, hash, or has segments separated by hyphens/underscores of varying length?** → IDENTIFIER or UNBOUNDED. Drop.
4. **Is it chosen from a fixed vocabulary defined at deploy time?** → Probably BOUNDED. Check actual cardinality to confirm.
5. **Does the cardinality roughly equal the number of running instances/nodes/pods?** → DEPLOYMENT_DEPENDENT. Flag if count is high but not an immediate problem.

When uncertain — report the attribute name, its observed cardinality, and the value pattern (e.g. "looks like UUIDs", "looks like IP:port pairs") and let the user verify.

---

## Fix reference

For Infra-page metric families, the required identity attributes and page metadata in
`infra-do-not-drop.md` override the generic fixes below.

| Problem | Fix | Where |
|---------|-----|-------|
| UNBOUNDED label on existing metric | `metricstransform` processor — aggregate the label away (merges series) | OTel Collector |
| ACCUMULATING label | Same — `metricstransform` aggregate | OTel Collector |
| IDENTIFIER label (span.id, trace.id, user.id) | `metricstransform` `aggregate_labels` to merge series — or stop emitting it as a metric label | OTel Collector / SDK |
| Raw SQL / stack traces as labels | Instrument correctly — use `db.operation` not `db.query.text` | SDK / instrumentation config |
| Client port (net.peer.port, client.port) | `metricstransform` `aggregate_labels` to merge series — or stop emitting it at the SDK | OTel Collector / SDK |
| Too many service instances | `service.instance.id` is expected to be high — only a problem if it contains timestamps/UUIDs that don't reflect real instance count | Check format |

**Important — cardinality reduction means fewer samples, and samples are the billable cost.**
Use the `metricstransform` processor's `aggregate_labels` action to *merge* the
series that share the remaining labels — that is what actually cuts the series and sample count.
Do **not** use the `transform` processor's `delete_key`: removing a label key without merging
leaves the same number of samples and produces colliding series (SigNoz sums them), so cost does
not drop. If a label is essential to the metric's identity, drop the whole metric or stop
emitting the label at the SDK instead.

Docs: https://signoz.io/docs/metrics-management/dropping-metric-labels/
Docs: https://signoz.io/docs/logs-management/guides/remove-resource-attributes/
