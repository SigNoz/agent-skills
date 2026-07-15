---
name: signoz-generating-queries
description: >
  Generate, write, or run an ad-hoc query against SigNoz observability
  data — metrics, logs, or traces — without wrapping it in
  a dashboard panel or alert. Make sure to use this skill whenever the
  user asks "show me error rates", "query logs for timeout errors",
  "what's the p99 latency for the cart service", "how many requests hit
  the payment endpoint", "find slow traces", "errors in the last hour",
  or otherwise asks an exploratory question that needs live observability
  data — even if they don't say "query" or "search" explicitly.
---

# Query Generate

## Prerequisites

This skill calls SigNoz MCP server tools heavily (`signoz_execute_builder_query`,
`signoz_query_metrics`, `signoz_search_logs`, `signoz_search_traces`,
`signoz_aggregate_logs`, `signoz_aggregate_traces`, `signoz_get_field_keys`,
`signoz_get_field_values`, `signoz_list_metrics`, `signoz_list_services`,
`signoz_get_service_top_operations`, `signoz_get_trace_details`). Before
running the workflow, confirm the `signoz_*` tools are available. If they
are not, run `signoz-mcp-setup` first to initialize or repair the MCP connection.
Do not fall back to raw HTTP calls or fabricate query results without the MCP
tools.

## When to use

Use this skill when the user asks to:
- Query, search, or look up observability data (traces, logs, metrics)
- Compute aggregations (error rate, p99 latency, request count, throughput)
- Find specific log entries, traces, or metric values
- Investigate patterns (spikes, drops, trends over time)

Do NOT use when:
- User wants raw ClickHouse SQL for a dashboard panel (custom joins, window
  functions, regex over log bodies) — that's a separate dashboard-panel SQL
  workflow, not this skill.
- User needs the Exceptions Explorer as an exception-specific signal — the
  current MCP contract has no exception query tool. Explain that limitation and
  offer an equivalent error-trace or error-log query only if it answers their
  underlying question.

## Instructions

### Step 1: Determine the signal type

Map the user's intent to the right signal:

| User intent | Signal | Why |
|---|---|---|
| Error rate, latency, throughput, request count | **metrics** (preferred) or **traces** | Metrics are pre-aggregated and fastest. Use traces if the user needs per-request detail or no matching metric exists. |
| p50/p75/p90/p95/p99 latency | **metrics** (histogram) or **traces** (aggregate on `duration_nano`) | Prefer metrics if a histogram metric exists (e.g., `signoz_latency_bucket`). Fall back to trace aggregation. |
| Find specific log entries, error messages, stack traces | **logs** | Text search, pattern matching, severity filtering. |
| Find specific traces, slow requests, error spans | **traces** | Per-request detail, span attributes, duration filtering. |
| Infrastructure metrics (CPU, memory, disk, network) | **metrics** | Always metrics for resource utilization. |
| Ingestion volume (bytes or count), cost, or billing usage | **metrics** with `source=meter` (Cost Meter) | `signoz.meter.*` ingestion metrics (logs/spans/datapoints by count **and** bytes) live only in the meter store; bytes are unavailable on the raw signals. Dollar **cost is not a metric** — derive it from volume × per-unit price (see Step 2). groupBy/filter work like a normal metric, but only over the limited attribute set the meter retains (not arbitrary log/trace fields). For a *count* sliced by an attribute the meter doesn't carry, aggregate logs/traces directly instead. |
| "How many X per Y" (count/rate grouped by dimension) | **traces** or **logs** (aggregate) | Use `signoz_aggregate_traces` or `signoz_aggregate_logs` for grouped counts. |

If the signal is genuinely ambiguous, ask the user before proceeding. The
host application decides how the question is surfaced (e.g. a structured
clarification tool or an inline `<assistant_question>` tag) — follow the
host's UI rendering rules.

### Step 2: Discover available data

**Always discover before querying.** Use only names returned by tools — never
guess from training knowledge.

Run discovery calls in parallel where possible:

- **For metrics**: Call `signoz_list_metrics` with a `searchText` substring
  matching the user's intent (e.g., `searchText: "http"`, `searchText: "latency"`).
  The response includes metric type, temporality, and isMonotonic — pass these to
  `signoz_query_metrics` to avoid extra lookups.
