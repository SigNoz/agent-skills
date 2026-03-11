# SigNoz Skills Marketplace

Official SigNoz skills for Claude Code and the `skills.sh` ecosystem.

This repository publishes the `signoz` Claude Code plugin through the `signoz-skills` marketplace and remains compatible with `agent-skills` / `skills.sh`.

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
- **Repository**: `SigNoz/agent-skills`

Reserve `signoz` for the primary official SigNoz plugin. Add more installable plugins only when they need a genuinely separate audience or release cadence.

## Repository Structure

```text
.
├── .claude-plugin/
│   └── marketplace.json
├── plugins/
│   └── signoz/
│       ├── .claude-plugin/
│       │   └── plugin.json
│       └── skills/
│           ├── signoz-clickhouse-query/
│           └── signoz-docs/
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

## License

MIT. See [LICENSE](./LICENSE).

## Example Usage

<img width="727" height="611" alt="image" src="https://github.com/user-attachments/assets/57768ec6-dbb4-420b-b479-271734e0856f" />

<img width="718" height="500" alt="image" src="https://github.com/user-attachments/assets/09b688f8-0d53-467b-978e-8883d600d5e5" />
