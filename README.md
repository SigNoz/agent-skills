# SigNoz Agent Skills

Official SigNoz skills and MCP configuration for Claude Code, Codex, Cursor,
and the [skills.sh](https://skills.sh) ecosystem. The MCP setup skill also
includes client-specific recipes for VS Code/GitHub Copilot, Claude Desktop,
Gemini CLI, Windsurf, Zed, Antigravity, OpenCode, and generic HTTP MCP
clients.

## Skills

| Skill | Description |
|-------|-------------|
| [signoz-mcp-setup](plugins/signoz/skills/signoz-mcp-setup/SKILL.md) | Initialize or repair the SigNoz MCP server configuration for Claude Code, Codex, Cursor, VS Code/GitHub Copilot, Claude Desktop, Gemini CLI, Windsurf, Zed, Antigravity, OpenCode, or another MCP client. |
| [signoz-creating-alerts](plugins/signoz/skills/signoz-creating-alerts/SKILL.md) | Create SigNoz alert rules for threshold breaches, error rates, latency, anomaly detection, and absent-data conditions across metrics, logs, and traces. |
| [signoz-explaining-alerts](plugins/signoz/skills/signoz-explaining-alerts/SKILL.md) | Explain and interpret an existing SigNoz alert rule's configuration, evaluation behavior, notification routing, and recent fire frequency. |
| [signoz-investigating-alerts](plugins/signoz/skills/signoz-investigating-alerts/SKILL.md) | Diagnose why a SigNoz alert fired by correlating its signal with neighbor metrics, traces, and logs around the fire window, and ranking likely causes. |
| [signoz-creating-dashboards](plugins/signoz/skills/signoz-creating-dashboards/SKILL.md) | Create a new SigNoz dashboard from a natural-language intent — import a curated template (PostgreSQL, Redis, JVM, k8s, APM, LLM, etc.) when one fits, or build a custom dashboard with metric, trace, and log panels. |
| [signoz-explaining-dashboards](plugins/signoz/skills/signoz-explaining-dashboards/SKILL.md) | Explain panels, queries, and layout of an existing SigNoz dashboard. |
| [signoz-modifying-dashboards](plugins/signoz/skills/signoz-modifying-dashboards/SKILL.md) | Modify an existing SigNoz dashboard: add, remove, or edit panels, variables, queries, and layout. |
| [signoz-generating-queries](plugins/signoz/skills/signoz-generating-queries/SKILL.md) | Generate queries against SigNoz observability data (traces, logs, metrics). |
| [signoz-writing-clickhouse-queries](plugins/signoz/skills/signoz-writing-clickhouse-queries/SKILL.md) | Optimized ClickHouse queries for SigNoz OpenTelemetry traces and logs. |
| [signoz-searching-docs](plugins/signoz/skills/signoz-searching-docs/SKILL.md) | SigNoz docs guidance for instrumentation, setup, querying, alerts, and APIs. |
| [signoz-managing-views](plugins/signoz/skills/signoz-managing-views/SKILL.md) | Create, list, inspect, update, or delete SigNoz saved Explorer views (logs, traces, metrics) via the SigNoz MCP server. |

## Installation

The Claude Code, Codex, and Cursor plugins ship with MCP registration files
plus an MCP setup skill so users do not have to hand-edit MCP configuration.
After installing, run `signoz-mcp-setup` once if the MCP server is not already
connected. It accepts a SigNoz Cloud region such as `us`, `us2`, `eu`, `eu2`,
`in`, or `in2`, any hosted MCP URL, or a self-hosted HTTP `/mcp` endpoint.

See the full setup guide in the [SigNoz MCP Server docs](https://signoz.io/docs/ai/signoz-mcp-server/).

### Claude Code

```sh
/plugin marketplace add SigNoz/agent-skills
/plugin install signoz@signoz-skills
```

Then run `/mcp`, select the `signoz` server, and complete the authentication flow.
If the server is not connected yet, ask Claude Code to run `signoz-mcp-setup` first.

Update:

```sh
/plugin marketplace update
/plugin update signoz@signoz-skills
```

> The plugin ships a `PreToolUse` hook that auto-allows `WebFetch` to `signoz.io` domains. This does not affect `Bash`-based network calls (`curl`, `wget`), which follow the normal permission flow.

### Codex

1. Open the repository in Codex (restart if already running).
2. Run `/plugins` and install `signoz` from the `SigNoz` marketplace.
3. Ask Codex to run `signoz-mcp-setup` with your SigNoz Cloud region or
   self-hosted HTTP MCP URL. This updates the bundled `.mcp.json` placeholder
   used by the Codex plugin.
4. Restart Codex if the `signoz` MCP server does not appear.
5. Run `codex mcp login signoz`, then `/mcp` to verify the connection.

The Codex plugin already declares `mcpServers: "./.mcp.json"`, so normal plugin
installs do not need a separate native Codex MCP entry. To use in another repo,
copy `plugins/signoz` into the target repo's `plugins/` directory, add a
marketplace entry in `$REPO_ROOT/.agents/plugins/marketplace.json`, and repeat
the setup step for that workspace.

### Cursor

Not yet on the public Cursor Marketplace. Install via a Team Marketplace:

1. Add `https://github.com/SigNoz/agent-skills` as a team marketplace in `Settings -> Plugins`.
2. Install the `signoz` plugin from the marketplace panel.
3. Enter the MCP URL for your SigNoz Cloud region when prompted, such as
   `https://mcp.us2.signoz.cloud/mcp`. For self-hosted HTTP mode, enter your
   server's `/mcp` URL, such as `http://localhost:8000/mcp`.
4. Open Cursor's MCP settings and complete authentication for the `signoz` server if prompted.

If you skipped the prompt, picked the wrong region, or need to change a
self-hosted HTTP MCP endpoint, run `/signoz-mcp-setup` in an agent chat
window. If Cursor keeps using the install-time URL, clear the SigNoz MCP URL
plugin setting and reload.

### Other MCP Clients

The setup skill includes native config recipes for VS Code/GitHub Copilot,
Claude Desktop, Gemini CLI, Windsurf, Zed, Antigravity, OpenCode, and generic
HTTP MCP clients. These clients do not all consume this plugin automatically;
install or copy the skill where your client supports skills, or use the
client-specific setup snippets in the skill as a reference.

For SigNoz Cloud, prefer the hosted MCP URL and client OAuth flow. For
self-hosted SigNoz, the skill supports HTTP `/mcp` endpoints and stdio
local-binary recipes. It avoids writing API keys into tracked project files.

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
│   ├── .mcp.json                           # Claude Code and Codex MCP config
│   ├── mcp.json                            # Cursor MCP config
│   ├── hooks/                              # Auto-allow hooks
│   └── skills/
│       ├── signoz-mcp-setup/
│       │   └── references/                 # Endpoint mapping and client recipes
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