- **For Cost Meter** (ingestion volume, cost, billing): pass `source=meter` to
  `signoz_list_metrics` to discover the metrics (`signoz.meter.*`) — they're
  invisible in the default store and the set evolves, so don't hardcode it.
  groupBy/filters/aggregations then work like any metric, with three caveats:
  *bytes exist only here* (count is also available via direct
  `signoz_aggregate_logs`/`_traces`); the meter retains only a *limited
  attribute set* — discover groupable keys via `signoz_get_field_keys(signal:
  "metrics", source: "meter")`, and fall back to a direct count (no bytes) to
  slice by an attribute it lacks; and **dollar cost is not a meter metric** —
  the store holds only volume, so don't `searchText: "cost"` expecting a hit.
  For a cost question, query the volume metric (bytes for logs/traces, count
  for metric datapoints) and multiply by the per-unit price from Settings →
  Billing — ask the user for the price if you don't have it.
- **For traces**: Call `signoz_list_services` to confirm the service name exists,
  following `pagination.nextOffset` while `pagination.hasMore` is true before
  declaring it missing.
  Optionally call `signoz_get_service_top_operations` for the service to find
  operation names. Call `signoz_get_field_keys(signal: "traces")` if you need
  to filter on a non-standard attribute.
- **For logs**: Call `signoz_get_field_keys(signal: "logs")` if filtering on
  attributes beyond `body`, `severity_text`, and `service.name`. Call
  `signoz_get_field_values` to validate specific filter values.

If the user already provides exact field names, service names, or metric names
from context (e.g., from a dashboard or @mention), skip redundant discovery.

### Step 3: Choose the right tool

**Use the simplest tool that answers the question:**

| Question type | Tool | When to use |
|---|---|---|
| Metric time series or scalar | `signoz_query_metrics` | Ordinary metrics queries, plus Cost Meter trends or per-second rates. Handles aggregation defaults automatically and supports formulas via `formula` + `formulaQueries` params. |
| Cost Meter total or grouped total attribution | `signoz_execute_builder_query` | Use the discovered meter metric with raw `timeAggregation: "sum"`; sum complete hourly buckets. Do not use `signoz_query_metrics` for totals. |
| Log search (find matching entries) | `signoz_search_logs` | Finding specific log lines. Use `searchText` for body text, `filter` for field filters, `severity` for level filtering. |
| Trace search (find matching spans) | `signoz_search_traces` | Finding specific traces/spans. Use `service`, `operation`, `error`, `minDuration`/`maxDuration` shortcuts plus `filter` for field filters. |
| Log aggregation (count, avg, percentiles) | `signoz_aggregate_logs` | "How many errors?", "error count by service", "p99 response time from logs". Set `requestType` to `scalar` for totals or `time_series` for trends. |
| Trace aggregation (count, avg, percentiles) | `signoz_aggregate_traces` | "p99 latency for checkout", "error count per operation", "request rate by endpoint". Set `requestType` to `scalar` for totals or `time_series` for trends. |
| Complex multi-query or formula | `signoz_execute_builder_query` | Only when simpler tools cannot express it. Read the guide for the actual signal: traces or logs query-builder guide, metrics aggregation guide, or PromQL instructions. |

**`requestType` decision for aggregations:**
- `scalar` (default): "How many?", "What is the p99?", "Which service has the most?"
- `time_series`: "When did errors spike?", "How did latency change?", "Show trend"
- If the question has ANY temporal component (spike, trend, change), use `time_series`

### Step 4: Execute the query

- Always include `searchContext` with the user's original question — it improves
  result relevance.
- Default time range is last 1 hour. Respect the user's time range if specified.
  Convert relative times ("last 6 hours", "yesterday") to `timeRange` param format
  (e.g., `6h`, `24h`) or Unix millisecond `start`/`end`.
- Use shortcut parameters (`service`, `severity`, `operation`, `error`) when they
  match the user's filters — they are simpler and less error-prone than building
  `filter` expressions.
- Combine shortcut params with `filter` for additional constraints — they
  are ANDed together.
- For `signoz_query_metrics`, pass `metricType`, `temporality`, and `isMonotonic`
  from the `signoz_list_metrics` response to avoid an extra auto-fetch round trip.
