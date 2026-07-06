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

- Keep each file's existing server key. The bundled Claude Code file
  (`.signoz_claude_mcp.json`) ships `mcp`; the Codex and Cursor bundled files and
  native client configs use `signoz`. Do not rename it.
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
     same file in place — do not pick a different scope for the new value.
     This matters most for CLI clients like Devin CLI, Codex, and Claude Code
     that support multiple config layers (user/global, project, project-local):
     re-deriving the scope from scratch on every repair can silently create a
     second, shadowing or shadowed entry in a different file, or make the
     skill go looking for a project file in whatever directory the current
     session happens to be in — even an unrelated project that has nothing to
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

### Bundled Claude Code plugin

In `.signoz_claude_mcp.json` in the SigNoz plugin root, replace only the `url`
value with the resolved MCP endpoint (concrete URL rule from `mcp-settings.md`).
Leave the server key (`mcp`), the `type` field, and other settings unchanged.

```json
{
  "mcpServers": {
    "mcp": {
      "type": "http",
      "url": "https://mcp.us.signoz.cloud/mcp"
    }
  }
}
```

### Bundled Codex plugin

In `.mcp.json` in the SigNoz plugin root, replace only the `url` value with the
resolved MCP endpoint (concrete URL rule from `mcp-settings.md`). Codex does not
reliably expand shell-style environment defaults in plugin MCP URLs.

```json
{
  "mcpServers": {
    "signoz": {
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

### VS Code / GitHub Copilot

Use `.vscode/mcp.json` in the workspace, or the user-level MCP config opened
by the `MCP: Open User Configuration` command.

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

Claude Desktop can add SigNoz Cloud as a custom connector from Settings. If
the user asks for raw config, add the `signoz` entry to
`claude_desktop_config.json`.

```json
{
  "mcpServers": {
    "signoz": {
      "url": "https://mcp.us.signoz.cloud/mcp"
    }
  }
}
```

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
order — highest first** — for an existing `signoz` entry, since that is the
one actually in effect:

1. `.devin/config.local.json` in the current project root — gitignored,
   project-local. Highest precedence.
2. `.devin/config.json` in the current project root — team-shared, committed.
3. `~/.config/devin/config.json` (`%APPDATA%\devin\config.json` on Windows) —
   user/global, applies to every project. Lowest precedence.

Edit the **first (highest-precedence) file that already has a `signoz`
entry** — editing a lower-precedence file while a higher one still defines
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

Remote servers must use the `serverUrl` key — Antigravity does not support
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
  `signoz` server, and complete authentication.
- Claude Desktop: restart or reconnect the custom connector, then complete
  authentication.
- Claude Code: run `/mcp`, select `signoz`, and complete authentication.
- Codex (SigNoz Cloud): run `codex mcp login signoz`, then verify with `/mcp`.
- Codex (self-hosted HTTP): no OAuth step unless the server runs with
  `OAUTH_ENABLED=true`; skip `codex mcp login` and verify the already-authenticated
  `signoz` server with `/mcp`.
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
