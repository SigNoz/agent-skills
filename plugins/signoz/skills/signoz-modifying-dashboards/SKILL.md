---
name: signoz-modifying-dashboards
description: >
  Modify an existing SigNoz dashboard: add or remove panels, edit a
  panel's query, threshold, or unit, rename the dashboard, change a
  panel type (graph ↔ table ↔ value), rearrange the layout, add or edit
  variables, or update tags. Make sure to use this skill whenever the
  user says "add a panel to my dashboard", "change the query on this
  panel", "remove the latency widget", "rename my dashboard", "update
  the filters", "rearrange the layout", "add a variable", "change panel
  type from graph to table", or otherwise asks to change something on a
  dashboard that already exists, even if they don't say "modify" or
  "edit" explicitly.
---

# Dashboard Modify

## Prerequisites

This skill calls SigNoz MCP server tools (`signoz_get_dashboard`,
`signoz_patch_dashboard`, `signoz_update_dashboard`, `signoz_list_dashboards`,
`signoz_list_metrics`, `signoz_get_field_keys`, `signoz_get_field_values`,
`signoz_execute_builder_query`).
Before running the workflow, confirm the `signoz_*` tools are available.
If they are not, the SigNoz MCP server is not installed or configured;
run `signoz-mcp-setup` first to initialize or repair the MCP connection. Do not
fall back to raw HTTP calls or hand-edit dashboard JSON without the MCP tools.

## When to use

Use this skill when the user asks to:
- Add, remove, or edit panels on an existing dashboard
- Change a panel's query, title, type, or display settings
- Add, remove, or edit dashboard variables
- Rename or re-describe a dashboard
- Rearrange panel layout or resize panels
- Change a panel type (e.g., graph to table, value to graph)
- Add or modify thresholds on a panel
- Update tags on a dashboard

Do NOT use when:
- User wants to understand what a dashboard shows → `signoz-explaining-dashboards`
- User wants to create a new dashboard → `signoz-creating-dashboards`

## Instructions

### Step 1: Identify the target dashboard

Use an id supplied directly or by dashboard resource context. A name is not an
id; resolve every name-only request:

1. Call `signoz_list_dashboards`, narrowing with the `filter` argument. Read
   `signoz://dashboard/list-filter-guide` before writing a filter longer than
   one free-text word. If a filtered listing returns nothing, list again
   without the filter, from offset 0.
2. Cover the whole listing. Start at offset 0 and keep the same filter and
   sort. While the result's `pagination.hasMore` is true, continue at
   `pagination.nextOffset`; when it is false, stop. When the result has no
   `pagination` object, raise `offset` by the number of dashboards the page
   returned and stop once the offset reaches the reported `total`. Do not
   raise `offset` by `limit`, because a page can hold fewer dashboards than
   `limit`. If a page returns no dashboards before the offset reaches
   `total`, tell the user the listing is incomplete.
3. Match on `spec.display.name`. If multiple dashboards match, present them
   and ask which one to modify; if one matches, use its id.
4. If the matched row has `legacy: true`, stop and tell the user: the
   dashboard is still in the v1 schema, and `signoz_get_dashboard`,
   `signoz_patch_dashboard`, and `signoz_update_dashboard` cannot fetch or
   edit it.

### Step 2: Fetch the current dashboard state

Call `signoz_get_dashboard` with the dashboard id to retrieve its full
configuration. This is **mandatory**: `signoz_update_dashboard` requires the
complete post-update state, and a patch still needs the real panel ids and grid
item indices. Never skip this step.

Read from the response the panel ids in `spec.panels`, each Grid in
`spec.layouts` with its items, the variables, and each panel's query. Each
Grid is one section with its own items.

The fetched `source` is `user`, `system`, or `integration`. Only `source=user`
dashboards are mutable. If it is `system` or `integration`, explain that it is
immutable and stop. The list excludes system rows, but a known system id can
still be fetched. Do not search for a special system discovery tool or attempt
to change `source`.

### Step 3: Plan the modification

Based on the user's request, plan the changes.

