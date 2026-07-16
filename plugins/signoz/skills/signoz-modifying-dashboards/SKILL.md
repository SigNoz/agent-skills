---
name: signoz-modifying-dashboards
description: >
  Modify an existing SigNoz dashboard — add or remove panels, edit a
  panel's query, threshold, or unit, rename the dashboard, change a
  panel type (graph ↔ table ↔ value), rearrange the layout, add or edit
  variables, or update tags. Make sure to use this skill whenever the
  user says "add a panel to my dashboard", "change the query on this
  panel", "remove the latency widget", "rename my dashboard", "update
  the filters", "rearrange the layout", "add a variable", "change panel
  type from graph to table", or otherwise asks to change something on a
  dashboard that already exists — even if they don't say "modify" or
  "edit" explicitly.
---

# Dashboard Modify

## Prerequisites

This skill calls SigNoz MCP server tools (`signoz_get_dashboard`,
`signoz_update_dashboard`, `signoz_list_dashboards`, `signoz_list_metrics`,
`signoz_get_field_keys`, `signoz_get_field_values`,
`signoz_execute_builder_query`).
Before running the workflow, confirm the `signoz_*` tools are available.
If they are not, the SigNoz MCP server is not installed or configured —
run `signoz-mcp-setup` first to initialize or repair the MCP connection. Do not
fall back to raw HTTP calls or hand-edit dashboard JSON without the MCP tools.

## When to use

Use this skill when the user asks to:
- Add, remove, or edit panels/widgets on an existing dashboard
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

Use a UUID supplied directly or by dashboard resource context. A name is not an
ID: resolve every name-only request with `signoz_list_dashboards`, paginating via
`pagination.nextOffset` while `pagination.hasMore` is true. If multiple dashboards
match, present them and ask which one to modify; if one matches, use its UUID.

### Step 2: Fetch the current dashboard state

Call `signoz_get_dashboard` with the dashboard UUID to retrieve its full
configuration. This is **mandatory** — `signoz_update_dashboard` requires the
complete post-update state, not a partial patch. Never skip this step.

Examine the response to understand:
- Current widgets and their IDs
- Current layout positions (x, y, w, h in the 12-column grid)
- Current variables
- Current queries on each panel
- The `panelMap` structure (row-to-child mappings)

### Step 3: Plan the modification

Based on the user's request, plan the changes.

**Confirm with the user before applying if:**
- The modification is **destructive** — removing panels, deleting variables,
  replacing an entire query with a different one, changing a panel's `dataSource`
  (e.g., traces → logs), or fundamentally altering what data is shown (changing
  aggregation from p99 to avg, removing groupBy dimensions)
- The request is **ambiguous** — multiple panels could match "the latency panel"
- The change is **large** — restructuring sections, adding many panels at once

