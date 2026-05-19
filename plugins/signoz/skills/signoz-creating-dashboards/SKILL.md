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
configured — run `signoz-mcp-setup` first to initialize or repair the MCP
connection. Do not fall back to raw HTTP calls or fabricate dashboard JSON
without the MCP tools.

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

If a required input is missing and cannot be discovered, **stop before
calling any write tool** and ask the user. The host application decides
how the question is surfaced (a structured clarification tool, inline
`<assistant_question>` tags, an interactive prompt, etc.) — follow the
host's UI rendering rules.

What to include in the question:

- **What is missing** — name the input concretely (e.g. "no service or
  cluster specified for the custom build").
- **Candidate lists** populated from your discovery calls — concrete
  values per attribute the user can pick from. Example shape:
  `service.name` → `frontend`, `checkout`, `payments`, `inventory`;
  `k8s.cluster.name` → `prod-us-east-1`, `staging`.
- **Allow free-form input** so the user can name a value you didn't
  surface.

In autonomous mode (no human), escalate to the caller or fill the gap
from upstream context. Either way, do not proceed to
`signoz:signoz_create_dashboard` / `signoz:signoz_import_dashboard` with
a guessed value.

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

Call `signoz:signoz_list_dashboards`. Most installs fit in the default
page (`limit=50`); only paginate when `pagination.hasMore=true`. Use
string values for `limit` / `offset` (e.g. `"50"`, `"0"`) — the schema
expects strings, not integers.

**Match by relevance.** Compare each existing
dashboard's lowercased `name`, `description`, and `tags` against the
user's technology/domain. Surface only matches a human would recognize
as the same thing — a "redis" dashboard does not match a "postgresql"
request just because both have a `database` tag. Collect each match's
`name`, `uuid`, and `createdAt` for the next step.

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

Hand off immediately to `signoz-modifying-dashboards` with the chosen
dashboard UUID and the user's intent. Do not call
`signoz:signoz_update_dashboard` from this skill — modification is out
of scope. (See "Scope boundary" in Guardrails.)

#### Step 3b: Create a new dashboard

Run the template lookup first. The user has already agreed to create
new — the lookup decides *how* we build it.

Call `signoz:signoz_list_dashboard_templates` once with no arguments.
The full catalog (~95 entries) returns in a single call — read it
in-context and pick the best match for the user's intent. When several
entries plausibly fit, present the top 3–5 and let the user choose.

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

- **Metric-based templates** (most infra/runtime templates): call
  `signoz:signoz_list_metrics` with `searchText` set to the technology
  prefix (e.g. `searchText="postgresql"`). Empty result → metric family
  is not being ingested. *Early out:* if this returns empty, declare
  "None present" and skip the rest of the metric probes — they will all
  return zero. Note: `signoz:signoz_list_metrics` has no `timeRange` parameter;
  pass `start`/`end` (unix-ms strings) only if you need a window other
  than the server default.
- **Trace-based templates** (APM-style): call
  `signoz:signoz_aggregate_traces` with `aggregation=count`,
  `timeRange=1h`. No filter is needed for the "is anything flowing"
  probe — adding `filter="service.name EXISTS"` is fragile and
  unnecessary. Zero count → no traces flowing.
- **Log-based templates**: call `signoz:signoz_aggregate_logs` with
  `aggregation=count`, `timeRange=1h`, no filter. Zero count → no logs.
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
- **None present** → tell the user no data was found for this
  technology in the probe window, explain the dashboard will show "No
  data" until ingestion is set up, and offer to create it anyway or
  stop. Wait for the user's choice.

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
4. **Customization handling.** If the user asks for any change to the
   imported dashboard, hand off to `signoz-modifying-dashboards` with
   the new dashboard's UUID and the requested changes. Do not call
   `signoz:signoz_update_dashboard` from this skill.

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

1. **Metrics** — call `signoz:signoz_list_metrics` with `searchText`
   tied to the technology (e.g. `searchText="postgresql"`) to get the
   *exact* OTel metric names. Catalog presence ≠ data flowing — for
   any metric you intend to use, follow up with `signoz:signoz_query_metrics`
   on a representative window to confirm it actually has datapoints.
2. **Resource attributes** — call `signoz:signoz_get_field_keys` with
   `fieldContext=resource` for the relevant signal to enumerate
   available attributes; call `signoz:signoz_get_field_values` on the
   ones you'll use as variables to confirm concrete values exist. Note
   that the live data may use older OTel semconv (e.g.
   `deployment.environment` rather than `deployment.environment.name`)
   — always trust the discovered key over the one in the defaults
   table.

Per-panel validation happens later as a hard requirement — see
Step 3b-ii.6 and the "Mandatory dry-run before save" guardrail.

If **none** of the discovered signals return data, tell the user the
dashboard's data isn't being ingested yet, explain the panels will
show "No data" until ingestion is set up, and offer to build anyway
or stop. Wait for the user's choice before building.

##### Step 3b-ii.3: Read the dashboard MCP resources

These are the source of truth for the JSON schema, panel types, query
builder shape, and layout rules — do not transcribe schema text into
this skill, it will rot out of sync with the server. Read the four
core resources before authoring widget JSON.

> **Fallback when the MCP resource-reader is unavailable.** Some MCP
> client harnesses do not expose a resource-reading tool. If you
> cannot read `signoz://...` URIs in this session, fall back to
> `signoz:signoz_list_dashboards` + `signoz:signoz_get_dashboard` on
> an existing dashboard of the same signal type (metrics / traces /
> logs) and read its `widgets` array for v5 widget shapes. The
> mandatory dry-run in Step 3b-ii.6 then backstops any shape errors
> the fallback misses.

- `signoz://dashboard/instructions` — title, tags, description,
  variables.
- `signoz://dashboard/widgets-instructions` — 7 panel types and layout
  rules.
- `signoz://dashboard/widgets-examples` — complete widget configs with
  all required fields (the most important resource — every widget
  must include `id`, `panelTypes`, `title`, `query`, `selectedLogFields`,
  `selectedTracesFields`, `thresholds`, `contextLinks`).
- `signoz://dashboard/query-builder-example` — query builder reference,
  including operator semantics for `filters.items[].op`.

Add signal-specific resources as needed:

- Metrics (PromQL): `signoz://promql/instructions`.
- Metrics (ClickHouse): `signoz://dashboard/clickhouse-schema-for-metrics`
  + `signoz://dashboard/clickhouse-metrics-example`.
- Metrics (Query Builder aggregation rules):
  `signoz://metrics-aggregation-guide` — required for picking valid
  `timeAggregation` / `spaceAggregation` per metric type.
- Traces (Query Builder): `signoz://traces/query-builder-guide`.
- Traces (ClickHouse): `signoz://dashboard/clickhouse-schema-for-traces`
  + `signoz://dashboard/clickhouse-traces-example`.
- Logs (ClickHouse): `signoz://dashboard/clickhouse-schema-for-logs`
  + `signoz://dashboard/clickhouse-logs-example`.

##### Step 3b-ii.4: Build the dashboard JSON

Follow the v5 schema as documented in the resources above. Use OTel
semantic attribute names (not shorthand) in filters, groupBy, and
variables. Apply the defaults below unless the user specified otherwise.

Non-trivial panels (groupBy, formula, disabled queries, dynamic
variables, non-string attributes) are validated in Step 3b-ii.6 via the
mandatory dry-run before save. Author the JSON here as you intend to
save it — the dry-run uses the exact shape from `queryData`.

**Defaults the skill applies (and surfaces in the preview):**

| Field | Default | When to override |
|---|---|---|
| Time range | last 1h | longer for capacity planning, shorter for live debugging |
| Refresh | manual (no auto-refresh) | set 30s–1m only when the user explicitly wants live updates |
| Section structure (APM/services) | Overview / Latency / Errors / Throughput | domain-specific (e.g. DB: Overview / Connections / Throughput / Slow Queries) |
| Section structure (infra/runtime) | Overview / Saturation / Errors / Latency | domain-specific |
| Headline panels (services) | request rate, error rate, p50/p95/p99 latency, throughput | omit those that don't apply |
| Headline panels (infra) | resource utilization (CPU, mem), saturation, error/restart counts, throughput | tailor to the technology |
| Variables (services) | `service.name`, `deployment.environment` (or `deployment.environment.name` — verify which exists via `signoz:signoz_get_field_keys`) | add `k8s.cluster.name` / `k8s.namespace.name` when k8s-flavored |
| Variables (k8s/infra) | `k8s.cluster.name`, `k8s.namespace.name` (or `host.name` for hostmetrics) | drop `service.name` — it is rarely populated on infra signals |
| Layout | 2-column grid (`w: 6`), 12 columns wide | full-width (`w: 12`) for tables and time-series with many series |
| GroupBy on per-service panels | `service.name` resource attribute | drop when filtering to a single service |

**Title and description.** The dashboard title should name the
technology and the scope clearly: "PostgreSQL — prod-us-east-1", not
just "PostgreSQL". Description should answer "what is this for" in one
sentence. Tags: technology + signal types + environment when known.

##### Step 3b-ii.5: Shape check before save

`signoz://dashboard/widgets-examples` is the source of truth for widget
required fields, panel-type-specific shapes, the canonical
`filters.items[].key.id` form, operator casing, and common write-shape
errors. Re-skim it before serialising any custom widget JSON.

One rule `widgets-examples` does not call out, but
`signoz:signoz_create_dashboard` enforces: **no `JSON.stringify` on
arrays/objects.** `layout`, `widgets`, `tags`, and `variables` are
native JSON — stringifying them produces errors like
`cannot unmarshal string into ... layout of type []LayoutItem`.

##### Step 3b-ii.6: Dry-run before save (mandatory)

Call `signoz:signoz_execute_builder_query` per panel. The dry-run
validates the query is well-formed *and* confirms data flows under
that filter — the per-panel data probe folds in here.

**Envelope translation.** Widget JSON wraps queries in
`compositeQuery.builder.queryData[]` and `queryFormulas[]`, but
`signoz_execute_builder_query` takes
`compositeQuery.queries[].{type, spec}`. Translate per panel: each
`queryData[i]` → `{ type: "builder_query", spec: { signal, filter:
{expression}, groupBy, aggregations } }`; each `queryFormulas[i]` →
`{ type: "builder_formula", spec: { name, expression } }`. The
endpoint cannot consume widget JSON directly.

Non-empty response = pass; server error, "filter type mismatch", or
unexpected zero rows = fail (fix the panel JSON before save).

Coverage:

- **≤10 panels:** dry-run every panel, trivial or not. Trivial panels
  fail silently too (wrong severity filter, wrong resource scope).
- **>10 panels:** dry-run all panels with `groupBy`, formula,
  disabled queries, dynamic variables, or non-string filters, plus a
  ~5 sample of the trivial ones.

##### Step 3b-ii.7: Preview, save, report

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
   > sections [list]. Variables: [list]. Time range default 1h.
   > Dry-run: [N]/[total] panels validated against live data (any
   > panels that failed have been fixed; any panels deliberately
   > sampled or skipped are listed).

   In autonomous mode the consumer proceeds; in interactive mode the
   human can intervene before save.

2. **Save.** Call `signoz:signoz_create_dashboard` with the payload.

3. **Report.** Tell the user:
   - The created dashboard's UUID and title.
   - Panel count and section breakdown.
   - Which variables are wired.
   - The dry-run summary: how many panels were dry-run, how many
     failed and were fixed pre-save, and any panels deliberately
     sampled or skipped under the size rule above.
   - Two follow-up offers: "Want me to adjust panels, layout, or
     variables?" and "Want me to wire alerts for any of these signals?
     (`signoz-creating-alerts`)".

## Guardrails

- **Strict inputs over guessing.** Resource scope is required for custom
  builds. If missing, stop and ask the user (see *Required inputs*
  above). A guessed scope on a shared dashboard is harder to clean up
  than asking.
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
- **Mandatory dry-run before save on custom builds.** Before
  `signoz:signoz_create_dashboard`, run
  `signoz:signoz_execute_builder_query` per Step 3b-ii.6 — translate
  each panel's `builder.queryData[]` / `queryFormulas[]` into the
  endpoint's `queries[].{type, spec}` envelope (mapping in Step
  3b-ii.6). Skipping is equivalent to skipping the duplicate check.
  The create-dashboard schema accepts queries that 500 at query time
  — a `groupBy` on a numeric attribute, an unquoted bool filter
  (`is_error = 'true'` is correct; `is_error = true` 500s), an
  aggregation incompatible with the metric type — and the result
  ships as a silently empty panel. The JSON preview a human reads
  cannot catch these; autonomous mode has no preview at all, so the
  dry-run is the only safety net.
