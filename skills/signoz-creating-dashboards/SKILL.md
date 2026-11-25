---
name: signoz-creating-dashboards
description: >
  Create a new SigNoz dashboard from a natural-language intent: import a
  curated template (PostgreSQL, Redis, JVM, k8s, hostmetrics, APM, LLM,
  etc.) when one fits, or build a custom dashboard from scratch with
  metric / trace / log panels. Make sure to use this skill whenever the
  user says "create a dashboard for…", "set up monitoring for…",
  "build me a dashboard…", "I need observability for…", "import a
  dashboard template", or asks to track / visualize a service, database,
  cluster, or AI/LLM platform, even if they don't explicitly say
  "dashboard". Also use it when someone wants to "monitor", "watch", or
  "see metrics for" a technology and the natural answer is a dashboard.
metadata:
  argument-hint: <natural-language dashboard intent>
---

# Dashboard Create

## Prerequisites

This skill calls SigNoz MCP server tools (`signoz_create_dashboard`,
`signoz_list_dashboards`, `signoz_list_dashboard_templates`,
`signoz_import_dashboard`, `signoz_get_dashboard`,
`signoz_update_dashboard`, `signoz_list_metrics`,
`signoz_get_field_keys`, `signoz_get_field_values`,
`signoz_aggregate_logs`, `signoz_aggregate_traces`, etc.).
Before running the workflow, confirm the `signoz_*` tools are
available. If they are not, the SigNoz MCP server is not installed or
configured; run `signoz-mcp-setup` first to initialize or repair the MCP
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
to clean up. The skill enforces a soft input contract; most fields have
sensible defaults, but a few cannot be guessed:

| Input | Required | Source if missing |
|---|---|---|
| Dashboard intent (NL goal) | yes | `$ARGUMENTS` or recent user turn |
| Technology / domain (e.g. PostgreSQL, Redis, "payment pipeline") | yes | parse from intent; otherwise ask |
| Confirmation to create (plus the modify-or-create choice when duplicates exist) | yes | ask the user (Step 2); still required with zero duplicates and under stated urgency |
| Resource scope for custom builds (service / namespace / cluster) | yes for custom builds | discover via `signoz_get_field_keys` + `signoz_get_field_values`; fall back to a dashboard variable |
| Specific metrics / signals for custom builds | inferred | derive from technology + the Step 3b-ii.3 guides; surface in preview |
| Layout | inferred | apply defaults (see "Defaults" below) |

If a required input is missing and cannot be discovered, **stop before
calling any write tool** and ask the user. The host application decides
how the question is surfaced (a structured clarification tool, inline
`<assistant_question>` tags, an interactive prompt, etc.); follow the
host's UI rendering rules.

What to include in the question:

