---
name: signoz-creating-dashboards
description: >
  Create a new SigNoz dashboard from a natural-language intent — import a
  curated template (PostgreSQL, Redis, JVM, k8s, hostmetrics, APM, LLM,
  etc.) when one fits, or build a custom dashboard from scratch with
  metric / trace / log panels. Make sure to use this skill whenever the
  user says "create a dashboard for…", "set up monitoring for…",
  "build me a dashboard…", "I need observability for…", "import a
  dashboard template", or asks to track / visualize a service, database,
  cluster, or AI/LLM platform — even if they don't explicitly say
  "dashboard". Also use it when someone wants to "monitor", "watch", or
  "see metrics for" a technology and the natural answer is a dashboard.
argument-hint: <natural-language dashboard intent>
---

# Dashboard Create

Build a SigNoz dashboard from a user's natural-language intent. The skill
targets two consumers: an autonomous AI SRE agent that runs without a
human in the loop, and a human at a Claude Code / Codex / Cursor prompt.
Both go through the same flow — the human just gets a chance to intervene
at the preview step.

## Prerequisites

This skill calls SigNoz MCP server tools (`signoz:signoz_create_dashboard`,
`signoz:signoz_list_dashboards`, `signoz:signoz_list_dashboard_templates`,
`signoz:signoz_import_dashboard`, `signoz:signoz_get_dashboard`,
`signoz:signoz_update_dashboard`, `signoz:signoz_list_metrics`,
`signoz:signoz_get_field_keys`, `signoz:signoz_get_field_values`,
`signoz:signoz_aggregate_logs`, `signoz:signoz_aggregate_traces`, etc.).
Before running the workflow, confirm the `signoz:signoz_*` tools are
available. If they are not, the SigNoz MCP server is not installed or
configured — stop and direct the user to set it up:
<https://signoz.io/docs/ai/signoz-mcp-server/>. Do not fall back to raw
HTTP calls or fabricate dashboard JSON without the MCP tools.

## When to use

Use this skill when the user wants to:
- Create, set up, or build a new dashboard.
- "Monitor" or "set up observability" for a service, database,
  infrastructure component, or AI/LLM platform.
- Import a curated dashboard template.
- Visualize a set of metrics / traces / logs together on one screen.

Do NOT use when the user wants to:
- Modify an existing dashboard → `signoz-modifying-dashboards`.
- Understand what an existing dashboard shows → `signoz-explaining-dashboards`.
- Run a one-off query without persisting it → `signoz-generating-queries`.

## Required inputs (strict)

Dashboard creation is a write operation. Guessing here clutters the
shared workspace with empty or wrongly-scoped dashboards someone else has
to clean up. The skill enforces a soft input contract — most fields have
sensible defaults, but a few cannot be guessed:

| Input | Required | Source if missing |
|---|---|---|
| Dashboard intent (NL goal) | yes | `$ARGUMENTS` or recent user turn |
| Technology / domain (e.g. PostgreSQL, Redis, "payment pipeline") | yes | parse from intent; otherwise ask |
| Modify-or-create choice when duplicates exist | yes | ask the user (Step 2) |
| Resource scope for custom builds (service / namespace / cluster) | yes for custom builds | discover via `signoz:signoz_get_field_keys` + `signoz:signoz_get_field_values`; fall back to a dashboard variable |
| Specific metrics / signals for custom builds | inferred | derive from technology + MCP `signoz://dashboard/*` resources; surface in preview |
| Default time range, refresh, layout | inferred | apply defaults (see "Defaults" below) |

If a required input is missing and cannot be discovered, emit a
structured `needs_input` block and stop **before** calling any write
tool:

```text
needs_input:
  missing:
    - resource_scope: "no service or cluster specified for the custom build"
  candidates:
    service.name: ["frontend", "checkout", "payments", "inventory"]
    k8s.cluster.name: ["prod-us-east-1", "staging"]
```

In interactive mode, the human picks. In autonomous mode, the caller
fills the gap from upstream context or escalates. Either way, do not
proceed to `signoz:signoz_create_dashboard` /
`signoz:signoz_import_dashboard` with a guessed value.

