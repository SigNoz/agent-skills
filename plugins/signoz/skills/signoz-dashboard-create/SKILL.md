---
name: dashboard-create
description: >
  Trigger when the user wants to create a new dashboard, set up monitoring
  for a service or infrastructure component, or import a pre-built dashboard
  template. Includes requests like "create a dashboard for PostgreSQL",
  "monitor my Redis cluster", "set up observability for my k8s cluster",
  "I need a dashboard for tracking LLM costs".
---

# Dashboard Create

## When to use

Use this skill when the user asks to:
- Create, set up, or build a new dashboard
- Monitor a specific technology (database, service, infrastructure, AI/LLM platform)
- "Set up observability" for a service or component
- Import a dashboard template

Do NOT use when:
- User wants to modify an existing dashboard → `dashboard-modify`
- User wants to understand what a dashboard shows → `dashboard-explain`
- User wants to query data without creating a dashboard → `query-generate`

## Instructions

### Step 1: Check for duplicates

Call `signoz_list_dashboards` to see what dashboards already exist. **Paginate
through all pages** — check `pagination.hasMore` in the response. If `hasMore`
is true, call again with `offset` set to `pagination.nextOffset` and repeat until
all pages are exhausted. Only after checking every page can you conclude no
similar dashboard exists.

**Match aggressively.** For each existing dashboard, compare its lowercased
`name` and `tags` against the user's request (and against the template title
you are about to import, if Step 2 has matched one). A match is any of:
- lowercased name contains the technology/domain keyword (e.g. "redis",
  "postgres", "k8s"/"kubernetes", "docker"/"container");
- any tag matches the keyword;
- existing name and the template title share the root token (e.g.
  "Redis - Overview" vs "Redis overview").

**If any potential match exists**, list the concrete matches back to the user —
name, UUID, and created-at — and ask explicitly: "I found these dashboards
that look similar: [list]. Do you want to (a) modify an existing one, (b)
create a new one anyway, or (c) skip?" Do not create until the user picks.
If they pick (a), call `signoz_get_dashboard` with the chosen UUID to fetch
its full configuration, then use `signoz_update_dashboard` to apply the
changes.

### Step 2: Search the template catalog

Run the search tool via Bash from the skill's base directory (shown in the
initial skill-load message):

```bash
python3 "<skill-base>/tools/search_templates.py" "<query>" --limit 5
```

The query should be the user's request boiled down to the technology or
domain words (e.g., "postgresql", "redis", "kubernetes nodes"). The tool
emits a JSON array of `{id, title, path, description, category, score}`
entries. If the array is empty, no template matches — **go to Step 3**.

**Narrowing by category (optional).** When the user's request is broad
(e.g. "give me an APM dashboard", "something for Kubernetes") and the
keyword search returns too many or too few hits, you can list the
categories first and search inside one:

```bash
python3 "<skill-base>/tools/search_templates.py" --list-categories
python3 "<skill-base>/tools/search_templates.py" "" --category "Apm" --limit 10
```

A category-only call (empty query) returns every template in that
category, ordered by title.

**If a template matches:**

1. Confirm with the user. If the search result has a non-empty `description`,
   use: "I found a pre-built [title] dashboard template — [description].
   Should I import it?" If `description` is empty (common — most entries
   have none), fall back to: "I found a pre-built [title] dashboard template
   (category: [category], file: [path]). Should I import it?"
2. On confirmation, fetch the template JSON:

   ```bash
   python3 "<skill-base>/tools/fetch_template.py" "<path>"
   ```

   where `<path>` is the `path` field from the search result. **Always quote
   the path** — some entries contain spaces (e.g., `temporal.io/Temporal Cloud Metrics.json`).
   The tool writes raw JSON to stdout. It handles HTTP/network errors — if it
   exits non-zero, tell the user and offer Step 3 (custom build) instead.
3. **Validate and normalize the fetched JSON before creating.** The
   `signoz_create_dashboard` tool's input schema enumerates every required
   widget and `queryData` field — use it as the source of truth and add any
   that the template JSON is missing. If the schema is unclear or you need
   richer guidance (panel-type-specific examples, layout rules), also read
   the MCP resources `signoz://dashboard/widgets-instructions` and
   `signoz://dashboard/widgets-examples`.
