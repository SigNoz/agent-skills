---
name: signoz-setting-up-observability
description: >
  Run the full end-to-end observability setup for a service after its
  telemetry is already flowing into SigNoz — sequence SLI/SLO capture,
  data exploration (RED/USE), focused dashboards, saved Explorer views,
  burn-rate and absent-data alerts, and a tuning loop into one
  opinionated, SLO-aware workflow. Make sure to use this skill whenever the user says "set up
  observability after ingestion", "now that data is flowing, give me
  dashboards and alerts", "onboard this service to SigNoz end-to-end",
  "I want the full monitoring setup for X", or asks to go from raw
  telemetry to a complete dashboard + alerts + views package — even if
  they don't say "observability" explicitly. This is the orchestration
  layer: for a single artifact (just a dashboard, just one alert, just a
  saved view, or one static threshold alert, or a one-off query) use
  signoz-creating-dashboards, signoz-creating-alerts,
  signoz-managing-views, or signoz-generating-queries directly.
argument-hint: <service name + what to set up (dashboard / alerts / views)>
---

# Setting Up Observability After Ingestion

Take a service from "telemetry is flowing into SigNoz" to "I have a
dashboard, alerts, saved views, and a tuning loop." This skill is an
**orchestration layer, not a standalone reference** — the mechanical
work lives in the sibling SigNoz skills and the MCP tools/resources hold
the current payload schemas. This skill sequences them and supplies the
judgment calls (scope, SLOs, thresholds, what to skip) that no single
skill owns; it deliberately does not restate payload schemas or field
rules, so read the relevant `signoz://…` resource before composing any
payload.

Use this when traces, logs, or metrics are **already landing** in
SigNoz and you want an opinionated, SLO-aware setup — not when you're
still wiring up the SDK. Audience: two consumers — an autonomous AI SRE
agent that runs without a human in the loop (e.g. an in-product SigNoz
assistant), and an engineer at a Claude Code / Codex / Cursor prompt.
Both follow the same flow; where a step needs a human decision (Phase 1
triage, Phase 5 sign-off), the host decides how to surface it, and an
autonomous host fills the gap from upstream context instead of blocking.

## Prerequisites

This skill calls SigNoz MCP server tools (`signoz:signoz_list_services`,
`signoz:signoz_list_dashboards`, `signoz:signoz_get_field_keys`,
`signoz:signoz_execute_builder_query`, `signoz:signoz_create_dashboard`,
`signoz:signoz_create_alert`, `signoz:signoz_create_view`, etc.) and
delegates to sibling skills. Before running the workflow, confirm the
`signoz:signoz_*` tools are available. If they are not, the SigNoz MCP
server is not installed or configured — run `signoz-mcp-setup` first. Do
not fall back to raw HTTP calls or fabricate payloads.

## When to use

Use this skill when the user wants the **whole post-ingestion setup**:
SLI/SLO → exploration → dashboard → views → alerts → tuning, in any
combination of those deliverables, sequenced as one workflow.

Do NOT use this skill when the user wants a single artifact — hand off
directly:
- Just a dashboard → `signoz-creating-dashboards`.
- Just one static / threshold alert or notification rule →
  `signoz-creating-alerts`. (But SLO / burn-rate / error-budget
  alerting — even with no dashboard — stays *here*: it needs the SLI/SLO
  capture and burn-rate judgment in the phases below.)
- Just a saved Explorer view → `signoz-managing-views`.
- A one-off exploratory query → `signoz-generating-queries`.
- A concept/doc lookup (SRE methods, OTel conventions, burn-rate math)
  → `signoz-searching-docs` / `signoz:signoz_search_docs`.

Each phase below points to the skill that does the mechanical work; this
skill owns the order and the decisions.

## Phase 1 — Triage scope (don't skip)

Before touching any tools, get these answers. Each unblocks a downstream
phase.

1. **What does this service do, and does it call external services?**
   One or two sentences. This shapes the SLI (what "working" means) and
   flags downstream dependencies worth monitoring — if it calls a DB,
   cache, queue, or third-party API, plan to watch the client-span
   latency and error rate to each dependency, since a healthy service
   fronting a sick dependency still fails users.
2. **What deliverables?** dashboard / alerts / saved views — any
   combination.
3. **Infra monitoring too? (optional — ask)** If the service runs on
   infra you own (k8s pods, VMs, containers) shipping telemetry under
   the same resource attributes, you can add USE/infra panels (CPU,
   memory, restarts, network) with no extra instrumentation — see Phase
   3. Skip if a platform team already owns the host/cluster dashboard.
