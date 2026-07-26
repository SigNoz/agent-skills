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
`signoz_patch_dashboard`, `signoz_update_dashboard`, `signoz_list_dashboards`,
`signoz_list_metrics`, `signoz_get_field_keys`, `signoz_get_field_values`,
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

Use an id supplied directly or by dashboard resource context. A name is not an
ID: resolve every name-only request with `signoz_list_dashboards`, narrowing with
the `filter` argument (see `signoz://dashboard/list-filter-guide`) and paging by
`offset` until you have covered `total`. Match on `spec.display.name`. If multiple
dashboards match, present them and ask which one to modify; if one matches, use
its id.

### Step 2: Fetch the current dashboard state

Call `signoz_get_dashboard` with the dashboard id to retrieve its full
configuration. This is **mandatory** — `signoz_update_dashboard` requires the
complete post-update state, and a patch still needs the real panel ids and grid
item indices. Never skip this step.

Examine the response to understand:
- Current panels and their ids (`spec.panels` is a map keyed by panel id)
- Current grid item positions (x, y, width, height in the 12-column grid)
- Current variables
- Current query on each panel (exactly one per panel)
- The `spec.layouts` structure — one Grid per section, each with its own items

### Step 3: Plan the modification

Based on the user's request, plan the changes.

**Confirm with the user before applying if:**
- The modification is **destructive** — removing panels, deleting variables,
  replacing an entire query with a different one, changing a query's `signal`
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
them as a single write — one patch array may carry many ops. Do not apply and
re-fetch between changes.

### Step 4: Apply the modification

**Pick the write tool first.** Default to `signoz_patch_dashboard` (RFC 6902):
it sends only the changed ops, so it cannot drop a panel that was never in
question. Read `signoz://dashboard/patch-instructions` for the JSON Pointer
paths. Reach for `signoz_update_dashboard` — a full replacement merged into the
Step 2 state — only when most of the dashboard changes. The rules below apply to
both; each names its patch path.

**Ops apply in sequence, against the document as the previous ops left it.** When
one patch removes several entries from the same array — grid items, layouts,
variables, tags, or a composite's member queries — order those removals by
**descending index**. Otherwise each removal reindexes the entries after it, and a
stale index quietly drops the wrong entry or no-ops (remove on a missing path is
not an error). Indices planned against the Step 2 state are only valid for the
first removal from each array.

**Modification rules:**

- **Time range and refresh are viewer controls.** Dashboard payloads do
  not persist a default time range or refresh interval. If asked to change one,
  explain that panels follow the viewer-selected global range; do not invent
  `timeRange`, `defaultTimeRange`, or `refresh` fields.

- **Preserve supported mutable state.** Copy the fetched dashboard, change only
  what the user requested, and compare semantics after MCP normalization. Do not
  drop unrelated panels, variables, grid items, or sections.

- **Preserve panel/grid-item identity.** Every panel id in `spec.panels` needs
  exactly one grid item whose `content.$ref` names it; add or remove both
  together. Reuse existing panel ids verbatim — a rename is a display change,
  not a new id.

- **Read schemas before every write.** Read all required and applicable
  conditional resources named by the write tool. For Query Builder,
  also read `signoz://metrics-aggregation-guide`,
  `signoz://traces/query-builder-guide`, or
  `signoz://logs/query-builder-guide` for the signal. MCP is the source of truth.

- **Adding a panel:**
  1. Build the panel with a short, stable id and `add` it at
     `/spec/panels/<id>`. When the dashboard already holds a panel of the
     target type, start from that panel's JSON in the Step 2 response instead
     of composing one — the same diff-and-merge principle the update path
     follows, and the server's own shape is known-valid. Re-point every field
     that identifies the data (aggregation, `groupBy`, `filter.expression`,
     `order`, `legend`, alias, `signal`); a clone with one stale field is
     well-formed and will be accepted, so the mandatory dry-run below is what
     catches it. Compose from `signoz://dashboard/widgets-examples` only when
     no panel of that type exists.
  2. Pick the Grid the user meant: sections are separate entries in
     `spec.layouts`, each with its own `spec.display.title` and its own item
     coordinates, so adding to an earlier section touches only that Grid.
  3. `add` a grid item at `/spec/layouts/<n>/spec/items/-` whose `content.$ref`
     is `#/spec/panels/<id>`, obeying the bounds below. Unless side-by-side
     placement is explicit, place it at `x: 0`, `y: max(y + height)` within that
     Grid. A panel with no grid item is accepted and never renders.