4. **Pre-flight no-data check.** Before calling `signoz_create_dashboard`,
   probe whether the template's signals are actually being ingested:
   - Walk the fetched JSON and collect what each widget queries:
     - **Metrics** — `query.builder.queryData[].aggregateAttribute.key`
       on widgets where `dataSource = "metrics"`.
     - **Traces** — widgets where `dataSource = "traces"`; collect any
       `service.name` filter values plus the aggregated attribute.
     - **Logs** — widgets where `dataSource = "logs"`; collect filter
       attribute keys.
     - **Raw ClickHouse / PromQL** — extract the metric names referenced
       in the SQL/PromQL string.
   - Probe up to ~5 representative signals using these MCP tools (one
     per metric/attribute — keep the total small):
     - Metrics: `signoz_list_metrics` with `searchText=<metric_name>`
       and `timeRange=1h`. Empty result → metric is not being ingested.
     - Traces: `signoz_aggregate_traces` with `aggregation=count`,
       `service=<svc>` (or `filter=<attr> EXISTS`), `timeRange=1h`.
       A zero count → no traces.
     - Logs: `signoz_aggregate_logs` with `aggregation=count`,
       `filter=<attr> EXISTS`, `timeRange=1h`. A zero count → no logs.
     - Resource attribute values referenced by template variables:
       `signoz_get_field_values` with the matching `signal` and `name`.
   - If **none** of the probed signals return data, warn the user
     verbatim: "I couldn't find data for [list] in the last hour — this
     template is for [technology] and it doesn't look like that data is
     being ingested yet. I can still create the dashboard (it will just
     show 'No data' until you ingest), or I can stop here. Which would
     you like?" Wait for the user's choice.
   - If **some** signals are present and others aren't, list which are
     missing and proceed only on confirmation.
   - If everything is present, proceed silently.
5. Pass `title`, `description`, `tags`, `layout`, `widgets`, and `variables`
   to `signoz_create_dashboard`.
6. Report what was created: title, panel count, sections.
7. Offer customization. If the user requests changes, call
   `signoz_get_dashboard`, then `signoz_update_dashboard` with the modified
   full JSON.

### Step 3: Custom build path

When no template fits the user's request, build a dashboard from scratch.

1. **Gather requirements** — ask the user:
   - What signals to monitor (metrics, traces, logs, or a combination)
   - What specific metrics or data points matter most
   - Which services or components to include
   - What filters/variables they need (environment, service name, instance)
2. **Read the dashboard MCP resources** for JSON structure, panel types,
   query builder format, and layout rules:
   - `signoz://dashboard/instructions` — title, tags, description, variables.
   - `signoz://dashboard/widgets-instructions` — 7 panel types and layout rules.
   - `signoz://dashboard/widgets-examples` — complete widget configurations.
   - `signoz://dashboard/query-builder-example` — query builder reference.
   Add metric/trace/log-specific resources (`signoz://dashboard/clickhouse-*`,
   `signoz://dashboard/promql-example`, `signoz://traces/query-builder-guide`)
   as needed for the signal types involved.
3. **Build the dashboard JSON** following the v5 schema as documented in the
   MCP resources loaded in the previous step. Use OTel semantic attribute
   names (not shorthand) in filters, groupBy, and variables.
4. **Pre-flight no-data check.** Before calling `signoz_create_dashboard`,
   probe a representative subset of the metrics / attributes you used,
   using the same MCP tools listed in Step 2.4 (`signoz_list_metrics` for
   metrics, `signoz_aggregate_traces` / `signoz_aggregate_logs` for
   trace/log presence, `signoz_get_field_values` for variable values).
   If none return data in the last hour, warn the user (same wording as
   Step 2.4) and wait for confirmation before creating.
5. Call `signoz_create_dashboard` with the built JSON.
6. Report what was created and offer to adjust anything. If the user requests
   changes, call `signoz_get_dashboard` to fetch the current state, then use
   `signoz_update_dashboard` with the modified full dashboard JSON.

