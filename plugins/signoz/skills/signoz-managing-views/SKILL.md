---
name: signoz-managing-views
description: >
  Use when the user wants to create, list, get, update, rename, or delete a
  SigNoz saved Explorer view. Trigger on phrases like "save this query as a
  view", "save this filter", "bookmark this search", "list my saved views",
  "show me views for traces/logs/metrics/meter", "rename the X view", "update my
  saved view to also filter Y", "delete the X view", or any request to manage
  Explorer saved views — even if they don't say "view" explicitly. Also use
  when someone wants to share a recurring Explorer query with their team and
  asks how to "save" or "bookmark" it.
argument-hint: <view name, source (traces/logs/metrics/meter), and filter intent>
---

# Manage SigNoz saved views

Saved views use the v2 typed contract. Read `signoz://view/instructions` before
creating or updating one, and `signoz://view/examples` only when a worked
shape is needed. The resources and tool schemas are authoritative.

## Resolve identity

Use canonical `id` for get, update, and delete. Never send `uuid`. If only a
display label or machine name is known, call `signoz_list_views` for the
relevant source. If source is unknown, search `traces`, `logs`, `metrics`,
and `meter`, following every page before concluding the view is absent.

Machine `name` is immutable. The human-facing label is `spec.displayName`.
Rename by changing `spec.displayName`, not `name`.

## Create a view

1. Determine source: `traces`, `logs`, `metrics`, or `meter`.
2. Use `signoz-generating-queries` to build and execute the intended query.
3. Translate the validated query into the v2 saved-view `spec` described by
   `signoz://view/instructions`.
4. Run a small representative fetch using the exact saved filter/query.
5. Preview display name, source, panel/request type, filters, and sample result.
6. Call `signoz_create_view` and report the returned canonical id.

Create accepts either:

- explicit DNS-1123 `name` plus `spec.displayName`; or
- `generateName: true`, empty/omitted `name`, and `spec.displayName`.

Do not copy the execution-only outer range, formatting envelope, or variables
into the saved view unless the resource explicitly includes them in `spec`.
Preserve raw query entries exactly where the v2 resource permits them.

For Cost Meter, set view `source: "meter"`; each builder query uses
`signal: "metrics"` and `source: "meter"`.

## List and get

Use `signoz_list_views` to browse and resolve identities. Paginate completely.
Use `signoz_get_view` for the full current object before replacement or when
the user asks for complete details.

List summaries are insufficient for update. Do not reconstruct a full view from
a list row.

## Update or rename

`signoz_update_view` is a full replacement. Use read-modify-write:

1. Reuse a complete `signoz_get_view` result from the same still-current
   prepared operation, or fetch it.
2. Preserve every unchanged authored field, including source, schemaVersion,
   panel/request type, queries, selected fields, and display settings.
3. Strip server-populated fields such as id, created/updated timestamps, and
   creator/updater, and omit immutable machine `name` from the replacement.
4. Apply only the requested change.
5. If query semantics changed, validate the exact new query and sample it.
6. Preview the diff and call `signoz_update_view` with top-level canonical
   `id` plus the complete postable `view`.

Do not flatten view fields beside `id`, and do not replay an ambiguous write.

## Delete

Resolve the exact view and call `signoz_get_view` to verify it. Show the
display name, source, and id, then ask for confirmation. Call
`signoz_delete_view` only after confirmation and report the recognizable
display name.

## Query and rendering boundaries

Saved-view query entries follow `signoz://view/instructions`. Do not persist
legacy `sourcePage`, `category`, `compositeQuery`, `extraData`, or old
flat selected-field structures.

Raw heatmap execution may preserve `requestType: "heatmap"`, bucket options,
and returned bucket/count/overflow data where the current saved-view schema
round-trips them. Do not promise that the UI renders a saved heatmap. There is
no HeatmapPanel plugin to advertise.

Preserve raw payloads across read-modify-write. Do not normalize away bucket
metadata, formula disabled flags, PromQL/SQL envelopes, selected fields, or
unknown authored content that the current typed resource permits. Strip only
known server-populated fields.

## Prepared-operation reuse

Reuse discovery, get results, schema resources, and authorization already
obtained for the same prepared operation. Refresh only if state may have
changed. A successful write followed by a read failure is not permission to
repeat the write; inspect by returned id once access is restored.

## Guardrails

- Use canonical ids and the v2 typed resource.
- Preserve authored payloads during full replacement.
- Validate query changes through `signoz-generating-queries`.
- Keep meter views under source=meter.
- Require confirmation for delete.
- Do not claim saved-view heatmap UI support.