- **Removing a panel:** Remove the grid item (0-based index within its Grid) and
  the `/spec/panels/<id>` entry together; an item left pointing at a removed panel is rejected.
  **Do not** try to auto-compact or shift `y` positions of remaining panels — the
  SigNoz frontend grid engine handles gap-closing automatically. Simply remove the
  two references (panel entry, grid item) and leave all other positions
  unchanged.

- **Editing a panel's query:** Replace the query at `/spec/panels/<id>/spec/queries/0`
  and keep all other panel fields intact — never append a second one, since a
  panel holds exactly one query.

- **Changing panel type:** Update the plugin `kind` and the query envelope `kind`
  together (`signoz/TimeSeriesPanel` + `time_series` → `signoz/TablePanel` +
  `scalar`): follow the target type's complete shape in `widgets-examples`. Preserve the
  existing query and signal; change only visualization-specific fields.

- **Adding/editing variables:**
  1. For ambiguous or version-sensitive attributes, call `signoz_get_field_keys`
     and optionally `signoz_get_field_values` with the relevant signal and
     `fieldContext=resource`. Trust the discovered key (for example,
     `deployment.environment` versus `deployment.environment.name`).
  2. Show the panel list and ask whether the variable applies to all panels or a
     selected subset.
  3. Use a `ListVariable` with a `signoz/DynamicVariable` plugin for an
     attribute-backed dropdown, appended at `/spec/variables/-`. Its `spec.name`
     is the `$handle`; `plugin.spec.name` is the attribute key.
  4. Add `$<name>` only to the selected panels' `filter.expression`, preserve
     unselected panels, and dry-run every query changed by the variable.

- **Rearranging layout / side-by-side placement:** patch the grid items at
  `/spec/layouts/<n>/spec/items/<i>`; the panels map is untouched.
  - SigNoz uses a **12-column grid**, never 24: every entry must satisfy
    `0 <= x < 12`, `1 <= width <= 12`, and `x + width <= 12`.
  - Two panels side-by-side: each gets `width: 6`, first at `x: 0`, second at
    `x: 6`, same `y` and `height`.
  - Three panels in a row: `width: 4` at `x: 0`, `x: 4`, `x: 8`.
  - When resizing an existing panel to make room, update its `width` and `x`,
    then place the new panel in the freed space at the same `y`.
  - Common heights: `height: 6` for graphs/tables, `height: 2`–`3` for value
    panels.

**Dry-run modified panels (mandatory).** For every added or changed query-bearing
panel, read the compact
[`dashboard-to-query-builder-v5` reference](./references/dashboard-to-query-builder-v5.md).
The panel already stores the execution spec, so lift it into the outer envelope and
call `signoz_execute_builder_query` with that payload. Dry-run over a short
absolute Unix-ms window — usually the last 30-60 minutes, never the panel's
display range by reflex; apply the reference's dry-run hygiene rules before
widening or retrying after a timeout. Use representative variable values in the
dry-run copy and keep `$var` in saved state.

Preserve or add explicit result bounds on every changed builder query/formula:
the saved spec carries a positive `limit` plus non-empty `order`, and the dry-run
sends those same values unchanged. List
and trace-request panels default to 100 rows ordered by timestamp desc (raw logs
also id desc), but preserve a deliberate smaller positive list limit.
Standalone aggregate queries and formula outputs default to
100 groups. Every base query referenced by a formula uses 10000 because base
limits are applied before formula evaluation; raise an existing smaller bound
unless it was an intentional pre-formula top-N selection. Find the complete
base-query set by inspecting every formula expression, including formulas with
`disabled: true`, and following formula references to all `builder_query`
leaves. This dependency walk chooses bounds only; it does not establish
deterministic formula-to-formula evaluation order, so dry-run the complete
composite payload. Base queries order by their primary aggregation and formulas
by `__result`, in the saved panel and the dry-run alike. For time series, this
top-N is chosen over the whole window, so a short-lived local spike can be
omitted. Narrow filters/grouping if formula-input cardinality can exceed 10000.

If the reference's safety gate finds an unsupported execution field, report the
panel as unvalidated and continue only after explicit acceptance. Server or
validation errors and unexpected empty results block unless explicitly accepted.

Call `signoz_patch_dashboard` with the id and an op array; the result is
validated after the ops apply, and locked dashboards are rejected:

```text
signoz_patch_dashboard({
  "id": "<dashboard-id>",
  "patch": [{"op": "replace", "path": "/spec/display/name", "value": "New title"}]
})
```

**If the write fails, never resend the same payload.** A client-side
`InputValidationError` never reached SigNoz, so an identical retry cannot
succeed — and working out *why* it failed does not license another attempt.
That reasoning is what turns two failures into twenty. Allow at most two
attempts per approach, then change approach: clone-and-re-point rather than
author, or split one patch into several. If two approaches have failed, stop
and report the exact ops and error text to the user instead of trying a third.
This bounds client-side validation failures only — a dry-run timeout is a
server-side condition where retrying over a narrower window is correct.