- For a **Cost Meter total or grouped total attribution**, use
  `signoz_execute_builder_query`, not `signoz_query_metrics`. Pass the full tool arguments with
  an outer `query` object, Unix-millisecond `start`/`end`, `requestType: "time_series"`,
  `formatOptions`, and `variables`. The builder spec keeps `signal: "metrics"`,
  `source: "meter"`, the discovered `metricName` and `temporality`, `stepInterval: 3600`,
  and raw `timeAggregation: "sum"` plus `spaceAggregation: "sum"`. For grouped totals,
  discover the meter field with `signoz_get_field_keys` and copy its `name`,
  `fieldDataType`, `fieldContext`, and `signal` into `groupBy` without dropping
  or translating fields. Exclude datapoints marked `partial: true`, then sum the
  complete hourly buckets for each returned group.
- `signoz_query_metrics` remains appropriate for a Cost Meter trend or rate that is not a total
  attribution. Carry `source=meter`, use `stepInterval: 3600`, use
  `timeAggregation: increase` for a volume trend, and `rate` only for a per-second rate.

### Step 5: Handle results

**Data returned:**
- Present findings as neutral observations with timestamps and values.
- Include the time range in your response.
- For aggregations with `groupBy`, highlight the top entries and mention total
  group count if truncated by `limit`.
- For search results, summarize patterns rather than listing every entry.

**No data returned — apply three-way distinction:**
1. **Healthy zero**: The query ran successfully but the count is zero. Say so:
   "No errors found for checkout-service in the last hour — error count is zero."
2. **No data in range**: The field/metric exists but no data points fall in the
   time window. Suggest expanding: "No data in the last hour. Try a wider range?"
3. **Missing instrumentation**: The metric, field, or service doesn't exist in
   discovery results. Say what's missing and suggest how to instrument.

**Drill-down:**
- If an aggregation reveals an interesting pattern (spike, outlier service),
  offer to drill into individual traces or logs for that scope.
- If a trace search returns interesting spans, offer to fetch full trace details
  via `signoz_get_trace_details`.

## Guardrails

- **Discovery first**: Never guess metric names, field names, or service names.
  Use discovery tools or context to confirm they exist before querying.
- **Never claim root cause**: Present data patterns and correlations. Write
  "Error rate for checkout increased from 0.2% to 4.1% at 14:05" not "The
  deployment caused the errors."
- **One focused query per question**: Do not scatter-shot multiple queries when
  one precise query answers the question. Use parallel discovery calls, but be
  precise for execution.
- **Respect MCP server rules**: The MCP server enforces rules about resource
  attribute filters, filter operators, and redundant queries. Follow them —
  especially preferring resource attributes in filters for faster queries.
- **No raw ClickHouse SQL**: Always use the Query Builder tools. Never construct
  raw SQL.
- **Scope boundary**: This skill queries data. If the user wants to wrap the
  query into a recurring alert, redirect to `signoz-creating-alerts`.
- **Emit `apply_filter` on the final message.** When the user asks you to
  write, build, generate, or show a query, include an `apply_filter` action
  on your final assistant message with the exact full v5 `query` object you
  passed to a successful `signoz_execute_builder_query` call in this turn. The
  chip carries the entire query-range envelope (`schemaVersion`, `start`,
  `end`, `requestType`, `compositeQuery`), not just the inner
  `compositeQuery`, and you must copy it verbatim rather than reconstructing
  it. If you answered via simplified tools (`signoz_search_logs`,
  `signoz_search_traces`, `signoz_aggregate_*`, `signoz_query_metrics`), run
  one validating `signoz_execute_builder_query` with a small `limit` and copy
  that exact query object, or skip the chip. Use the appropriate `signal`
  field (`metrics`, `logs`, or `traces`). This signals to the SigNoz UI that
  the user wants to apply the query to an explorer page. Only emit
  `apply_filter` when the user's primary intent is to obtain a runnable query
  — not when the user is asking a one-shot data question that the analysis text
  already answers. For a Cost Meter query keep `signal: metrics` and ensure the
  copied query spec carries `source: meter`.

## Examples

**User:** "Show me the error rate for the checkout service in the last hour"

