---
name: signoz-managing-views
description: >
  Use when the user wants to create, list, get, update, rename, or delete a
  SigNoz saved Explorer view. Trigger on phrases like "save this query as a
  view", "save this filter", "bookmark this search", "list my saved views",
  "show me views for traces/logs/metrics/meter", "rename the X view", "update my
  saved view to also filter Y", "delete the X view", or any request to manage
  Explorer saved views, even if they don't say "view" explicitly. Also use
  when someone wants to share a recurring Explorer query with their team and
  asks how to "save" or "bookmark" it.
argument-hint: <view name, source (traces/logs/metrics/meter), and filter intent>
---

# Managing Saved Views

Create, read, update, and delete SigNoz **saved Explorer views** via the
SigNoz MCP server. A saved view is a reusable snapshot of an Explorer query
on the Logs, Traces, Metrics, or Cost Meter page: name + filters + panel
type, scoped to one `source`. They are not dashboards and not alerts.

The tools call the v2 `/api/v2/saved_views` API. The create/update payloads
are the typed v2 shape (`source` + `spec`), not the retired v1
`compositeQuery`/`category`/`tags`/`extraData` shape; the `sourcePage`
parameter was renamed to `source`.

This skill covers the full CRUD surface in one place because the operations
share the same schema, the same identity model (UUID per view), and the same
prerequisite resources. The only operation with real blast radius is delete,
and update has a sharp edge (full-body replace); both get explicit guards
below.

## Prerequisites

This skill calls SigNoz MCP server tools (`signoz_create_view`,
`signoz_list_views`, `signoz_get_view`,
`signoz_update_view`, `signoz_delete_view`,
`signoz_get_field_keys`, `signoz_get_field_values`). Before
running the workflow, confirm the `signoz_*` tools are available. If
they are not, run `signoz-mcp-setup` first to initialize or repair the MCP
connection. Do not fall back to raw HTTP calls or fabricate view payloads
without the MCP tools.

## When to use

Use this skill when the user wants to:

- **Create** a saved view from a current or described Explorer query.
- **List / find** existing views (by `source` or name).
- **Inspect** a single view's filter or panel type.
- **Update** a view: rename its display label, or change its filter,
  panel type, or aggregations.
- **Delete** a view that is no longer useful.

Do NOT use when the user wants to:

- Build a dashboard panel → `signoz-creating-dashboards` /
  `signoz-modifying-dashboards`.
- Run an ad-hoc Explorer query without saving it → `signoz-generating-queries`.
- Create or change an alert rule → `signoz-creating-alerts`.

## Schema reference

**Read both resources BEFORE composing any create or update payload.** Do not
hand-compose a `spec` from memory. The correct schema is the v2 typed spec
(`schemaVersion: "v2"`) described in these resources; the retired v1 fields
(`compositeQuery`, `category`, `tags`, `extraData`) are not accepted.

Read both MCP resources by URI using your client's resource-read mechanism:

- `signoz://view/instructions`: SavedView field reference, `source`
  rules, the `spec` fields, the GET-then-replace update flow, the minimal
  create body.
- `signoz://view/examples`: round-tripped v2 payloads (traces list, logs
  list, metrics graph, and a Cost Meter graph) you can adapt verbatim.

## Operation flows

### Create a view

1. **Resolve `source`**: must be exactly one of `traces`, `logs`,
   `metrics`, `meter`. If the user's intent is ambiguous ("save this query"),
   ask which Explorer they mean. It cannot be inferred from filter strings
   alone. Use `meter` for **Cost Meter** (usage / billing) views; it is a
   distinct Explorer page from `metrics`, even though the query runs on the
   metrics signal (see Step 4).
2. **Read the schema resources.** Read both `signoz://view/instructions`
   and `signoz://view/examples` using your client's resource-read mechanism
   before composing any payload. Do not skip this step even if you think
   you know the schema.