- **Preview before save on custom builds.** Emit the JSON + summary
  before `signoz:signoz_create_dashboard`. Preview is for human
  intervention on intent, not a substitute for the dry-run.
- **OTel attribute names only.** `service.name` not `service`,
  `host.name` not `host`. Wrong names produce empty panels. Verify the
  exact key (`deployment.environment` vs `deployment.environment.name`,
  for instance) against `signoz:signoz_get_field_keys` rather than guessing —
  installs running classic OTel semconv emit the no-`.name` form.
- **No metric guessing.** For custom builds, verify metric names with
  `signoz:signoz_list_metrics` before authoring. Wrong names produce
  empty panels and the user only finds out later.
- **Valid JSON shapes only.** Follow the v5 schema documented in
  `signoz://dashboard/*` MCP resources. Required widget and `queryData`
  fields are listed in `signoz://dashboard/widgets-instructions` and
  `signoz://dashboard/widgets-examples`. Never wrap arrays/objects in
  `JSON.stringify`.
- **Scope boundary.** This skill creates dashboards. The moment the
  user asks to modify, edit, rearrange, or extend an existing dashboard
  — including immediately after import — hand off to
  `signoz-modifying-dashboards`. Do not call
  `signoz:signoz_update_dashboard` from this skill.

## Examples