**Agent:**
1. Calls `signoz_list_metrics(searchText: "calls", timeRange: "1h")` and
   selects the exact returned request-count metric. In this example discovery
   returns `signoz_calls_total` with `metricType: "sum"`,
   `temporality: "cumulative"`, and `isMonotonic: true`.
2. Calls `signoz_get_field_keys(signal: "metrics", metricName:
   "signoz_calls_total", searchText: "status")`, then calls
   `signoz_get_field_values` with `signal: "metrics"`, the returned field
   `name` and `fieldContext`, and the same `metricName`, confirming the error
   value `STATUS_CODE_ERROR`.
3. Calls `signoz_query_metrics` with these complete arguments. The primary
   arguments define query A; `formulaQueries` explicitly defines query B with
   a different filter so the denominator includes every checkout request:

   ```json
   {
     "searchContext": "Show me the error rate for the checkout service in the last hour",
     "metricName": "signoz_calls_total",
     "metricType": "sum",
     "isMonotonic": true,
     "temporality": "cumulative",
     "timeAggregation": "increase",
     "spaceAggregation": "sum",
     "filter": "service.name = 'checkout-service' AND status_code = 'STATUS_CODE_ERROR'",
     "timeRange": "1h",
     "requestType": "scalar",
     "formula": "A / B * 100",
     "formulaQueries": [{
       "name": "B",
       "metricName": "signoz_calls_total",
       "metricType": "sum",
       "isMonotonic": true,
       "temporality": "cumulative",
       "timeAggregation": "increase",
       "spaceAggregation": "sum",
       "filter": "service.name = 'checkout-service'"
     }]
   }
   ```

   Replace every concrete metric, metadata value, field, and field value above
   with the tenant's discovery results; never assume this example exists.
4. Presents: "Error rate for checkout-service: 2.3% over the last hour (14:00–
   15:00 UTC). 47 errors out of 2,041 total requests."
5. Offers drill-down: "Want me to check which operations have the highest error
   rate?"

---

**User:** "Find timeout errors in logs"

**Agent:**
1. Calls `signoz_search_logs(searchText: "timeout", severity: "ERROR",
   timeRange: "1h")`.
2. Presents: "Found 23 timeout errors in the last hour. Most are from
   payment-service (18) and gateway (5). Common pattern: 'context deadline
   exceeded' in gRPC calls to downstream-api."
3. Offers: "Want me to check traces for these services to see where the
   timeouts occur?"

---

**User:** "What's the p99 latency for the cart service?"

**Agent:**
1. Calls `signoz_aggregate_traces(aggregation: "p99",
   aggregateOn: "duration_nano", service: "cart-service",
   requestType: "scalar", timeRange: "1h")`.
2. Presents: "p99 latency for cart-service: 1.2s over the last hour."
3. Offers: "Want me to break this down by operation or show the trend over time?"

---

**User:** "When did errors spike for the frontend?"

**Agent:**
1. Calls `signoz_aggregate_traces(aggregation: "count", error: "true",
   service: "frontend", requestType: "time_series", timeRange: "6h")`.
2. Presents: "Error count for frontend over the last 6 hours. Spike at 11:30 UTC
   — error count jumped from ~5/min to ~45/min, returning to baseline by 12:15."
3. Offers: "Want me to check what error types appeared during the spike?"

---

**User:** "How much log data is each service ingesting?"

**Agent:**
1. Bytes by service → Cost Meter. `signoz_list_metrics(searchText: "log",
   source: "meter")` and selects the returned log-volume metric from its live name and unit.
2. Calls `signoz_execute_builder_query` with the outer `query` wrapper, Unix-ms range,
   `requestType: "time_series"`, `formatOptions`, `variables`, and a builder spec using
   `signal: "metrics"`, `source: "meter"`, the discovered metric name and temporality,
   `stepInterval: 3600`, raw `timeAggregation: "sum"`, `spaceAggregation: "sum"`, and
   the `service.name` field returned by `signoz_get_field_keys`, copying its
   `name`, `fieldDataType`, `fieldContext`, and `signal` into `groupBy`.
3. Excludes `partial: true` datapoints, sums complete hourly buckets per service, and presents
   per-service ingestion in the discovered unit. (If the meter lacks a requested attribute,
   fall back to a direct count and note that bytes remain meter-only.)
