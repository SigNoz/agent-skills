---
name: signoz-dashboard-create
description: >
  Trigger when the user wants to create a new dashboard, set up monitoring
  for a service or infrastructure component, or import a pre-built dashboard
  template. Includes requests like "create a dashboard for PostgreSQL",
  "monitor my Redis cluster", "set up observability for my k8s cluster",
  "I need a dashboard for tracking LLM costs".
---

# Dashboard Create

## Prerequisites

This skill calls SigNoz MCP server tools (`signoz_create_dashboard`,
`signoz_list_dashboards`, `signoz_list_metrics`, `signoz_get_field_values`,
`signoz_aggregate_logs`, `signoz_aggregate_traces`, etc.). Before running
the workflow, confirm the `signoz_*` tools are available. If they are not,
the SigNoz MCP server is not installed or configured — stop and direct the
user to set it up: <https://signoz.io/docs/ai/signoz-mcp-server/>. Do not
fall back to raw HTTP calls or fabricate dashboard JSON without the MCP
tools.

## When to use

Use this skill when the user asks to:
- Create, set up, or build a new dashboard
- Monitor a specific technology (database, service, infrastructure, AI/LLM platform)
- "Set up observability" for a service or component
- Import a dashboard template

Do NOT use when:
- User wants to modify an existing dashboard → `signoz-dashboard-modify`
- User wants to understand what a dashboard shows → `signoz-dashboard-explain`
- User wants to query data without creating a dashboard → `signoz-query-generate`

## Instructions

The three steps below run in order: **template search → duplicate check →
build**. The template search comes first deliberately. If we checked
duplicates first, then asked "create anyway?", a user who says yes is
easily misread as "skip templates and build custom" — and a custom build
when a curated template exists is a worse outcome than one extra prompt.
Searching templates up front means by the time we ask the user anything,
we already know whether we're proposing a template import or a custom
build, and the duplicate check can compare against the *actual title we'd
create* (template title or custom title), not just the user's raw words.

### Step 1: Search the template catalog

Run the search tool via Bash from the skill's base directory (shown in the
initial skill-load message):

```bash
python3 "<skill-base>/tools/search_templates.py" "<query>" --limit 5
```

The query should be the user's request boiled down to the technology or
domain words (e.g., "postgresql", "redis", "kubernetes nodes", "host
metrics"). The tool emits a JSON array of `{id, title, path, description,
category, score}` entries.

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

You leave Step 1 with one of two outcomes — carry it into Step 2:
- **Template candidate found** — note the top match's `title`, `path`,
  `category`, and `description`.
- **No template** — the JSON array is empty, or the top result is clearly
  unrelated to the user's request. Mark this request as a custom build.

Do **not** confirm template import with the user yet — first do the
duplicate check in Step 2, so a single confirmation can cover both
"there's already a similar dashboard" and "I'm about to import this
template / build a custom one".

### Step 2: Check for duplicates

Call `signoz_list_dashboards` to see what dashboards already exist.
**Paginate through all pages** — check `pagination.hasMore` in the
response. If `hasMore` is true, call again with `offset` set to
`pagination.nextOffset` and repeat until all pages are exhausted. Only
after checking every page can you conclude no similar dashboard exists.

**Match aggressively.** For each existing dashboard, compare its lowercased
`name` and `tags` against both the user's request **and** the Step 1
outcome (the template title if a template was found, otherwise the
keywords you'd use for a custom build). A match is any of:
- lowercased name contains the technology/domain keyword (e.g. "redis",
  "postgres", "k8s"/"kubernetes", "docker"/"container", "host");
- any tag matches the keyword;
- existing name and the candidate title share the root token (e.g.
  "Redis - Overview" vs "Redis overview").

**Decide what to ask the user based on Step 1 + Step 2 results:**

| Step 1 result    | Step 2 result   | What to ask                                                                                                                                                  |
| ---------------- | --------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Template found   | No duplicates   | "I found a pre-built [title] dashboard template — [description]. Should I import it?" (use file/category fallback if description is empty)                   |
| Template found   | Duplicates      | "There are already these similar dashboards: [list with name, UUID, created-at]. I also found a pre-built [title] template. Want me to (a) modify an existing one, (b) import the template as a new dashboard, or (c) stop?" |
| No template      | No duplicates   | "I don't have a pre-built template for this. I can build a custom one — want me to proceed and gather requirements?"                                         |
| No template      | Duplicates      | "There are already these similar dashboards: [list]. I don't have a pre-built template, so a new one would be custom-built. Want me to (a) modify an existing one, (b) build a new custom one, or (c) stop?" |

Wait for the user's choice before proceeding. If they pick "modify",
go to Step 3a. If they pick "import the template" or "build custom",
go to the matching path in Step 3. If they pick "stop", stop.

### Step 3: Create or modify

#### Step 3a: Modify an existing dashboard

Call `signoz_get_dashboard` with the chosen UUID to fetch the full
configuration, plan the requested changes, then call
`signoz_update_dashboard` with the complete updated JSON. Stop here.

#### Step 3b: Import a template (only if Step 1 found one)

Run this path when the user has confirmed in Step 2 that they want to
import the template found in Step 1.

> **Tool guardrail.** The only template-search tool is `search_templates.py`.
> Template JSON is fetched via the `WebFetch` tool against the pinned
> upstream commit (URL below) — do not invent other script names (no
> `fetch_template.py`, no `create_from_template.py`, no
> `import_template.py`).

1. Fetch the template JSON via the `WebFetch` tool. Construct the URL as:

   ```
   https://raw.githubusercontent.com/SigNoz/dashboards/61d374c50f9e1383e0eba3584fb81498f38c1f8d/<path>
   ```

   where `<path>` is the `path` field from the Step 1 search result
   (URL-encode spaces as `%20` — e.g.
   `temporal.io/Temporal%20Cloud%20Metrics.json`). Pass a prompt like
   "Return the raw JSON body unchanged" so WebFetch does not summarize
   it. If WebFetch fails or returns a non-JSON body, tell the user and
   offer Step 3c (custom build) instead.
2. **Validate and normalize the fetched JSON before creating.** The
   `signoz_create_dashboard` tool's input schema enumerates every required
   widget and `queryData` field — use it as the source of truth and add any
   that the template JSON is missing. If the schema is unclear or you need
   richer guidance (panel-type-specific examples, layout rules), also read
   the MCP resources `signoz://dashboard/widgets-instructions` and
   `signoz://dashboard/widgets-examples`.
