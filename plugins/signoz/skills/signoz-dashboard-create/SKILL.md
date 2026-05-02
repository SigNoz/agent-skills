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
`signoz_list_dashboards`, `signoz_list_dashboard_templates`,
`signoz_import_dashboard`, `signoz_list_metrics`,
`signoz_get_field_values`, `signoz_aggregate_logs`,
`signoz_aggregate_traces`, etc.). Before running the workflow, confirm
the `signoz_*` tools are available. If they are not, the SigNoz MCP
server is not installed or configured — stop and direct the user to set
it up: <https://signoz.io/docs/ai/signoz-mcp-server/>. Do not fall back
to raw HTTP calls or fabricate dashboard JSON without the MCP tools.

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

The flow runs in order: **duplicate check → user picks modify-or-create →
on create, template lookup decides template-import vs custom-build**.
Duplicate check comes first so we never silently create a second copy of
something that already exists. Once the user has chosen to create a new
dashboard, the template lookup is an internal implementation detail — if
a curated template exists we use it, otherwise we build from scratch.
The user is offered exactly two choices: modify an existing dashboard, or
create a new one.

### Step 1: Check for duplicates

Call `signoz_list_dashboards` to see what dashboards already exist.
**Paginate through all pages** — check `pagination.hasMore` in the
response. If `hasMore` is true, call again with `offset` set to
`pagination.nextOffset` and repeat until all pages are exhausted. Only
after checking every page can you conclude no similar dashboard exists.

**Match aggressively.** For each existing dashboard, compare its lowercased
`name` and `tags` against the user's request. A match is any of:
- lowercased name contains the technology/domain keyword (e.g. "redis",
  "postgres", "k8s"/"kubernetes", "docker"/"container", "host");
- any tag matches the keyword;
- existing name and the user's request share the root token (e.g.
  "Redis - Overview" vs a request for a Redis dashboard).

### Step 2: Ask the user — modify or create

Present exactly two options:

- **Duplicates found:** "There are already these similar dashboards:
  [list with name, UUID, created-at]. Want me to (a) modify one of these,
  (b) create a new dashboard anyway, or (c) stop?"
