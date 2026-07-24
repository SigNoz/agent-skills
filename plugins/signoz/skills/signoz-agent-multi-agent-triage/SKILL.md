---
name: signoz-agent-multi-agent-triage
description: >
  Diagnose why a specific agent in a multi-agent fleet (Claude Code, Codex,
  OpenCode, Grok, or any agent emitting gen_ai.* OpenTelemetry spans) failed,
  stalled, produced wrong output, or burned unexpected tokens/cost — by
  correlating its own gen_ai spans with the upstream baton/handoff chain,
  tool-call errors, and token anomalies in SigNoz, then ranking likely causes
  and suggesting a fix. Use this skill whenever the user asks "why did agent X
  fail", "triage the fleet", "what went wrong with <agent>", "root-cause this
  agent", "which agent is stalling", or wants agent-native (self-reading)
  observability of a coding-agent fleet rather than a human staring at a
  dashboard — even if they never say "SigNoz", "spans", or "traces" explicitly,
  so long as a multi-agent fleet is failing and its telemetry lands in SigNoz.
  Read-only — it queries SigNoz and does not modify the fleet.
argument-hint: <agent id> [service name] [time window]
---

# SigNoz Agent Multi-Agent Triage

Diagnose one agent in a multi-agent fleet from its **own** OpenTelemetry traces.
When a single agent in a hand-off pipeline fails, the cause is rarely visible in
that agent alone: it may be an upstream agent that passed a corrupt baton, a
tool call that timed out, or a context window that quietly overflowed. This skill
correlates the agent's `gen_ai.*` spans with the handoff that led into it and the
fleet's token baseline, then ranks the likely causes with evidence and a fix.

It works with **any** multi-agent system that emits standard `gen_ai.*` spans to
SigNoz — not just one framework. It is the fleet-level companion to
`signoz-investigating-alerts` (which diagnoses a fired alert) and
`signoz-writing-clickhouse-queries` (which optimizes the SQL below).

## Prerequisites

- SigNoz MCP connected (`signoz-mcp-setup`). This skill uses
  `signoz_search_traces` / `signoz_execute_builder_query`, or the ClickHouse SQL
  below via `signoz-writing-clickhouse-queries`.
- The fleet emits spans carrying at minimum:
  - `gen_ai.agent.id` — the agent identifier (required for correlation)
  - `gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens`
  - `status_code` (`STATUS_CODE_OK` = 1 / `STATUS_CODE_ERROR` = 2)
  - `duration_nano`
- For handoff correlation: upstream context attributes such as
  `notch.handoff.from` / `notch.handoff.to`. Adapt the attribute names in the
  `WHERE` clauses to your framework if it labels handoffs differently.

## When to use

Use it when a fleet agent is failing, stalling, looping, producing wrong output,
or spending unexpectedly — and you want the specific span, the upstream handoff,
and a concrete fix, not a wall of traces. Do **not** use it to explain a fired
alert (use `signoz-investigating-alerts`) or to build a query from scratch (use
`signoz-generating-queries`).

## Required inputs

- `agent_id` — e.g. `opencode`, `claude-code`, `codex`.
- `service_name` — the OTel `service.name` for the fleet (often `notch`).
- `time_window` — default the last 1 hour.

## Workflow

### 1. Fetch the agent's recent spans

Pull the agent's own turns plus the handoffs it is part of. Reference SQL:

```sql
SELECT
  trace_id,
  span_id,
  name,
  status_code,
  duration_nano / 1e6                              AS duration_ms,
  toUnixTimestamp64Milli(timestamp)                AS ts_ms,
  attributes_string['gen_ai.agent.id']             AS agent_id,
  attributes_string['gen_ai.system']               AS ade,
  attributes_string['gen_ai.request.model']        AS model,
  attributes_number['gen_ai.usage.input_tokens']   AS tokens_in,
  attributes_number['gen_ai.usage.output_tokens']  AS tokens_out,
  attributes_number['gen_ai.usage.cost_usd']       AS cost_usd,
  attributes_string['notch.handoff.from']          AS handoff_from,
  attributes_string['notch.handoff.to']            AS handoff_to
FROM signoz_traces.distributed_signoz_index_v3
WHERE `resource_string_service$$name` = 'notch'
  AND ( attributes_string['gen_ai.agent.id']  = 'opencode'
     OR attributes_string['notch.handoff.to']   = 'opencode'
     OR attributes_string['notch.handoff.from'] = 'opencode' )
  AND timestamp >= now() - INTERVAL 1 HOUR
ORDER BY timestamp DESC
LIMIT 50
```