4. **Which signals are emitted?** traces / logs / metrics. Drives which
   `signoz:signoz_get_field_keys` calls you make.
5. **What's the canonical resource filter?** Usually `service.name`.
   Confirm the exact value before querying — don't guess.
6. **What does success look like for users of this service?** (Sets up
   Phase 2.) Even a one-line answer ("requests under 1s with no 5xx") is
   enough — it becomes the SLI.
7. **Who owns it, and is there a runbook?** Owning team, service tier,
   and the prod/staging scope — these become alert labels and
   annotations in Phase 8. Capture a real runbook URL if one exists;
   never invent one.

Offer "explore data first" as an explicit option.

## Phase 1.5 — Inventory what already exists

Each create sub-skill runs its own rigorous duplicate-check when invoked
(`signoz-creating-dashboards` lists dashboards; `signoz-creating-alerts`
paginates alert rules) — don't re-implement that here. The orchestration
value is a single up-front sweep so you *sequence around* what exists
instead of hitting collisions mid-build:

- **Is the service reporting, and under what exact name?**
  (`signoz:signoz_list_services`.) This name is the resource filter every
  later phase reuses — pin it before anything else.
- **Does a dashboard / alert / saved view already exist for it?** If so,
  plan to **extend** it — route to `signoz-modifying-dashboards`,
  `signoz-managing-views`, or `signoz:signoz_update_alert` — rather than
  standing up a parallel one. `signoz-explaining-dashboards` /
  `signoz-explaining-alerts` summarize anything you're inheriting.
- **Is there a notification channel to reuse?** (Carried into Phase 5.)

Learn just enough to decide extend-vs-create per artifact; leave the
exhaustive listing to the sub-skills.

## Phase 2 — Capture the SLI/SLO before designing anything

This is the gating artifact. Without it, alerts become "the metric
crossed a line" instead of "the user-visible error budget is being burnt
fast enough to matter."

Collect:
- **SLI formula** — `good events / valid events`. E.g. *successful
  checkout requests / total checkout requests* (excluding health checks,
  synthetic probes, scanner traffic, and non-user long-poll endpoints).
- **SLO target** — e.g. 99.5% over a 30-day rolling window.
- **Exclusions** — what doesn't count as a valid event (synthetic
  probes, scanner traffic, streaming endpoints).
- **Error budget remaining** — derived from target. Drives burn-rate
  alert math.

Carry these forward — they feed Phase 8 directly. (SLO/burn-rate
background: `signoz-searching-docs`.)

## Phase 3 — Explore what's actually there (RED + USE coverage)

`signoz-generating-queries` owns the exploration itself — the
discover-before-querying rule, every discovery call
(`signoz:signoz_list_metrics`, `signoz:signoz_get_field_keys`,
`signoz:signoz_get_field_values`,
`signoz:signoz_get_service_top_operations`), tool choice, and the
no-data distinction. Drive it to inventory the data; don't restate its
query mechanics here. (`signoz-searching-docs` covers the RED/USE methods
and SigNoz field semantics if you need a refresher.)

The orchestration job is to map what it finds onto **RED** (Request
rate, Errors, Duration) and **USE** (Utilization, Saturation, Errors),
spot the gaps, and make the judgment calls generating-queries doesn't:

**Coverage checklist** (RED for services, USE for infra/resources):

- [ ] **R**ate — request/call rate per operation
- [ ] **E**rrors — error count or rate per operation
- [ ] **D**uration — p50/p95/p99 latency from spans or histograms
- [ ] **U**tilization — CPU, memory, disk, queue depth, pool occupancy (only if you own the infra)
- [ ] **S**aturation — request queue, GC pause, connection pool wait
- [ ] **E**rrors at the resource layer — disk failures, evictions, OOM kills

A missing signal (e.g. no error count) is an **instrumentation gap** —
flag it before building around what's there.

