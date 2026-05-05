---
name: signoz-managing-views
description: >
  Use when the user wants to create, list, get, update, rename, or delete a
  SigNoz saved Explorer view. Trigger on phrases like "save this query as a
  view", "save this filter", "bookmark this search", "list my saved views",
  "show me views for traces/logs/metrics", "rename the X view", "update my
  saved view to also filter Y", "delete the X view", or any request to manage
  Explorer saved views — even if they don't say "view" explicitly. Also use
  when someone wants to share a recurring Explorer query with their team and
  asks how to "save" or "bookmark" it.
argument-hint: <natural-language view request>
---

# Managing Saved Views

Create, read, update, and delete SigNoz **saved Explorer views** via the
SigNoz MCP server. A saved view is a reusable snapshot of an Explorer query
on the Logs, Traces, or Metrics page — name + filters + panel type, scoped
to one `sourcePage`. They are not dashboards and not alerts.

This skill covers the full CRUD surface in one place because the operations
share the same schema, the same identity model (UUID per view), and the same
prerequisite resources. The only operation with real blast radius is delete,
and update has a sharp edge (full-body replace) — both get explicit guards
below.

## Prerequisites

This skill calls SigNoz MCP server tools (`signoz:signoz_create_view`,
`signoz:signoz_list_views`, `signoz:signoz_get_view`,
`signoz:signoz_update_view`, `signoz:signoz_delete_view`,
`signoz:signoz_get_field_keys`, `signoz:signoz_get_field_values`). Before
running the workflow, confirm the `signoz:signoz_*` tools are available. If
they are not, the SigNoz MCP server is not installed or configured — stop
and direct the user to set it up:
<https://signoz.io/docs/ai/signoz-mcp-server/>. Do not fall back to raw HTTP
calls or fabricate view payloads without the MCP tools.

## When to use

Use this skill when the user wants to:

- **Create** a saved view from a current or described Explorer query.
- **List / find** existing views (by `sourcePage`, name, or category).
- **Inspect** a single view's filter or panel type.
- **Update** a view — rename, recategorize, or change its filter,
  panel type, or aggregations.
- **Delete** a view that is no longer useful.

Do NOT use when the user wants to:

- Build a dashboard panel → `signoz-creating-dashboards` /
  `signoz-modifying-dashboards`.
- Run an ad-hoc Explorer query without saving it → `signoz-generating-queries`.
- Create or change an alert rule → `signoz-creating-alerts`.

## Schema reference

**Read both resources BEFORE composing any create or update payload.** Do not
hand-compose a `compositeQuery` from memory — the correct schema is not the
legacy `builder.queryData` format; it is the v5 spec described in these
resources. Sending a legacy payload causes a silent HTTP 400.

Call `ReadMcpResourceTool` with each URI to load them:

```
ReadMcpResourceTool(uri="signoz://view/instructions")
ReadMcpResourceTool(uri="signoz://view/examples")
```

- `signoz://view/instructions` — SavedView field reference, `sourcePage`
  rules, the GET-then-PUT update flow, the minimal create body.
- `signoz://view/examples` — three round-tripped payloads (traces list, logs
  list, metrics graph) you can adapt verbatim.

The server returns HTTP 400 on legacy v3/v4 fields (`builder`, `promql`,
`unit`, top-level `id`, `queryFormulas`, `queryTraceOperator`) — the failure
mode is silent for the user, so reading the resources first is mandatory, not
optional.

## Operation flows

### Create a view

1. **Resolve `sourcePage`** — must be exactly one of `traces`, `logs`,
   `metrics`. If the user's intent is ambiguous ("save this query"), ask
   which Explorer they mean. It cannot be inferred from filter strings alone.
2. **Read the schema resources.** Call `ReadMcpResourceTool` for both
   `signoz://view/instructions` and `signoz://view/examples` before composing
   any payload. Do not skip this step even if you think you know the schema —
   the legacy `builder.queryData` format is rejected with HTTP 400.
3. **Build the query using `signoz-generating-queries` — mandatory.** Invoke
   the `signoz-generating-queries` skill to construct and validate the
   `compositeQuery`. Do not hand-compose a `compositeQuery` from the user's
   description alone. This surfaces filter mistakes before they become a
   saved view that needs to be deleted.
4. **Enforce `signal == sourcePage`** in every `builder_query` spec. A
   `sourcePage:"traces"` view with `signal:"logs"` is a server-side error.
5. **Preview before writing — this step is not optional.** Before calling
   `signoz_create_view`, show the user a summary: name, sourcePage,
   panelType, and the full filter expression. For a human in the loop, wait
   for confirmation. For an autonomous agent, log the preview and proceed.
6. Call `signoz:signoz_create_view`. The server populates `id`,
   `createdAt/By`, `updatedAt/By` — never send those.

### List or find views

`signoz:signoz_list_views` requires a `sourcePage`. If the user did not
specify one and is searching by name, call it once per signal (traces,
logs, metrics) and merge — do not guess. Use the `name` and `category`
parameters for server-side partial-match filtering when the user gives a
substring; do not fetch everything and grep client-side.

The response paginates. **Always check `pagination.hasMore`** before
concluding a view does not exist. Default page size is 50; pass `offset =
pagination.nextOffset` to continue. Ten pages of misses is still a real
miss; one page of misses is not.

### Get a single view

