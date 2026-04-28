---
name: signoz-dashboard-explain
description: >
  Trigger when the user wants to understand, interpret, or get an overview of an
  existing dashboard. Includes requests like "explain this dashboard", "what does
  my Redis dashboard show", "walk me through the panels on this dashboard",
  "what should I watch for on this dashboard", "help me understand this dashboard".
---

# Dashboard Explain

## Prerequisites

This skill calls SigNoz MCP server tools (`signoz_get_dashboard`,
`signoz_list_dashboards`). Before running the workflow, confirm the
`signoz_*` tools are available. If they are not, the SigNoz MCP server
is not installed or configured — stop and direct the user to set it up:
<https://signoz.io/docs/ai/signoz-mcp-server/>. Do not guess at a
dashboard's contents from its title alone.

## When to use

Use this skill when the user asks to:
- Understand, explain, or interpret an existing dashboard
- Get a walkthrough of what panels show and why they matter
- Know what to watch for or what healthy/unhealthy looks like on a dashboard
- Understand the variables, filters, or queries on a dashboard

Do NOT use when:
- User wants to create a new dashboard → `signoz-dashboard-create`
- User wants to modify an existing dashboard → `signoz-dashboard-modify`
- User wants to query data without a dashboard context → `signoz-query-generate`

## Instructions

### Step 1: Identify the target dashboard

Determine which dashboard the user wants explained. If the user provides a
dashboard name, UUID, or it is clear from context (e.g., an @mention or
auto-context providing a dashboard resource), use that.

If the target dashboard is ambiguous:
1. Call `signoz_list_dashboards` to list existing dashboards. **Paginate through
   all pages** — check `pagination.hasMore` in the response. If `hasMore` is true,
   call again with `offset` set to `pagination.nextOffset` and repeat until all
   pages are exhausted. Never stop at the first page.
2. Present matching candidates to the user and ask which one to explain.

### Step 2: Fetch the full dashboard configuration

Call `signoz_get_dashboard` with the dashboard UUID. This is **mandatory** — you
need the complete JSON to explain the dashboard accurately. Never guess based on
the title alone.

Examine the response to understand:
- `title`, `description`, `tags` — the dashboard identity and author-provided context
- `variables` — dashboard-level filters (dropdowns the user can change)
- `widgets` — the panels, their types, titles, and queries
- `layout` — how panels are arranged in the 12-column grid
- `panelMap` — which panels belong to which row sections

### Step 3: Build the explanation

Structure your explanation in this order:

**1. Overview** — One paragraph summarizing the dashboard's purpose, what it
monitors, and what data sources it draws from (metrics, traces, logs). Mention
the `tags` if they provide useful context.

**2. Variables and filters** — Explain each variable:
- Name and what it filters (e.g., "The `service_name` variable filters all panels
  to a specific service")
- Type: DYNAMIC (auto-populated from telemetry), QUERY (SQL-driven dropdown), or
  TEXTBOX (free-form input)
- Whether it supports multi-select and has "ALL" option
- Note if any panels do NOT reference a variable in their filters — changing that
  variable dropdown would not affect those panels, which can be confusing

**3. Panel-by-panel walkthrough** — Group panels by their row sections using the
`panelMap` structure (row widget titles are the section headers). If the dashboard
has no rows (empty `panelMap`), walk through panels in layout order (by `y` then
`x` position) and organize by logical theme. For each panel:
- **Title** and **panel type** (graph, value, table, bar, pie, histogram, list)
- **What it shows** — interpret the query in plain language. For builder queries,
  explain the metric/data source, aggregation, filters, and groupBy. For formulas,
  explain each sub-query and how the formula combines them. For ClickHouse SQL or
  PromQL, translate the query intent into plain English.
- **What to watch for** — describe what healthy looks like and what patterns
  indicate trouble. Be specific: "sustained usage above 80% means..." not just
  "watch if it's high". Anchor advice to the actual metric being queried, not
  generic domain knowledge.
- **Unit** — mention the y-axis unit so the user knows how to read the values

For panels with complex queries:
- **Formulas** (queryFormulas): explain each sub-query (A, B, ...) separately,
  then explain what the formula computes and why
- **Multiple queries on one panel**: explain each query and how they relate
- **Functions** (rate, derivative, clampMin/Max, timeShift): explain the transform
  in plain terms (e.g., "rate converts the raw counter into a per-second value")

**4. Dashboard health observations** — After the walkthrough, note any structural
issues you spotted:
- Panels with no queries or empty/disabled queries
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

After the explanation, offer actionable follow-ups:
- "Want me to run the queries from any specific panel to check if they're returning
  data?"
- "Want me to add any missing panels or thresholds?" (→ `signoz-dashboard-modify`)
- "Want me to create a companion dashboard for [related area]?" (→ `signoz-dashboard-create`)

## Guardrails

- **Fetch before explaining**: Always call `signoz_get_dashboard` to get the full
  configuration. Never explain based on the dashboard title or listing alone.
- **Interpret, don't dump**: Translate queries into plain operational language. Never
  show raw query JSON to the user unless they specifically ask.
- **Anchor to actual content**: Base "what to watch for" advice on the actual metrics
  and queries in the dashboard, not on generic domain knowledge unrelated to the
  panels present.
- **Group by sections**: Use the `panelMap` row structure to group panels, not layout
  coordinates. The row titles are the section headers the dashboard author intended.
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
  something after your explanation, redirect to `signoz-dashboard-modify`. If they want a
  new dashboard, redirect to `signoz-dashboard-create`.

## Examples

**User:** "Explain my PostgreSQL dashboard"

**Agent:**
1. Calls `signoz_list_dashboards` (paginates all pages) — finds "PostgreSQL
   Overview" dashboard with UUID `abc-123`.
2. Calls `signoz_get_dashboard` with UUID `abc-123` — gets full configuration.
3. Provides structured explanation:
   - **Overview**: "This dashboard monitors PostgreSQL database health across
     connections, query performance, buffer cache efficiency, and replication. It
     uses metrics from the OpenTelemetry PostgreSQL receiver."
   - **Variables**: "Two variables — `host_name` (DYNAMIC, filters by
     `host.name`) and `database` (DYNAMIC, filters by `postgresql.database.name`).
     Both support multi-select."
   - **Panels by section**: Walks through each row section, explaining every panel's
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
1. Extracts dashboard UUID from the provided context.
2. Calls `signoz_get_dashboard` — gets full configuration.
3. Provides a focused panel-by-panel walkthrough grouped by row sections,
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