**Span metrics back alerts, not just panels.** When generating-queries
surfaces SigNoz's trace→metrics output (`signoz_calls_total`,
`signoz_latency_*`, DB/external-call span metrics), prefer it as the RED
source for *both* the dashboard and the burn-rate alerts: it's
pre-aggregated and cheap, whereas raw trace aggregation over a long alert
window is expensive and an unstable alert source. (Confirm exact
metric/label names via discovery — don't hardcode.)

**Verify the infra→service join (the USE half).** Don't assume
`service.name` is present on host/container/k8s metrics — they often
carry only `host.name` / `k8s.pod.name` / `k8s.node.name`, and
`k8s.deployment.name` may differ from `service.name`. Have
generating-queries confirm which identity attribute actually joins the
infra metric to this workload, then scope USE panels by that *confirmed*
attribute. If nothing joins, ask the user for the workload selector
rather than guessing.

**Discover downstream topology from traces, not the human's memory**
(Phase 1 Q1). The gotcha worth carrying: client spans are
`kind_string = 'Client'` in the SigNoz v5 schema — *not* `kind`, *not*
`SPAN_KIND_CLIENT` — so verify the field/value, then group by the
populated dependency attribute (`external_http_url` / `http_host` for
HTTP, `db_name` / `db_operation` for databases) to surface every
downstream the service actually calls, including ones the human forgot.

**Multi-tenant note** — if the service serves multiple tenants/regions,
look for a stable non-PII tenant/region attribute (e.g. `tenant.id`,
`region`, `deployment.environment`) — avoid raw URLs or user
identifiers. Per-tenant breakdowns belong on the dashboard;
aggregate-only views hide single-tenant outages.

**SLI hygiene** — confirm the events your SLI counts carry the right
labels. For a broad denominator ("all requests to the service"), scanner
traffic on `/.env*`, `/.git*` is real but should be **excluded** — it's
not user traffic. The exclusion predicate should *only subtract scanners*
and stay neutral otherwise, so use the **bare** negation —
`<url_or_route_field> NOT REGEXP '/\\.(env|git|aws|ssh|well-known)'` —
**not** `EXISTS AND …`. SigNoz negative operators also match rows where
the field is *absent*, so fieldless valid events (non-HTTP spans,
internal ops) stay counted; let the SLI's own scope filter
(`service.name`, `http.route`) define the event universe, not the
scanner predicate. (Pair `EXISTS` with a negation only for the *opposite*
intent — excluding a specific value among rows that have the field, e.g.
`service.name EXISTS AND service.name != 'redis'`.) A well-scoped SLI
already excludes scanner paths, so this mainly bites service-wide ratios.
Keep a separate security view if you care about scanners.

## Phase 4 — Classify labels by cardinality and cost

Before wiring labels into queries, classify each. Wrong classification
is the #1 source of metric-bill explosions and dashboard unreadability.

| Class | Cardinality | Where it goes |
|---|---|---|
| Routing | <20 | Alert label, inhibition rule, notification policy (e.g. `severity`, `team`) |
| Variable | <100, human-readable | Dashboard variable (e.g. `environment`, `tenant`) |
| Breakdown | <500 typically | groupBy on graphs / tables (e.g. `gen_ai.tool.name`) |
| Trace/log-only | Unbounded | Only on traces or logs — never on metric series |

Never let raw URLs, query strings, user IDs, session IDs, or request IDs
end up as metric labels — they explode cardinality and the bill. Those
belong on traces/logs.

Cardinality matters more for *cost* than for *display performance* —
SigNoz/ClickHouse handles 100s of variable values fine; the limit is
human readability of the dropdown.

## Phase 5 — Confirm channels, burn-rate windows, recovery thresholds

Lock in before creating alerts:

1. **Notification routing.** Decide *which* channel each severity tier
   routes to (e.g. critical → PagerDuty, warning → Slack). Reuse an
   existing channel from `signoz:signoz_list_notification_channels` where
   one fits; never invent a name. The actual channel resolution/creation
   and secret handling are owned by `signoz-creating-alerts` (Phase 8) —
   here you only lock the tier→channel mapping.
2. **Burn-rate windows.** Common starting points for a 99.9% SLO over a
   30-day budget:

   | Severity | Burn rate | Long window | Short window | Routing |
   |---|---|---|---|---|
   | Page-now critical | 14.4× | 1h | 5m | PagerDuty |
   | Slow burn warning | 6× | 6h | 30m | Slack |
   | Ticket-level low | 1× | 3d | 6h | Ticket queue |

   The burn-rate multipliers are SLO-independent — for a different
   target, compute each absolute threshold inline as
   `error-rate = burn rate × (1 − SLO)` (e.g. 14.4× → 1.44% at 99.9%).
   `signoz-searching-docs` explains the burn-rate *method*; it can't
   compute your numbers.

   Both windows must trip simultaneously for the alert to fire: the long
   window suppresses brief spikes; the short window gives fast recovery
   so a resolved incident stops paging quickly. (The 6× row is a page in
   the canonical SRE table — routing it to Slack here is a deliberate
   severity downgrade; adjust to your on-call norms.)
3. **Recovery thresholds** (hysteresis). Decide that every numeric alert
   recovers *below* its firing target (e.g. fire at 80%, recover at 70%)
   to prevent boundary flapping — `signoz-creating-alerts` carries this
   into the `recoveryTarget` field.

Surface these as a clarification with concrete proposed values, using
the host application's question/UI mechanism (a structured clarification
tool, inline tags, an interactive prompt — follow the host's rules).
Never ask open-ended "what threshold do you want?" — propose, let the
user adjust.
Get explicit sign-off on scope and thresholds before building. Flag
baselines that affect thresholds ("current error rate is 5.1%, so a
static 5% alert will be noisy — proposing a burn-rate alert instead").

## Phase 6 — Build the dashboard(s)

Hand off to `signoz-creating-dashboards` — it owns templates, the
layout/variable/OTel-naming defaults, the v5 schema and its gotchas, the
no-data probe, and the mandatory per-panel dry-run (`signoz-modifying-dashboards`
for later edits). Do **not** restate panel JSON or grid mechanics here;
pass intent and let that skill build.

**Prefer several focused dashboards over one large one.** Since
`signoz-creating-dashboards` builds one dashboard per call — and its
template catalog is already organized per technology — the orchestration
decision is *which set of boards to compose*. Default to splitting by
category/audience and invoking the sub-skill once per board:

- **Service / RED (APM):** KPI tiles + request rate, errors,
  p50/p95/p99. The primary on-call board.
- **Infra / USE:** CPU, memory, restarts, network — only if infra
  monitoring was opted into (Phase 1 Q3), scoped by the attribute
  *confirmed* in Phase 3. Usually a stock template (`hostmetrics`,
  `k8s`) imported as its own board.
- **Downstream dependencies:** client-span p99 + error rate per
  dependency — only if the service has external deps (Phase 1 Q1),
  grouped by the attribute found in Phase 3 (`external_http_url` /
  `db_name`).
- **Business / SLO:** the SLI ratio and error budget, with a per-tenant
  breakdown if multi-tenant (Phase 3) — aggregate-only panels hide
  single-tenant outages.

Splitting keeps each board fast, single-purpose, and ownable by the
right audience (SRE vs app dev vs platform). **Collapse into one board
only when the split would otherwise yield several near-empty ones** — a
small service's handful of panels reads better as rows on one board than
as four 2-panel dashboards. Each board still passes the Phase 1.5
extend-vs-create check, so you reuse an existing board rather than adding
a parallel one.

**Quality bar (every board you create):** production config for a 3am
responder — each panel earns a "what to watch for" description and a
drill-down, and each dashboard earns a top-of-page "start here". Pass
this as intent so `signoz-creating-dashboards` applies it.

## Phase 7 — Saved Explorer views

Hand off to `signoz-managing-views` for the create mechanics (it owns
the view payload and the `extraData`/`selectColumns` shape). The
orchestration value is *which* views to stand up — cheaper than panels
and high-leverage mid-incident:

- ERROR/FATAL logs for the service.
- API request list — the Traces *list* view over server spans
  (`kind_string = 'Server'`, verify per Phase 3): a per-request table
  surfacing service / operation (or `http.route`) /
  `http.response.status_code` / duration / `trace_id`. The fastest "what
  are my endpoints doing right now" surface — sortable by latency or
  status, one click to the full trace, and the broad view that the
  failing/slow-span views below are just filtered subsets of.
- Failing spans for the canonical operation (`has_error = true`).
- Slow spans (`duration_nano > <threshold>`).
- Failed sub-flows (e.g. OAuth requests with errors).
- Correlation drill-downs — error logs carrying `trace_id` (a log spike
  jumps straight to the trace) and slow/error traces that link back to
  their logs.

Two cross-phase constraints to pass along: every view carries the same
environment/tenant filter as the dashboard (so `prod` and `staging` rows
never mix), and the selected columns pass the same PII / no-identifiers
gate as Phase 4.

## Phase 8 — Alerts

`signoz-creating-alerts` owns every per-alert mechanic — channel
resolution (create-first with a test message, name-not-UUID, secret
handling), severity defaults, `op`/`matchType`, units, annotations,
`evalWindow`/`recoveryTarget`, anomaly-rule shape, and the mandatory
dry-run. Drive it once per alert and don't restate any of that here.
(`signoz-explaining-alerts` reads a rule back; `signoz-investigating-alerts`
does RCA once one fires.)

What this orchestration layer adds on top of that skill:

- **SLI-bound alerts are burn-rate pairs, not static thresholds.** A
  static threshold on a ratio flaps; the burn-rate pair is the default
  for anything tied to the Phase 2 SLO.
- **The burn-rate recipe** (the one thing `signoz-creating-alerts`
  can't derive without the SLO). Hand it the *inputs*, not a rule shape:
  the bad/total event definition (prefer the Phase-3 `signoz_calls_total`
  error/total split over raw trace aggregation), the long+short window
  lengths from Phase 5, and the firing target `burnRate × (1 − SLO)`.
  Two judgment calls travel with those inputs — the long and short
  windows must be evaluated as **one rule that ANDs both** (two
  independent rules page on every short spike; if the SigNoz version
  can't express the short-window confirmation in a single rule, ship the
  long window alone and *say so*), and if no clean bad/total split
  exists in the ingested data, burn-rate isn't buildable yet — fall back
  to a baseline-tuned threshold rather than emit a broken rule. Let
  `signoz-creating-alerts` + `signoz://alert/*` pick the
  version-correct rule shape. Note that creating-alerts' "would have
  fired N times in the last 1h" calibration can't grade a 6h/3d
  burn-rate window — don't read a "fired 0 times" there as tuned; the
  Phase 9 re-tune-after-a-week loop is the real calibration.
- **Burn-rate only covers ratio SLIs — schedule the non-ratio failure
  modes too.** A service that stops emitting, or whose traffic
  collapses, never burns error budget (the SLI ratio is undefined at
  zero volume), so the burn-rate pair pages no one. A complete setup
  adds a telemetry-presence / absent-data alert on the primary signal,
  and treats traffic/throughput as its own signal. Hand these intents
  to `signoz-creating-alerts` — it owns the rule shape (absent-data,
  anomaly, threshold) and the healthy-zero handling; the orchestration
  decision is only that they belong in the package.
- **Batch + sequence.** Resolve/confirm the channel (Phase 5 mapping)
  before any rule references it, then create the alerts as a batch
  grouped by routing tier — not one rule per metric.
- **Manual-TODO boundary.** Inhibition rules, org-level notification
  policies (`usePolicy: true` only *opts into* one), and maintenance
  windows are configured in the SigNoz UI / Terraform — these tools
  don't create them. Flag as TODO; never report them done.

## Phase 9 — Hand off

Hand back to the human:
- Dashboard ID(s), view IDs, alert IDs. Don't synthesize frontend URLs —
  return IDs and let the UI resolve them.
- Open questions you couldn't resolve — hand them over as explicit
  TODOs.
- Baselines that may need tuning (e.g. "tool error rate is 5.1% today;
  burn-rate alert tuned for 99% SLO will fire occasionally — re-tune
  after a week of data").

## What to avoid

- **Inventing channel names or webhook URLs.** Ask.
- **Static thresholds for SLI-bound alerts.** Burn-rate pairs are the
  modern default; static thresholds for ratios produce flap.
- **Wrong-sizing dashboards.** Don't cram 18 panels where 12 will do,
  and don't scatter four 2-panel boards where one would read better —
  split by category, then right-size each. Sprawl cuts both ways.
- **Skipping dry-runs to save time.** A 500 at create time is harder to
  debug than at dry-run time.
- **One alert per metric.** Group by routing tier, not per-metric.
- **High-cardinality labels on metric series.** They detonate the bill.
  Move to traces/logs.
- **Synthesizing frontend URLs.** Tools return IDs. Return IDs.
- **Including scanner traffic in SLI denominators.** Real but
  irrelevant. Exclude.
- **Treating exploration findings as throwaway.** Baselines,
  cardinalities, and error counts set your thresholds and tuning
  baseline — don't drop them. Persist them where they survive *any*
  host: bake the numbers into the artifacts (panel/dashboard
  descriptions, alert annotations) and the Phase 9 hand-off, all of
  which live in SigNoz. Don't rely on a local notes file.
- **Letting AI-written instrumentation ship unaudited.** Spot-check what
  is actually emitted before designing dashboards around it.
