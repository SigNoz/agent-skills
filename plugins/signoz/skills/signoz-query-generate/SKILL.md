---
name: signoz-query-generate
description: >
  Trigger when the user wants to generate, write, or run a query against their
  observability data.  Includes requests like "show me error rates",
  "query logs for timeout errors", "what's the p99 latency for the cart service",
  "how many requests hit the payment endpoint", "find slow traces".
---

# Query Generate

## When to use

Use this skill when the user asks to:
- Query, search, or look up observability data (traces, logs, metrics)
- Compute aggregations (error rate, p99 latency, request count, throughput)
- Find specific log entries, traces, or metric values
- Investigate patterns (spikes, drops, trends over time)

Do NOT use when:
- User wants to create a dashboard → `signoz-dashboard-create`
- User wants to modify a dashboard → `signoz-dashboard-modify`
- User wants to create or modify an alert → alert skills
- User wants to understand what a dashboard/alert shows → explain the entity directly

## Instructions

### Step 1: Determine the signal type

Map the user's intent to the right signal:

| User intent | Signal | Why |
|---|---|---|
| Error rate, latency, throughput, request count | **metrics** (preferred) or **traces** | Metrics are pre-aggregated and fastest. Use traces if the user needs per-request detail or no matching metric exists. |
| p50/p75/p90/p95/p99 latency | **metrics** (histogram) or **traces** (aggregate on `durationNano`) | Prefer metrics if a histogram metric exists (e.g., `signoz_latency_bucket`). Fall back to trace aggregation. |
| Find specific log entries, error messages, stack traces | **logs** | Text search, pattern matching, severity filtering. |
| Find specific traces, slow requests, error spans | **traces** | Per-request detail, span attributes, duration filtering. |
| Infrastructure metrics (CPU, memory, disk, network) | **metrics** | Always metrics for resource utilization. |
| "How many X per Y" (count/rate grouped by dimension) | **traces** or **logs** (aggregate) | Use `signoz_aggregate_traces` or `signoz_aggregate_logs` for grouped counts. |

If the signal is genuinely ambiguous, ask using `<assistant_question>`.

### Step 2: Discover available data

**Always discover before querying.** Use only names returned by tools — never
guess from training knowledge.

Run discovery calls in parallel where possible:

- **For metrics**: Call `signoz_list_metrics` with a `searchText` substring
  matching the user's intent (e.g., `searchText: "http"`, `searchText: "latency"`).
  The response includes metric type, temporality, and isMonotonic — pass these to
  `signoz_query_metrics` to avoid extra lookups.
- **For traces**: Call `signoz_list_services` to confirm the service name exists.
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
| Metric time series or scalar | `signoz_query_metrics` | Any metrics query. Handles aggregation defaults automatically. Supports formulas via `formula` + `formulaQueries` params. |
| Log search (find matching entries) | `signoz_search_logs` | Finding specific log lines. Use `searchText` for body text, `query` for field filters, `severity` for level filtering. |
| Trace search (find matching spans) | `signoz_search_traces` | Finding specific traces/spans. Use `service`, `operation`, `error`, `minDuration`/`maxDuration` shortcuts plus `query` for field filters. |
| Log aggregation (count, avg, percentiles) | `signoz_aggregate_logs` | "How many errors?", "error count by service", "p99 response time from logs". Set `requestType` to `scalar` for totals or `time_series` for trends. |
| Trace aggregation (count, avg, percentiles) | `signoz_aggregate_traces` | "p99 latency for checkout", "error count per operation", "request rate by endpoint". Set `requestType` to `scalar` for totals or `time_series` for trends. |
| Complex multi-query or formula | `signoz_execute_builder_query` | Only when the simpler tools above cannot express the query — e.g., joining multiple data sources, complex filter expressions, or queries needing the full Query Builder v5 schema. Read `signoz://traces/query-builder-guide` before using. |

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
  `query` expressions.
- Combine shortcut params with `query`/`filter` for additional constraints — they
  are ANDed together.
- For `signoz_query_metrics`, pass `metricType`, `temporality`, and `isMonotonic`
  from the `signoz_list_metrics` response to avoid an extra auto-fetch round trip.

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
- **Scope boundary**: This skill queries data. If the user's query results lead
  to wanting a dashboard, redirect to `signoz-dashboard-create`. If they want an alert,
  redirect to the alert skill.

## Examples

**User:** "Show me the error rate for the checkout service in the last hour"

**Agent:**
1. Calls `signoz_list_metrics(searchText: "error")` — finds
   `signoz_calls_total` metric.
2. Calls `signoz_query_metrics` with `metricName: "signoz_calls_total"`,
   `filter: "service.name = 'checkout'"`, `formula: "A / B * 100"` where A is
   error count and B is total count, `timeRange: "1h"`.
3. Presents: "Error rate for checkout-service: 2.3% over the last hour (14:00–
   15:00 UTC). 47 errors out of 2,041 total requests."
4. Offers drill-down: "Want me to check which operations have the highest error
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
   aggregateOn: "durationNano", service: "cart-service",
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
