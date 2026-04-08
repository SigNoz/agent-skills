# SigNoz Agent Skills

Official SigNoz skills for Claude Code, Codex, Cursor, and the [skills.sh](https://skills.sh) ecosystem.

## Skills

| Skill | Description |
|-------|-------------|
| [signoz-clickhouse-query](plugins/signoz/skills/signoz-clickhouse-query/SKILL.md) | Optimized ClickHouse queries for SigNoz OpenTelemetry traces and logs. |
| [signoz-docs](plugins/signoz/skills/signoz-docs/SKILL.md) | SigNoz docs guidance for instrumentation, setup, querying, alerts, and APIs. |

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
npx skills add SigNoz/agent-skills --skill signoz-docs                # specific skill
npx skills add SigNoz/agent-skills --skill signoz-clickhouse-query    # specific skill
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
│       ├── signoz-clickhouse-query/
│       └── signoz-docs/
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
