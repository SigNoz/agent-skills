# SigNoz Agent Skills

Official SigNoz skills for Claude Code, Codex, Cursor, and the [skills.sh](https://skills.sh) ecosystem.

## Skills

| Skill | Description |
|-------|-------------|
| [signoz-creating-alerts](plugins/signoz/skills/signoz-creating-alerts/SKILL.md) | Create SigNoz alert rules for threshold breaches, error rates, latency, anomaly detection, and absent-data conditions across metrics, logs, and traces. |
| [signoz-explaining-alerts](plugins/signoz/skills/signoz-explaining-alerts/SKILL.md) | Explain and interpret an existing SigNoz alert rule's configuration, evaluation behavior, notification routing, and recent fire frequency. |
| [signoz-investigating-alerts](plugins/signoz/skills/signoz-investigating-alerts/SKILL.md) | Diagnose why a SigNoz alert fired by correlating its signal with neighbor metrics, traces, and logs around the fire window, and ranking likely causes. |
| [signoz-explaining-dashboards](plugins/signoz/skills/signoz-explaining-dashboards/SKILL.md) | Explain panels, queries, and layout of an existing SigNoz dashboard. |
| [signoz-modifying-dashboards](plugins/signoz/skills/signoz-modifying-dashboards/SKILL.md) | Modify an existing SigNoz dashboard: add, remove, or edit panels, variables, queries, and layout. |
| [signoz-generating-queries](plugins/signoz/skills/signoz-generating-queries/SKILL.md) | Generate queries against SigNoz observability data (traces, logs, metrics). |
| [signoz-writing-clickhouse-queries](plugins/signoz/skills/signoz-writing-clickhouse-queries/SKILL.md) | Optimized ClickHouse queries for SigNoz OpenTelemetry traces and logs. |
| [signoz-searching-docs](plugins/signoz/skills/signoz-searching-docs/SKILL.md) | SigNoz docs guidance for instrumentation, setup, querying, alerts, and APIs. |
| [signoz-managing-views](plugins/signoz/skills/signoz-managing-views/SKILL.md) | Create, list, inspect, update, or delete SigNoz saved Explorer views (logs, traces, metrics) via the SigNoz MCP server. |

## Installation

### Claude Code

```sh
/plugin marketplace add SigNoz/agent-skills
/plugin install signoz@signoz-skills
```

Update:

```sh
/plugin marketplace update
/plugin update signoz@signoz-skills
```

> The plugin ships a `PreToolUse` hook that auto-allows `WebFetch` to `signoz.io` domains. This does not affect `Bash`-based network calls (`curl`, `wget`), which follow the normal permission flow.

### Codex

1. Open the repository in Codex (restart if already running).
2. Run `/plugins` and install `signoz` from the `SigNoz` marketplace.

To use in another repo, copy `plugins/signoz` into the target repo's `plugins/` directory and add a marketplace entry in `$REPO_ROOT/.agents/plugins/marketplace.json`.

### Cursor

Not yet on the public Cursor Marketplace. Install via a Team Marketplace:

1. Add `https://github.com/SigNoz/agent-skills` as a team marketplace in `Settings -> Plugins`.
2. Install the `signoz` plugin from the marketplace panel.

### skills.sh

```sh
npx skills add SigNoz/agent-skills                                   # all skills
npx skills add SigNoz/agent-skills --skill signoz-searching-docs                # specific skill
npx skills add SigNoz/agent-skills --skill signoz-writing-clickhouse-queries    # specific skill
```

## Repository Structure

```text
.
├── .agents/plugins/marketplace.json        # Codex marketplace
├── .claude-plugin/marketplace.json         # Claude Code marketplace
├── .cursor-plugin/marketplace.json         # Cursor marketplace
├── plugins/signoz/
│   ├── .codex-plugin/plugin.json           # Codex plugin manifest
│   ├── .claude-plugin/plugin.json          # Claude Code plugin manifest
│   ├── .cursor-plugin/plugin.json          # Cursor plugin manifest
│   ├── hooks/                              # Auto-allow hooks
│   └── skills/
│       ├── signoz-creating-alerts/
│       ├── signoz-explaining-alerts/
│       ├── signoz-investigating-alerts/
│       ├── signoz-writing-clickhouse-queries/
│       ├── signoz-explaining-dashboards/
│       ├── signoz-modifying-dashboards/
│       ├── signoz-searching-docs/
│       ├── signoz-generating-queries/
│       └── signoz-managing-views/
└── README.md
```

| ID | Value |
|----|-------|
| Marketplace | `signoz-skills` |
| Plugin | `signoz` |
| Repository | `SigNoz/agent-skills` |
| Versioning | CalVer (`YYYY.MM.DD`) — auto-bumped |

## Contributing

See [CONTRIBUTING.md](./CONTRIBUTING.md).

## License

MIT. See [LICENSE](./LICENSE).