**User:** "Create a dashboard for my PostgreSQL database"

**Agent:**
1. `signoz:signoz_list_dashboards` (paginated) → no PostgreSQL
   dashboard exists.
2. Says: "I'll create a new dashboard for PostgreSQL. Proceed?" User
   confirms.
3. `signoz:signoz_list_dashboard_templates` → picks
   `postgresql/postgresql.json`. Tells user: "I found a pre-built
   PostgreSQL template and will use it."
4. No-data probe: `signoz:signoz_list_metrics searchText="postgresql"`
   → returns `postgresql.connections.usage`, `postgresql.commits`, etc.
   Data flowing.
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
3. `signoz:signoz_list_dashboard_templates` → reads the full catalog
   in-context, filters to APM entries (APM RED, APM Errors, etc.).
4. Presents the list and asks which to import. User picks "APM RED".
5. No-data probe: `signoz:signoz_aggregate_traces aggregation=count
   timeRange=1h` → returns rows. Data flowing.
6. Imports, reports panels and variables. Offers to wire latency
   alerts via `signoz-creating-alerts`.

---

**User:** "Set up monitoring for Redis" (existing "Redis - Overview"
dashboard found)

**Agent:** surfaces the existing dashboard with UUID and `createdAt`,
asks the user (a) modify / (b) create new / (c) stop. If user picks
(b), follows the PostgreSQL flow above against the `redis/redis.json`
template. If (a), hands off to `signoz-modifying-dashboards` with the
dashboard's UUID and the user's intent (no `signoz:signoz_get_dashboard` call
from this skill).

