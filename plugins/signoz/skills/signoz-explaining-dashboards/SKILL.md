---
name: signoz-explaining-dashboards
description: >
  Explain what an existing SigNoz dashboard shows in plain operational
  language — the panels, queries, variables, and what to watch for on
  each. Make sure to use this skill whenever the user asks "explain this
  dashboard", "what does my [X] dashboard show", "walk me through the
  panels", "what should I watch for on this dashboard", or "help me
  understand this dashboard", or otherwise asks for an interpretation of
  a dashboard's contents — even if they don't say "explain" explicitly.
  Also use it when someone is onboarding to a service and wants to
  understand what its existing observability looks like.
---

# Dashboard Explain

## Prerequisites

This skill calls SigNoz MCP server tools (`signoz_get_dashboard`,
`signoz_list_dashboards`). Before running the workflow, confirm the
`signoz_*` tools are available. If they are not, the SigNoz MCP server
is not installed or configured — run `signoz-mcp-setup` first to initialize or
repair the MCP connection. Do not guess at a dashboard's contents from its
title alone.

## When to use

Use this skill when the user asks to:
- Understand, explain, or interpret an existing dashboard
- Get a walkthrough of what panels show and why they matter
- Know what to watch for or what healthy/unhealthy looks like on a dashboard
- Understand the variables, filters, or queries on a dashboard

Do NOT use when:
- User wants to modify an existing dashboard → `signoz-modifying-dashboards`

## Instructions

### Step 1: Identify the target dashboard

Use a supplied id or a dashboard resource that includes its id directly.
For any name-only request, call `signoz_list_dashboards` and resolve the name to
an id, matching on `spec.display.name`. **Cover the whole listing** — narrow with
the `filter` argument, re-run unfiltered when it comes back empty, and page by
raising `offset` by `limit` until you have covered `total`. Never pass a
dashboard name to `signoz_get_dashboard` or conclude it is missing from the
first page.

If multiple dashboards match, present the candidates and ask which one to
explain.

### Step 2: Fetch the full dashboard configuration

Call `signoz_get_dashboard` with the dashboard id. This is **mandatory** — you
need the complete JSON to explain the dashboard accurately. Never guess based on
the title alone.

Examine the response to understand:
- `spec.display.name`, `.description`, `tags` — the dashboard identity and author-provided context
- `spec.variables` — dashboard-level filters (dropdowns the user can change)
- `spec.panels` — a map keyed by panel id: the panels, their plugin kinds, titles, and queries
- `spec.layouts` — Grid entries placing panels in the 12-column grid via `content.$ref`
- each Grid's `spec.display.title` — the section a panel belongs to

### Step 3: Build the explanation

Structure your explanation in this order:

**1. Overview** — One paragraph summarizing the dashboard's purpose, what it
monitors, and what data sources it draws from (metrics, traces, logs). Mention
the `tags` if they provide useful context.

**2. Variables and filters** — Explain each variable:
- Name (`spec.name`, the `$handle` queries reference) and what it filters — for a
  `signoz/DynamicVariable` that is `plugin.spec.name` on `plugin.spec.signal`
- Kind: `signoz/DynamicVariable` (auto-populated from telemetry),
  `signoz/QueryVariable` (query-driven dropdown), `signoz/CustomVariable`
  (configured choices), or a `TextVariable` (free-form input)
- Whether it supports multi-select (`allowMultiple`) and an "ALL" option
- Note if any panels do NOT reference a variable in their `filter.expression` —
  changing that variable dropdown would not affect those panels, which can be
  confusing

**3. Panel-by-panel walkthrough** — Group panels by Grid section: walk
`spec.layouts` in order, using each Grid's `spec.display.title` as the section
header and following its `spec.items` (by `y` then `x`) to the panels they
`$ref`. For a single untitled Grid, walk panels in position order and organize
by logical theme. For each panel:
- **Title** and **panel type** in plain words, from the plugin `kind`:
  `signoz/TimeSeriesPanel`, `signoz/NumberPanel` (single value),
  `signoz/TablePanel`, `signoz/BarChartPanel`, `signoz/PieChartPanel`,
  `signoz/HistogramPanel`, `signoz/ListPanel` (raw rows)
- **What it shows** — interpret the panel's one query in plain language. For
  `signoz/BuilderQuery`, explain the signal, aggregation, `filter.expression`,
  and `groupBy`. For a `signoz/CompositeQuery`, explain each member and how the
  formula combines them. For ClickHouse SQL or PromQL, translate the query
  intent into plain English.
- **What to watch for** — describe what healthy looks like and what patterns
  indicate trouble. Be specific: "sustained usage above 80% means..." not just
  "watch if it's high". Anchor advice to the actual metric being queried, not
  generic domain knowledge.
- **Unit** — mention `plugin.spec.formatting.unit` so the user knows how to read the values

For panels with complex queries:
- **Formulas** (inside a composite): explain each member (A, B, ...) separately,
  then explain what the formula computes and why