## Guardrails

- **Template-first**: Always check the template catalog before proposing a custom
  build. Never build from scratch when a matching template exists.
- **No blind creation**: Always confirm with the user before creating. For
  templates: one confirmation. For custom: confirm the plan after gathering
  requirements.
- **No duplicate dashboards**: Always call `signoz_list_dashboards` first and
  paginate through all pages before concluding no similar dashboard exists.
- **Valid JSON only**: When building custom dashboards, follow the v5 schema
  as documented in the `signoz://dashboard/*` MCP resources. Required widget
  and `queryData` fields are listed in `signoz://dashboard/widgets-instructions`
  and `signoz://dashboard/widgets-examples` — include all of them. Never
  generate malformed queries or layouts.
- **OTel attribute names**: Always use OpenTelemetry semantic conventions for
  attribute names in filters, groupBy, and variables. Use `service.name` not
  `service`, `host.name` not `host`, `deployment.environment.name` not `env`.
- **No metric guessing**: For custom builds, if you are not sure what metrics are
  available, ask the user. Wrong metric names produce empty panels.
- **No-data warning before create**: Always run the pre-flight probe (Step
  2.4 / Step 3.4) before `signoz_create_dashboard`. A "No data" dashboard
  is a worse user outcome than one extra confirmation prompt. Skip the
  probe only if the user has explicitly opted out for this request.
- **GitHub fetch failures**: If fetching a template JSON from GitHub fails, tell
  the user and offer to build a custom version instead.
- **Full state on update**: `signoz_update_dashboard` requires the complete
  dashboard JSON (not a partial patch). Always call `signoz_get_dashboard` first
  to get the current state, merge your changes into that full object, and pass
  the result to `signoz_update_dashboard`.
- **Scope boundary**: This skill creates dashboards. Post-creation modifications
  beyond the initial customization offer belong to `dashboard-modify`.

## Examples

**User:** "Create a dashboard for my PostgreSQL database"

**Agent:**
1. Calls `signoz_list_dashboards` — no existing PostgreSQL dashboard.
2. Runs `python3 "<skill-base>/tools/search_templates.py" "postgresql"` —
   top result is `postgresql/postgresql.json`.
3. Confirms: "I found a pre-built PostgreSQL dashboard template — this
   dashboard provides a high-level overview of your PostgreSQL databases.
   Should I import it?"
4. User confirms.
5. Runs `python3 "<skill-base>/tools/fetch_template.py" "postgresql/postgresql.json"`.
6. Reads `signoz://dashboard/widgets-instructions` and
   `signoz://dashboard/widgets-examples`, normalizes any missing required
   widget fields, then calls `signoz_create_dashboard`.
7. Reports: "Created 'Postgres overview' dashboard with N panels across M
   sections. Want me to adjust any panels, add variables, or change the
   layout?"

---

**User:** "Create a dashboard to track our payment processing pipeline"

**Agent:**
1. Calls `signoz_list_dashboards` — no existing payment dashboard.
2. Runs `python3 "<skill-base>/tools/search_templates.py" "payment processing"` —
   empty array, no match.
3. Says: "I don't have a pre-built template for payment processing. Let me help
   you build a custom one. What signals are you monitoring — traces, metrics,
   logs, or a combination?"
4. Gathers requirements: transaction count, latency, error rate, services
   involved, filter needs.
5. Reads `signoz://dashboard/instructions`, `widgets-instructions`, and
   `widgets-examples` for JSON structure.
6. Builds dashboard with sections: Overview, Latency, Errors, Infrastructure.
7. Calls `signoz_create_dashboard`.
8. Reports what was created, offers customization.

---

**User:** "Set up monitoring for Redis"

**Agent:**
1. Calls `signoz_list_dashboards` — finds existing "Redis Overview" dashboard.
2. Says: "There's already a 'Redis Overview' dashboard. Would you like me to
   create another one from the template, or modify the existing one?"
3. If user chooses to modify: calls `signoz_get_dashboard` with the existing
   dashboard's UUID to fetch the full configuration, plans the changes, then
   calls `signoz_update_dashboard` with the updated JSON.
