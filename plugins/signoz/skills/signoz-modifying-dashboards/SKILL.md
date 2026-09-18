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

# Modify a SigNoz dashboard

Use the SigNoz MCP tools. Hand new-dashboard requests to
`signoz-creating-dashboards` and explanation-only requests to
`signoz-explaining-dashboards`.

## Resolve and read the target

Dashboard tools accept canonical `id` only. Never send `uuid`. If the user
gave a name, call `signoz_list_dashboards` and follow pagination until `total`
is covered. Resolve ambiguous matches with the user.

The v2 list excludes system dashboards. A known id can still be fetched with
`signoz_get_dashboard`; preserve the returned `source`. Only `source=user`
dashboards can be updated, patched, or deleted. If `source=system` or
`source=integration`, briefly explain that it is immutable and stop. Do not
search for a special discovery tool or suggest changing its source.

Fetch the complete dashboard once for the prepared operation. Reuse that result
while it remains current. Read:

- `signoz://dashboard/instructions`
- `signoz://dashboard/widgets-instructions`
- `signoz://dashboard/widgets-examples`
- `signoz://dashboard/patch-instructions`
- `signoz://dashboard/query-builder-example` when a query changes
- the relevant signal guide for query changes

The MCP resources and tool schemas are authoritative. For dry-run translation,
read [references/dashboard-to-query-builder-v5.md](references/dashboard-to-query-builder-v5.md).

## Choose patch or full replacement

Prefer `signoz_patch_dashboard` for targeted edits. Use
`signoz_update_dashboard` only when the requested change truly needs a full
replacement.

Patch paths target the postable Perses shape:

- panel: `/spec/panels/<panel-id>`
- panel query: `/spec/panels/<panel-id>/spec/queries/0`
- layout item: `/spec/layouts/<layout-index>/spec/items/<item-index>`
- visible title: `/spec/display/name`
- variables: `/spec/variables/<index>`
- tags: `/tags/<index>`

Adding a panel requires two operations in one patch: add the panel under
`/spec/panels/<id>`, then add a Grid item under
`/spec/layouts/<n>/spec/items` whose `content.$ref` is
`#/spec/panels/<id>`. Removing one requires removing both the referencing
grid item and the panel map entry. A move or resize replaces the grid item.

Never patch top-level `name`; it is immutable. Rename via
`/spec/display/name`. Do not invent paths under legacy `widgets`, `layout`,
or `panelMap`.

## Perses dashboard invariants

- `spec.panels` is a map keyed by panel id.
- `spec.layouts` contains `Grid` envelopes; items use `x`, `y`, `width`,
  `height`, and `content.$ref`.
- Every panel has exactly one grid item and every reference resolves.
- Grid items stay inside 12 columns and do not overlap.
- Query panels have exactly one `spec.queries` entry. Multi-series or formulas
  are nested in one `signoz/CompositeQuery`.
- `signoz/TextPanel` uses mode `markdown` or `text` and non-null
  `queries: []`. It is the sole queryless panel shape.
- Do not persist legacy `widgets`, `panelTypes`, `queryData`, `panelMap`,
  `selectedLogFields`, or `selectedTracesFields`.

There is no advertised heatmap panel plugin. Do not convert an executable raw
heatmap into a fictional dashboard panel.

## Change recipes

### Add a panel

Choose a fresh stable panel id, copy the closest panel shape from
`signoz://dashboard/widgets-examples`, and add a non-overlapping Grid item.
For a text panel, use `signoz/TextPanel`, `queries: []`, and skip query
discovery/dry-run. For a query panel, author exactly one query entry and
dry-run it before patching.

### Edit a panel or query

Change the smallest leaf or replace `spec.queries/0`. Preserve the panel's
other display and plugin fields. When a query needs several inputs, use one
`signoz/CompositeQuery`; computed outputs ordinarily disable inputs and leave
one formula enabled. PromQL and ClickHouse SQL remain valid where the resources
allow them.

### Remove a panel

Show the exact panel and request confirmation because removal is destructive.
After confirmation, remove its grid item and map entry in one patch. Preserve
unrelated positions unless the user asked for compaction.

### Move or resize

Replace only the target Grid item. Keep every `content.$ref` unchanged and
verify bounds and overlap across all layouts.

### Add or change a variable

Prefer a dynamic resource-backed variable. Discover unfamiliar attributes.
Before wiring `$variable` into queries, list panel ids and titles and ask
whether it applies to all or a subset. Patch the variable and only the selected
panel queries.

## Query validation

For every changed query-bearing panel, translate the authored Perses query to
the execution contract and call `signoz_execute_builder_query` with absolute
integer Unix-millisecond `start` and `end`. Substitute representative values
only for dry-running dashboard variables.

Keep the persisted Perses query unchanged. Do not save the executor envelope,
and do not claim that a stripped query validated unsupported semantics. Skip
query dry-runs for unchanged panels and TextPanels.

## Full replacement discipline

When `signoz_update_dashboard` is necessary, perform read-modify-write:

1. Start from the complete current result from the same prepared operation.
2. Preserve all unchanged authored fields and the immutable top-level `name`.
3. Strip server-populated fields such as timestamps, creator/updater, org
   metadata, `locked`, `source`, and generated links.
4. Apply only the requested semantic changes.
5. Send the flat canonical update object:
   `{id, schemaVersion, name, tags, spec}`.

Do not rebuild from a list summary or wrap the replacement in `dashboard`;
that nested field is discarded. Do not replay a failed or ambiguous write.

## Preview and report

Show a compact diff with affected panel ids/titles, query changes, variable
scope, and grid coordinates. Confirmation is required for deletion or other
destructive removal; apply ordinary reversible edits after preview.

Reuse the already prepared reads and authorization. On success, report the
canonical dashboard id and changes actually returned by the server.

## Guardrails

- Preserve all unrelated authored state.
- Respect `source`; all non-user dashboards are immutable.
- Use only canonical `id`, Perses paths, and current MCP resources.
- Never persist legacy dashboard fields or advertise a HeatmapPanel plugin.
- Never claim a dry-run covered fields the execution tool could not represent.
