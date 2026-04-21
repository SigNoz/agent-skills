---
name: dashboard-modify
description: >
  Trigger when the user wants to modify, update, or change an existing dashboard.
  Includes requests like "add a panel to my dashboard", "change the query on this
  panel", "remove the latency widget", "rename my dashboard", "update the filters",
  "rearrange the layout", "add a variable", "change panel type from graph to table".
---

# Dashboard Modify

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
- User wants to create a new dashboard from scratch → `dashboard-create`
- User wants to understand what a dashboard shows → `dashboard-explain`
- User wants to query data without modifying a dashboard → `query-generate`

## Instructions

### Step 1: Identify the target dashboard

Determine which dashboard the user wants to modify. If the user provides a
dashboard name, UUID, or it is clear from context (e.g., an @mention or auto-context
providing a dashboard resource), use that.

If the target dashboard is ambiguous:
1. Call `signoz_list_dashboards` to list existing dashboards. **Paginate through
   all pages** — check `pagination.hasMore` in the response. If `hasMore` is true,
   call again with `offset` set to `pagination.nextOffset` and repeat until all
   pages are exhausted. Never stop at the first page.
2. Present matching candidates to the user and ask which one to modify.

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

**Non-destructive changes proceed directly:** renaming, adding a single panel,
changing a unit, adding a variable, changing panel type (the query is preserved),
adjusting layout, adding thresholds.

**Compound modifications:** When a request involves multiple changes (e.g., remove a
panel + add a panel + rename), plan all changes against the fetched state and apply
them as a single update. Do not apply and re-fetch between changes.

### Step 4: Apply the modification

Merge the planned changes into the full dashboard JSON from Step 2.

**Modification rules:**

- **Preserve everything you are not changing.** Copy the entire dashboard object
  and only modify the specific fields the user asked about. Do not drop widgets,
  variables, layout items, or panelMap entries that are not part of the change.

- **Adding a panel:**
  1. Create a new widget with a UUID for its `id` (use `crypto.randomUUID()` format).
  2. Include **all** required widget fields: `id`, `title`, `description`,
     `panelTypes`, `query`, `opacity` ("1"), `nullZeroValues` ("zero"),
     `timePreferance` ("GLOBAL_TIME" — note the deliberate misspelling),
     `stepSize` (60), `yAxisUnit`, `isStacked` (false), `fillSpans` (false),
     `isLogScale` (false), `mergeAllActiveQueries` (false), `thresholds` ([]),
     `softMin` (0), `softMax` (0), `legendPosition` ("bottom"), `columnUnits` ({}),
     `customLegendColors` ({}), `selectedLogFields` ([]), `selectedTracesFields`
     ([]), `contextLinks` ({"linksData": []}).
  3. Add a layout entry with `i` matching the widget ID, and appropriate `x`, `y`,
     `w`, `h` values in the 12-column grid.
  4. If the dashboard uses rows, add the panel's layout to the appropriate row's
     `panelMap[rowId].widgets` array. If the dashboard has no rows (empty
     `panelMap`), skip panelMap — the panel lives at the top level.
  5. For query construction, read the `signoz://dashboard/query-builder-example`
     MCP resource for the v5 builder query format. Use the signal-specific
     resources as needed (`signoz://dashboard/promql-example`,
     `signoz://dashboard/clickhouse-*`, `signoz://traces/query-builder-guide`).

- **Removing a panel:** Remove the widget from `widgets`, its entry from `layout`,
  and its entry from the parent row's `panelMap.widgets` (if it exists in panelMap).
  **Do not** try to auto-compact or shift `y` positions of remaining panels — the
  SigNoz frontend grid engine handles gap-closing automatically. Simply remove the
  three references (widget, layout, panelMap entry) and leave all other positions
  unchanged.

- **Editing a panel's query:** Replace the query object on the target widget. Keep
  all other widget fields intact.

- **Changing panel type:** Update `panelTypes` and handle type-specific fields:
  - `graph` → `table`: add `columnUnits` ({}) and `columnWidths` ({}) if missing.
    Graph-only fields like `isStacked`, `fillSpans`, `isLogScale` become inert but
    are harmless to leave.
  - `graph`/`table` → `histogram`: add `bucketCount` (30) and `bucketWidth` (0).
  - Any → `list` (logs): add `selectedLogFields` array.
  - Any → `list` (traces): add `selectedTracesFields` array.
  - Keep the existing query intact — the data source and query are independent of
    the visualization type.