## Workflow

The flow runs in order: **duplicate check → user picks modify-or-create
→ on create, template lookup decides template-import vs custom-build →
no-data probe → preview → save**. Duplicate check comes first so we
never silently create a second copy of something that already exists.
Once the user has chosen to create, the template lookup is an internal
implementation detail — if a curated template fits we use it, otherwise
we build from scratch. The user is offered exactly two upfront choices:
modify an existing dashboard, or create a new one.

### Step 1: Check for duplicates

Call `signoz:signoz_list_dashboards` and **paginate through every page**
— `pagination.hasMore` is true until you have walked the full list.
Stopping at page 1 misses near-duplicates and produces clutter the user
will later regret.

**Match aggressively.** For each existing dashboard, compare its
lowercased `name`, `description`, and `tags` against the user's request.
A match is any of:
- lowercased name contains the technology / domain keyword (e.g.
  `redis`, `postgres`, `k8s`/`kubernetes`, `docker`/`container`,
  `host`, `jvm`, `llm`/`openai`/`anthropic`);
- any tag matches the keyword;
- existing name and the user's request share the root token (e.g.
  "Redis - Overview" vs a request for a Redis dashboard);
- description mentions the same technology or service the user named.

Collect every match with its `name`, `uuid`, and `createdAt` for the
next step.

### Step 2: Ask the user — modify or create

