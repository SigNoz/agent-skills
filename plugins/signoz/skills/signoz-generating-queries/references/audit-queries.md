# SigNoz audit events

Read this before the first query about who created, changed, or deleted
something in SigNoz: a dashboard, alert rule, saved view, notification
channel, user, role, or service account. Also read the audit section of
`signoz://logs/query-builder-guide`. It lists the audit fields, their values,
and filter examples.

## Before the first query

Check the input schema of `signoz_search_logs` or `signoz_aggregate_logs`. If
neither lists a `source` parameter that allows `"audit"`, tell the user their
SigNoz MCP server is too old to query audit events and needs an upgrade, then
stop. An older server ignores `source` and returns application logs, which
would read as changes that never happened.

## What audit events cover

SigNoz records each create, update, delete, attach, and detach of a SigNoz
resource as an audit event: who made the change, to which object, and whether
it succeeded. It does not record reads or sign-ins. An event names the object
by kind and id only, never by its name.

## Choosing the query

- Pass `source: "audit"` on every call. Without it the same filter reads
  application logs.
- For specific changes ("who deleted the checkout dashboard?"), use
  `signoz_search_logs` filtered on `signoz.resource.kind` and
  `signoz.audit.verb`.
- For an object the user names, resolve the name to an id first with the
  matching list tool (`signoz_list_dashboards`, `signoz_list_alert_rules`,
  `signoz_list_views`, `signoz_list_notification_channels`), then filter on
  `signoz.resource.id`. A deleted object no longer appears in those lists;
  return the deletions of that kind in the window with their ids and say the
  audit event does not record the name.
- For counts and rankings ("who changes alert rules most?"), use
  `signoz_aggregate_logs` grouped by `signoz.principal.email`,
  `signoz.audit.verb`, or `signoz.resource.kind`.
- Do not pass `service`; every audit event has `service.name = signoz`.
- `signoz_get_field_values` returns nothing for audit fields. To see the
  values present, group by the field with `signoz_aggregate_logs`.

## Reading results

- Quote the row's `body.message`. It already reads as a sentence, such as
  "alice@acme.com (<id>) deleted dashboard (<id>)".
- A row with `signoz.audit.outcome = failure` is a change attempt that did
  not apply. Report failures separately from successful changes.
- An attach or detach between two objects writes one row per object. Filter
  on `signoz.resource.kind` before counting them.

## Empty results

An empty audit result does not show that nobody made a change. Run
`signoz_aggregate_logs(source: "audit", aggregations: "count()",
timeRange: "30d")` once, then report by its count:

- Zero: "No audit events were recorded in this workspace in the last 30 days.
  Either no one created, changed, or deleted anything in that time, or audit
  logging is not available here (it needs an active license)." Do not state
  either cause as fact.
- Above zero: no recorded change matched the filter in the requested window.
  Reads and sign-ins are never recorded, so the result says nothing about
  them.

## No `apply_filter` chip

Do not emit `apply_filter` for an audit query. The SigNoz UI has no audit
explorer, and the logs explorer would show application logs instead.