Replace `'notch'` and `'opencode'` with the real `service_name` and `agent_id`.

### 2. Classify the failure

Apply this table to the retrieved spans and take the **highest-ranked** signal
that fires:

| Signal | Threshold | Classification |
|---|---|---|
| `status_code = 2` (ERROR) | any error span | **Tool / process error** |
| `duration_ms > 60000` | any turn | **LLM stall / timeout** |
| `tokens_in > 100000` | any turn | **Context window overflow** |
| cumulative `cost_usd` over budget | running total | **Budget overrun** |
| `handoff_from` present, no OK turn follows | — | **Upstream bad handoff** |
| 0 spans returned | — | **Not instrumented / never ran** |

Rank when several fire: Error > Stall > Overflow > Budget > Bad handoff.

### 3. Trace the upstream handoff chain (when relevant)

For **Upstream bad handoff**, pull the upstream agent's final span before it
passed the baton in:

```sql
SELECT
  attributes_string['gen_ai.agent.id']  AS agent_id,
  attributes_string['notch.handoff.to'] AS handed_to,
  status_code,
  duration_nano / 1e6                    AS duration_ms,
  toUnixTimestamp64Milli(timestamp)      AS ts_ms
FROM signoz_traces.distributed_signoz_index_v3
WHERE `resource_string_service$$name` = 'notch'
  AND attributes_string['notch.handoff.to'] = 'opencode'
  AND timestamp >= now() - INTERVAL 1 HOUR
ORDER BY timestamp DESC
LIMIT 10
```

A `status_code = 2` on the upstream agent's last span before the handoff is the
root cause: it passed a corrupt or incomplete payload downstream.

### 4. Compare token usage against the fleet baseline

```sql
SELECT
  attributes_string['gen_ai.agent.id']                 AS agent_id,
  avg(attributes_number['gen_ai.usage.input_tokens'])  AS avg_tokens_in,
  avg(attributes_number['gen_ai.usage.cost_usd'])      AS avg_cost_usd,
  count()                                               AS turns
FROM signoz_traces.distributed_signoz_index_v3
WHERE `resource_string_service$$name` = 'notch'
  AND name = 'gen_ai.agent.turn'
  AND timestamp >= now() - INTERVAL 1 HOUR
GROUP BY agent_id
```

Flag the agent if its `avg_tokens_in` is more than 2× the fleet average — a sign
of context bloat, an oversized baton payload, or prompt injection.

### 5. Produce the root-cause report

```
Agent: <agent_id>   Classification: <from step 2>   Confidence: High / Medium / Low
Root cause: <one paragraph, specific to the actual span values and timestamps>
Evidence:
  - <span name> at <ts> — status=<OK|ERROR>, <duration>ms, <N> tokens
  - Upstream handoff from <agent> — <OK|ERROR>
  - Token anomaly: <N>k vs fleet avg <M>k
Suggested fix: <specific and actionable>
Follow-up:
  - Full trace in SigNoz: <signoz-url>/trace/<trace_id>
  - Prevent recurrence — signoz-creating-alerts
```

If there are **no** error spans, report the agent as healthy (turn count, slowest
turn) — do not invent a failure.

### 6. Offer prevention alerts

After the diagnosis, offer `signoz-creating-alerts` to catch a recurrence:
- error-rate alert: `status_code = 2` rate > 5% over 5 minutes;
- latency alert: p95 `duration_ms` > 60000;
- token alert: `avg_tokens_in` above the fleet baseline.

## Limitations

- Requires `gen_ai.agent.id` on every span; without it, fleet-level correlation
  is impossible.
- Handoff tracing needs `notch.handoff.*` (or your framework's equivalent) — adapt
  the `WHERE` clauses accordingly.
- An agent reporting `0` tokens is not emitting usage from its CLI adapter; fix
  the adapter before attempting cost-based triage.

## Related Skills

- `signoz-generating-queries` — construct MCP trace/log/metric queries.
- `signoz-writing-clickhouse-queries` — optimized ClickHouse SQL for the queries above.
- `signoz-investigating-alerts` — root-cause a fired alert (single signal).
- `signoz-creating-alerts` — set up recurrence prevention.

## Follow-up

1. If the fix is a code change, instrument the gap and confirm the new spans land
   in SigNoz within the next turn.
2. If the upstream agent was the culprit, re-run this skill on that agent.
3. Use `signoz-creating-alerts` to prevent recurrence, and share the trace with
   your team.