3. **Pre-flight no-data check.** Before calling `signoz_create_dashboard`,
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
5. **Shape check before create.** The `signoz_create_dashboard` tool rejects
   stringified JSON for array/object fields with errors like
   `cannot unmarshal string into ... layout of type []LayoutItem`. Verify
   the values you are about to pass match the input schema's types — do
   **not** wrap them in `JSON.stringify` / `json.dumps`:
   - `tags` → array of strings, e.g. `["host", "infra"]` (not `"[\"host\"]"`).
   - `layout` → array of `{i, x, y, w, h}` objects (not a JSON string).
   - `widgets` → array of widget objects (not a JSON string).
   - `variables` → object/map keyed by variable name (not a JSON string).
   - `title`, `description` → plain strings.
6. Pass `title`, `description`, `tags`, `layout`, `widgets`, and `variables`
   to `signoz_create_dashboard`.
7. Report what was created: title, panel count, sections.
8. Offer customization. If the user requests changes, call
   `signoz_get_dashboard`, then `signoz_update_dashboard` with the modified
   full JSON.

#### Step 3c: Custom build (no template, or template fetch failed)

Run this path when Step 1 found no template, or when the user opted for
a custom build, or when the `WebFetch` of the template JSON failed.
Build a dashboard from scratch.

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
   using the same MCP tools listed in Step 3b.3 (`signoz_list_metrics`
   for metrics, `signoz_aggregate_traces` / `signoz_aggregate_logs` for
   trace/log presence, `signoz_get_field_values` for variable values).
   If none return data in the last hour, warn the user (same wording as
   Step 2.4) and wait for confirmation before creating.
5. **Shape check before create.** The `signoz_create_dashboard` tool rejects
   stringified JSON for array/object fields with errors like
   `cannot unmarshal string into ... layout of type []LayoutItem` /
   `... tags of type []string`. Verify the values you are about to pass
   match the input schema's types — do **not** wrap them in
   `JSON.stringify` / `json.dumps`:
   - `tags` → array of strings.
   - `layout` → array of `{i, x, y, w, h}` objects.
   - `widgets` → array of widget objects.
   - `variables` → object/map keyed by variable name.
   - `title`, `description` → plain strings.
6. Call `signoz_create_dashboard` with the built JSON.
7. Report what was created and offer to adjust anything. If the user requests
   changes, call `signoz_get_dashboard` to fetch the current state, then use
   `signoz_update_dashboard` with the modified full dashboard JSON.

## Guardrails

- **Template-first**: Always check the template catalog before proposing a custom
  build. Never build from scratch when a matching template exists. If the user
  picks "(b) create anyway" in Step 1's duplicate-check branch, that is **not**
  permission to skip Step 2 — you must still run `search_templates.py` before
  any `signoz_create_dashboard` call. "Create anyway" overrides the duplicate
  warning, not the template-first rule.
