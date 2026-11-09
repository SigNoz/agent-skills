# AI agent and LLM queries

Read this before the first query about LLM calls or AI-agent runs: cost,
tokens, models, tool calls, or AI Observability showing no data. Also read
`signoz://ai/query-builder-guide`. It lists the eight per-trace AI keys, the
rules SigNoz enforces on them, and arguments to copy.

## Choosing the query

- The keys decide `queryType`:
  - `gen_ai.*` span attributes only: keep the default `builder_query`.
  - A per-trace AI key, such as `trace.estimated_total_cost` or
    `trace.tool_call_count`, in `aggregations`, `filter`, or `orderBy`, or
    AI trace rows: set `queryType: "builder_ai_query"`.
- Per call (one LLM or tool call), default `queryType`: use
  `signoz_search_traces` with `requestType: "raw"` (the default) for the
  calls themselves, and `signoz_aggregate_traces` for statistics, filtering
  or grouping on `gen_ai.*` span attributes, such as
  `sum(signoz.gen_ai.usage.tokens.cost)` grouped by `gen_ai.request.model`.
  To keep only the calls in some runs, also filter on a per-trace AI key,
  such as `trace.tool_call_count > 10`, and set `builder_ai_query`; span
  rows then hold only the LLM, tool, and agent spans.
- Per trace (one agent run, its total cost, tokens, or call counts),
  `builder_ai_query`: use `signoz_search_traces` with `requestType: "trace"`
  for the runs themselves, ordered by a key such as
  `trace.estimated_total_cost desc`, and `signoz_aggregate_traces` for
  statistics across runs, such as `avg(trace.estimated_total_cost)`.
- Discover AI keys with `signoz_get_field_keys(signal: "traces",
  queryType: "builder_ai_query")`; it also lists the per-trace AI keys.

## Aggregation rules

- One `signoz_aggregate_traces` call is either all per-trace AI key
  aggregations or all span aggregations. `count()` and
  `count_distinct(trace_id)` are span aggregations, so count runs in a
  separate call from `avg(trace.estimated_total_cost)`.
- For spend or tokens by model, sum the per-call span attributes
  (`sum(signoz.gen_ai.usage.tokens.cost)` grouped by `gen_ai.request.model`)
  with the default `queryType`.
- `groupBy` cannot use a per-trace AI key; group by a span attribute such
  as `gen_ai.request.model` or `service.name` instead.

## Results

Relay the notes `builder_ai_query` responses carry, such as cost being a
USD estimate.

- A null or 0 cost means an unpriced model, not zero calls or zero spend.
  List unpriced models with `signoz_get_ai_pricing(view: "unpriced_models")`.
  That view covers only the last hour; if it is empty, compare the models in
  the result with `view: "rules"`.
- An empty AI result in a window with traffic can mean the app's vendor keys
  are not mapped to `gen_ai.*`. Report "no AI traces matched", not "no LLM
  calls", then check the mappings below.

## Missing AI data: attribute mappings

1. List the saved mapping groups with `signoz_list_ai_attribute_mappings`.
2. Take an LLM span's attributes from `signoz_get_trace_details` on one of
   the app's traces and pass them to `signoz_test_ai_attribute_mapping`. A
   span that gains `gen_ai.request.model` is mapped; otherwise its keys show
   what the saved groups miss.
3. To check a fix, pass a draft group in `groups` with `enabled: true`.
4. No MCP tool saves a mapping. Tell the user to add the group on the
   Attribute Mapping tab of AI Observability; mappings apply only to spans
   ingested afterwards. Spans already stored stay queryable with the default
   `queryType` on their own keys.
