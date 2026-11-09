# SigNoz MCP Client Config Reference

Use this reference after resolving the SigNoz MCP endpoint in
[mcp-settings.md](mcp-settings.md). It mirrors the client setup patterns in the
SigNoz MCP Server docs and adds OpenCode's native config shape.

## Contents

- [Safety Rules](#safety-rules)
- [Cloud or Self-Hosted HTTP](#cloud-or-self-hosted-http)
- [Header-Based Auth Fallback](#header-based-auth-fallback)
- [Self-Hosted Stdio](#self-hosted-stdio)
- [Authentication Finish Steps](#authentication-finish-steps)

## Safety Rules

- Keep each file's existing server key. The plugin-root `mcp.json` used by
  Agent Plugins v1 and Codex, the bundled Cursor file, and native client
  configs use `signoz`; the bundled Claude Code file
  (`.signoz_claude_mcp.json`) uses `mcp`. Do not rename either key. Leave the
  Claude file's `${user_config.SIGNOZ_MCP_URL}` placeholder intact and update
  the persisted plugin option instead. In the portable file, also preserve the
  canonical `$schema` and `type: "streamable-http"`.
- Prefer SigNoz Cloud OAuth over header-based auth whenever the client supports
  interactive OAuth.
- Do not write service account API keys, bearer tokens, or header-based auth
  values into tracked project files.
- If secrets are needed for self-hosted stdio, prefer user-level config,
  environment-variable references, or a command the user can run.
- When editing JSON, TOML, or JSONC, preserve unrelated settings and other MCP
  servers. Update only the existing SigNoz server entry, and do not rename its
  key.
- If the client supports both project and user/global config, prefer the scope
  the user requested. If they did not choose:
  1. **Check every scope the client supports for an existing `signoz` (or
     equivalently-purposed) entry first.** If one exists anywhere, edit that
     same file in place; do not pick a different scope for the new value.
     This matters most for CLI clients like Devin CLI, Codex, and Claude Code
     that support multiple config layers (user/global, project, project-local):
     re-deriving the scope from scratch on every repair can silently create a
     second, shadowing or shadowed entry in a different file, or make the
     skill go looking for a project file in whatever directory the current
     session happens to be in, even an unrelated project that has nothing to
     do with the endpoint being configured.
  2. Only when no existing entry is found in any scope, choose a scope: prefer
     user/global for secrets and for CLI tools in general (they are
     typically configured per developer machine, not per project), and
     project scope only when the user asks for a team-shared, project-committed
     value.

## Cloud or Self-Hosted HTTP

Use these shapes for SigNoz Cloud hosted MCP URLs such as
`https://mcp.us.signoz.cloud/mcp` and self-hosted HTTP MCP URLs such as
`http://localhost:8000/mcp`.

### Portable Agent Plugins v1 package

In `mcp.json` in the installed SigNoz plugin root, replace only the `url` value
with the resolved MCP endpoint. Preserve the canonical `$schema`, the `signoz`
server key, and `type: "streamable-http"`. Agent Plugins v1 does not expand
environment variables in remote URLs and leaves OAuth to the client.

Apply the portable endpoint eligibility and native-client routing rules from
`mcp-settings.md` before editing this file.

```json
{
  "$schema": "https://agent-plugins.org/schemas/1.0.0/mcp.schema.json",
  "mcpServers": {
    "signoz": {
      "type": "streamable-http",
      "url": "https://mcp.us.signoz.cloud/mcp"
    }
  }
}
```

### Bundled Claude Code plugin

Do not edit `.signoz_claude_mcp.json` in the installed plugin cache. It must
keep the server key (`mcp`), `type: "http"`, and the user-configuration
placeholder:

```json
{
  "mcpServers": {
    "mcp": {
      "type": "http",
      "url": "${user_config.SIGNOZ_MCP_URL}"
    }
  }
}
```

Use `claude plugin list --json` to identify the exact enabled SigNoz plugin ID.
Update only `pluginConfigs[<plugin-id>].options.SIGNOZ_MCP_URL` in
`~/.claude/settings.json`, regardless of the plugin's installation scope, and
preserve every unrelated setting and option. Claude ignores `pluginConfigs` in
project and local settings. For example, with the actual marketplace suffix in
place of `<marketplace>`:

```json
{
  "pluginConfigs": {
    "signoz@<marketplace>": {
      "options": {
        "SIGNOZ_MCP_URL": "https://mcp.us.signoz.cloud/mcp"
      }
    }
  }
}
```

If managed settings or a `--settings` source supplies this option, it outranks
user settings; report the controlling source and have its owner change it.
Otherwise `/plugin` -> installed SigNoz plugin -> **Customize** writes the same
user setting. Persisted plugin options survive plugin updates; cached plugin
files do not.

### Codex Agent Plugins v1 package

Use the Agent Plugins v1 `mcp.json` in the SigNoz plugin root. The root
`plugin.json` selects this file, and `.codex-plugin/plugin.json` points at it for
compatibility. Replace only the `url` value with the resolved MCP endpoint
(concrete URL rule from `mcp-settings.md`), preserving the `signoz` server key
and `type: streamable-http`. Do not create a fallback if the file is missing.

```json
{
  "$schema": "https://agent-plugins.org/schemas/1.0.0/mcp.schema.json",
  "mcpServers": {
    "signoz": {
      "type": "streamable-http",
      "url": "https://mcp.us.signoz.cloud/mcp"
    }
  }
}
```

### Bundled Cursor plugin

Update `.signoz_cursor_mcp.json` in the SigNoz plugin root using the concrete URL
rule from `mcp-settings.md`. Do not rely on shell-style environment defaults in
Cursor plugin MCP URLs.

```json
{
  "mcpServers": {
    "signoz": {
      "url": "https://mcp.us.signoz.cloud/mcp"
    }
  }
}
```

### Cursor native config

Use `.cursor/mcp.json` in the project root.

```json
{
  "mcpServers": {
    "signoz": {
      "url": "https://mcp.us.signoz.cloud/mcp"
    }
  }
}
```

### VS Code / GitHub Copilot native fallback

Use this native configuration only when no Agent Plugins v1 install is active,
the user explicitly requests native configuration, or the resolved endpoint is
not eligible for portable `mcp.json`. For an eligible endpoint in an active
Agent Plugins v1 install, update the plugin-root `mcp.json` instead; creating a
native entry would register a second `signoz` server.

For native setup, use `.vscode/mcp.json` in the workspace, or the user-level MCP
config opened by the `MCP: Open User Configuration` command.

```json
{
  "servers": {
    "signoz": {
      "type": "http",
      "url": "https://mcp.us.signoz.cloud/mcp"
    }
  }
}
```

### Claude Desktop

For SigNoz Cloud or a **publicly reachable** self-hosted HTTP endpoint, add
SigNoz through **Settings → Connectors → Add custom connector** and enter the
resolved MCP URL. Complete OAuth when SigNoz Cloud prompts for it. Claude
Desktop remote connectors originate from Anthropic's cloud, so `localhost`,
VPN-only, and private-network endpoints are not reachable through this path;
use a local stdio registration for those deployments.

Do not put a remote `url` entry in `claude_desktop_config.json`; Claude Desktop
does not use that file for remote MCP custom connectors. The file is only for a
local stdio registration with `command`, `args`, and `env`, as shown under
[Self-Hosted Stdio](#self-hosted-stdio).

### Claude Code native CLI

For user scope:

```sh
claude mcp add --scope user --transport http signoz https://mcp.us.signoz.cloud/mcp
```

For project scope, use `--scope project` instead of `--scope user`.

### Codex native CLI or TOML

CLI:

```sh
codex mcp add signoz --url https://mcp.us.signoz.cloud/mcp
```

TOML:

```toml
[mcp_servers.signoz]
url = "https://mcp.us.signoz.cloud/mcp"
```

Use the native Codex entry when the user wants a durable setup or reports that
the bundled plugin `mcp.json` keeps resetting after updates. The
bundled file is copied into a versioned plugin cache, but `codex mcp add` writes
the user-level Codex config. Verify the effective server with
`codex mcp get signoz` or `codex mcp list`.

### Grok Build CLI

Grok ships the plugin's bundled `.signoz_grok_mcp.json`, which registers
`signoz` against the `us` SigNoz Cloud endpoint by default and expands a
`SIGNOZ_MCP_URL` environment override when one is set. **Do not edit that
bundled file.** Write the endpoint to Grok's own config instead: a
`[mcp_servers.signoz]` entry replaces the plugin-provided server of the same
name, and unlike the bundled file it survives plugin updates.

CLI (preferred):

```sh
grok mcp add signoz -t http https://mcp.us.signoz.cloud/mcp -s user
```

Use `-s user` for `~/.grok/config.toml` (per-machine, the sane default for a
personal CLI) and `-s project` for `./.grok/config.toml` (team-shared,
committed with the repo). Re-running the command updates the existing entry in
place instead of adding a second server.

TOML equivalent:

```toml
[mcp_servers.signoz]
url = "https://mcp.us.signoz.cloud/mcp"
enabled = true
```

Precedence for `[mcp_servers]`, highest first: `./.grok/config.toml` >
`<repo-root>/.grok/config.toml` > `~/.grok/config.toml` > plugin-provided
servers. Same-name entries replace lower-priority ones, so exactly one `signoz`
server stays live. Check each scope for an existing `signoz` entry before
writing a new one, and edit the highest-precedence file that already defines it.

Writing the config entry is also what **de-duplicates** Grok's compatibility
sources. Grok reads `~/.claude.json`, `~/.cursor/mcp.json`, and `.mcp.json`
alongside its own config, and a compat-sourced server does not replace the
plugin's; both load. A user who already has SigNoz configured in Claude Code or
Cursor therefore ends up with two live `signoz` servers pointing at different
endpoints (for example a self-hosted `http://localhost:8000/mcp` from
`~/.claude.json` and the plugin's Cloud default), which `grok mcp doctor` reports
as two separate servers. A `[mcp_servers.signoz]` entry outranks both and
collapses them to one. If the user reports duplicate or unexpectedly-routed
SigNoz tools in Grok, check `grok mcp doctor` for a second `signoz` and write the
config entry.

For a one-off or CI run, skip config entirely and export the environment
override that the bundled registration reads:

```sh
export SIGNOZ_MCP_URL=https://mcp.eu.signoz.cloud/mcp
```

Verify with `grok mcp list` and diagnose with `grok mcp doctor signoz`.

### Gemini CLI

CLI:

```sh
gemini mcp add -t http signoz https://mcp.us.signoz.cloud/mcp
```

Or edit `~/.gemini/settings.json`:

```json
{
  "mcpServers": {
    "signoz": {
      "httpUrl": "https://mcp.us.signoz.cloud/mcp"
    }
  }
}
```

### Devin CLI

Devin merges MCP servers by name across scopes, with later-checked scopes
overriding earlier ones: user/global is overridden by project, which is
overridden by project-local. Check these three files in **precedence
order (highest first)** for an existing `signoz` entry, since that is the
one actually in effect:

1. `.devin/config.local.json` in the current project root: gitignored,
   project-local. Highest precedence.
2. `.devin/config.json` in the current project root: team-shared, committed.
3. `~/.config/devin/config.json` (`%APPDATA%\devin\config.json` on Windows):
   user/global, applies to every project. Lowest precedence.

Edit the **first (highest-precedence) file that already has a `signoz`
entry**: editing a lower-precedence file while a higher one still defines
`signoz` would be silently shadowed and the active endpoint would not change.
If more than one scope defines `signoz`, tell the user which scope is
currently winning and ask whether to update that one or remove the
override so a lower scope takes effect instead.

If no scope has a `signoz` entry yet, default to user/global
(`~/.config/devin/config.json`): Devin CLI is a personal developer tool, so a
per-machine endpoint is the sane default. Only use `.devin/config.json`
instead when the user explicitly asks for a team-shared, project-committed
value, and only use `.devin/config.local.json` when the user is in a specific
project and wants a project-local (not machine-global) override.

```json
{
  "mcpServers": {
    "signoz": {
      "url": "https://mcp.us.signoz.cloud/mcp"
    }
  }
}
```

### Windsurf

Edit `~/.codeium/windsurf/mcp_config.json`.

```json
{
  "mcpServers": {
    "signoz": {
      "serverUrl": "https://mcp.us.signoz.cloud/mcp"
    }
  }
}
```

### Antigravity CLI

Remote servers must use the `serverUrl` key; Antigravity does not support
the legacy `url` or `httpUrl` fields.

If the SigNoz plugin is installed (`agy plugin install https://github.com/SigNoz/agent-skills`),
it already ships this `mcp_config.json` (default `us` Cloud endpoint), staged at
`~/.gemini/antigravity-cli/plugins/signoz/`. To repoint it, edit the `serverUrl`
value in that installed copy, then run `/mcp` to reload. Without the plugin, add
the server directly to the global `~/.gemini/config/mcp_config.json` (or workspace
`.agents/mcp_config.json`).

```json
{
  "mcpServers": {
    "signoz": {
      "serverUrl": "https://mcp.us.signoz.cloud/mcp"
    }
  }
}
```

### OpenCode

Edit `opencode.json` or `opencode.jsonc`.

```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "signoz": {
      "type": "remote",
      "url": "https://mcp.us.signoz.cloud/mcp",
      "enabled": true
    }
  }
}
```

### Generic HTTP MCP client

If the client is not listed, use its native remote or HTTP MCP shape with:

- server name: `signoz`
- transport/type: HTTP, remote, or streamable HTTP
- URL: the resolved SigNoz MCP endpoint

## Header-Based Auth Fallback

Use header-based auth only when the MCP client cannot complete interactive
OAuth, or when the user explicitly asks for a non-OAuth setup. SigNoz Cloud
needs both headers:

- `SIGNOZ-API-KEY`: service account API key
- `X-SigNoz-URL`: SigNoz instance URL, such as `https://your-instance.signoz.cloud`

Prefer environment-variable references if the client supports them. Do not
write real header values into tracked project files.

Generic shape:

```json
{
  "mcpServers": {
    "signoz": {
      "url": "https://mcp.us.signoz.cloud/mcp",
      "headers": {
        "SIGNOZ-API-KEY": "<your-api-key>",
        "X-SigNoz-URL": "<your-signoz-instance-url>"
      }
    }
  }
}
```

## Self-Hosted Stdio

Use stdio/local-binary mode only when the user explicitly requests it or the
client cannot use HTTP. Collect:

- absolute path to the `signoz-mcp-server` binary
- SigNoz instance URL
- service account API key

Prefer placeholders or environment-variable references when writing examples.
Avoid storing real API keys in tracked project files.

### JSON clients using `mcpServers`

Cursor, Claude Desktop, Windsurf, Gemini CLI, Devin CLI, and Antigravity CLI can
use this basic stdio shape, with client-specific file locations from the HTTP
section. For Devin CLI, prefer `.devin/config.local.json` and its
`${env:VAR_NAME}` interpolation syntax over literal secrets.

```json
{
  "mcpServers": {
    "signoz": {
      "command": "<path-to-binary>/signoz-mcp-server",
      "args": [],
      "env": {
        "SIGNOZ_URL": "<your-signoz-url>",
        "SIGNOZ_API_KEY": "<your-api-key>",
        "LOG_LEVEL": "info"
      }
    }
  }
}
```

### VS Code / GitHub Copilot stdio

```json
{
  "servers": {
    "signoz": {
      "type": "stdio",
      "command": "<path-to-binary>/signoz-mcp-server",
      "args": [],
      "env": {
        "SIGNOZ_URL": "<your-signoz-url>",
        "SIGNOZ_API_KEY": "<your-api-key>",
        "LOG_LEVEL": "info"
      }
    }
  }
}
```

### Claude Code stdio

```sh
claude mcp add --scope user signoz "<path-to-binary>/signoz-mcp-server" \
  -e SIGNOZ_URL="<your-signoz-url>" \
  -e SIGNOZ_API_KEY="<your-api-key>" \
  -e LOG_LEVEL=info
```

### Codex stdio

CLI:

```sh
codex mcp add signoz \
  --env SIGNOZ_URL="<your-signoz-url>" \
  --env SIGNOZ_API_KEY="<your-api-key>" \
  --env LOG_LEVEL=info \
  -- "<path-to-binary>/signoz-mcp-server"
```

TOML:

```toml
[mcp_servers.signoz]
command = "<path-to-binary>/signoz-mcp-server"
args = []

[mcp_servers.signoz.env]
SIGNOZ_URL = "<your-signoz-url>"
SIGNOZ_API_KEY = "<your-api-key>"
LOG_LEVEL = "info"
```

### Grok Build CLI stdio

CLI (stdio is the default transport, so `-t` is not needed; everything after
`--` is the server command):

```sh
grok mcp add signoz \
  -e SIGNOZ_URL="<your-signoz-url>" \
  -e SIGNOZ_API_KEY="<your-api-key>" \
  -e LOG_LEVEL=info \
  -s user \
  -- "<path-to-binary>/signoz-mcp-server"
```

TOML:

```toml
[mcp_servers.signoz]
command = "<path-to-binary>/signoz-mcp-server"
args = []
env = { SIGNOZ_URL = "<your-signoz-url>", SIGNOZ_API_KEY = "<your-api-key>", LOG_LEVEL = "info" }
```

Grok expands `${VAR}` and `${VAR:-default}` in `command`, `args`, and `env`
values as well as `url`, so prefer a reference over a literal key:

```sh
grok mcp add signoz -e SIGNOZ_API_KEY='${SIGNOZ_API_KEY}' -s user -- "<path-to-binary>/signoz-mcp-server"
```

Keep the server name `signoz` here too: the stdio entry replaces the bundled
HTTP registration of the same name rather than running alongside it.

### Zed

Edit Zed settings.

```json
{
  "context_servers": {
    "signoz": {
      "command": "<path-to-binary>/signoz-mcp-server",
      "args": [],
      "env": {
        "SIGNOZ_URL": "<your-signoz-url>",
        "SIGNOZ_API_KEY": "<your-api-key>",
        "LOG_LEVEL": "info"
      }
    }
  }
}
```

### OpenCode local

Edit `opencode.json` or `opencode.jsonc`.

```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "signoz": {
      "type": "local",
      "command": ["<path-to-binary>/signoz-mcp-server"],
      "environment": {
        "SIGNOZ_URL": "<your-signoz-url>",
        "SIGNOZ_API_KEY": "<your-api-key>",
        "LOG_LEVEL": "info"
      },
      "enabled": true
    }
  }
}
```

## Authentication Finish Steps

- Cursor: reload the window, then authenticate the `signoz` MCP server in
  Tools & MCP if prompted.
- VS Code / GitHub Copilot: open Copilot Chat in Agent mode, approve the
  `signoz` server if prompted, and complete authentication for SigNoz Cloud.
  A self-hosted endpoint needs no OAuth unless its MCP server runs with
  `OAUTH_ENABLED=true`.
- Claude Desktop hosted/public HTTP: reconnect the custom connector, then
  complete authentication when applicable.
- Claude Desktop local stdio: restart Claude Desktop so it reloads the local
  command entry in `claude_desktop_config.json`; do not add a remote URL there.
- Claude Code: run `/reload-plugins`, then `/mcp`; select the `signoz` plugin's
  `mcp` server (`plugin:signoz:mcp`) and complete authentication.
- Codex (SigNoz Cloud): run `codex mcp login signoz`, then verify with `/mcp`.
- Codex (self-hosted HTTP): no OAuth step unless the server runs with
  `OAUTH_ENABLED=true`; skip `codex mcp login` and verify the already-authenticated
  `signoz` server with `/mcp`.
- Grok Build CLI (SigNoz Cloud): run `/mcps` (or press Ctrl+L and open the MCP
  Servers tab), select `signoz`, and press `i` to start the OAuth flow. Press
  `r` to reload the list after a config change. Tokens are cached in
  `~/.grok/mcp_credentials.json`.
- Grok Build CLI (self-hosted HTTP): no OAuth step unless the server runs with
  `OAUTH_ENABLED=true`; press `r` in `/mcps` and verify the `signoz` server is
  connected.
- Gemini CLI: run `/mcp auth signoz`.
- Devin CLI (SigNoz Cloud): start a new session, then run
  `devin mcp login signoz` to complete OAuth.
- Devin CLI (self-hosted or header-based): start a new session; no OAuth step
  is expected.
- Windsurf: reload and complete authentication when prompted.
- Zed: reload after stdio config changes.
- Antigravity CLI: type `/mcp`, select the `signoz` server, and choose
  **Authenticate** to start the OAuth flow. If auth is stuck, clear dynamic
  authentication providers and retry.
- OpenCode: run `opencode mcp auth signoz` if auth does not start
  automatically, then verify with `opencode mcp list`.
- Header-based auth: no OAuth step is expected; verify the `signoz` tools after
  the client reloads.