**Confirm with the user before applying if:**
- The modification is **destructive**: removing panels, deleting variables,
  replacing an entire query with a different one, changing a query's `signal`
  (e.g., traces → logs), or fundamentally altering what data is shown (changing
  aggregation from p99 to avg, removing groupBy dimensions)
- The request is **ambiguous**: multiple panels could match "the latency panel"
- The change is **large**: restructuring sections, adding many panels at once

**Destructive means data loss or silent behavior change.** Even if the user says
"just do it quickly," a brief confirmation ("I'll remove 'Memory Fragmentation'
permanently. OK?") takes seconds and prevents irreversible mistakes. User urgency
does not override this guardrail.

**Non-destructive changes need no destructive confirmation:** renaming, adding a
panel or variable, changing a unit or panel type, adjusting layout, and adding
thresholds. Variable additions still require the panel-applicability prompt below.

**Compound modifications:** When a request involves multiple changes (e.g., remove a
panel + add a panel + rename), plan all changes against the fetched state and apply
them as a single write: one patch array may carry many ops. Do not apply and
re-fetch between changes.

### Step 4: Pick the write tool and read the guides the change needs

Default to `signoz_patch_dashboard` (RFC 6902): it sends only the changed ops,
so it cannot drop a panel that was never in question. Reach for
`signoz_update_dashboard` (a full replacement merged into the Step 2 state)
only when most of the dashboard changes or `signoz_patch_dashboard` is
unavailable. The Step 5 rules apply to both.

Read these before composing the change:

1. `signoz://dashboard/patch-instructions`: before every
   `signoz_patch_dashboard` call. It has the JSON Pointer paths and the
   multi-op recipes.
2. `signoz://dashboard/instructions`, `signoz://dashboard/widgets-instructions`,
   and `signoz://dashboard/widgets-examples`: before adding a panel, changing
   a panel's kind or query, adding a variable, or changing the layout.
3. `signoz://dashboard/examples`: before a full replacement with
   `signoz_update_dashboard`.
4. The guides for the language of each query you add or change:
   - Query Builder: `signoz://dashboard/query-builder-example`, plus the
     signal's guide: `signoz://metrics-aggregation-guide`,
     `signoz://traces/query-builder-guide`,
     `signoz://logs/query-builder-guide`, or
     `signoz://ai/query-builder-guide` for LLM and AI-agent telemetry.
   - PromQL: `signoz://promql/instructions`.
   - ClickHouse SQL: the schema and example for the signal, one pair of
     `signoz://dashboard/clickhouse-schema-for-metrics` and
     `signoz://dashboard/clickhouse-metrics-example`,
     `signoz://dashboard/clickhouse-schema-for-traces` and
     `signoz://dashboard/clickhouse-traces-example`, or
     `signoz://dashboard/clickhouse-schema-for-logs` and
     `signoz://dashboard/clickhouse-logs-example`.

If this client cannot read `signoz://` resources, take paths and field shapes
from the `signoz_patch_dashboard` and `signoz_update_dashboard` input schemas,
and copy panel, grid-item, and variable shapes from the Step 2 response.

### Step 5: Apply the modification

**Order removals by descending index.** Ops apply in sequence, against the
document as the previous ops left it. When one patch removes several entries
from the same array (grid items, layouts, variables, tags, or a composite's
member queries), each removal reindexes the entries after it, and a stale
index drops the wrong entry or does nothing, because a remove on a missing
path is not an error. Indices planned against the Step 2 state are valid only
for the first removal from each array.

**Modification rules:**

- **Default time range and refresh.** `spec.duration` and
  `spec.refreshInterval` store them, so set them when the user asks. Whether
  the UI applies them depends on the SigNoz version: read each field's
  description in the write tool's input schema and tell the user what it
  says. Do not invent `timeRange`, `defaultTimeRange`, or `refresh` fields.

- **Preserve supported mutable state.** Copy the fetched dashboard, change only
  what the user requested, and compare semantics after MCP normalization. Do not
  drop unrelated panels, variables, grid items, or sections.

- **Preserve panel and grid-item identity.** Every grid item's `content.$ref`
  must name an existing panel, and a panel takes at most one grid item.
  SigNoz accepts a panel with no grid item and does not show it: leave an
  existing unplaced panel as it is, and give each panel you add one grid
  item. The input schemas are authoritative here, although the layout
  checklist in `signoz://dashboard/instructions` asks for one grid item per
  panel. Reuse existing panel ids verbatim: a rename is a display change, not
  a new id.

- **Adding a panel:**
  1. Build the panel with a short, stable id. When the dashboard already holds
     a panel of the target type, start from that panel's JSON in the Step 2
     response instead of composing one (the same diff-and-merge principle the
     update path follows, and the server's own shape is known-valid). Re-point
     every field that identifies the data (aggregation, `groupBy`,
     `filter.expression`, `order`, `legend`, alias, `signal`), then compare
     each of them with the request: SigNoz accepts a well-formed clone with
     one stale field, and that clone can return data in the dry-run. Check the
     clone against the target kind's section in
     `signoz://dashboard/widgets-instructions`. Compose from
     `signoz://dashboard/widgets-examples` only when no panel of that type
     exists.
  2. Pick the Grid the user meant: each section is its own entry in
     `spec.layouts` with its own title and item coordinates, so adding to an
     earlier section touches only that Grid.
  3. Add the panel and its grid item in one patch, with the grid item
     appended to that Grid (`/spec/layouts/<n>/spec/items/-`; the tool
     description's example uses Grid 0). Unless side-by-side placement is
     explicit, place it at `x: 0`, `y: max(y + height)` within that Grid.
- **Removing a panel:** Remove the grid item (0-based index within its Grid) and
  the panel entry together; SigNoz rejects an item left pointing at a removed
  panel. Do not shift the `y` positions of the remaining panels: the
  dashboard UI compacts each section vertically when it renders, so leave all
  other positions unchanged.

- **Editing a panel's query:** Replace the panel's query in place and keep
  all other panel fields intact; never append a second one.

- **Adding or editing text:** Follow the Markdown TextPanel recipes in
  `signoz://dashboard/patch-instructions`. A TextPanel has no query, so skip
  query discovery and the dry-run. Do not invent a row panel; a section is a
  Grid.

- **Changing panel type:** First check that the target kind accepts the
  panel's query kind. The query `plugin` description in the
  `signoz_update_dashboard` input schema and the panel sections of
  `signoz://dashboard/widgets-instructions` say what each kind rejects; pie
  and table panels, for example, reject PromQL. If the query is compatible,
  change the plugin `kind` and the query envelope `kind` together
  (`signoz/TimeSeriesPanel` + `time_series` → `signoz/TablePanel` + `scalar`),
  follow the target kind's shape in `signoz://dashboard/widgets-examples`,
  and keep the query spec and signal. If it is not, tell the user and offer a
  compatible query or panel kind before changing anything.
  `signoz/TimeSeriesPanel` and `signoz/AreaChartPanel` both keep the
  `time_series` query, so switching between them changes only the plugin. Do
  not stack latency, percentiles, or ratios in an area chart.

- **Adding/editing variables:**
  1. For ambiguous or version-sensitive attributes, call `signoz_get_field_keys`
     and optionally `signoz_get_field_values` with the relevant signal and
     `fieldContext=resource`. Trust the discovered key (for example,
     `deployment.environment` versus `deployment.environment.name`).
  2. Show the panel list and ask whether the variable applies to all panels or a
     selected subset.
  3. Add the variable with the "Add a variable" recipe in
     `signoz://dashboard/patch-instructions`. Default to a list variable fed
     by observed attribute values (`signoz/DynamicVariable`), as
     `signoz://dashboard/instructions` recommends.
  4. Reference `$<name>` only in the selected panels' queries, in the form the
     query language takes: a Builder `filter.expression`, the PromQL text, or
     the ClickHouse SQL text. Preserve unselected panels, and dry-run every
     query the variable changed.

- **Rearranging layout / side-by-side placement:** patch the grid items; the
  panels map is untouched. The grid has 12 columns, not 24.
  - Two panels side-by-side: each gets `width: 6`, first at `x: 0`, second at
    `x: 6`, same `y` and `height`.
  - Three panels in a row: `width: 4` at `x: 0`, `x: 4`, `x: 8`.
  - When resizing an existing panel to make room, update its `width` and `x`,
    then place the new panel in the freed space at the same `y`.
  - Common heights: `height: 6` for graphs and tables, `height: 2` to `3` for
    value panels.

**Dry-run modified panels (mandatory).** For every added or changed query-bearing
panel, follow "Dry-run a panel query" in
`signoz://dashboard/widgets-instructions`; if that guide is unreadable, take
the request shape from the `signoz_execute_builder_query` input schema. Send
the panel's saved query spec, never the panel JSON. Dry-run over a short
absolute Unix-ms window, usually the last 30-60 minutes, never the panel's
display range by reflex; apply that section's empty-result and timeout rules
before widening or retrying. Use representative variable values in the
dry-run copy and keep `$var` in saved state.

**Result bounds.** For each added or changed query, follow the result-bounds
rule in `signoz://dashboard/widgets-examples`, which the
`signoz_execute_builder_query` input schema also states: a standalone query
and a formula result carry a `limit` and an `order`, and a formula's base
queries carry neither. A query that a formula with `disabled: true` reads is
still a base query. The panel sections of
`signoz://dashboard/widgets-instructions` override that rule for Top List
(the limit is the row count) and Geo Map (no limit that drops places).
Preserve a deliberate bound already on the panel, such as a smaller list
limit. Remove a limit from a formula input unless it was an intentional
pre-formula top-N. On a time series the limit keeps the top groups ranked
over the whole window, so a short-lived spike can fall outside it. Send the
same `limit` and `order` in the dry-run as in the saved panel, and dry-run
the complete composite payload.

**Dry-run outcomes.** A server or validation error blocks the write: fix the
query and re-run it, or stop and report the error. An unexpected empty result
blocks unless the user has accepted that the telemetry is absent. If the
executor cannot represent a saved field, keep the field, report the panel as
unvalidated, and write only after the user explicitly accepts.

Call `signoz_patch_dashboard` with the id and the op array.

**If the write fails, never resend the same payload.** When the client rejects
the call before sending it (an `InputValidationError`, for example), the
request never reached SigNoz, so an identical retry cannot succeed, and
working out *why* it failed does not license another attempt. Allow at most
two attempts per approach, then change approach: clone-and-re-point rather
than author, or split one patch into several. If two approaches have failed,
stop and report the exact ops and error text to the user instead of trying a
third. This bounds client-side validation failures only; a dry-run timeout is
a server-side condition where retrying over a narrower window is correct.

For a full replacement, `signoz_update_dashboard` takes the merged state **flat**
beside `id`, not nested under a `dashboard` key. Merge into the `data` object
of the Step 2 response; the tool rejects the `{status, data}` envelope. Send
every field of that object that the `signoz_update_dashboard` input schema
accepts, including `image` when the dashboard has one, so a small edit does
not drop authored state. Send the fetched `name` (an immutable machine label)
back unchanged. Leave out the fields the server populates (`createdAt`,
`updatedBy`, `orgId`, `source`, `webUrl`, and lock metadata); refuse non-user
writes instead of sending `source` back.

### Step 6: Report the result

Briefly tell the user what was changed. Offer further modifications if relevant.

## Guardrails

- **Patch first; full state on update**: prefer `signoz_patch_dashboard` for
  targeted edits. When a full replacement is warranted, `signoz_update_dashboard`
  takes the complete dashboard **flat** beside `id`, never nested under a
  `dashboard` key. Always call `signoz_get_dashboard` first, merge into that
  response's `data` object, round-trip `name` unchanged, and never construct
  a payload from scratch.
- **Preserve what you don't change**: Preserve supported mutable semantics for
  panels, variables, and grid items outside the request. Diff-and-merge;
  do not rebuild or promise byte-for-byte equality after MCP normalization.
- **Confirm destructive changes**: Before removing panels, replacing queries, or
  deleting variables, confirm with the user, even if they say "just do it" or
  express urgency. Additions, renames, type changes, and variable additions do not
  need confirmation.
- **Validate changed queries** Follow the mandatory dry-run step above before
  the write.
- **Valid JSON only**: Follow the write tool's input schema and the guides
  named in Step 4. Never generate malformed queries or layouts.
- **OTel attribute names**: Use `service.name` not `service` and `host.name` not
  `host`, but discover version-sensitive keys such as `deployment.environment`
  versus `deployment.environment.name` instead of forcing one form.
- **No metric guessing**: If adding or changing queries and you are not sure what
  metrics are available, ask the user or call `signoz_list_metrics` to discover
  available metrics. Wrong metric names produce empty panels.
- **Cover the whole dashboard listing**: When searching for a dashboard by
  name, follow the Step 1 paging rule to the end before concluding a
  dashboard does not exist.
- **Identifiers**: Give new panels short, stable ids and reference them from the
  grid item's `content.$ref`; keep each variable's `spec.name` identical to the
  `$handle` its queries use, and keep query names such as `A`, `B`, and `F1`
  stable.
- **Perses and source only**: Use canonical v6 Perses paths and fields. Never
  persist legacy `widgets`, `panelMap`, `panelTypes`, `queryData`,
  `selectedLogFields`, or `selectedTracesFields`. Never write a non-user
  dashboard.
- **Real dashboard IDs only**: Never send a sentinel such as `"unused"` as a
  dashboard id. Resolve it through `signoz_list_dashboards` and
  `signoz_get_dashboard` first.
- **Scope boundary**: This skill modifies existing dashboards. Hand new-dashboard
  requests to `signoz-creating-dashboards`.

## Examples

**User:** "Add an error rate panel to my Redis dashboard"

**Agent:**
1. Calls `signoz_list_dashboards` with `filter="redis"`; finds "Redis Overview"
   dashboard with id `abc-123`.
2. Calls `signoz_get_dashboard` with id `abc-123`; gets full configuration with
   8 existing panels across two Grid sections.
3. Calls `signoz_list_metrics` to find available Redis error metrics.
4. Creates a new timeseries panel (a `signoz/CompositeQuery` holding the two
   disabled base queries and the error-rate formula) and a grid item for it below
   the last item in the Overview Grid.
5. Dry-runs the new panel with `signoz_execute_builder_query`; fixes any error or
   unexpected empty result.
6. Calls `signoz_patch_dashboard` with two ops (`add /spec/panels/error-rate` and
   `add /spec/layouts/0/spec/items/-`) rather than re-sending all 9 panels.
7. Reports: "Added an 'Error Rate' timeseries panel to your Redis Overview dashboard
   under the Overview section. Want me to adjust anything?"

---

**User:** "Change the latency panel from a graph to a table on my API dashboard"

**Agent:**
1. Resolves "API Monitoring" through a filtered `signoz_list_dashboards`, then calls
   `signoz_get_dashboard` with its id.
2. Finds the panel titled "Request Latency"; if multiple panels could match,
   confirms with user: "I found 'Request Latency'. Convert that one to a table?"
3. Confirms that a table accepts the panel's Builder query (it would reject
   PromQL), then changes the plugin `kind` to `signoz/TablePanel` and the
   query `kind` to `scalar`, matches the table shape in
   `signoz://dashboard/widgets-examples`, and keeps the query intact.
4. Dry-runs the table execution shape because panel type affects request shape.
5. Calls `signoz_patch_dashboard` with replace ops on that panel's plugin and
   query kind.
6. Reports: "Changed 'Request Latency' from a graph to a table. Want me to adjust
   column widths or add column units?"

---

**User:** "Remove the CPU panel and rename the dashboard to 'Service Health'"

**Agent:**
1. Fetches the dashboard via `signoz_get_dashboard`.
2. Finds the "CPU Usage" panel. Confirms: "I'll remove the 'CPU Usage' panel and
   rename the dashboard to 'Service Health'. Proceed?" (Removal is destructive;
   always confirm.)
3. User confirms.
4. Removes the panel entry and its grid item. Leaves all other panel positions
   unchanged (the dashboard UI compacts each section when it renders). Renames via
   `/spec/display/name`, never the immutable top-level `name`.
5. Calls `signoz_patch_dashboard` with all three ops in one array.
6. Reports: "Removed the 'CPU Usage' panel and renamed the dashboard to 'Service
   Health'. Anything else to adjust?"