Present exactly two options (no template-import as a separate top-level
choice — that's an internal decision in Step 3b):

- **Duplicates found:** "There are already these similar dashboards:
  [list with name, UUID, created-at]. Want me to (a) modify one of
  these, (b) create a new dashboard anyway, or (c) stop?"
- **No duplicates:** "I'll create a new dashboard for this. Proceed?"
  (No "modify" option when there's nothing to modify.)

Wait for the user's choice. "modify" → Step 3a. "create new" / confirm
→ Step 3b. "stop" → stop.

### Step 3: Create or modify

#### Step 3a: Modify an existing dashboard

Call `signoz:signoz_get_dashboard` with the chosen UUID to fetch the full
configuration, plan the requested changes, then call
`signoz:signoz_update_dashboard` with the **complete** updated JSON
(not a partial patch — see Guardrails). Stop here; further modification
work belongs to `signoz-modifying-dashboards`.

#### Step 3b: Create a new dashboard

Run the template lookup first. The user has already agreed to create
new — the lookup decides *how* we build it.

Call `signoz:signoz_list_dashboard_templates` with `searchContext` set
to the user's raw request. The tool returns the catalog as a JSON array
of `{id, title, path, description, category, keywords}` entries. Read
the list and pick the entry whose `title` / `description` / `keywords`
/ `category` best matches the user's intent — this is a model judgment,
not a keyword score.

**Narrowing by category.** When the user's request is broad (e.g. "give
me an APM dashboard", "something for Kubernetes", "a database
dashboard"), pass `category` to restrict the catalog (case-insensitive),
e.g. `category="Apm"` or `category="K8S Infra Metrics"`. Present the
narrowed list to the user and ask them to pick before importing — when
multiple templates fit, the user is the right judge of which one.

Branch on the result:
- **Single clear template match** — proceed to Step 3b-i (template
  import). Briefly tell the user "I found a pre-built [title] template
  and will use it" so they know what's being created; do not block on
  yes/no.
- **Multiple plausible matches** — present them and ask the user to
  pick. Once picked, proceed to Step 3b-i.
- **No template** — proceed to Step 3b-ii (custom build).

#### Step 3b-i: Import the template

> **Tool guardrail.** The only template tools are
> `signoz:signoz_list_dashboard_templates` and
> `signoz:signoz_import_dashboard`. Do not shell out, fetch raw GitHub
> URLs, or invent other tool names.
> `signoz:signoz_import_dashboard` takes the template `path` from the
> catalog entry and creates the dashboard in one call — you do not need
> to fetch the JSON yourself or call `signoz:signoz_create_dashboard`
> afterwards.

##### Step 3b-i.1: Pre-flight no-data probe (fail fast)

Before calling `signoz:signoz_import_dashboard`, confirm the template's
signals are actually being ingested. The most common silent failure for
template imports is "the template imports cleanly but every panel reads
'No data' because the technology isn't being scraped" — the user only
discovers it after clicking through to a useless dashboard.

Since we don't fetch the template body up front, base the probe on the
catalog entry's `category`, `title`, and `keywords` plus the user's
stated technology. Pick up to ~5 representative signals and check them
— keep the total small:

- **Metric-based templates** (most infra/runtime templates — e.g.
  PostgreSQL, Redis, JVM, hostmetrics, k8s, MongoDB, Kafka): call
  `signoz:signoz_list_metrics` with `searchText=<technology prefix>`
  (e.g. `postgresql`, `redis`, `jvm`, `system.`, `k8s.`, `mongo`,
  `kafka`) and `timeRange=1h`. Empty result → metric family is not
  being ingested.
- **Trace-based templates** (APM-style): call
  `signoz:signoz_aggregate_traces` with `aggregation=count`, an
  appropriate filter (e.g. `service.name EXISTS`), `timeRange=1h`.
  Zero count → no traces flowing.
- **Log-based templates**: call `signoz:signoz_aggregate_logs` with
  `aggregation=count`, a relevant filter, `timeRange=1h`. Zero count
  → no logs.
- **Variable values** (when the template clearly relies on a resource
  attribute, e.g. `service.name`, `k8s.cluster.name`): call
  `signoz:signoz_get_field_values` to confirm there are values to pick
  from. A dashboard whose top-level dropdown is empty is barely
  better than one full of empty panels.

Branch on the probe result:

- **All signals present** → proceed silently to Step 3b-i.2.
- **Some present, some missing** → list which are missing and ask the
  user to confirm before continuing. Many templates are useful even with
  partial coverage; let them decide.
- **None present** → warn the user verbatim: "I couldn't find data for
  [list] in the last hour — this template is for [technology] and it
  doesn't look like that data is being ingested yet. I can still create
  the dashboard (it will just show 'No data' until you ingest), or I can
  stop here. Which would you like?" Wait for the user's choice.

This probe is cheap (a handful of queries, ~hundreds of ms total), and
catching the no-data case early avoids the worst UX failure mode of the
template path.

##### Step 3b-i.2: Preview, import, report

1. **Preview.** Tell the user what's about to happen in one short
   paragraph: which template (`title`, `path`), what category, what the
   probe found. In autonomous mode the consumer proceeds; in interactive
   mode the human can intervene.
2. **Import.** Call `signoz:signoz_import_dashboard` with the `path`
   from the chosen catalog entry (e.g. `postgresql/postgresql.json`).
   The server fetches the JSON, validates it, and creates the dashboard
   in one call.
3. **Report.** Read the response and tell the user the dashboard's
   title, panel count, and section breakdown. Surface the dashboard's
   variables ("filter by `service.name`", "filter by
   `k8s.cluster.name`") so the user knows what knobs they have. Offer
   two follow-ups: "Want me to adjust panels, layout, or variables?"
   and "Want me to wire alerts for any of these signals?
   (`signoz-creating-alerts`)".
4. **Customization handling.** If the user asks for changes, call
   `signoz:signoz_get_dashboard` to fetch the current state, apply the
   changes, and call `signoz:signoz_update_dashboard` with the full
   updated JSON. Beyond the initial customization round, hand off to
   `signoz-modifying-dashboards`.

#### Step 3b-ii: Custom build (no template, or import failed)

Run this path when the Step 3b template lookup found no match, the user
explicitly rejected the suggested template, or
`signoz:signoz_import_dashboard` failed.

##### Step 3b-ii.1: Gather requirements

Ask the user (skip questions whose answer is already clear from intent):

1. **Signals** — metrics, traces, logs, or a combination.
2. **Specific signals** — which metrics, which span attributes, which
   log severities matter most.
3. **Resource scope** — which service(s), namespace(s), cluster(s), or
   environment(s).
4. **Variables** — what should be a dropdown vs. a hard-coded filter
   (typical: `service.name`, `deployment.environment.name`,
   `k8s.cluster.name`).
5. **Sections** — group panels into Overview / Latency / Errors /
   Saturation, or another structure that fits the domain.

If the user is non-specific ("just make me something useful for X"),
apply the defaults table below and surface them in the preview.

##### Step 3b-ii.2: Discover names and probe data

The MCP guideline applies: **always prefer resource-attribute filters**.
Before authoring panels, confirm the names you'll use exist and emit
data:

1. **Metrics** — call `signoz:signoz_list_metrics` with a search term
   tied to the technology to get the *exact* OTel metric names. Wrong
   names produce empty panels.
2. **Resource attributes** — call `signoz:signoz_get_field_keys` with
   `fieldContext=resource` for the relevant signal to enumerate
   available attributes; call `signoz:signoz_get_field_values` for the
   most likely attributes (typically `service.name`, then `host.name`,
   then `k8s.namespace.name`) to get concrete values for variables.
3. **Per-panel data probe** — for the headline panels, run a short
   `signoz:signoz_query_metrics` / `signoz:signoz_aggregate_traces` /
   `signoz:signoz_aggregate_logs` with the same filter the panel will
   use to confirm data exists. Keep the probe set small (~5 panels
   max).

If **none** of the probed signals return data, warn the user with the
same wording as Step 3b-i.1 and wait for confirmation before building.

##### Step 3b-ii.3: Read the dashboard MCP resources

These are the source of truth for the JSON schema, panel types, query
builder shape, and layout rules — do not transcribe schema text into
this skill, it will rot out of sync with the server:

- `signoz://dashboard/instructions` — title, tags, description,
  variables.
- `signoz://dashboard/widgets-instructions` — 7 panel types and layout
  rules.
- `signoz://dashboard/widgets-examples` — complete widget configs.
- `signoz://dashboard/query-builder-example` — query builder reference.

Add signal-specific resources as needed:

- Metrics: `signoz://dashboard/promql-example`,
  `signoz://dashboard/clickhouse-metrics-example`.
- Traces: `signoz://traces/query-builder-guide`.
- Logs: `signoz://dashboard/clickhouse-logs-example`.

##### Step 3b-ii.4: Build the dashboard JSON

Follow the v5 schema as documented in the resources above. Use OTel
semantic attribute names (not shorthand) in filters, groupBy, and
variables — `service.name` not `service`, `host.name` not `host`,
`deployment.environment.name` not `env`. Apply the defaults below
unless the user specified otherwise.

**Defaults the skill applies (and surfaces in the preview):**

| Field | Default | When to override |
|---|---|---|
| Time range | last 1h | longer for capacity planning, shorter for live debugging |
| Refresh | 30s | longer (5m+) for low-traffic dashboards |
| Section structure (infra) | Overview / Saturation / Errors / Latency | domain-specific (e.g. DB: Overview / Connections / Throughput / Slow Queries) |
| Headline panels (any signal) | request rate, error rate, p50/p95/p99 latency, saturation gauge (CPU or memory) | omit those that don't apply |
| Variables | `service.name`, `deployment.environment.name` | add `k8s.cluster.name` / `k8s.namespace.name` when the request is k8s-flavored |
| Layout | 2-column grid (`w: 6`), 12 columns wide | full-width (`w: 12`) for tables and time-series with many series |
| GroupBy on per-service panels | `service.name` resource attribute | drop when filtering to a single service |

**Title and description.** The dashboard title should name the
technology and the scope clearly: "PostgreSQL — prod-us-east-1", not
just "PostgreSQL". Description should answer "what is this for" in one
sentence. Tags: technology + signal types + environment when known.

##### Step 3b-ii.5: Shape check before save

`signoz:signoz_create_dashboard` rejects stringified JSON for
array/object fields with errors like
`cannot unmarshal string into ... layout of type []LayoutItem` /
`... tags of type []string`. Verify the values you are about to pass
match the input schema's types — do **not** wrap them in
`JSON.stringify` / `json.dumps`:

- `tags` → array of strings.
- `layout` → array of `{i, x, y, w, h}` objects.
- `widgets` → array of widget objects.
- `variables` → object/map keyed by variable name.
- `title`, `description` → plain strings.

##### Step 3b-ii.6: Preview, save, report

1. **Preview.** Emit a one-paragraph plain-language summary plus a
   fenced JSON code block containing the exact payload that will be sent
   to `signoz:signoz_create_dashboard`:

   ```json
   {
     "title": "...",
     "description": "...",
     "tags": ["..."],
     "variables": { ... },
     "widgets": [ ... ],
     "layout": [ ... ]
   }
   ```

   > **Summary**: This dashboard tracks [signals] for [scope], with
   > sections [list]. Variables: [list]. Time range default 1h. The
   > no-data probe found data for [count]/[total] headline panels.

   In autonomous mode the consumer proceeds; in interactive mode the
   human can intervene before save.

2. **Save.** Call `signoz:signoz_create_dashboard` with the payload.

3. **Report.** Tell the user:
   - The created dashboard's UUID and title.
   - Panel count and section breakdown.
   - Which variables are wired.
   - The probe summary ("data found for N of M headline panels").
   - Two follow-up offers: "Want me to adjust panels, layout, or
     variables?" and "Want me to wire alerts for any of these signals?
     (`signoz-creating-alerts`)".

## Guardrails

- **Strict inputs over guessing.** Resource scope is required for custom
  builds. If missing, emit `needs_input` and stop. A guessed scope on a
  shared dashboard is harder to clean up than asking.
- **Always paginate `signoz:signoz_list_dashboards`.** Stopping at page
  1 misses duplicates and produces clutter.
- **Duplicate check first.** The user's only two upfront options are
  "modify an existing one" or "create a new one" — never offer
  template-import as a separate top-level choice.
- **Template-first on the create path.** Once the user has chosen to
  create, always run `signoz:signoz_list_dashboard_templates` before any
  `signoz:signoz_create_dashboard` call. If a matching template exists,
  import it via `signoz:signoz_import_dashboard` (just inform the user);
  only build from scratch when no template matches.
- **No-data probe is mandatory before save.** Run the pre-flight probe
  (Step 3b-i.1 / Step 3b-ii.2) before `signoz:signoz_import_dashboard`
  / `signoz:signoz_create_dashboard`. A "No data" dashboard is a worse
  outcome than one extra confirmation prompt. Skip only if the user has
  explicitly opted out for this request.
- **Preview before save on custom builds.** Emit the JSON + summary
  before `signoz:signoz_create_dashboard` so the human (or the
  autonomous consumer) has a chance to intervene.
- **OTel attribute names only.** `service.name` not `service`,
  `host.name` not `host`, `deployment.environment.name` not `env`.
  Wrong names produce empty panels.
- **No metric guessing.** For custom builds, verify metric names with
  `signoz:signoz_list_metrics` before authoring. Wrong names produce
  empty panels and the user only finds out later.
- **Valid JSON shapes only.** Follow the v5 schema documented in
  `signoz://dashboard/*` MCP resources. Required widget and `queryData`
  fields are listed in `signoz://dashboard/widgets-instructions` and
  `signoz://dashboard/widgets-examples`. Never wrap arrays/objects in
  `JSON.stringify`.
- **Full state on update.** `signoz:signoz_update_dashboard` requires
  the **complete** dashboard JSON, not a partial patch. Always call
  `signoz:signoz_get_dashboard` first, merge changes into the full
  object, and pass the result to `signoz:signoz_update_dashboard`.
- **Scope boundary.** This skill only creates dashboards (and handles
  the initial customization round). Sustained modification work belongs
  to `signoz-modifying-dashboards`.

## Examples

**User:** "Create a dashboard for my PostgreSQL database"

**Agent:**
1. `signoz:signoz_list_dashboards` (paginated) → no PostgreSQL
   dashboard exists.
2. Says: "I'll create a new dashboard for PostgreSQL. Proceed?" User
   confirms.
3. `signoz:signoz_list_dashboard_templates searchContext="postgresql"`
   → picks `postgresql/postgresql.json`. Tells user: "I found a
   pre-built PostgreSQL template and will use it."
4. No-data probe: `signoz:signoz_list_metrics searchText=postgresql
   timeRange=1h` → returns `postgresql.connections.usage`,
   `postgresql.commits`, etc. Data flowing.
5. Calls `signoz:signoz_import_dashboard path=postgresql/postgresql.json`.
6. Reports: "Created 'PostgreSQL Overview' (UUID `…`) — 24 panels
   across Overview / Connections / Throughput / Replication. Variables:
   `postgresql.host.name`. Probe found data for all headline panels.
   Want me to adjust anything, or wire alerts for slow queries?"

*Variant — no PG data ingested:* the probe in step 4 returns empty;
agent emits the verbatim no-data warning from Step 3b-i.1 and waits for
the user to choose between "create anyway" and "stop".

---

**User:** "I need an APM dashboard — what do you have?"

**Agent:**
1. `signoz:signoz_list_dashboards` (paginated) → no APM dashboard.
2. Says: "I'll create a new APM dashboard. Want me to show you what
   templates we have first?" User: yes.
3. `signoz:signoz_list_dashboard_templates category="Apm"` → returns
   several templates (APM RED, APM Errors, etc.).
4. Presents the list and asks which to import. User picks "APM RED".
5. No-data probe: `signoz:signoz_aggregate_traces aggregation=count
   filter="service.name EXISTS" timeRange=1h` → returns rows. Data
   flowing.
6. Imports, reports panels and variables. Offers to wire latency
   alerts via `signoz-creating-alerts`.

---

**User:** "Set up monitoring for Redis" (existing "Redis - Overview"
dashboard found)

**Agent:** surfaces the existing dashboard with UUID and `createdAt`,
asks the user (a) modify / (b) create new / (c) stop. If user picks
(b), follows the PostgreSQL flow above against the `redis/redis.json`
template. If (a), hands off to `signoz-modifying-dashboards` after
fetching the current state with `signoz:signoz_get_dashboard`.

---

**User:** "Create a dashboard to track our payment processing pipeline"
(custom build — no template match)

**Agent:**
1. Duplicate check (none) and creation confirmation as above.
2. `signoz:signoz_list_dashboard_templates searchContext="payment
   pipeline"` → no match. Falls through to custom build (Step 3b-ii).
3. Gathers requirements: signals (traces + metrics), which services
   are in the pipeline, variables (`service.name`,
   `deployment.environment.name`).
4. Discovery: `signoz:signoz_get_field_keys signal=traces
   fieldContext=resource`, then `signoz:signoz_get_field_values
   name=service.name` → user picks `checkout`, `payments`,
   `inventory`, `notifications`.
5. Reads the `signoz://dashboard/*` MCP resources. Builds sections
   Overview / Latency / Errors / Throughput, with headline panels
   (request rate, p99 latency, error rate `A*100/B`, throughput) and
   the two variables.
6. Per-panel probe via `signoz:signoz_aggregate_traces` for the
   headline queries. Emits JSON preview + summary, then calls
   `signoz:signoz_create_dashboard`. Reports UUID, panels, sections,
   variables, probe summary. Offers to wire error-rate alerts via
   `signoz-creating-alerts`.

## Additional resources

- `signoz://dashboard/instructions`,
  `signoz://dashboard/widgets-instructions`,
  `signoz://dashboard/widgets-examples`,
  `signoz://dashboard/query-builder-example` MCP resources — full
  dashboard JSON schema, panel types, query builder shape, and layout
  rules. Always preferred over any transcribed copy.
- `signoz-generating-queries` skill — for authoring or testing queries
  before wrapping them in dashboard panels.
- `signoz-modifying-dashboards` skill — for sustained modification work
  beyond the initial customization round.
- `signoz-creating-alerts` skill — for wiring alerts on the signals
  shown in the dashboard.