3. **Build the query using `signoz-generating-queries`, mandatory.** Use
   the `Skill` tool to invoke `signoz-generating-queries`. The sub-skill
   handles field discovery, type checking, and live-data validation in one
   pass; adapting an example payload from `signoz://view/examples` or
   running a bare `signoz_search_traces` call skips the field-type
   checks and service-name resolution that catch silent 400s before they
   become permanent bad views. Skipping it means a malformed filter becomes
   a saved view that must be deleted and recreated.
   For a `meter` view, tell `signoz-generating-queries` it's a **Cost Meter**
   query (`source=meter`) so discovery hits the meter store, not the default one.
   Retain the exact `queries` array from its successful
   `signoz_execute_builder_query` validation call, then translate it explicitly:

   ```text
   execution query.compositeQuery.queries
     -> saved spec.queries
   ```

   Build the `spec` argument to `signoz_create_view` as
   `{ "displayName": "<human label>", "panelType": "<list|graph|table|value|trace>",
   "requestType": "<raw|time_series|scalar|trace>", "queries": <copied queries> }`,
   adding `selectedFields` / `display` when the Explorer layout calls for them.
   Copy the `queries` array losslessly, but do not copy the execution-only
   envelope fields `schemaVersion`, `start`, `end`, `requestType` (the
   execution envelope's), `formatOptions`, or `variables`; do not put a
   `query` key or a `compositeQuery` object inside the saved spec. Choose
   `panelType` and `requestType` from the saved-view intent rather than
   inventing them from the execution envelope.
   Set the top-level `name` (a DNS-1123 label: lowercase letters, digits,
   hyphens) or pass `generateName: true` to derive it from
   `spec.displayName`. `schemaVersion` is always `"v2"`; the server fills it
   in when omitted.
   The copied queries must retain every positive `spec.limit` and v5
   `spec.order` entry losslessly. Never translate them to dashboard `orderBy`.
   Raw/list views use 100 rows (logs: timestamp/id desc; traces: timestamp
   desc); standalone aggregate views and formula results use 100 groups.
   Builder queries referenced by a formula use 10000 because their limits are
   applied before evaluation. Order by the primary aggregation or `__result`
   desc as appropriate. Time-series top-N ranks groups over the whole selected
   window and can omit a short-lived local spike.
4. **Enforce the signal rule** in every `builder_query` spec.
   - For `traces` / `logs` / `metrics`: `signal == source`. A
     `source:"traces"` view with `signal:"logs"` is a server-side error.
   - For `meter` (Cost Meter): `signal:"metrics"` **and** `source:"meter"`:
     a Cost Meter view is queried on the metrics signal against the meter
     store. Omitting `source:"meter"` silently queries the default metrics
     store; setting `source:"meter"` on a non-`meter` source view is rejected.
5. **Mandatory pre-save sample fetch.** Probe with the **exact** filter
   from `spec.queries[0].spec` against the destination
   signal:
   - `source=traces` → `signoz_search_traces` with `limit=1`
   - `source=logs` → `signoz_search_logs` with `limit=1`
   - `source=metrics` → `signoz_query_metrics` with the
     `metricName` from `spec.aggregations[0].metricName` plus the same
     filter, `timeRange=1h`, `requestType=scalar`. Repeat per metric
     query if the view has multiple. The tool requires `metricName`;
     a filter-only probe is not supported.
   - `source=meter` → `signoz_query_metrics` with the `metricName`
     from `spec.aggregations[0].metricName`, **`source=meter`**, the same
     filter, `timeRange=24h` (Cost Meter rolls up hourly, so a 1h window
     can be a single partial bucket), `requestType=scalar`.

   Required even if Step 3 ran cleanly: the sub-skill validates the
   query *it* authored, not whatever you persist after edits or lifts.
   Empty → save anyway / revise / abort. Autonomous mode without
   authorization to persist empty views: abort and escalate.
6. **Preview before writing; this step is not optional.** Before calling
   `signoz_create_view`, show the user a summary: name, source,
   panelType, the full filter expression, and the Step 5 probe result
   ("sample fetch: N rows in last 1h"; for a `meter` view the probe window
   is 24h, so report it as such). For a human in the loop, wait
   for confirmation. For an autonomous agent, log the preview and proceed.
7. Call `signoz_create_view`. On success the response `data` carries the
   new view's `id` (HTTP 201 upstream). The server populates `id`,
   `createdAt/By`, `updatedAt/By`; never send those.

### List or find views

`signoz_list_views` requires a `source`. If the user did not
specify one and is searching by name, call it once per source (traces,
logs, metrics, meter) and merge; do not guess. Use the `name`
parameter for server-side partial-match filtering when the user gives a
substring; do not fetch everything and grep client-side. There is no
`category` filter; it was removed with the v2 API.

The response paginates. **Always check `pagination.hasMore`** before
concluding a view does not exist. Default page size is 50; pass `offset =
pagination.nextOffset` to continue. A view is only confirmed missing for a
given `source` once you have walked pages until `hasMore = false`. As
long as `hasMore = true`, keep paginating; there is no page-count cap.

### Get a single view

Use `signoz_get_view` with the UUID (`id`; the legacy alias
`viewId` also works). The returned `data` object is
the canonical SavedView shape; it is what you pass back to
`signoz_update_view`. Treat that data as the source of truth, not
whatever the user described from memory.

### Update a view (GET-then-replace)

`signoz_update_view` is a **full replacement**. Sending a partial body
wipes the unspecified fields. The machine `name` is immutable server-side;
renaming a view means changing `spec.displayName`. The flow:

1. `signoz_get_view` with the view's `id` → returns
   `{ "status": "success", "data": { ...SavedView... } }`.
2. Take the `data` object. Strip server-populated fields (`id`,
   `createdAt`, `createdBy`, `updatedAt`, `updatedBy`) and drop `name`; the
   MCP server strips them for you, but omitting them up front makes the
   diff readable.
3. **If the update changes `spec.queries`** (new filter, different panel
   type, different aggregation), invoke `signoz-generating-queries` to
   build and validate the new query before proceeding. Do not hand-edit
   `spec.queries` from the user's description; the same Step 4 signal
   rule applies (including the `meter` case: `signal:"metrics"` +
   `source:"meter"`), and `panelType` changes often imply a `stepInterval`
   change too. For a `meter` view, tell `signoz-generating-queries` it is a
   **Cost Meter** query (`source=meter`) so it discovers and validates against
   the meter store. Derive the replacement `spec.queries` from the
   successful execution query using the same explicit translation as Create:
   copy only `query.compositeQuery.queries`. Exclude the execution-only
   envelope fields. For pure metadata tweaks (display-label rename), skip
   this step and do not touch `spec.queries`.
4. Modify only the field(s) the user asked to change. Keep `source`
   unchanged; a cross-source move is rejected.
5. **Mandatory pre-save sample fetch, when `spec.queries` changed.**
   Run the 1-row probe from the Create flow's Step 5 against the new
   filter. Empty → save anyway / revise / abort. Skip only for pure
   metadata tweaks (display-label rename).
6. **Show a diff-style preview before writing.** One line per changed
   field: `spec.displayName: "slow-checkout" → "slow-checkout-p99"`.
   Explicitly note any fields that are unchanged (e.g. "queries:
   unchanged") and include the Step 5 probe result when `spec.queries`
   changed. This prevents silent mistakes and gives the user a chance to
   catch a wrong target view. Wait for confirmation on any change to
   `spec.queries`, since that changes what the view actually shows.
7. Call `signoz_update_view` with `{ "id": "<id>", "view": <modified data> }`.
   `view` must carry `source` and the full `spec`; success is an empty
   204 upstream.

### Delete a view

Deletion is destructive and immediately removes the view from the shared
list; any team member who had the view bookmarked will see it disappear.
Depending on the host application, the user may be offered a one-click
restore action shortly after the delete (the SigNoz Assistant captures a
snapshot and exposes a `restore` action), but treat that as a recovery
affordance, not a substitute for getting the delete right. Treat this like
dropping a row from a shared table:

1. **List to locate.** Call `signoz_list_views` to find the view
   by name. If `source` is unknown, search all four sources (traces,
   logs, metrics, meter).
2. **Get to confirm, mandatory.** Call `signoz_get_view` with the
   UUID from step 1. Do NOT skip this step even when you got the UUID from
   a list result that looks correct. List results are paginated and a name
   match is not a UUID guarantee; `signoz_get_view` is the confirmation
   that the UUID maps to the view the user named.
   Never call `signoz_delete_view` on a UUID without a prior
   `signoz_get_view` confirming the matching name and `source`.
3. **Show and ask.** Present the resolved view's name and `source`,
   and explicitly ask for confirmation. Do **not** auto-confirm
   based on the original prompt, even an emphatic one; destructive
   operations get a fresh confirmation against the resolved target.
4. Call `signoz_delete_view`. Report success with the deleted
   view's name (not just the UUID), so the user can recognize it.

For autonomous agents without a human in the loop: refuse delete unless
the calling context has been explicitly authorized for destructive
operations on saved views, and log the resolved view metadata before the
call.

## Guardrails

- **Mandatory pre-save sample fetch on create and on `spec.queries`
  updates.** Step 5 of each flow runs a 1-row probe against the
  destination signal using the exact filter from the about-to-save
  payload. Skipping is equivalent to skipping get-before-delete. The
  Step 3 `signoz-generating-queries` delegation is necessary but not
  sufficient; it validates the query *it* authored, not the filter
  you persist after edits.

  *Cross-signal-lift footgun:* field keys are signal-scoped. An
  attribute observed on **metrics** (e.g. `oauth.error_code` on a
  counter) may not exist on **traces** or **logs** for the same
  tenant, even when emitted by the same service. Lifting an attribute
  from a sibling dashboard panel, alert rule, or view that targets a
  different signal is the most common source of empty saved views.
  `signoz_get_field_keys signal=<destination signal>` is necessary but
  not sufficient; sparse emission still produces zero-result views.
  Only the sample fetch confirms. The destination signal equals `source`
  for traces/logs/metrics; for a `meter` view it is `signal=metrics` with
  `source=meter` (never `signal=meter`).

  A saved view returning zero rows under its own filter is a
  permanent artifact in a shared workspace; the human preview can't
  tell from JSON that the filter won't match, and autonomous mode
  has no preview, so the sample fetch is the only safety net.

- **Translate the execution envelope before saving.** The executable query and
  saved-view spec intentionally have different outer shapes. Save exactly
  `spec: {displayName, panelType, requestType, queries, ...}` in the create
  call or `view.spec`, where `queries`
  comes from the validated execution `query.compositeQuery.queries`. Never copy
  the range, request, formatting, or variables envelope into a view.

## Quick reference

| Operation | Tools called | Key guard |
|-----------|-------------|-----------|
| Create | read `signoz://view/instructions` + `signoz://view/examples` → `signoz-generating-queries` → **sample fetch on exact filter** → preview → `signoz_create_view` | Mandatory pre-save sample fetch; preview before write; no v1 fields |
| List | `signoz_list_views` (× 4 if no source given: traces/logs/metrics/meter) | Check `pagination.hasMore` |
| Get | `signoz_get_view(id)` | Returns canonical body for update |
| Update | `signoz_get_view` → modify → **sample fetch if `spec.queries` changed** → diff preview → `signoz_update_view` | Full replacement; name immutable (rename = `spec.displayName`); diff preview required |
| Delete | `signoz_list_views` → `signoz_get_view` → confirm → `signoz_delete_view` | Get-before-delete mandatory; fresh confirmation |

## Common mistakes

| Mistake | Fix |
|---------|-----|
| Hand-composing `spec.queries` from examples or memory (even after reading `signoz://view/examples`) | Use the `Skill` tool to invoke `signoz-generating-queries`; reading examples and validating with `signoz_search_traces` is not a substitute |
| Sending the retired v1 shape: `compositeQuery`, `category`, `tags`, `extraData`, or the `sourcePage` parameter | The v2 API takes `source` + `spec`; read both schema resources first |
| Copying the full executable query envelope into the saved `spec` | Copy only `query.compositeQuery.queries`, then construct the spec `{displayName, panelType, requestType, queries}`; exclude the execution-only `schemaVersion`, `start`, `end`, `requestType`, `formatOptions`, and `variables` |
| Lifting an attribute name from a metric, alert rule, or sibling view and using it in a `source=traces` / `=logs` view filter without re-verifying on the destination signal | Field keys are signal-scoped; an attribute on metrics may not exist on traces or logs. Always re-check via `signoz_get_field_keys signal=<destination signal>` (for a `meter` view, `signal=metrics source=meter`, never `signal=meter`) **and** run the mandatory pre-save sample fetch; the key check is necessary but not sufficient |
| Skipping the pre-save sample fetch because `signoz-generating-queries` already validated the query | The sub-skill validates the query *it* authored; the filter you persist may have been edited or lifted since then. The Step 5 sample fetch is mandatory regardless |
| Skipping `signoz_get_view` before delete (relying on list UUID alone) | Always call `signoz_get_view` to confirm name+source before `signoz_delete_view` |
| Trying to rename the machine `name` on update | `name` is immutable server-side; change `spec.displayName` for the visible label |
| `signal` ≠ `source` in builder query | For traces/logs/metrics, every `builder_query.signal` must equal the view's `source`. For a `meter` view, use `signal:"metrics"` + `source:"meter"` (not `signal:"meter"`) |
| Filing a Cost Meter view under `source:"metrics"` (with `source:"meter"`) | Cost Meter views go under `source:"meter"`; otherwise they're invisible in the Meter Explorer and mis-filed under Metrics. The server rejects `source:"meter"` on a non-`meter` source |
| Partial update body (omitting unchanged fields) | GET full body first → modify only changed fields → replace with `source` + full `spec` |
| Declaring "no such view" after only page 1 | Check `pagination.hasMore`; continue with `offset = pagination.nextOffset` |
| Using PromQL or raw ClickHouse in a view | Builder envelopes are the supported path; offer a dashboard panel instead |

## Reporting back

After any write (create / update / delete), include in your reply:
- The view's name and UUID.
- The `source`.
- A direct link **only** if the MCP response or SigNoz frontend provides a
  canonical URL, or the user explicitly asks for one. Do not fabricate
  frontend routes; saved-view paths differ per signal and change over
  time. When in doubt, omit the link and report the UUID + `source`.
- For updates, what changed (one-line diff).
- For deletes, an explicit "deleted" confirmation with the name.

## Follow-up suggestions

After a view operation, you may surface up to 3 follow-up intents that
match what just happened. The host application renders them; follow
the host's UI rendering rules for the exact mechanism. Use your
judgment about what's natural for the user's context; do not pad to 3.

Two anti-rules that override your judgment:

- **Read-only stays read-only at the chip surface.** After list / get /
  find, do not offer chips that propose a write (e.g. "Update this
  view", "Delete this view"). That contradicts the read-only stop rule
  in *Reporting back* below. Chips that re-run the view's underlying
  query are fine; those stay on the read path. If the user's next
  message names an update or delete, route from there.
- **Do not duplicate host-injected actions.** If the host offers a
  restore action after a delete (the SigNoz Assistant does), do not
  also surface restore as a follow-up; it would render twice.

When the user is purely exploring ("just listing my views", "what's
in here?") and signals no further intent, skip follow-ups entirely.
Offering no follow-ups is better than offering wrong ones.

Describe follow-ups by *user intent*, not by tool or skill name. The
label the user clicks should read like the user's next prompt.

Read-only operations (list, get) should report concisely (name, id,
source, filter expression, panel type) and stop. Don't narrate
the schema back to the user.
