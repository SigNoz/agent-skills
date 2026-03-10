# signoz-docs

Agent skill that answers SigNoz questions using official documentation from [signoz.io/docs](https://signoz.io/docs).

## How it works

1. **Docs fetch** — SigNoz docs support `Accept: text/markdown`. The skill teaches the agent to fetch any docs page as clean markdown instead of scraping HTML.
2. **Domain heuristics** — Decision trees that route the user to the right guide before fetching docs. Prevents the agent from jumping to a random guide without understanding the user's setup.

## Structure

```
skills/signoz-docs/
├── SKILL.md              # Entry point — goal, docs-fetch method, workflow, heuristic routing table
├── README.md
└── heuristics/
    └── sending-logs.md   # Log collection method decision tree
```

## Adding a heuristic

1. Create a new file in `heuristics/` (e.g., `sending-traces.md`)
2. Follow the pattern: questions → decision table → gotchas → reference link
3. Add a row to the routing table in `SKILL.md`:

```markdown
| Sending Traces | traces, instrumentation, APM, distributed tracing | [sending-traces.md](./heuristics/sending-traces.md) |
```

## Planned heuristics

- **Sending Traces** — language selection, auto vs manual instrumentation
- **Sending Metrics** — application metrics vs infrastructure vs Prometheus
- **Troubleshooting** — data not showing up, collector issues, common errors
