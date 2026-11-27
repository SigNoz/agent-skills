# SigNoz audit events

Read this before the first query about who created, changed, or deleted
something in SigNoz: a dashboard, alert rule, saved view, notification
channel, user, role, or service account. Also read the audit section of
`signoz://logs/query-builder-guide`. It lists the audit fields, their values,
and filter examples.

## Before the first query

Check the input schema of `signoz_search_logs` or `signoz_aggregate_logs`. If
neither lists a `source` parameter that allows `"audit"`, tell the user the
SigNoz MCP server they are connected to cannot query audit events yet, and
that a self-hosted server needs an upgrade. Then stop. A server without the
parameter ignores `source` and returns application logs, which would read as
changes that never happened.

## What audit events cover

SigNoz records each create, update, delete, attach, and detach of a SigNoz
resource as an audit event: who made the change, to which object, and whether
it succeeded. It does not record reads. An event names the object by kind and
id only, never by its name.

## Choosing the query

- Pass `source: "audit"` on every call. Without it the same filter reads
  application logs.
- For specific changes ("who deleted the checkout dashboard?"), use
  `signoz_search_logs` filtered on `signoz.resource.kind` and
  `signoz.audit.verb`.
- For an object the user names, resolve the name to an id first when a list
  tool covers its kind (`signoz_list_dashboards`, `signoz_list_alert_rules`,
  `signoz_list_views`, `signoz_list_notification_channels`), then filter on
  `signoz.resource.id`. When no list tool covers the kind, or the object was
  deleted and no longer appears in the list, return the changes of that kind
  in the window with their ids and say the audit event does not record the
  name.
- For counts and rankings ("who changes alert rules most?"), use
  `signoz_aggregate_logs` grouped by `signoz.principal.email`,
  `signoz.audit.verb`, or `signoz.resource.kind`. A count also includes
  failed attempts. To count changes that applied, add
  `signoz.audit.outcome = 'success'` to the filter; to report both, also
  group by `signoz.audit.outcome`.
- To find a person, object, or outcome, filter on its named field. SigNoz
  rejects `search()` and every `searchScope` other than `body` on audit
  events, so do not widen a text search as you would for application logs.

## Reading results

- Quote the row's `body.message`. It already reads as a sentence, such as
  "alice@acme.com (<id>) deleted dashboard (<id>)".
- A row with `signoz.audit.outcome = failure` is a change attempt that did
  not apply. Report failures separately from successful changes.
- An attach or detach can write one row for each of the two objects. Filter
  on `signoz.resource.kind` before counting them.

## Empty results

An empty audit result does not show that nobody made a change. Run
`signoz_aggregate_logs(source: "audit", aggregations: "count()",
timeRange: "30d")` once, then report by its count:

- Zero: "I found no audit events in this workspace for the last 30 days.
  Either no one created, changed, or deleted anything in that time, or this
  SigNoz does not record audit events where I can query them: it is too old,
  audit logging is not enabled, or it has no active license." Do not state
  any cause as fact.
- Above zero: no recorded change matched the filter in the requested window.
  Reads are never recorded, so the result says nothing about them.

## No `apply_filter` chip

Do not emit `apply_filter` for an audit query. The SigNoz UI has no audit
explorer to apply it to.
