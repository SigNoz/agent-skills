---
name: signoz-explaining-dashboards
description: >
  Explain what an existing SigNoz dashboard shows in plain operational
  language: the panels, queries, variables, and what to watch for on
  each. Make sure to use this skill whenever the user asks "explain this
  dashboard", "what does my [X] dashboard show", "walk me through the
  panels", "what should I watch for on this dashboard", or "help me
  understand this dashboard", or otherwise asks for an interpretation of
  a dashboard's contents, even if they don't say "explain" explicitly.
  Also use it when someone is onboarding to a service and wants to
  understand what its existing observability looks like.
---

# Dashboard Explain

## Prerequisites

This skill calls SigNoz MCP server tools (`signoz_get_dashboard`,
`signoz_list_dashboards`). Before running the workflow, confirm the
`signoz_*` tools are available. If they are not, the SigNoz MCP server
is not installed or configured; run `signoz-mcp-setup` first to initialize or
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
Resolve every name-only request to an id; never pass a dashboard name to
`signoz_get_dashboard`.

1. Call `signoz_list_dashboards`, narrowing with the `filter` argument. Read
   `signoz://dashboard/list-filter-guide` before writing a filter longer than
   one free-text word. If a filtered listing returns nothing, list again
   without the filter, from offset 0.
2. Cover the whole listing before concluding a dashboard is missing. Start at
   offset 0 and keep the same filter and sort. While the result's
   `pagination.hasMore` is true, continue at `pagination.nextOffset`; when it
   is false, stop. When the result has no `pagination` object, raise `offset`
   by the number of dashboards the page returned and stop once the offset
   reaches the reported `total`. Do not raise `offset` by `limit`, because a
   page can hold fewer dashboards than `limit`. If a page returns no
   dashboards before the offset reaches `total`, tell the user the listing is
   incomplete.
3. Match on `spec.display.name`. If multiple dashboards match, present the
   candidates and ask which one to explain.
4. If the matched row has `legacy: true`, stop and tell the user: the
   dashboard is still in the v1 schema and `signoz_get_dashboard` cannot
   fetch it. Do not explain it from the list row.

### Step 2: Fetch the dashboard and read the guides it needs

1. Call `signoz_get_dashboard` with the dashboard id. This is **mandatory**;
   you need the complete JSON to explain the dashboard accurately. Never guess
   from the title or the list row.
2. Read `signoz://dashboard/widgets-instructions` before interpreting the
   panels. It says what each panel kind draws, how each kind shows legends
   and thresholds, and which query kinds each accepts. Take the meaning of a
   plugin `kind` from this guide, not from memory.
3. Read `signoz://dashboard/instructions` when the dashboard has variables or
   more than one Grid. It explains the variable kinds, what the ALL option
   means, and how grid items place panels.
4. Read the guide for a query you cannot interpret from its JSON:
   - Query Builder: `signoz://traces/query-builder-guide`,
     `signoz://logs/query-builder-guide`, or
     `signoz://metrics-aggregation-guide` for the signal;
     `signoz://ai/query-builder-guide` for a `signoz/AIBuilderQuery`.
   - PromQL: `signoz://promql/instructions`.
   - ClickHouse SQL: `signoz://dashboard/clickhouse-schema-for-metrics`,
     `signoz://dashboard/clickhouse-schema-for-traces`, or
     `signoz://dashboard/clickhouse-schema-for-logs` for the tables the
     statement reads.

If this client cannot read `signoz://` resources, take the meaning of each
kind and field from the field descriptions in the `signoz_create_dashboard`
input schema, which describes the same shape the fetched dashboard uses.

From the response, read the dashboard's title, description, and tags; its
variables; each panel's plugin kind, title, and query; and each Grid in
`spec.layouts`, whose title names a section and whose items place panels.

### Step 3: Build the explanation

Write the explanation in this order. Do not rely on headers, bold labels, or
emoji to carry meaning: a host can strip them, so every part must read
correctly as plain sentences.