- **No duplicates:** "I'll create a new dashboard for this. Proceed?"
  (No "modify" option when there's nothing to modify.)

Wait for the user's choice. If they pick "modify", go to Step 3a. If they
pick "create new" (or confirm creation), go to Step 3b. If they pick
"stop", stop.

### Step 3: Create or modify

#### Step 3a: Modify an existing dashboard

Call `signoz_get_dashboard` with the chosen UUID to fetch the full
configuration, plan the requested changes, then call
`signoz_update_dashboard` with the complete updated JSON. Stop here.

#### Step 3b: Create a new dashboard

Run the template lookup first. The user has already agreed to create a
new dashboard — the lookup just decides *how* we build it, no extra
confirmation prompt.

Call `signoz_list_dashboard_templates` with `searchContext` set to the
user's raw request. The tool returns the full catalog as a JSON array of
`{id, title, path, description, category, keywords}` entries. Read the
list and pick the entry whose `title`/`description`/`keywords`/`category`
best matches the user's intent — this is a model judgment, not a keyword
score.

**Narrowing by category (optional).** When the user's request is broad
(e.g. "give me an APM dashboard", "something for Kubernetes"), pass
`category` to restrict the catalog (case-insensitive), e.g.
`category="Apm"` or `category="K8S Infra Metrics"`. Present the narrowed
list to the user and ask them to pick before importing.

Branch on the result:
- **Template found** (a catalog entry is clearly relevant) — proceed to
  Step 3b-i (template import). Briefly tell the user "I found a pre-built
  [title] template and will use it" so they know what's being created;
  do not block on a yes/no.
- **No template** (nothing in the catalog matches) — proceed to Step
  3b-ii (custom build).

#### Step 3b-i: Import the template

> **Tool guardrail.** The only template tools are
> `signoz_list_dashboard_templates` and `signoz_import_dashboard`. Do not
> shell out, fetch raw GitHub URLs, or invent other tool names.
> `signoz_import_dashboard` takes the template `path` from the catalog
> entry and creates the dashboard in one call — you do not need to fetch
> the JSON yourself or call `signoz_create_dashboard` afterwards.

1. **Pre-flight no-data check.** Before calling `signoz_import_dashboard`,
   probe whether the template's signals are actually being ingested.
   Since we don't fetch the template body up front, base the probe on
   the catalog entry's `category`, `title`, and `keywords` plus the
   user's stated technology. Pick up to ~5 representative signals and
   check them — keep the total small:
   - **Metric-based templates** (most infra/runtime templates — e.g.
     PostgreSQL, Redis, JVM, hostmetrics, k8s): call `signoz_list_metrics`
     with `searchText=<technology prefix>` (e.g. `postgresql`, `redis`,
     `jvm`, `system.`, `k8s.`) and `timeRange=1h`. Empty result → metric
     family is not being ingested.
   - **Trace-based templates** (APM-style): call `signoz_aggregate_traces`
     with `aggregation=count`, an appropriate filter (e.g. `service.name
     EXISTS`), `timeRange=1h`. A zero count → no traces.
   - **Log-based templates**: call `signoz_aggregate_logs` with
     `aggregation=count`, a relevant filter, `timeRange=1h`. A zero
     count → no logs.
   - **Variable values** (when the template clearly relies on a resource
     attribute, e.g. `service.name`, `k8s.cluster.name`): call
     `signoz_get_field_values` to confirm there are values to pick from.
   - If **none** of the probed signals return data, warn the user
     verbatim: "I couldn't find data for [list] in the last hour — this
     template is for [technology] and it doesn't look like that data is
     being ingested yet. I can still create the dashboard (it will just
     show 'No data' until you ingest), or I can stop here. Which would
     you like?" Wait for the user's choice.
   - If **some** signals are present and others aren't, list which are
     missing and proceed only on confirmation.
   - If everything is present, proceed silently.
2. **Create the dashboard.** Call `signoz_import_dashboard` with the
   `path` from the chosen catalog entry (e.g.
   `postgresql/postgresql.json`). The server fetches the JSON, validates
   it, and creates the dashboard in one call.
3. **Report and offer customization.** Tell the user what was created
   (title, panel count, sections — read these from the response). If the
   user requests changes, call `signoz_get_dashboard` to fetch the
   current state, then `signoz_update_dashboard` with the modified full
   JSON.

#### Step 3b-ii: Custom build (no template, or import failed)

Run this path when the Step 3b template lookup found no match, or when
`signoz_import_dashboard` failed. Build a dashboard from scratch.

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
   using the same MCP tools listed in Step 3b-i.1 (`signoz_list_metrics`
   for metrics, `signoz_aggregate_traces` / `signoz_aggregate_logs` for
   trace/log presence, `signoz_get_field_values` for variable values).
   If none return data in the last hour, warn the user (same wording as
   Step 3b-i.1) and wait for confirmation before creating.
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

- **Duplicate check first**: Always call `signoz_list_dashboards` (paginated)
  before anything else. The user's only two upfront options are "modify an
  existing one" or "create a new one" — never offer template-import as a
  separate top-level choice.
- **Template-first on the create path**: Once the user has chosen to create
  a new dashboard, always run `signoz_list_dashboard_templates` before any
  `signoz_create_dashboard` call. If a matching template exists, import it
  via `signoz_import_dashboard` (just inform the user); only build from
  scratch when no template matches.
- **No blind creation**: For custom builds, confirm the plan with the user
  after gathering requirements before calling `signoz_create_dashboard`.
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
  (Step 3b-i.1 / Step 3b-ii.4) before `signoz_import_dashboard` /
  `signoz_create_dashboard`. A "No data" dashboard is a worse user
  outcome than one extra confirmation prompt. Skip the probe only if the
  user has explicitly opted out for this request.
- **Full state on update**: `signoz_update_dashboard` requires the complete
  dashboard JSON (not a partial patch). Always call `signoz_get_dashboard` first
  to get the current state, merge your changes into that full object, and pass
  the result to `signoz_update_dashboard`.
- **Scope boundary**: This skill creates dashboards. Post-creation modifications
  beyond the initial customization offer belong to `signoz-dashboard-modify`.

## Examples

**User:** "Create a dashboard for my PostgreSQL database"

**Agent:**
1. Calls `signoz_list_dashboards` (paginated) — no existing PostgreSQL
   dashboard.
2. Says: "I'll create a new dashboard for PostgreSQL. Proceed?"
3. User confirms.
4. Calls `signoz_list_dashboard_templates` with the user's request as
   `searchContext` — picks the `postgresql/postgresql.json` entry. Tells
   the user: "I found a pre-built PostgreSQL template and will use it."
5. Runs the no-data probe (`signoz_list_metrics searchText=postgresql`),
   then calls `signoz_import_dashboard` with `path=postgresql/postgresql.json`.
6. Reports: "Created 'Postgres overview' dashboard with N panels across M
   sections. Want me to adjust any panels, add variables, or change the
   layout?"

---

**User:** "Create a dashboard to track our payment processing pipeline"

**Agent:**
1. Calls `signoz_list_dashboards` (paginated) — no existing payment
   dashboard.
2. Says: "I'll create a new dashboard for the payment processing
   pipeline. Proceed?"
3. User confirms.
4. Calls `signoz_list_dashboard_templates` — nothing in the catalog
   matches "payment processing". Falls through to custom build.
5. Gathers requirements: transaction count, latency, error rate, services
   involved, filter needs.
6. Reads `signoz://dashboard/instructions`, `widgets-instructions`, and
   `widgets-examples` for JSON structure.
7. Builds dashboard with sections: Overview, Latency, Errors,
   Infrastructure. Runs the no-data probe.
8. Calls `signoz_create_dashboard`.
9. Reports what was created, offers customization.

---

**User:** "Set up monitoring for Redis"

**Agent:**
1. Calls `signoz_list_dashboards` (paginated) — finds existing "Redis
   Overview" dashboard.
2. Says: "There's already a 'Redis Overview' dashboard. Want me to (a)
   modify it, (b) create a new dashboard anyway, or (c) stop?"
3. If user picks (a) — Step 3a: calls `signoz_get_dashboard`, plans
   changes, calls `signoz_update_dashboard` with the full updated JSON.
4. If user picks (b) — Step 3b: calls `signoz_list_dashboard_templates`,
   picks `redis/redis.json`, imports it via `signoz_import_dashboard`
   (Step 3b-i).