- **What is missing**: name the input concretely (e.g. "no service or
  cluster specified for the custom build").
- **Candidate lists** populated from your discovery calls: concrete
  values per attribute the user can pick from. Example shape:
  `service.name` → `frontend`, `checkout`, `payments`, `inventory`;
  `k8s.cluster.name` → `prod-us-east-1`, `staging`.
- **Allow free-form input** so the user can name a value you didn't
  surface.

In autonomous mode (no human), escalate to the caller or fill the gap
from upstream context. Either way, do not proceed to
`signoz_create_dashboard` / `signoz_import_dashboard` with
a guessed value.

## Workflow

The create path starts **duplicate check → modify-or-create choice → template
lookup**. A matching template uses **no-data probe → preview → import**;
a custom build uses **no-data probe → build → per-panel dry-run → preview →
create**. Template lookup is internal; the user's only upfront choices are
modify or create.

### Step 1: Check for duplicates

1. Call `signoz_list_dashboards`. When the wording is distinctive, narrow with
   the `filter` argument; read `signoz://dashboard/list-filter-guide` before
   writing a filter longer than one free-text word. If a filtered listing
   returns nothing, list again without the filter, from offset 0.
2. Cover the whole listing. Start at offset 0 and keep the same filter and
   sort. While the result's `pagination.hasMore` is true, continue at
   `pagination.nextOffset`; when it is false, stop. When the result has no
   `pagination` object, raise `offset` by the number of dashboards the page
   returned and stop once the offset reaches the reported `total`. Do not
   raise `offset` by `limit`, because a page can hold fewer dashboards than
   `limit`. If a page returns no dashboards before the offset reaches
   `total`, tell the user the listing is incomplete.
3. **Match by relevance** Compare each dashboard's lowercased
   `spec.display.name`, `.description`, and `tags` against the user's
   technology/domain. Surface only matches a human would recognize as the
   same thing: a "redis" dashboard does not match a "postgresql" request just
   because both have a `database` tag. Collect each match's
   `spec.display.name`, `id`, and `createdAt` for the next step.

### Step 2: Ask the user (modify or create)

Present exactly two options (no template-import as a separate top-level
choice; that's an internal decision in Step 3b):

- **Duplicates found:** "There are already these similar dashboards:
  [list with name, id, created-at]. Want me to (a) modify one of
  these, (b) create a new dashboard anyway, or (c) stop?"
- **No duplicates:** "I'll create a new dashboard for this. Proceed?"
  (No "modify" option when there's nothing to modify.)
- **A match whose list row has `legacy: true`:** list it as a duplicate, say
  that it is still in the v1 schema and that these tools cannot fetch or edit
  it, and do not offer to modify it.

Wait for the user's choice. "modify" → Step 3a. "create new" / confirm
→ Step 3b. "stop" → stop.

### Step 3: Create or modify

#### Step 3a: Modify an existing dashboard

Hand off immediately to `signoz-modifying-dashboards` with the chosen
dashboard id and the user's intent. Do not call
`signoz_update_dashboard` or `signoz_patch_dashboard` from this skill;
modification is out of scope. (See "Scope boundary" in Guardrails.)

#### Step 3b: Create a new dashboard

Run the template lookup first. The user has already agreed to create
new; the lookup decides *how* we build it.

Call `signoz_list_dashboard_templates` with `searchText` set to the technology
the user named; omit `searchText` only when the user asks what templates
exist. If nothing matches, retry with fewer words before concluding there is
no template. When several entries fit, present the top 3–5 and let the user
choose.

Branch on the result:
- **Single clear template match**: proceed to Step 3b-i (template
  import). Briefly tell the user "I found a pre-built [title] template
  and will use it" so they know what's being created; do not block on
  yes/no.
- **Multiple plausible matches**: present them and ask the user to
  pick. Once picked, proceed to Step 3b-i.
- **Template matches the technology but not the requested signals**:
  common for any specific ask ("Kafka, but I want consumer fetch rate by
  client"). Not "no template": import it, then hand the extra panels to
  `signoz-modifying-dashboards` with the new id. Building from scratch
  discards the curated baseline for no gain.
- **No template**: proceed to Step 3b-ii (custom build). That means no
  catalog entry for the technology, not an entry that looks imperfect or
  aimed at a different metric family. Template bodies are not readable
  before import, so a suspected mismatch is only a hypothesis, and the
  Step 3b-i.1 probe sits *inside* the import path, so it cannot justify
  leaving that path. Probe first, then decide.

#### Step 3b-i: Import the template

> **Tool guardrail** The only template tools are
> `signoz_list_dashboard_templates` and `signoz_import_dashboard`. Do not
> shell out, fetch raw GitHub URLs, or invent other tool names. The import
> creates the dashboard in one call: do not fetch the template JSON yourself
> or call `signoz_create_dashboard` afterwards.

##### Step 3b-i.1: Pre-flight no-data probe (fail fast)

Before calling `signoz_import_dashboard`, confirm the template's
signals are actually being ingested. The most common silent failure for
template imports is "the template imports cleanly but every panel reads
'No data' because the technology isn't being scraped": the user only
discovers it after clicking through to a useless dashboard.

Since we don't fetch the template body up front, base the probe on the
catalog entry's `category`, `title`, and `keywords` plus the user's
stated technology. Pick up to ~5 representative signals and check
them; keep the total small:

- **Metric-based templates** (most infra/runtime templates): call
  `signoz_list_metrics` with `searchText` set to the technology
  prefix (e.g. `searchText="postgresql"`). It lists the metrics active in
  the window (default 1h), so an empty result means none were active then.
  *Early out:* if it returns empty, declare "None present" and skip the rest
  of the metric probes. Pass `timeRange`, or `start` and `end`, to probe a
  different window.
- **Trace-based templates** (APM-style): call
  `signoz_aggregate_traces` with `aggregations="count()"`,
  `timeRange=1h`. No filter is needed for the "is anything flowing"
  probe; adding `filter="service.name EXISTS"` is fragile and
  unnecessary. Zero count → no traces flowing.
- **Log-based templates**: call `signoz_aggregate_logs` with
  `aggregations="count()"`, `timeRange=1h`, no filter. Zero count → no logs.
- **Variable values** (when the template clearly relies on a resource
  attribute, e.g. `service.name`, `k8s.cluster.name`): call
  `signoz_get_field_values` to confirm there are values to pick
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

The probe shows which signals were active in its window. It cannot show that
each template panel has data, because template bodies are not readable before
import: report the names it found and do not claim per-panel coverage.

##### Step 3b-i.2: Preview, import, report

1. **Preview** Tell the user what's about to happen in one short
   paragraph: which template (`title`, `path`), what category, what the
   probe found. In autonomous mode the consumer proceeds; in interactive
   mode the human can intervene.
2. **Import** Call `signoz_import_dashboard` with the `path`
   from the chosen catalog entry (e.g. `postgresql/postgresql.json`).
3. **Report** Read the response and tell the user the dashboard's
   title, panel count, and section breakdown. Surface the dashboard's
   variables ("filter by `service.name`", "filter by
   `k8s.cluster.name`") so the user knows what knobs they have. Offer
   two follow-ups: "Want me to adjust panels, layout, or variables?"
   and "Want me to wire alerts for any of these signals?
   (`signoz-creating-alerts`)".
4. **Customization handling** If the user asks for any change to the
   imported dashboard, hand off to `signoz-modifying-dashboards` with
   the new dashboard's id and the requested changes. Do not call
   `signoz_update_dashboard` from this skill.

#### Step 3b-ii: Custom build (no template, or import failed)

Run this path when the Step 3b template lookup found no match, the user
explicitly rejected the suggested template, or
`signoz_import_dashboard` failed.

##### Step 3b-ii.1: Gather requirements

Ask the user (skip questions whose answer is already clear from intent):

1. **Signals**: metrics, traces, logs, or a combination.
2. **Specific signals**: which metrics, which span attributes, which
   log severities matter most.
3. **Resource scope**: which service(s), namespace(s), cluster(s), or
   environment(s).
4. **Variables**: what should be a dropdown vs. a hard-coded filter
   (typical: `service.name`, `deployment.environment.name`,
   `k8s.cluster.name`).
5. **Sections**: group panels into Overview / Latency / Errors /
   Saturation, or another structure that fits the domain.

If the user is non-specific ("just make me something useful for X"),
apply the defaults table below and surface them in the preview.

##### Step 3b-ii.2: Discover names and probe data

The MCP guideline applies: **always prefer resource-attribute filters**.
Before authoring panels, confirm the names you'll use exist and emit
data:

1. **Metrics**: call `signoz_list_metrics` with `searchText`
   tied to the technology (e.g. `searchText="postgresql"`) to get the
   *exact* OTel metric names. A listed metric was active in the window,
   but not necessarily for your scope; for any metric you intend to use,
   run `signoz_query_metrics` with the panel's filter to confirm datapoints.
2. **Resource attributes**: call `signoz_get_field_keys` with
   `fieldContext=resource` for the relevant signal to enumerate
   available attributes; call `signoz_get_field_values` on the
   ones you'll use as variables to confirm concrete values exist. Note
   that the live data may use older OTel semconv (e.g.
   `deployment.environment` rather than `deployment.environment.name`);
   always trust the discovered key over the one in the defaults
   table.

If **none** of the discovered signals return data, tell the user the
dashboard's data isn't being ingested yet, explain the panels will
show "No data" until ingestion is set up, and offer to build anyway
or stop. Wait for the user's choice before building.

##### Step 3b-ii.3: Read the dashboard MCP resources

The MCP server owns the dashboard JSON shape, panel kinds, query shapes, and
layout rules; do not author from memory or from schema text copied into this
skill. Read these before authoring panel JSON:

1. `signoz://dashboard/instructions`: title, tags, description, layout,
   variables.
2. `signoz://dashboard/widgets-instructions`: the panel kinds, when to use
   each, which query kinds each accepts, legends, and the dry-run procedure.
   Take the list of panel kinds from this guide, not from memory.
3. `signoz://dashboard/widgets-examples`: one worked panel per common kind.
4. `signoz://dashboard/examples`: whole create payloads with panels, layouts,
   and variables assembled.
5. The guides for each query language the panels use:
   - Query Builder: `signoz://dashboard/query-builder-example`, plus the
     signal's guide: `signoz://metrics-aggregation-guide` (valid
     `timeAggregation` / `spaceAggregation` per metric type),
     `signoz://traces/query-builder-guide`,
     `signoz://logs/query-builder-guide`, or
     `signoz://ai/query-builder-guide` for LLM and AI-agent telemetry.
   - PromQL: `signoz://promql/instructions`. Grafana-only
     `$__rate_interval` and `$__interval` are invalid in SigNoz.
   - ClickHouse SQL on metrics:
     `signoz://dashboard/clickhouse-schema-for-metrics` and
     `signoz://dashboard/clickhouse-metrics-example`.
   - ClickHouse SQL on traces:
     `signoz://dashboard/clickhouse-schema-for-traces` and
     `signoz://dashboard/clickhouse-traces-example`.
   - ClickHouse SQL on logs: `signoz://dashboard/clickhouse-schema-for-logs`
     and `signoz://dashboard/clickhouse-logs-example`.

If this client cannot read `signoz://` resources, take field shapes and kind
names from the `signoz_create_dashboard` input schema, and call
`signoz_list_dashboards` then `signoz_get_dashboard` on an existing dashboard
of the same signal type (metrics / traces / logs) to read worked panels from
its `spec.panels` map.

##### Step 3b-ii.4: Build the dashboard JSON

Follow the `signoz_create_dashboard` input schema and the guides above for
every kind name and field shape; do not carry over Grafana names such as
`timeseries`. Use OTel semantic attribute names (not shorthand) in filters,
groupBy, and variables. Apply the defaults below unless the user specified
otherwise.

- **Name** Leave the top-level `name` out on create; the server derives that
  immutable label from `spec.display.name`.
- **Default time range and refresh** `spec.duration` and
  `spec.refreshInterval` store them. Set them when the user asks for a
  default. Whether the UI applies them depends on the SigNoz version, so
  read each field's description in the `signoz_create_dashboard` input
  schema. When it says the UI does not apply the field, panels compute over
  the range the viewer selects: tell the user in the handoff to select that
  range in the UI.
  Do not invent `timeRange`, `defaultTimeRange`, or `refresh` fields, and do
  not encode a PromQL range selector inside a Builder query.
- **Placement** Give every panel the user should see exactly one grid item.
  SigNoz accepts a panel with no grid item and does not show it; the input
  schema is authoritative here, although the layout checklist in
  `signoz://dashboard/instructions` asks for one grid item per panel. SigNoz
  rejects a grid item whose `$ref` names a missing panel, so when rebuilding
  from another dashboard drop the grid items of panels you did not carry
  over.
- **Request panels** A panel that reports requests (request rate, request
  count, request latency, or error rate), for one service or grouped by
  service, counts entry spans. Add `isEntryPoint = true OR isRoot = true` to
  the filter, in parentheses when you AND it with other conditions. Without
  it the query counts every span, and so do the span metrics
  `signoz_calls_total` and `signoz_latency`.

**Defaults the skill applies (and surfaces in the preview):**

| Field | Default | When to override |
|---|---|---|
| Section structure (APM/services) | Overview / Latency / Errors / Throughput | domain-specific (e.g. DB: Overview / Connections / Throughput / Slow Queries) |
| Section structure (infra/runtime) | Overview / Saturation / Errors / Latency | domain-specific |
| Headline panels (services) | request rate, error rate, p50/p95/p99 latency, throughput | omit those that don't apply |
| Headline panels (infra) | resource utilization (CPU, mem), saturation, error/restart counts, throughput | tailor to the technology |
| Counter render unit (rate vs. count) | per-second rate | per-interval **increase** count over a wider window (24h–7d) for any low-volume / bursty / human-paced counter (requests, **error counts**, restarts, OOM kills) where `/sec` renders as tiny decimals (e.g. `0.03/s`); gauges (CPU/mem/queue depth) are already absolute and unaffected; note `increase` rescales its y-axis with the selected range, so prefer it deliberately, not by reflex |
| Variables (services) | `service.name`, `deployment.environment` (or `deployment.environment.name`; verify which exists via `signoz_get_field_keys`) | add `k8s.cluster.name` / `k8s.namespace.name` when k8s-flavored |
| Variables (k8s/infra) | `k8s.cluster.name`, `k8s.namespace.name` (or `host.name` for hostmetrics) | drop `service.name`; it is rarely populated on infra signals |
| Layout | 2-column grid (`width: 6`) | full-width (`x: 0, width: 12`) for tables and time-series with many series |
| GroupBy on per-service panels | `service.name` resource attribute | drop when filtering to a single service |

**Sections** Use one Grid entry in `spec.layouts` per section, in display
order, titled with the section name. Item coordinates restart in each Grid.

**Title and description** The dashboard title (`spec.display.name`) should name the
technology and the scope clearly: "PostgreSQL - prod-us-east-1", not
just "PostgreSQL". `spec.display.description` should answer "what is this for" in one
sentence. Tags: technology + signal types + environment when known.

##### Step 3b-ii.5: Shape check before save

Check each panel against the `signoz_create_dashboard` input schema, which is
authoritative for required fields and plugin `kind` names, and against the
worked panel of the same kind in `signoz://dashboard/widgets-examples`. Send
`spec`, `tags`, and everything inside them as native JSON objects and arrays,
never as stringified JSON.

Bound each query on purpose. Follow the result-bounds rule in
`signoz://dashboard/widgets-examples`, which the
`signoz_execute_builder_query` input schema also states: a standalone query
and a formula result carry a `limit` and an `order`, and a formula's base
queries carry neither. A query that a formula with `disabled: true` reads is
still a base query. The panel sections of
`signoz://dashboard/widgets-instructions` override that rule for Top List
(the limit is the row count) and Geo Map (no limit that drops places). Use
the limit the user asked for, such as a top 5. On a time series the limit
keeps the top groups ranked over the whole window, so a short-lived spike
can fall outside it. Dry-run the complete composite payload.

##### Step 3b-ii.6: Dry-run before save (mandatory)

For every query-bearing panel, follow "Dry-run a panel query" in
`signoz://dashboard/widgets-instructions`; if that guide is unreadable, take
the request shape from the `signoz_execute_builder_query` input schema.
Send the panel's saved query spec, never the panel JSON. Dry-run over a short
absolute Unix-ms window (usually the last 30-60 minutes), never the panel's
display range by reflex; apply that section's empty-result and timeout rules
before widening or retrying. Use representative variable values in the
dry-run copy and keep `$var` in `signoz_create_dashboard`.

If the executor cannot represent a saved field, report the
panel as unvalidated and continue only after explicit user acceptance. Server or
validation errors block. Unexpected empty results block unless the user already
accepted absent telemetry.

##### Step 3b-ii.7: Preview, save, report

1. **Preview** Emit a one-paragraph plain-language summary of what
   will be created; no JSON dump. A 20–30 panel payload is hundreds
   of lines the user cannot meaningfully review in chat. Call out any
   validation gap the user explicitly accepted.

   > **Summary**: This dashboard tracks [signals] for [scope], with
   > sections [list]. Variables: [list].
   > Dry-run: [N] panels passed. Unvalidated: [none / accepted gaps].
   > Data: [confirmed / pending ingestion by explicit user choice].

2. **Save** Call `signoz_create_dashboard` with the payload.

3. **Report** Tell the user:
   - The created dashboard's id and title.
   - Panel count and section breakdown.
   - Which variables are wired.
   - Two follow-up offers: "Want me to adjust panels, layout, or
     variables?" and "Want me to wire alerts for any of these signals?
     (`signoz-creating-alerts`)".

## Guardrails

- **Strict inputs over guessing** Resource scope is required for custom
  builds. If missing, stop and ask the user (see *Required inputs*
  above). A guessed scope on a shared dashboard is harder to clean up
  than asking.
- **Cover the whole `signoz_list_dashboards` listing** Follow the Step 1
  paging rule; stopping at the first page misses duplicates.
- **Duplicate check first** The user's only two upfront options are
  "modify an existing one" or "create a new one"; never offer
  template-import as a separate top-level choice.
- **Template-first on the create path** Once the user has chosen to
  create, always run `signoz_list_dashboard_templates` before any
  `signoz_create_dashboard` call. If a matching template exists,
  import it via `signoz_import_dashboard` (just inform the user);
  only build from scratch when no template matches.
- **No-data probe is mandatory before save** Run the pre-flight probe
  (Step 3b-i.1 / Step 3b-ii.2) before `signoz_import_dashboard`
  / `signoz_create_dashboard`. A "No data" dashboard is a worse
  outcome than one extra confirmation prompt. Skip only if the user has
  explicitly opted out for this request.
- **Validate custom builds before save** Follow Step 3b-ii.6; never treat a
  dry-run that omits active query semantics as validated.
- **Preview before save on custom builds** Emit the plain-language
  summary before `signoz_create_dashboard` so the human can
  intervene on intent.
- **Prefer OTel attribute names** `service.name` not `service`,
  `host.name` not `host`. Wrong names produce empty panels. Verify the
  exact key (`deployment.environment` vs `deployment.environment.name`,
  for instance) against `signoz_get_field_keys` rather than guessing;
  installs running classic OTel semconv emit the no-`.name` form.
- **No metric guessing** For custom builds, verify metric names with
  `signoz_list_metrics` before authoring. Wrong names produce
  empty panels and the user only finds out later.
- **Valid JSON shapes only** The `signoz_create_dashboard` input schema and
  the Step 3b-ii.3 guides define the shape. Send native JSON, never
  stringified arrays or objects.
- **Scope boundary** This skill creates dashboards. The moment the
  user asks to modify, edit, rearrange, or extend an existing dashboard
  (including immediately after import), hand off to
  `signoz-modifying-dashboards`. Do not call
  `signoz_update_dashboard` or `signoz_patch_dashboard` from this skill.

## Examples

Four canonical flows (template happy path, template choice, duplicate
found, custom build) live in [`references/examples.md`](references/examples.md).