**1. Bottom line**: open with one or two sentences that say what the
dashboard is for and name the most important problem or gap you found, if
there is one. If you checked the structure and found no problem, say so. If
the user asked only about the panels and you did not check, give the purpose
alone.

**2. Overview**: one paragraph on what the dashboard monitors and which
signals it draws from (metrics, traces, logs). Mention the `tags` if they
provide useful context.

**3. Variables and filters**: explain each variable:
- Its name (the `$handle` queries reference) and what it filters.
- What kind of control it is, by its stored kind and in plain words: a list
  fed by observed attribute values, a list filled by a ClickHouse query, a
  fixed list of configured choices, or a free-text input. For a list, say
  where the choices come from.
- For a list, whether it allows several values at once and whether it offers
  an ALL option. A free-text variable has neither.
- Which panels it affects. Search every query for the `$handle`, including
  each member of a composite and the text of PromQL and ClickHouse SQL
  queries, before saying a variable has no effect on a panel. Name the
  panels that do not reference it: changing the variable does not change
  them, which can confuse a reader.

**4. Panel-by-panel walkthrough**. Group panels by Grid section: walk
`spec.layouts` in order, introduce each section by its Grid title in a
sentence, and follow its items (by `y` then `x`) to the panels they place.
For a single untitled Grid, walk panels in position order and organize by
logical theme. For each panel:
- **Title** and **panel type** in plain words, taken from the plugin `kind`
  and its section in `signoz://dashboard/widgets-instructions`. For a stacked
  area chart, say whether the stack shows the total (`normal`) or each
  series' share (`percent`).
- **What it shows**: interpret the panel's query in plain language. For
  `signoz/BuilderQuery`, explain the signal, aggregation, `filter.expression`,
  and `groupBy`. For a `signoz/CompositeQuery`, explain each member and how the
  formula or trace operator combines them. For ClickHouse SQL or PromQL,
  translate the query intent into plain English. A traces `count()` or
  `rate()` counts spans: call it a request count only when the filter
  includes `isEntryPoint = true OR isRoot = true`, and do not call it a count
  of traces.
- **What to watch for**: describe what healthy looks like and what patterns
  indicate trouble. Be specific: "sustained usage above 80% means..." not just
  "watch if it's high". Anchor advice to the actual metric being queried, not
  generic domain knowledge.
- **Unit**: give the unit of each displayed value. A panel's `formatting.unit`
  covers the panel; a table can also set a unit per column in
  `formatting.columnUnits`.

For panels with complex queries:
- **Formulas** (inside a composite): explain each member (A, B, ...) separately,
  then explain what the formula computes and why
- **Functions** (rate, derivative, clampMin/Max, timeShift): explain the transform
  in plain terms (e.g., "rate converts the raw counter into a per-second value")

**5. Dashboard health observations**. After the walkthrough, note any structural
issues you spotted:
- A query panel that shows nothing because every member of its composite is
  disabled. Disabled base queries under an enabled formula are the normal
  way to show only the computed series, and a `signoz/TextPanel` has no
  query by design; neither is a problem.
- Panels in `spec.panels` that no grid item references. SigNoz accepts them
  and does not show them, so report them as hidden, not as invalid.
- Variables defined but not referenced by any panel query
- Panels missing thresholds where they would be useful (e.g., a utilization
  panel with no saturation threshold). Describe a threshold the way that
  panel kind shows it, per `signoz://dashboard/widgets-instructions`: a time
  series colors the threshold label or tints the panel background and draws
  no line.
- Counters displayed without a rate function (raw counters produce ever-increasing
  ramps, not operational rates)
- Very wide step intervals that could hide spikes
- Panels with high-cardinality groupBy that may produce unreadable charts

**6. Coverage gaps**. Based on what the dashboard actually monitors, note
significant observability areas that are absent. Only mention gaps that are
directly related to the technology or domain the dashboard covers; do not
speculate about unrelated areas. Frame as suggestions: "You may want to consider
adding panels for X to cover Y."

### Step 4: Offer next steps

Surface up to 3 follow-up intents based on what the explanation
surfaced, such as running a specific panel's underlying query,
filling a coverage gap, or wiring an alert for an actionable threshold
the user has not yet alerted on. Use your judgment; do not pad to 3.