- **Functions** (rate, derivative, clampMin/Max, timeShift): explain the transform
  in plain terms (e.g., "rate converts the raw counter into a per-second value")

**4. Dashboard health observations** — After the walkthrough, note any structural
issues you spotted:
- Panels with no query, or a composite whose members are all disabled
- Panels in `spec.panels` that no grid item references (they never render)
- Variables defined but not referenced in any panel filter
- Panels missing thresholds where they would be useful (e.g., utilization panels
  without a saturation warning line)
- Counters displayed without a rate function (raw counters produce ever-increasing
  ramps, not operational rates)
- Very wide step intervals that could hide spikes
- Panels with high-cardinality groupBy that may produce unreadable charts

**5. Coverage gaps** — Based on what the dashboard actually monitors, note
significant observability areas that are absent. Only mention gaps that are
directly related to the technology or domain the dashboard covers — do not
speculate about unrelated areas. Frame as suggestions: "You may want to consider
adding panels for X to cover Y."

### Step 4: Offer next steps

Surface up to 3 follow-up intents based on what the explanation
surfaced — things like running a specific panel's underlying query,
filling a coverage gap, or wiring an alert for an actionable threshold
the user has not yet alerted on. Use your judgment; do not pad to 3.

Skip follow-ups when the user was clearly just onboarding to the
dashboard ("what is this?") and showed no further intent. No chips
beat wrong chips.

## Guardrails

- **Fetch before explaining**: Always call `signoz_get_dashboard` to get the full
  configuration. Never explain based on the dashboard title or listing alone.
- **Interpret, don't dump**: Translate queries into plain operational language. Never
  show raw query JSON to the user unless they specifically ask.
- **Anchor to actual content**: Base "what to watch for" advice on the actual metrics
  and queries in the dashboard, not on generic domain knowledge unrelated to the
  panels present.
- **Group by sections**: Use each Grid's `spec.display.title` to group panels, not layout
  coordinates. Those titles are the section headers the dashboard author intended.
- **No data queries by default**: Do not run live queries unless the user asks. The
  explain skill is about understanding the dashboard structure, not inspecting
  current data.
- **Paginate dashboard listing**: When searching for a dashboard by name, always
  paginate through all pages of `signoz_list_dashboards` before concluding a
  dashboard does not exist.
- **All query types**: Handle builder, ClickHouse SQL, and PromQL queries — each
  requires a different interpretation approach. For builder queries, read the
  aggregations, filter expression, and groupBy. For raw SQL/PromQL, parse the
  query string and explain the intent.
- **Scope boundary**: This skill explains dashboards. If the user wants to change
  something after your explanation, redirect to `signoz-modifying-dashboards`.

## Examples

**User:** "Explain my PostgreSQL dashboard"

**Agent:**
1. Calls `signoz_list_dashboards` (paginates all pages) — finds "PostgreSQL
   Overview" dashboard with id `abc-123`.
2. Calls `signoz_get_dashboard` with id `abc-123` — gets full configuration.
3. Provides structured explanation:
   - **Overview**: "This dashboard monitors PostgreSQL database health across
     connections, query performance, buffer cache efficiency, and replication. It
     uses metrics from the OpenTelemetry PostgreSQL receiver."
   - **Variables**: "Two variables — `host_name` (dynamic, filters by
     `host.name`) and `database` (dynamic, filters by `postgresql.database.name`).
     Both support multi-select."
   - **Panels by section**: Walks each Grid section, explaining every panel's
     metric, aggregation, and what to watch for.
   - **Health observations**: "The 'Connection Count' panel has no threshold
     configured — consider adding a line at 80% of your max_connections."
   - **Coverage gaps**: "No panels for vacuum/autovacuum health or lock contention.
     Consider adding these if you manage write-heavy workloads."
4. Offers: "Want me to run any panel queries to check for data, or add the
   suggested panels?"

---

**User:** "What does each panel on this dashboard show?" (with dashboard context
provided via @mention or auto-context)

**Agent:**
1. Extracts the dashboard id from the provided context.
2. Calls `signoz_get_dashboard` — gets full configuration.
3. Provides a focused panel-by-panel walkthrough grouped by Grid section,
   explaining what each panel shows and what to watch for.
4. Skips the health/gaps sections unless something notable stands out, since the
   user asked specifically about panels.

---

**User:** "Help me understand this LLM monitoring dashboard — I'm new to it"

**Agent:**
1. Identifies the dashboard, fetches full config.
2. Provides a beginner-friendly explanation with more context per panel:
   - Explains what the metrics mean (e.g., "Token usage measures how many
     tokens your LLM calls consume, which directly impacts cost")
   - Explains what the variables control and recommends starting with the "ALL"
     option to see the full picture before filtering
   - Highlights the most important panels to watch daily vs. those useful only
     during debugging
3. Offers to set up alerts on critical panels.
