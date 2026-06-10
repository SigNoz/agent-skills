# SigNoz Agent Skills

Official SigNoz skills and MCP configuration for Claude Code, Codex, Cursor,
Gemini CLI, and the [skills.sh](https://skills.sh) ecosystem. The MCP setup skill also
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
| [signoz-setting-up-observability](plugins/signoz/skills/signoz-setting-up-observability/SKILL.md) | Orchestrate the full post-ingestion observability setup for a service — SLI/SLO capture, RED/USE exploration, focused dashboards, saved views, burn-rate and absent-data alerts, and a tuning loop — sequencing the single-artifact skills into one SLO-aware workflow. |

## Installation

The Claude Code, Codex, and Cursor plugins ship with MCP registration files
plus an MCP setup skill so users do not have to hand-edit MCP configuration.
After installing, run `signoz-mcp-setup` once if the MCP server is not already
connected. It accepts a SigNoz Cloud region such as `us`, `us2`, `eu`, `eu2`,
`in`, or `in2`, any hosted MCP URL, or a self-hosted HTTP `/mcp` endpoint.
Plugin updates can reset bundled MCP registration files to the placeholder; if
that happens, rerun `signoz-mcp-setup`.

See the full setup guide in the [SigNoz MCP Server docs](https://signoz.io/docs/ai/signoz-mcp-server/).

### Claude Code

```sh
/plugin marketplace add SigNoz/agent-skills
/plugin install signoz@signoz-skills
```

On install, Claude Code prompts for your **SigNoz Cloud Region** (defaults to
`us`; one of `us`, `us2`, `eu`, `eu2`, `in`, `in2`). The bundled MCP config fills
this into the hosted endpoint `https://mcp.<region>.signoz.cloud/mcp`. Find your
region under **Settings -> Ingestion** in SigNoz, or see the
[region reference](https://signoz.io/docs/ingestion/signoz-cloud/keys/).

The install dialog also asks **Self-hosted SigNoz?** Type `yes` if you run your
own SigNoz instead of SigNoz Cloud (leave it blank or type `no` for Cloud). When
set to `yes`, the region is ignored, and at the next session start the plugin
reminds you to point it at your instance — run `signoz-mcp-setup` with your
self-hosted HTTP `/mcp` URL (for example `http://localhost:8000/mcp`).

> **The reminder fires on session start, not at install time.** Because you
> install the plugin mid-session, its `SessionStart` hook has no session-start
> event to fire on yet. Start a new session to trigger it: run `/clear`, restart
> Claude Code, or resume with `/resume` (or `claude --continue`). The reminder
> then appears immediately at the start of the new session — no prompt needed.

To change the region later, reconfigure the plugin's options or run
`signoz-mcp-setup`.

Then run `/mcp`, select the `signoz` server, and complete the authentication flow.
For a self-hosted SigNoz, or to set the endpoint explicitly, ask Claude Code to
run `signoz-mcp-setup`.

Update:

```sh
/plugin marketplace update
/plugin update signoz@signoz-skills
```

> The plugin ships a `PreToolUse` hook that auto-allows `WebFetch` to `signoz.io` domains. This does not affect `Bash`-based network calls (`curl`, `wget`), which follow the normal permission flow. It also ships a `SessionStart` hook that, only when **Self-hosted SigNoz?** is set to `yes` and the MCP endpoint still points at SigNoz Cloud, shows a reminder to finish setup with `signoz-mcp-setup` as soon as the session starts. Since `SessionStart` hooks only fire at session boundaries, this reminder appears on the next session after install — start one with `/clear`, a restart, or `/resume`.

### Codex

```sh
codex plugin marketplace add SigNoz/agent-skills
```

Then, in a Codex session started from your project:

1. Run `/plugins`, open the `SigNoz` marketplace, and install `signoz`.
2. Run `signoz-mcp-setup <region>` with your SigNoz Cloud region (`us`, `us2`,
   `eu`, `eu2`, `in`, `in2`) or a self-hosted HTTP MCP URL. This rewrites the
   bundled `.mcp.json` placeholder used by the Codex plugin to a concrete
   endpoint.
3. Authenticate the MCP server over OAuth:

   ```sh
   codex mcp login signoz
   ```

   Complete the browser flow with your SigNoz instance URL and a service account
   API key.
4. Verify the connection:

   ```sh
   codex mcp list   # signoz -> enabled, Auth = logged in
   ```

   or run `/mcp` in a session, then call any `signoz_*` tool. Restart Codex if
   the `signoz` server does not appear.

The Codex plugin declares `mcpServers: "./.mcp.json"`, so normal plugin installs
do not need a separate native Codex MCP entry. To use in another repo, copy
`plugins/signoz` into the target repo's `plugins/` directory, add a marketplace
entry in `$REPO_ROOT/.agents/plugins/marketplace.json`, and repeat the setup
step for that workspace.

### Cursor

Not yet on the public Cursor Marketplace. Install via a Team Marketplace:

1. Add `https://github.com/SigNoz/agent-skills` as a team marketplace in `Settings -> Plugins`.
2. Install the `signoz` plugin from the marketplace panel.
3. Run `/signoz-mcp-setup` in an agent chat with your SigNoz Cloud region or
   self-hosted HTTP MCP URL. This updates the bundled `.signoz_cursor_mcp.json`
   placeholder used by the Cursor plugin.
4. Reload Cursor, then open MCP settings and complete authentication for the
   `signoz` server if prompted.

If you picked the wrong region or need to change a self-hosted HTTP MCP
endpoint, run `/signoz-mcp-setup` again with the correct region or URL and
reload Cursor.

### Gemini CLI

```sh
gemini extensions install https://github.com/SigNoz/agent-skills
```

When prompted, enter your SigNoz Cloud region (`us`, `us2`, `eu`, `eu2`, `in`, or `in2`).

Then authenticate:

```
/mcp auth signoz
```

Follow the prompts to enter your SigNoz instance URL and API key.

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
├── gemini-extension.json                   # Gemini CLI extension manifest
├── skills -> plugins/signoz/skills         # Gemini CLI skills (symlink)
├── plugins/signoz/
│   ├── .codex-plugin/plugin.json           # Codex plugin manifest
│   ├── .claude-plugin/plugin.json          # Claude Code plugin manifest
│   ├── .cursor-plugin/plugin.json          # Cursor plugin manifest
│   ├── .signoz_claude_mcp.json             # Claude Code MCP config
│   ├── .mcp.json                           # Codex MCP config
│   ├── .signoz_cursor_mcp.json             # Cursor MCP config
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