Skip follow-ups when the user was clearly just onboarding to the
dashboard ("what is this?") and showed no further intent. Offering no
follow-ups is better than offering wrong ones.

## Guardrails

- **Fetch before explaining**: Always call `signoz_get_dashboard` to get the full
  configuration. Never explain based on the dashboard title or listing alone.
- **Interpret, don't dump**: Translate queries into plain operational language. Never
  show raw query JSON to the user unless they specifically ask.
- **Anchor to actual content**: Base "what to watch for" advice on the actual metrics
  and queries in the dashboard, not on generic domain knowledge unrelated to the
  panels present.
- **Bottom line first**: Open with what the dashboard is for and the most
  important problem or gap, before the walkthrough.
- **Group by sections**: Use each Grid's title to group panels, not layout
  coordinates. Those titles are the sections the dashboard author intended.
- **No data queries by default**: Do not run live queries unless the user asks. The
  explain skill is about understanding the dashboard structure, not inspecting
  current data.
- **Cover the whole dashboard listing**: When searching for a dashboard by
  name, follow the Step 1 paging rule to the end before concluding a
  dashboard does not exist.
- **All query types**: Handle builder, ClickHouse SQL, and PromQL queries; each
  requires a different interpretation approach. For builder queries, read the
  aggregations, filter expression, and groupBy. For raw SQL/PromQL, parse the
  query string and explain the intent.
- **Scope boundary**: This skill explains dashboards. If the user wants to change
  something after your explanation, redirect to `signoz-modifying-dashboards`.

## Examples

**User:** "Explain my PostgreSQL dashboard"

**Agent:**
1. Calls `signoz_list_dashboards` and covers the whole listing: finds
   "PostgreSQL Overview" dashboard with id `abc-123`.
2. Calls `signoz_get_dashboard` with id `abc-123`, then reads
   `signoz://dashboard/widgets-instructions` and
   `signoz://dashboard/instructions`.
3. Explains the dashboard in order, as plain sentences:
   - Bottom line: "This dashboard tracks PostgreSQL health for one host and
     database. Its main gap is that nothing covers vacuum or lock contention."
   - Overview: "It monitors connections, query performance, buffer cache
     efficiency, and replication, using metrics from the OpenTelemetry
     PostgreSQL receiver."
   - Variables: "Two list variables fed by observed attribute values:
     `host_name` filters by `host.name` and `database` filters by
     `postgresql.database.name`. Both allow several values at once."
   - Panels: walks each Grid section, introducing it by its title and
     explaining every panel's metric, aggregation, and what to watch for.
   - Health observations: "The 'Connection Count' panel has no threshold;
     consider one at 80% of max_connections. SigNoz colors the label or
     tints the panel when the value crosses it."
   - Coverage gaps: "No panels cover vacuum/autovacuum health or lock
     contention. Consider adding these if you manage write-heavy workloads."
4. Offers: "Want me to run any panel queries to check for data, or add the
   suggested panels?"

---

**User:** "What does each panel on this dashboard show?" (with dashboard context
provided via @mention or auto-context)

**Agent:**
1. Extracts the dashboard id from the provided context.
2. Calls `signoz_get_dashboard`: gets full configuration.
3. Opens with the bottom line, then gives a focused panel-by-panel walkthrough
   grouped by Grid section, explaining what each panel shows and what to
   watch for.
4. Skips the health and gaps parts unless something notable stands out, since
   the user asked specifically about panels.

---

**User:** "Help me understand this LLM monitoring dashboard. I'm new to it"

**Agent:**
1. Identifies the dashboard, fetches full config.
2. Opens with the bottom line, then gives a beginner-friendly explanation
   with more context per panel:
   - Explains what the metrics mean (e.g., "Token usage measures how many
     tokens your LLM calls consume, which directly impacts cost")
   - Explains what the variables control and recommends starting with the "ALL"
     option to see the full picture before filtering
   - Highlights the most important panels to watch daily vs. those useful only
     during debugging
3. Offers to set up alerts on critical panels.