---

**User:** "Create a dashboard to track our payment processing pipeline"
(custom build — no template match)

**Agent:**
1. Duplicate check (none) and creation confirmation as above.
2. `signoz:signoz_list_dashboard_templates` → no match in the catalog.
   Falls through to custom build (Step 3b-ii).
3. Gathers requirements: signals (traces + metrics), which services
   are in the pipeline, variables (`service.name` plus the env key
   that actually exists in the install).
4. Discovery (parallel): `signoz:signoz_get_field_keys signal=traces
   fieldContext=resource` → confirms `service.name` and
   `deployment.environment` (no `.name` suffix in this install);
   `signoz:signoz_get_field_values name=service.name` → user picks
   `checkout`, `payments`, `inventory`, `notifications`.
5. Reads the `signoz://dashboard/*` MCP resources. Builds sections
   Overview / Latency / Errors / Throughput, with headline panels
   (request rate, p99 latency, error rate `A*100/B`, throughput) and
   the two variables.
6. Per-panel probe via `signoz:signoz_aggregate_traces` for the
   headline queries. Emits JSON preview + summary, then calls
   `signoz:signoz_create_dashboard`. Reports UUID, panels, sections,
   variables, probe summary. Offers to wire error-rate alerts via
   `signoz-creating-alerts`.
