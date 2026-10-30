# AI agent and LLM queries

Read this before the first query about LLM calls or AI-agent runs: cost,
tokens, models, tool calls, or AI Observability showing no data. Also read
`signoz://ai/query-builder-guide`. It lists the eight per-trace AI keys, the
rules SigNoz enforces on them, and arguments to copy.

## Choosing the query

- Set `queryType: "builder_ai_query"` for AI trace rows and whenever
  `aggregations`, `filter`, or `orderBy` uses a per-trace AI key, such as
  `trace.estimated_total_cost` or `trace.tool_call_count`. Otherwise keep
  the default.
- Per call (one LLM or tool call): filter or group on `gen_ai.*` span
  attributes, for example `sum(signoz.gen_ai.usage.tokens.cost)` grouped by
  `gen_ai.request.model`. To keep only the calls in some runs, use
  `signoz_search_traces` with `requestType: "raw"` and filter on a per-trace
  AI key, such as `trace.tool_call_count > 10`; span rows then hold only the
  LLM, tool, and agent spans.
- Per trace (one agent run, its total cost, tokens, or call counts): use
  `signoz_search_traces` with `requestType: "trace"` for the runs
  themselves, ordered by a key such as `trace.estimated_total_cost desc`,
  and `signoz_aggregate_traces` for statistics across runs, such as
  `avg(trace.estimated_total_cost)`.
- Discover AI keys with `signoz_get_field_keys(signal: "traces",
  queryType: "builder_ai_query")`; it also lists the per-trace AI keys.

## Aggregation rules

- One `signoz_aggregate_traces` call is either all per-trace AI key
  aggregations or all span aggregations. `count()` and
  `count_distinct(trace_id)` are span aggregations, so count runs in a
  separate call from `avg(trace.estimated_total_cost)`.
- For spend or tokens by model, sum the per-call span attributes
  (`sum(signoz.gen_ai.usage.tokens.cost)` grouped by `gen_ai.request.model`)
  with the default `queryType`. Grouping a per-trace AI key by a span
  attribute splits each run across groups, so one run can appear under
  several models.

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