Use `signoz:signoz_get_view` with the UUID. The returned `data` object is
the canonical SavedView shape — it is what you pass back to
`signoz:signoz_update_view`. Treat that data as the source of truth, not
whatever the user described from memory.

### Update a view (GET-then-PUT)

`signoz:signoz_update_view` is a **full-body replace** (HTTP PUT
upstream). Sending a partial body wipes the unspecified fields. The flow:

1. `signoz:signoz_get_view` with the view's `id` → returns
   `{ "status": "success", "data": { ...SavedView... } }`.
2. Take the `data` object. Strip server-populated fields (`id`,
   `createdAt`, `createdBy`, `updatedAt`, `updatedBy`) — the MCP server
   strips them for you, but omitting them up front makes the diff
   readable.
3. **If the update changes `compositeQuery`** (new filter, different panel
   type, different aggregation), invoke `signoz-generating-queries` to
   build and validate the new query before proceeding. Do not hand-edit
   `compositeQuery` from the user's description — the same
   `signal == sourcePage` rule applies, and `panelType` changes often
   imply a `stepInterval` change too. For pure metadata tweaks (rename,
   recategorize), skip this step and do not touch `compositeQuery`.
4. Modify only the field(s) the user asked to change.
5. **Show a diff-style preview before writing.** One line per changed
   field: `name: "slow-checkout" → "slow-checkout-p99"`. Explicitly note
   any fields that are unchanged (e.g. "compositeQuery: unchanged"). This
   prevents silent mistakes and gives the user a chance to catch a wrong
   target view. Wait for confirmation on any change to `compositeQuery`,
   since that changes what the view actually shows.
6. Call `signoz:signoz_update_view` with `{ "viewId": "<id>", "view": <modified data> }`.

### Delete a view

Deletion is permanent — there is no undo, and any team member who had the
view bookmarked will see it disappear. Treat this like dropping a row from
a shared table:

1. **List to locate.** Call `signoz:signoz_list_views` to find the view
   by name. If `sourcePage` is unknown, search all three signals.
2. **Get to confirm — mandatory.** Call `signoz:signoz_get_view` with the
   UUID from step 1. Do NOT skip this step even when you got the UUID from
   a list result that looks correct. List results are paginated and a name
   match is not a UUID guarantee — `signoz_get_view` is the confirmation
   that the UUID maps to the view the user named.
   Never call `signoz:signoz_delete_view` on a UUID without a prior
   `signoz:signoz_get_view` confirming the matching name and `sourcePage`.
3. **Show and ask.** Present the resolved view's name, `sourcePage`, and
   category, and explicitly ask for confirmation. Do **not** auto-confirm
   based on the original prompt, even an emphatic one — destructive
   operations get a fresh confirmation against the resolved target.
4. Call `signoz:signoz_delete_view`. Report success with the deleted
   view's name (not just the UUID), so the user can recognize it.

For autonomous agents without a human in the loop: refuse delete unless
the calling context has been explicitly authorized for destructive
operations on saved views, and log the resolved view metadata before the
call.

## Quick reference

| Operation | Tools called | Key guard |
|-----------|-------------|-----------|
| Create | `ReadMcpResourceTool` × 2 → `signoz-generating-queries` → preview → `signoz_create_view` | Preview before write; no legacy fields |
| List | `signoz_list_views` (× 3 if no sourcePage given) | Check `pagination.hasMore` |
| Get | `signoz_get_view(viewId)` | Returns canonical body for update |
| Update | `signoz_get_view` → modify → preview → `signoz_update_view` | Full-body replace; diff preview required |
| Delete | `signoz_list_views` → `signoz_get_view` → confirm → `signoz_delete_view` | Get-before-delete mandatory; fresh confirmation |

## Common mistakes

| Mistake | Fix |
|---------|-----|
| Hand-composing `compositeQuery` using legacy `builder.queryData` format | Read `signoz://view/instructions` first; use `signoz-generating-queries` to build the query |
| Skipping `signoz_get_view` before delete (relying on list UUID alone) | Always call `signoz_get_view` to confirm name+sourcePage before `signoz_delete_view` |
| Sending legacy fields: `builder`, `promql`, `unit`, top-level `id`, `queryFormulas` | Read schema resources; server returns HTTP 400 silently |
| `signal` ≠ `sourcePage` in builder query | Every `builder_query.signal` must equal the view's `sourcePage` |
| Partial update body (omitting unchanged fields) | GET full body first → modify only changed fields → PUT entire body |
| Declaring "no such view" after only page 1 | Check `pagination.hasMore`; continue with `offset = pagination.nextOffset` |
| Using PromQL or raw ClickHouse in a view | Only `queryType: "builder"` is supported; offer a dashboard panel instead |
| Setting `category` to an enum value | `category` is free-form string; omit if user doesn't specify |

## Reporting back

After any write (create / update / delete), include in your reply:
- The view's name and UUID.
- The `sourcePage`.
- A direct link if you can construct one
  (`<base>/saved-views?sourcepage=<traces|logs|metrics>` is a reasonable
  fallback when the deep link is not known).
- For updates, what changed (one-line diff).
- For deletes, an explicit "deleted" confirmation with the name.

Read-only operations (list, get) should report concisely — name, id,
sourcePage, filter expression, panel type — and stop. Don't narrate
the schema back to the user.