- **Adding/editing variables:** Add or update entries in the `variables` map. Use
  OTel attribute names for the underlying attribute (e.g., `service.name`,
  `deployment.environment.name`). Use DYNAMIC type when the values come from a
  standard telemetry attribute. Each variable needs a UUID for `id` and `key`.

- **Rearranging layout / side-by-side placement:**
  - Dashboard uses a **12-column grid**. `x` ranges 0–11, `w` ranges 1–12.
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

Call `signoz_update_dashboard` with the dashboard UUID and the **complete** modified
dashboard JSON.

### Step 5: Report the result

Briefly tell the user what was changed. Offer further modifications if relevant.

## Guardrails

- **Full state on update**: `signoz_update_dashboard` requires the complete
  dashboard JSON (not a partial patch). Always call `signoz_get_dashboard` first
  to get the current state, merge your changes into that full object, and pass
  the result to `signoz_update_dashboard`. Never construct an update payload from
  scratch.
- **Preserve what you don't change**: Never drop or overwrite widgets, variables,
  layout items, or panelMap entries that are outside the scope of the user's request.
  Diff-and-merge, do not rebuild.
- **Confirm destructive changes**: Before removing panels, replacing queries, or
  deleting variables, confirm with the user — even if they say "just do it" or
  express urgency. Additions, renames, type changes, and variable additions do not
  need confirmation.
- **Valid JSON only**: Follow the v5 schema documented in the
  `signoz://dashboard/*` MCP resources (`instructions`, `widgets-instructions`,
  `widgets-examples`, `query-builder-example`). Include all required widget
  fields (see "Adding a panel" above). Never generate malformed queries or
  layouts.
- **OTel attribute names**: Always use OpenTelemetry semantic conventions for
  attribute names in filters, groupBy, and variables. Use `service.name` not
  `service`, `host.name` not `host`, `deployment.environment.name` not `env`.
- **No metric guessing**: If adding or changing queries and you are not sure what
  metrics are available, ask the user or call `signoz_list_metrics` to discover
  available metrics. Wrong metric names produce empty panels.
- **Paginate dashboard listing**: When searching for a dashboard by name, always
  paginate through all pages of `signoz_list_dashboards` before concluding a
  dashboard does not exist.
- **UUIDs for new objects**: Every new widget, layout item, variable, and query
  needs a unique UUID (`crypto.randomUUID()` format). Never use sequential IDs
  or short strings.
- **Scope boundary**: This skill modifies existing dashboards. If the user wants to
  create a new dashboard, redirect to `dashboard-create`.

## Examples

**User:** "Add an error rate panel to my Redis dashboard"

**Agent:**
1. Calls `signoz_list_dashboards` (paginates all pages) — finds "Redis Overview"
   dashboard with UUID `abc-123`.
2. Calls `signoz_get_dashboard` with UUID `abc-123` — gets full configuration with
   8 existing panels.
3. Calls `signoz_list_metrics` to find available Redis error metrics.
4. Creates a new graph widget (with UUID, all required fields, and a formula query
   for error rate), adds a layout entry at the next available `y` position, and
   adds it to the appropriate row's `panelMap`.
5. Calls `signoz_update_dashboard` with the full modified JSON (all 9 panels).
6. Reports: "Added an 'Error Rate' graph panel to your Redis Overview dashboard
   under the Overview section. Want me to adjust anything?"

---

**User:** "Change the latency panel from a graph to a table on my API dashboard"

**Agent:**
1. Identifies "API Monitoring" dashboard from context, calls `signoz_get_dashboard`.
2. Finds the panel titled "Request Latency" — if multiple panels could match,
   confirms with user: "I found 'Request Latency'. Convert that one to a table?"
3. Changes `panelTypes` from `"graph"` to `"table"`, adds `columnUnits` and
   `columnWidths` if missing, keeps the query intact.
4. Calls `signoz_update_dashboard` with the full modified JSON (all panels
   preserved).
5. Reports: "Changed 'Request Latency' from a graph to a table. Want me to adjust
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
   automatically). Updates `title` and `name` to "Service Health".
5. Calls `signoz_update_dashboard` with the full modified JSON.
6. Reports: "Removed the 'CPU Usage' panel and renamed the dashboard to 'Service
   Health'. Anything else to adjust?"
