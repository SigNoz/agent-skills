# SigNoz Agent Skills

Official SigNoz skills for Claude Code, Cursor, and the `skills.sh` ecosystem.

This repository keeps the SigNoz skills in one canonical location and exposes them through Claude and Cursor plugin manifests plus the standard Agent Skills layout.

## Available Skills

| Skill | Description |
|-------|-------------|
| [signoz-clickhouse-query](plugins/signoz/skills/signoz-clickhouse-query/SKILL.md) | Write optimized ClickHouse queries for SigNoz OpenTelemetry data to build dashboard panels from traces and logs. |
| [signoz-docs](plugins/signoz/skills/signoz-docs/SKILL.md) | Use official SigNoz docs to answer instrumentation, setup, querying, troubleshooting, deployment, and API questions. |

## Installation

### Claude Code

```sh
/plugin marketplace add SigNoz/agent-skills
/plugin install signoz@signoz-skills
```

To update after new releases:

```sh
/plugin marketplace update
/plugin update signoz@signoz-skills
```

### Cursor Plugin

This repository includes a Cursor marketplace manifest at `.cursor-plugin/marketplace.json` and a Cursor plugin manifest at `plugins/signoz/.cursor-plugin/plugin.json`.

For repository-backed distribution:

1. Add `https://github.com/SigNoz/agent-skills` as a Cursor team marketplace.
2. Install the `signoz` plugin from that marketplace.

For local development, use `plugins/signoz/` as the plugin root.

Claude Code and Cursor both point at the same `plugins/signoz/skills/` directory, so there is no duplicated skill content to maintain.

### `skills.sh`

Install all SigNoz skills:

```sh
npx skills add SigNoz/agent-skills
```

Install a specific skill:

```sh
npx skills add SigNoz/agent-skills --skill signoz-docs
npx skills add SigNoz/agent-skills --skill signoz-clickhouse-query
```

## IDs

- **Marketplace id**: `signoz-skills`
- **Plugin id**: `signoz`
- **Cursor plugin root**: `plugins/signoz`
- **Repository**: `SigNoz/agent-skills`

Reserve `signoz` for the primary official SigNoz plugin. Add more installable plugins only when they need a genuinely separate audience or release cadence.

## Repository Structure

```text
.
├── .claude-plugin/
│   └── marketplace.json
├── .cursor-plugin/
│   └── marketplace.json
├── plugins/
│   ├── signoz/
│   │   ├── .claude-plugin/
│   │   │   └── plugin.json
│   │   ├── .cursor-plugin/
│   │   │   └── plugin.json
│   │   └── skills/
│   │       ├── signoz-clickhouse-query/
│   │       └── signoz-docs/
└── README.md
```

## Creating New Skills

Skills in this repository should follow the [Agent Skills specification](https://agentskills.io/specification) and live under `plugins/signoz/skills/<skill-name>/SKILL.md`.

Use Anthropic's [skill-creator](https://skills.sh/anthropics/skills/skill-creator) as the default workflow for creating or evolving a skill. It helps draft the skill, refine trigger descriptions, and iterate with realistic evaluations.

Install it with:

```sh
npx skills add https://github.com/anthropics/skills --skill skill-creator
```

For a new SigNoz skill:

```text
plugins/signoz/skills/my-skill/
└── SKILL.md
```

Keep these conventions:

- `name` in frontmatter must exactly match the directory name.
- `description` should explain both what the skill does and when it should trigger.
- Keep `SKILL.md` concise and move deeper reference material into `references/`, `scripts/`, or `assets/` when needed.
- Bump `plugins/signoz/.claude-plugin/plugin.json` whenever a skill or other plugin-shipped content changes so Claude Code users receive updates.
- Bump `plugins/signoz/.cursor-plugin/plugin.json` whenever the Cursor plugin ships updated skill content.

## License

MIT. See [LICENSE](./LICENSE).

## Example Usage

<img width="727" height="611" alt="image" src="https://github.com/user-attachments/assets/57768ec6-dbb4-420b-b479-271734e0856f" />

<img width="718" height="500" alt="image" src="https://github.com/user-attachments/assets/09b688f8-0d53-467b-978e-8883d600d5e5" />