- **No stringified JSON in tool args**: `signoz_create_dashboard` and
  `signoz_update_dashboard` reject array/object fields passed as JSON strings.
  `tags`, `layout`, `widgets` must be real arrays; `variables` must be a real
  object. Never `JSON.stringify` / `json.dumps` these before passing them.
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
- **No-data warning before create**: Always run the pre-flight probe
  (Step 3b.3 / Step 3c.4) before `signoz_create_dashboard`. A "No data"
  dashboard is a worse user outcome than one extra confirmation prompt.
  Skip the probe only if the user has explicitly opted out for this
  request.
- **GitHub fetch failures**: If `WebFetch` of a template JSON from GitHub fails
  (network error, non-200, non-JSON body), tell the user and offer to build a
  custom version instead.
- **Full state on update**: `signoz_update_dashboard` requires the complete
  dashboard JSON (not a partial patch). Always call `signoz_get_dashboard` first
  to get the current state, merge your changes into that full object, and pass
  the result to `signoz_update_dashboard`.
- **Scope boundary**: This skill creates dashboards. Post-creation modifications
  beyond the initial customization offer belong to `signoz-dashboard-modify`.

## Examples

**User:** "Create a dashboard for my PostgreSQL database"

**Agent:**
1. Runs `python3 "<skill-base>/tools/search_templates.py" "postgresql"` —
   top result is `postgresql/postgresql.json`.
2. Calls `signoz_list_dashboards` (paginated) — no existing PostgreSQL
   dashboard.
3. Confirms: "I found a pre-built PostgreSQL dashboard template — this
   dashboard provides a high-level overview of your PostgreSQL databases.
   Should I import it?"
4. User confirms.
5. Fetches the template via `WebFetch` against
   `https://raw.githubusercontent.com/SigNoz/dashboards/61d374c50f9e1383e0eba3584fb81498f38c1f8d/postgresql/postgresql.json`.
6. Reads `signoz://dashboard/widgets-instructions` and
   `signoz://dashboard/widgets-examples`, normalizes any missing required
   widget fields, runs the no-data probe, then calls
   `signoz_create_dashboard`.
7. Reports: "Created 'Postgres overview' dashboard with N panels across M
   sections. Want me to adjust any panels, add variables, or change the
   layout?"

---

**User:** "Create a dashboard to track our payment processing pipeline"

**Agent:**
1. Runs `python3 "<skill-base>/tools/search_templates.py" "payment processing"` —
   empty array, no match. Marks request as custom build.
2. Calls `signoz_list_dashboards` (paginated) — no existing payment
   dashboard.
3. Says: "I don't have a pre-built template for payment processing. I can
   build a custom one — want me to proceed and gather requirements?"
4. User confirms. Gathers requirements: transaction count, latency, error
   rate, services involved, filter needs.
5. Reads `signoz://dashboard/instructions`, `widgets-instructions`, and
   `widgets-examples` for JSON structure.
6. Builds dashboard with sections: Overview, Latency, Errors,
   Infrastructure. Runs the no-data probe.
7. Calls `signoz_create_dashboard`.
8. Reports what was created, offers customization.

---

**User:** "Create a host metrics dashboard"

(This is the failure mode from earlier — many existing host dashboards
plus a curated template. Template-search-first means we propose the
template even though duplicates exist.)

**Agent:**
1. Runs `python3 "<skill-base>/tools/search_templates.py" "host metrics"` —
   top result is `hostmetrics/hostmetrics.json` (title: "OpenTelemetry
   Host Metrics Dashboard").
2. Calls `signoz_list_dashboards` (paginated) — finds 8 dashboards
   matching "host"/"system"/"infrastructure".
3. Says: "There are already these similar dashboards: [list with name,
   UUID, created-at]. I also found a pre-built 'OpenTelemetry Host
   Metrics Dashboard' template. Want me to (a) modify an existing one,
   (b) import the template as a new dashboard, or (c) stop?"
4. User picks (b). Goes to Step 3b — fetches the template, normalizes,
   probes for no-data, creates the dashboard. **Does not** detour into a
   custom-build that re-discovers host metrics from scratch.

---

**User:** "Set up monitoring for Redis"

**Agent:**
1. Runs `python3 "<skill-base>/tools/search_templates.py" "redis"` — top
   result is `redis/redis.json`.
2. Calls `signoz_list_dashboards` (paginated) — finds existing "Redis
   Overview" dashboard.
3. Says: "There's already a 'Redis Overview' dashboard. I also found a
   pre-built Redis template. Want me to (a) modify the existing one, (b)
   import the template as a new dashboard, or (c) stop?"
4. If user picks (a) — Step 3a: calls `signoz_get_dashboard`, plans
   changes, calls `signoz_update_dashboard` with the full updated JSON.