**Destructive means data loss or silent behavior change.** Even if the user says
"just do it quickly," a brief confirmation ("I'll remove 'Memory Fragmentation'
permanently — OK?") takes seconds and prevents irreversible mistakes. User urgency
does not override this guardrail.

**Non-destructive changes need no destructive confirmation:** renaming, adding a
panel or variable, changing a unit or panel type, adjusting layout, and adding
thresholds. Variable additions still require the panel-applicability prompt below.

**Compound modifications:** When a request involves multiple changes (e.g., remove a
panel + add a panel + rename), plan all changes against the fetched state and apply
them as a single update. Do not apply and re-fetch between changes.

### Step 4: Apply the modification

Merge the planned changes into the full dashboard JSON from Step 2.

**Modification rules:**

- **Time range and refresh are viewer controls.** Dashboard update payloads do
  not persist a default time range or refresh interval. If asked to change one,
  explain that panels follow the viewer-selected global range; do not invent
  `timeRange`, `defaultTimeRange`, or `refresh` fields.

- **Preserve supported mutable state.** Copy the fetched dashboard, change only
  what the user requested, and compare semantics after MCP normalization. Do not
  drop unrelated widgets, variables, layout items, or panelMap entries.

- **Preserve widget/layout identity.** Keep non-row widget/layout IDs bijective;
  add/remove both entries together. Row widgets need no layout entry; preserve
  matching row layout entries when present. Reuse widget IDs verbatim. Strip any
  literal `"__dropping-elem__"` widget/layout id leaked by the UI drag state.

- **Read schemas before every update.** Read all required and applicable
  conditional resources named by `signoz_update_dashboard`. For Query Builder,
  also read `signoz://metrics-aggregation-guide`,
  `signoz://traces/query-builder-guide`, or
  `signoz://logs/query-builder-guide` for the signal. MCP is the source of truth.

- **Adding a panel:**
  1. Build the widget from `signoz://dashboard/widgets-examples`, with a UUID for
     its `id`.
  2. Detect rows from `widgets[].panelTypes == "row"`. Unless side-by-side
     placement is explicit, append at `x: 0`, `y: max(y + h)` only when rowless
     or targeting the final row. For an earlier row, insert the widget and layout
     before the next row at `x: 0`, `y: <next row's old y>` (the target row's
     current bottom), then shift that row and all later top-level and `panelMap`
     `y` positions down by the new panel's height.
  3. Add a layout entry whose `i` matches the widget ID and obeys the bounds below.
     If rows exist, add it to the intended row's `panelMap[rowId].widgets`,
     creating that entry when absent. An empty `panelMap` does not prove the
     dashboard is rowless.
- **Removing a panel:** Remove the widget from `widgets`, its entry from `layout`,
  and its entry from the parent row's `panelMap.widgets` (if it exists in panelMap).
  **Do not** try to auto-compact or shift `y` positions of remaining panels — the
  SigNoz frontend grid engine handles gap-closing automatically. Simply remove the
  three references (widget, layout, panelMap entry) and leave all other positions
  unchanged.

- **Editing a panel's query:** Replace the query object on the target widget and
  keep all other widget fields intact.

- **Changing panel type:** Update `panelTypes` and handle type-specific fields:
  follow the target type's complete shape in `widgets-examples`. Preserve the
  existing query and data source; change only visualization-specific fields.

- **Adding/editing variables:**
  1. For ambiguous or version-sensitive attributes, call `signoz_get_field_keys`
     and optionally `signoz_get_field_values` with the relevant signal and
     `fieldContext=resource`. Trust the discovered key (for example,
     `deployment.environment` versus `deployment.environment.name`).
  2. Show the panel list and ask whether the variable applies to all panels or a
     selected subset.
  3. Use a DYNAMIC variable for an attribute-backed dropdown, with a UUID `id`.
     Keep its human-readable variables-map key and `name` identical.
  4. Add `$<key>` only to the selected panel filters, preserve unselected panels,
     and dry-run every query changed by the variable.

- **Rearranging layout / side-by-side placement:**
  - SigNoz uses a **12-column grid**, never 24: every entry must satisfy
    `0 <= x < 12`, `1 <= w <= 12`, and `x + w <= 12`.
  - Two panels side-by-side: each gets `w: 6`, first at `x: 0`, second at `x: 6`,
    same `y` and `h`.
  - Three panels in a row: `w: 4` at `x: 0`, `x: 4`, `x: 8`.
  - When resizing an existing panel to make room, update its `w` and `x`, then
    place the new panel in the freed space at the same `y`.
  - Common heights: `h: 6` for graphs/tables, `h: 2`–`h: 3` for value panels,
    `h: 1` for row headers.
  - **Keep panelMap in sync**: whenever you change `x`, `y`, `w`, or `h` in the
    top-level `layout` array, apply the same change to the matching entry in
    `panelMap[rowId].widgets`. These are duplicated and must stay consistent.

**Dry-run modified panels (mandatory).** For every added or changed query-bearing
panel, read the compact
[`dashboard-to-query-builder-v5` reference](./references/dashboard-to-query-builder-v5.md).
When the execution schema can represent the panel, call
`signoz_execute_builder_query` with the translated payload. Dry-run over a short
absolute Unix-ms window — usually the last 30-60 minutes, never the panel's
display range by reflex; apply the reference's dry-run hygiene rules before
widening or retrying after a timeout. Use representative variable values and
keep editor aliases unchanged in saved state.

Preserve or add explicit result bounds on every changed builder query/formula:
dashboard state uses positive `limit` plus editor-model `orderBy`; the dry-run
translation uses the same positive `limit` plus Query Builder v5 `order`. List
and trace-request panels default to 100 rows ordered by timestamp desc (raw logs
also id desc), but preserve a deliberate smaller positive list limit such as
the panel pageSize. Standalone aggregate queries and formula outputs default to
100 groups. Every base query referenced by a formula uses 10000 because base
limits are applied before formula evaluation; raise an existing smaller bound
unless it was an intentional pre-formula top-N selection. Find the complete
base-query set by inspecting every formula expression, including formulas with
`disabled: true`, and following formula references to all `builder_query`
leaves. This dependency walk chooses bounds only; it does not establish
deterministic formula-to-formula evaluation order, so dry-run the complete
composite payload. Saved base queries order by their primary aggregation and
saved formulas by `__result`; during dry-run translation, log/trace base queries
retain the primary aggregation key, metric base queries translate it to
`__result`, and formulas use `__result`. For time series, this top-N is chosen
over the whole window, so a short-lived local spike can be omitted. Narrow
filters/grouping if formula-input cardinality can exceed 10000.

If the reference's safety gate finds an unsupported execution field, report the
panel as unvalidated and continue only after explicit acceptance. Server or
validation errors and unexpected empty results block unless explicitly accepted.
Skip row panels and validate their shape against
`signoz://dashboard/widgets-examples`.

Call `signoz_update_dashboard` with this exact outer wrapper, where `dashboard`
is the **complete** modified dashboard object, not a partial patch:

```text
signoz_update_dashboard({
  "id": "<dashboard-uuid>",
  "dashboard": <complete merged object from signoz_get_dashboard>
})
```

### Step 5: Report the result

Briefly tell the user what was changed. Offer further modifications if relevant.

## Guardrails

- **Full state on update**: `signoz_update_dashboard` requires the complete
  dashboard JSON nested under `{id, dashboard}` (not a partial patch). Always call
  `signoz_get_dashboard` first, merge into that full object, and place the result
  under `dashboard`. Never flatten dashboard fields beside `id` or construct an
  update payload from scratch.
- **Preserve what you don't change**: Preserve supported mutable semantics for
  widgets, variables, layout, and panelMap outside the request. Diff-and-merge;
  do not rebuild or promise byte-for-byte equality after MCP normalization.
- **Confirm destructive changes**: Before removing panels, replacing queries, or
  deleting variables, confirm with the user — even if they say "just do it" or
  express urgency. Additions, renames, type changes, and variable additions do not
  need confirmation.
- **Validate changed queries** Follow the mandatory dry-run step above before
  update.
- **Valid JSON only**: Follow the v5 schema documented in the
  `signoz://dashboard/*` MCP resources (`instructions`, `widgets-instructions`,
  `widgets-examples`, `query-builder-example`). Never generate malformed queries
  or layouts.
- **OTel attribute names**: Use `service.name` not `service` and `host.name` not
  `host`, but discover version-sensitive keys such as `deployment.environment`
  versus `deployment.environment.name` instead of forcing one form.
- **No metric guessing**: If adding or changing queries and you are not sure what
  metrics are available, ask the user or call `signoz_list_metrics` to discover
  available metrics. Wrong metric names produce empty panels.
- **Paginate dashboard listing**: When searching for a dashboard by name, always
  paginate through all pages of `signoz_list_dashboards` before concluding a
  dashboard does not exist.
- **Identifiers**: Use UUIDs for new widget and variable IDs. Reuse the widget ID
  as `layout.i`; keep each variable map key identical to its human-readable `name`,
  and keep query names such as `A`, `B`, and `F1` stable.
- **Real dashboard IDs only**: Never send a sentinel such as `"unused"` as a
  dashboard UUID. Resolve it through `signoz_list_dashboards` and
  `signoz_get_dashboard` first.
- **Scope boundary**: This skill modifies existing dashboards. Hand new-dashboard
  requests to `signoz-creating-dashboards`.

## Examples

**User:** "Add an error rate panel to my Redis dashboard"

**Agent:**
1. Calls `signoz_list_dashboards` (paginates all pages) — finds "Redis Overview"
   dashboard with UUID `abc-123`.
2. Calls `signoz_get_dashboard` with UUID `abc-123` — gets full configuration with
   8 existing panels.
3. Calls `signoz_list_metrics` to find available Redis error metrics.
4. Creates a new graph widget (with UUID, all required fields, and a formula query
   for error rate), appends it below the current layout, and adds it to the
   appropriate row's `panelMap`.
5. Dry-runs the new panel with `signoz_execute_builder_query`; fixes any error or
   unexpected empty result.
6. Calls `signoz_update_dashboard` with
   `{id: "abc-123", dashboard: <full modified JSON>}` (all 9 panels).
7. Reports: "Added an 'Error Rate' graph panel to your Redis Overview dashboard
   under the Overview section. Want me to adjust anything?"

---

**User:** "Change the latency panel from a graph to a table on my API dashboard"

**Agent:**
1. Resolves "API Monitoring" through paginated `signoz_list_dashboards`, then calls
   `signoz_get_dashboard` with its UUID.
2. Finds the panel titled "Request Latency" — if multiple panels could match,
   confirms with user: "I found 'Request Latency'. Convert that one to a table?"
3. Changes `panelTypes` from `"graph"` to `"table"`, matches the table shape in
   `widgets-examples`, and keeps the query intact.
4. Dry-runs the table execution shape because panel type affects request shape.
5. Calls `signoz_update_dashboard` with `{id, dashboard: <full modified JSON>}`.
6. Reports: "Changed 'Request Latency' from a graph to a table. Want me to adjust
   column widths or add column units?"

---

**User:** "Remove the CPU panel and rename the dashboard to 'Service Health'"

**Agent:**
1. Fetches the dashboard via `signoz_get_dashboard`.
2. Finds the "CPU Usage" panel. Confirms: "I'll remove the 'CPU Usage' panel and
   rename the dashboard to 'Service Health'. Proceed?" (Removal is destructive —
   always confirm.)
3. User confirms.
4. Removes the widget from `widgets`, its layout entry, and its panelMap reference.
   Leaves all other panel positions unchanged (the frontend grid closes gaps
   automatically). Updates `title` to "Service Health".
5. Calls `signoz_update_dashboard` with `{id, dashboard: <full modified JSON>}`.
6. Reports: "Removed the 'CPU Usage' panel and renamed the dashboard to 'Service
   Health'. Anything else to adjust?"
