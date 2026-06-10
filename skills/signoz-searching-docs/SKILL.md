---
name: signoz-searching-docs
description: >
  Look up information in SigNoz documentation. Make sure to use this skill
  whenever the user asks "how do I", "where in the docs", "what does the
  docs say about", "find docs for", or otherwise needs reference material
  on SigNoz instrumentation, OpenTelemetry setup, self-hosted deployment,
  API endpoints, auth headers, or troubleshooting steps — even if they
  don't say the word "docs" explicitly. Docs lookup only — for actions
  inside SigNoz, the agent will pick the matching `signoz-*` action skill.
---

# SigNoz Docs

Use official `signoz.io` documentation and API references only. Ground every answer in fetched docs content and cite the canonical docs URL.

## Access Docs

Prefer the SigNoz MCP server tools when available; fall back to direct HTTP fetch.

### Preferred: MCP tools

- `signoz:signoz_search_docs` — BM25 search over the indexed docs corpus. Pass the user's natural-language query as `query`. Narrow with `section_slug` when the question maps cleanly to a single docs section (the tool's own schema lists valid slugs — defer to it rather than memorizing). Trust the ranking — the index handles relevance.
- `signoz:signoz_fetch_doc` — full markdown for one indexed page. Pass the canonical URL or `/docs/...` path; optionally narrow to a section with `heading`.

### Fallback: direct HTTP fetch

If the MCP tools are unavailable, SigNoz docs support `Accept: text/markdown` natively.

Discover via the sitemap:

```
GET https://signoz.io/docs/sitemap.md
```

Fetch a specific page:

```
GET https://signoz.io/docs/<path>/
Accept: text/markdown
```

## Workflow

1. **Identify the domain** from the user's question: instrumentation, OpenTelemetry setup, querying, dashboards, alerts, troubleshooting, deployment, or API docs.
2. **Check the heuristics table below**. If a heuristic matches, read it before answering — heuristics encode product decisions (which path/method fits the user's environment), useful in both paths.
3. **Search and fetch** — pick the path based on tool availability:
   - **With MCP tools**: call `signoz:signoz_search_docs` with the user's query; pass `section_slug` if the domain maps cleanly to one. Read the top 1-3 results and call `signoz:signoz_fetch_doc` on the chosen URL (use `heading` to narrow if the page is large and the question is sub-section-specific).
   - **Without MCP tools**: grep `sitemap.md` for candidate pages, rank the best 2-5 by how directly they answer the task, and `GET` the top page(s) with `Accept: text/markdown`. Heuristic coverage is sparse — for topics without a heuristic row, skim the sitemap by section path and prefer setup/troubleshooting/API-reference pages over overviews.
   - Fetch **one page** for narrow questions; fetch **multiple pages** when the task spans setup + troubleshooting, or method-selection + language guide. Keep the set small.
4. **Answer from the fetched docs** and cite canonical `https://signoz.io/docs/...` URLs.
5. **Handle ambiguity deliberately**: if multiple pages are plausible, prefer the one that completes the task most directly; mention alternates only when they materially change the answer.

## Message Actions

On the terminal answer, emit FE-handoff actions per the SigNoz Skills & MCP spec:

- **`open_docs`** — include with the canonical URL of the primary cited page. Docs lookups are precisely the case where deep-linking to the source page helps the user read in context and verify the answer.
- **`follow_up`** — 1-2 next-step prompts that build on a docs answer. After a setup guide: *"walk me through the first command"* or *"what's a common gotcha here?"*. After a concept page: *"show me a worked example."*
- **Do NOT emit `apply_filter`.** Docs answers do not produce a query for an explorer page; emitting `apply_filter` would overwrite the user's working query.

Verbatim guardrail: *When answering a SigNoz docs question, include an `open_docs` action on the final message with the canonical URL of the primary cited page.*

## Domain Heuristics

Read the matching heuristic file **before** fetching docs. Each file contains decision logic to route the user to the right guide.

| Topic | Trigger keywords | Heuristic file |
|---|---|---|
| Sending Logs | logs, log collection, logging, send logs | [sending-logs.md](./heuristics/sending-logs.md) |
