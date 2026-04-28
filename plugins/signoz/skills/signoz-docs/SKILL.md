---
name: signoz-docs
description: Look up information in SigNoz documentation. Use this skill when the user asks "how do I", "where in the docs", "what does the docs say about", "find docs for", or otherwise needs reference material on SigNoz instrumentation, OpenTelemetry setup, self-hosted deployment, API endpoints, auth headers, or troubleshooting steps. Do NOT use this skill to perform actions in SigNoz — for creating alerts use signoz-alert-create, explaining alerts use signoz-alert-explain, investigating alert fires use signoz-alert-investigate, creating/explaining/modifying dashboards use signoz-dashboard-*, generating queries use signoz-query-generate, and writing raw ClickHouse SQL for dashboard panels use signoz-clickhouse-query. Docs lookup only.
---

# SigNoz Docs

Use official `signoz.io` documentation and API references only. Ground every answer in fetched docs content and cite the canonical docs URL.

## Access Docs

SigNoz docs support `Accept: text/markdown`. Fetch docs pages as markdown instead of scraping HTML.

### Discover pages

Use the sitemap to search for candidate pages:

```
GET https://signoz.io/docs/sitemap.md
```

### Fetch a page

Fetch any docs page as markdown by requesting it with:

```
GET https://signoz.io/docs/<path>/
Accept: text/markdown
```

For example, to fetch the logs overview page:

```
GET https://signoz.io/docs/logs-management/overview/
Accept: text/markdown
```

## Workflow

1. **Identify the domain** from the user's question: instrumentation, OpenTelemetry setup, querying, dashboards, alerts, troubleshooting, deployment, or API docs.
2. **Check the heuristics table below**. If a heuristic matches, read that file before choosing docs pages.
3. **Search `sitemap.md` for candidate pages** that match the user's product area, environment, language, and task.
4. **Rank the best 2-5 official pages** by how directly they help the user complete the task.
5. **Fetch only the top page(s)** as markdown with `Accept: text/markdown`.
   - Fetch **one page** for narrow questions that map cleanly to a single setup guide, troubleshooting page, or API reference.
   - Fetch **multiple pages** when the task clearly spans multiple needs, such as collection-method selection plus a language guide, setup plus troubleshooting, or overview plus exact API/auth details.
   - Keep the fetch set small and purposeful. Do not fetch loosely related pages just because they share keywords.
6. **Answer from the fetched docs** and cite canonical `https://signoz.io/docs/...` URLs.
7. **Handle ambiguity deliberately**: if multiple pages are plausible, prefer the page that completes the task most directly and mention alternates only when they materially change the answer.

## Ranking Hints

- Prefer setup, troubleshooting, or API-reference pages over overview pages when the user needs an action.
- Prefer pages that match the user's runtime, language, deployment environment, or SigNoz product area.
- For API questions, prefer the exact endpoint/auth/reference page over a general guide.
- Stay within official `signoz.io` docs pages when this skill applies.

## Domain Heuristics

Read the matching heuristic file **before** fetching docs. Each file contains decision logic to route the user to the right guide.

| Topic | Trigger keywords | Heuristic file |
|---|---|---|
| Sending Logs | logs, log collection, logging, send logs | [sending-logs.md](./heuristics/sending-logs.md) |
