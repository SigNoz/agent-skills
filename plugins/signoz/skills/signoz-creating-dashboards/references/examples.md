# Examples — `signoz-creating-dashboards`

Walkthroughs of the four canonical flows: template import with data,
template import without data, duplicate-found choice, and custom build.

## Template import — happy path

**User:** "Create a dashboard for my PostgreSQL database"

**Agent:**
1. `signoz:signoz_list_dashboards` (paginated) → no PostgreSQL
   dashboard exists.
2. Says: "I'll create a new dashboard for PostgreSQL. Proceed?" User
   confirms.
3. `signoz:signoz_list_dashboard_templates` → picks
   `postgresql/postgresql.json`. Tells user: "I found a pre-built
   PostgreSQL template and will use it."
4. No-data probe: `signoz:signoz_list_metrics searchText="postgresql"`
   → returns `postgresql.connections.usage`, `postgresql.commits`, etc.
   Data flowing.
5. Calls `signoz:signoz_import_dashboard path=postgresql/postgresql.json`.
6. Reports: "Created 'PostgreSQL Overview' (UUID `…`) — 24 panels
   across Overview / Connections / Throughput / Replication. Variables:
   `postgresql.host.name`. Probe found data for all headline panels.
   Want me to adjust anything, or wire alerts for slow queries?"

*Variant — no PG data ingested:* the probe in step 4 returns empty;
agent emits the verbatim no-data warning from Step 3b-i.1 and waits for
the user to choose between "create anyway" and "stop".

## Template choice when several match

**User:** "I need an APM dashboard — what do you have?"

**Agent:**
1. `signoz:signoz_list_dashboards` (paginated) → no APM dashboard.
2. Says: "I'll create a new APM dashboard. Want me to show you what
   templates we have first?" User: yes.
3. `signoz:signoz_list_dashboard_templates` → reads the full catalog
   in-context, filters to APM entries (APM RED, APM Errors, etc.).
4. Presents the list and asks which to import. User picks "APM RED".
5. No-data probe: `signoz:signoz_aggregate_traces aggregation=count
   timeRange=1h` → returns rows. Data flowing.
6. Imports, reports panels and variables. Offers to wire latency
   alerts via `signoz-creating-alerts`.

## Duplicate found — modify-or-create

**User:** "Set up monitoring for Redis" (existing "Redis - Overview"
dashboard found)

**Agent:** surfaces the existing dashboard with UUID and `createdAt`,
asks the user (a) modify / (b) create new / (c) stop. If user picks
(b), follows the PostgreSQL flow above against the `redis/redis.json`
template. If (a), hands off to `signoz-modifying-dashboards` with the
dashboard's UUID and the user's intent (no `signoz:signoz_get_dashboard` call
from this skill).

## Custom build — no template match

**User:** "Create a dashboard to track our payment processing pipeline"
(custom build — no template match)

**Agent:**
1. Duplicate check (none) and creation confirmation as above.
2. `signoz:signoz_list_dashboard_templates` → no match in the catalog.
   Falls through to custom build (Step 3b-ii).
3. Gathers requirements: signals (traces + metrics), which services
   are in the pipeline, variables (`service.name` plus the env key
   that actually exists in the install).
4. Discovery (parallel): `signoz:signoz_get_field_keys signal=traces
   fieldContext=resource` → confirms `service.name` and
   `deployment.environment` (no `.name` suffix in this install);
   `signoz:signoz_get_field_values name=service.name` → user picks
   `checkout`, `payments`, `inventory`, `notifications`.
5. Reads the `signoz://dashboard/*` MCP resources. Builds sections
   Overview / Latency / Errors / Throughput, with headline panels
   (request rate, p99 latency, error rate `A*100/B`, throughput) and
   the two variables.
6. Per-panel dry-run via `signoz:signoz_execute_builder_query` for the
   headline queries (envelope translation per Step 3b-ii.6). Emits
   JSON preview + summary, then calls `signoz:signoz_create_dashboard`.
   Reports UUID, panels, sections, variables, dry-run summary. Offers
   to wire error-rate alerts via `signoz-creating-alerts`.
