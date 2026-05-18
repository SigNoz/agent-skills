---
name: signoz-mcp-setup
description: >
  Initialize or repair SigNoz MCP server configuration for Claude Code, Codex,
  Cursor, VS Code/GitHub Copilot, Claude Desktop, Gemini CLI, Windsurf, Zed,
  Antigravity, OpenCode, or another MCP client. Use this skill before any
  SigNoz docs, query, dashboard, alert, or view workflow when
  `signoz:signoz_*` tools are unavailable, or when the user says "setup SigNoz
  MCP", "configure SigNoz plugin", "wrong region", "change SigNoz region",
  "MCP auth failed", or asks to connect SigNoz Cloud or a self-hosted MCP
  endpoint, even if they do not mention the plugin.
argument-hint: <client, SigNoz Cloud region, MCP URL, or self-hosted /mcp URL>
---

# SigNoz MCP Setup

Initialize or repair the SigNoz MCP server registration shipped with this
plugin. The target state is one working `signoz` MCP server. Do not create a
duplicate server unless the user explicitly asks for a separate configuration.

## Shared reference

Read [references/mcp-settings.md](references/mcp-settings.md) before checking
state, mapping user input, or editing registration files. It contains the
server-state check, registration file locations, editing rules, and region
mapping used by this procedure.

Read [references/client-configs.md](references/client-configs.md) when the
user names a client other than the bundled Claude Code, Codex, or Cursor
plugin path, when a native client config already exists, or when self-hosted
stdio/local-binary setup is requested.

## Configuration procedure

### Step 1: Check state

Silently determine the SigNoz MCP server state using the reference flow:

- **working** — continue with the user's original SigNoz request.
- **not-setup** — run Step 2.
- **configured-but-not-working** — if the user provided a new region or MCP URL,
  run Step 2. Otherwise tell them the SigNoz MCP server is configured but not
  connected, then ask for the SigNoz Cloud region or MCP URL to repair it. If
  they believe the endpoint is already correct, tell them to complete the
  client authentication step in Step 5.

Do not fall back to raw HTTP calls for SigNoz data when MCP is unavailable.
The MCP server is the supported API surface for this plugin's live SigNoz
workflows.

### Step 2: Identify the client

Use the client named in `$ARGUMENTS` or the user's latest message. If no
client is named, infer it only when the active environment is obvious:

- Claude Code, Codex, or Cursor plugin install: use the bundled plugin
  registration files.
- VS Code / GitHub Copilot, Claude Desktop, Gemini CLI, Windsurf, Zed,
  Antigravity, or OpenCode: use the matching native client recipe in
  `client-configs.md`.
- Unknown or unsupported client: use the generic HTTP MCP recipe and point the
  user to the SigNoz MCP Server docs for their client's exact config surface.

If you need to edit a native client config and the client is still ambiguous,
ask which client they want to configure.

### Step 3: Resolve the endpoint

Use `$ARGUMENTS` or the user's latest message if it already contains a region
or URL. Otherwise ask for one of:

- SigNoz Cloud region: `us`, `us2`, `eu`, `eu2`, `in`, `in2`, or a newer
  region code
- SigNoz Cloud MCP URL, such as `https://mcp.us.signoz.cloud/mcp`
- Self-hosted HTTP MCP URL, such as `http://localhost:8000/mcp`

Map the response using `mcp-settings.md`. If the user gives only a SigNoz
workspace URL such as `https://your-instance.signoz.cloud`, do not guess the
region from it. Ask them to check **Settings -> Ingestion** in SigNoz and
provide the region.

Do not ask for an API key for SigNoz Cloud setup. OAuth asks for the instance
URL and service account API key after the hosted MCP URL is configured. For
self-hosted SigNoz, prefer HTTP mode when the user gives an `/mcp` endpoint.
For stdio/local-binary mode, collect the binary path, SigNoz URL, and API key
only if the user explicitly asks you to configure that mode. For clients that
cannot complete interactive OAuth, use the header-based fallback in
`client-configs.md` only when the user asks for it or the client requires it.

### Step 4: Apply the endpoint

For bundled Claude Code, Codex, and Cursor plugin installs, edit the registration
files using the reference editing rules:

1. In `.mcp.json` for Claude Code and Codex, replace the full `url` value with
   the resolved MCP endpoint.
2. In `mcp.json` for Cursor, replace the full `url` value with the resolved MCP
   endpoint.
3. Preserve unrelated MCP servers and settings.

Claude Code and Codex target shape:

```json
{
  "mcpServers": {
    "signoz": {
      "url": "https://mcp.us.signoz.cloud/mcp"
    }
  }
}
```

Cursor target shape:

```json
{
  "mcpServers": {
    "signoz": {
      "url": "https://mcp.us.signoz.cloud/mcp"
    }
  }
}
```

If either bundled file still uses any `SIGNOZ_MCP_URL` wrapper from an older
version, replace it with the concrete resolved URL.

Bundled registration files live inside the installed plugin. Plugin updates can
reset them to the placeholder; if that happens, rerun this setup skill. For a
more durable native-client setup, use the relevant recipe in `client-configs.md`.

For native client setup, use `client-configs.md`:

- Edit an existing native client config only when the user named that client or
  the target file is clearly the active config for the task.
- Create a new native client config only when the user asks for that client to
  be configured.
- Never write service account API keys, bearer tokens, or header-based auth
  values into tracked project files. Prefer client OAuth for SigNoz Cloud,
  user-level config, environment-variable references, or short commands the
  user can run locally.
- Preserve unrelated MCP servers and existing client settings.
- Keep the server name `signoz`.

### Step 5: Tell the user how to finish

Tell the user that the SigNoz MCP endpoint has been configured, then give the
client-specific authentication step:

- **Cursor** — reload the window, then authenticate the `signoz` MCP server in
  Tools & MCP if prompted.
- **VS Code / GitHub Copilot** — open Copilot Chat in Agent mode, approve the
  `signoz` server if prompted, then complete the authentication flow.
- **Codex** — restart Codex if the server does not appear, then run
  `codex mcp login signoz` and verify with `/mcp`.
- **Claude Code** — restart Claude Code if the server does not appear, then run
  `/mcp`, select `signoz`, and complete authentication.
- **Claude Desktop** — restart Claude Desktop or reconnect the custom
  connector, then complete authentication when prompted.
- **Gemini CLI** — restart Gemini CLI if needed, then run `/mcp auth signoz`.
- **Windsurf** — reload Windsurf and complete authentication when prompted.
- **Zed** — reload Zed after config changes; self-hosted stdio mode reads the
  configured environment from the context server entry.
- **Antigravity** — reload the agent window and complete OAuth when prompted.
  If authentication is stuck, clear cached dynamic auth providers and retry.
- **OpenCode** — run `opencode mcp auth signoz` if authentication does not
  start automatically, then verify with `opencode mcp list`.

Keep the response short. Do not expose registration file paths, placeholder
values, environment variable names, API keys, tokens, or file contents unless
the user explicitly asks for implementation details.