For a full replacement, `signoz_update_dashboard` takes the merged state **flat**
beside `id`, not nested under a `dashboard` key. Merge into the `data` object of the
Step 2 response — passing the `{status, data}` envelope itself is rejected. Send the
fetched `name` — an immutable machine label — back unchanged, and drop the read-only
fields the GET returns (`createdAt`, `updatedBy`, `orgId`, `webUrl`, and friends):

```text
signoz_update_dashboard({
  "id": "<dashboard-id>",
  "schemaVersion": "v6",
  "name": "<the fetched name, unchanged>",
  "tags": [...],
  "spec": <complete merged spec from signoz_get_dashboard>
})
```

### Step 5: Report the result

Briefly tell the user what was changed. Offer further modifications if relevant.

## Guardrails

- **Patch first; full state on update**: prefer `signoz_patch_dashboard` for
  targeted edits. When a full replacement is warranted, `signoz_update_dashboard`
  takes the complete dashboard **flat** beside `id` (`schemaVersion`, `name`,
  `tags`, `spec`) — never nested under a `dashboard` key. Always call
  `signoz_get_dashboard` first, merge into that response's `data` object, round-trip `name`
  unchanged, and never construct a payload from scratch.
- **Preserve what you don't change**: Preserve supported mutable semantics for
  panels, variables, and grid items outside the request. Diff-and-merge;
  do not rebuild or promise byte-for-byte equality after MCP normalization.
- **Confirm destructive changes**: Before removing panels, replacing queries, or
  deleting variables, confirm with the user — even if they say "just do it" or
  express urgency. Additions, renames, type changes, and variable additions do not
  need confirmation.
- **Validate changed queries** Follow the mandatory dry-run step above before
  the write.
- **Valid JSON only**: Follow the schema documented in the
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
  page through the whole `signoz_list_dashboards` result before concluding a
  dashboard does not exist.
- **Identifiers**: Give new panels short, stable ids and reference them from the
  grid item's `content.$ref`; keep each variable's `spec.name` identical to the
  `$handle` its queries use, and keep query names such as `A`, `B`, and `F1`
  stable.
- **Real dashboard IDs only**: Never send a sentinel such as `"unused"` as a
  dashboard id. Resolve it through `signoz_list_dashboards` and
  `signoz_get_dashboard` first.
- **Scope boundary**: This skill modifies existing dashboards. Hand new-dashboard
  requests to `signoz-creating-dashboards`.

## Examples

**User:** "Add an error rate panel to my Redis dashboard"

**Agent:**
1. Calls `signoz_list_dashboards` with `filter="redis"` — finds "Redis Overview"
   dashboard with id `abc-123`.
2. Calls `signoz_get_dashboard` with id `abc-123` — gets full configuration with
   8 existing panels across two Grid sections.
3. Calls `signoz_list_metrics` to find available Redis error metrics.
4. Creates a new timeseries panel (a `signoz/CompositeQuery` holding the two
   disabled base queries and the error-rate formula) and a grid item for it below
   the last item in the Overview Grid.
5. Dry-runs the new panel with `signoz_execute_builder_query`; fixes any error or
   unexpected empty result.
6. Calls `signoz_patch_dashboard` with two ops — `add /spec/panels/error-rate` and
   `add /spec/layouts/0/spec/items/-` — rather than re-sending all 9 panels.
7. Reports: "Added an 'Error Rate' timeseries panel to your Redis Overview dashboard
   under the Overview section. Want me to adjust anything?"

---

**User:** "Change the latency panel from a graph to a table on my API dashboard"

**Agent:**
1. Resolves "API Monitoring" through a filtered `signoz_list_dashboards`, then calls
   `signoz_get_dashboard` with its id.
2. Finds the panel titled "Request Latency" — if multiple panels could match,
   confirms with user: "I found 'Request Latency'. Convert that one to a table?"
3. Changes the plugin `kind` to `signoz/TablePanel` and the query `kind` to
   `scalar`, matches the table shape in `widgets-examples`, and keeps the query
   intact.
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
   rename the dashboard to 'Service Health'. Proceed?" (Removal is destructive —
   always confirm.)
3. User confirms.
4. Removes the panel entry and its grid item. Leaves all other panel positions
   unchanged (the frontend grid closes gaps automatically). Renames via
   `/spec/display/name`, never the immutable top-level `name`.
5. Calls `signoz_patch_dashboard` with all three ops in one array.
6. Reports: "Removed the 'CPU Usage' panel and renamed the dashboard to 'Service
   Health'. Anything else to adjust?"
