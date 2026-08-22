---
name: signoz-mcp-setup
description: >
  Initialize or repair SigNoz MCP server configuration for Agent Plugins v1,
  Claude Code, Codex, Cursor, VS Code/GitHub Copilot, Claude Desktop, Gemini
  CLI, Devin CLI, Grok Build, Windsurf, Zed, Antigravity CLI, OpenCode, or
  another MCP client. Use this skill before any SigNoz docs, query, dashboard,
  alert, or view workflow when
  `signoz_*` tools are unavailable, or when the user says "setup SigNoz
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

Read [references/client-configs.md](references/client-configs.md) for a portable
Agent Plugins v1 install, when the user names a client other than the bundled
Claude Code, Codex, or Cursor plugin path, when a native client config already
exists, or when self-hosted stdio/local-binary setup is requested.

## Configuration procedure

### Step 1: Identify the client

Determine this before checking state: it decides where state is allowed to be
checked from.

Use the client named in `$ARGUMENTS` or the user's latest message. If no
client is named, infer it only when the active environment is obvious (which
agent CLI or editor is running this skill, not just what files happen to exist
on disk):

Classify the install from the format the active client loaded, not from other
files that happen to coexist in the plugin root. An Agent Plugins v1 install
uses the portable `mcp.json` when its root `plugin.json` declares the canonical
Agent Plugins schema, even if the same root contains registration files for
Claude Code, Codex, Cursor, or Grok Build. Use a client-specific registration
file only when that client loaded the corresponding compatibility package.

- Portable Agent Plugins v1 install, including a VS Code installation whose
  root manifest declares the Agent Plugins schema: use the standard `mcp.json`
  in the installed plugin root.
- Claude Code, Codex, or Cursor compatibility-package install: use the bundled
  client-specific registration files.
- Grok Build: use the Grok Build CLI recipe in `client-configs.md`. It ships a
  bundled registration file, but its endpoint is configured through
  `[mcp_servers.signoz]`, not by editing that file.
- VS Code / GitHub Copilot native MCP setup: use the native recipe only when no
  Agent Plugins v1 install is active, the user explicitly requests native
  config, or the endpoint is not eligible for portable `mcp.json`.
- Claude Desktop, Gemini CLI, Devin CLI, Windsurf, Zed, Antigravity CLI, or
  OpenCode: use the matching native client recipe in `client-configs.md`.
- Unknown or unsupported client: use the generic HTTP MCP recipe and point the
  user to the SigNoz MCP Server docs for their client's exact config surface.

If you need to edit a native client config and the client is still ambiguous,
ask which client they want to configure.

### Step 2: Check state

Silently determine the SigNoz MCP server state using the reference flow,
**scoped to the client identified in Step 1**:

Probe with `signoz_list_services(timeRange: "1h", limit: 1)`. Do not use docs
tools (`signoz_search_docs` or `signoz_fetch_doc`) for this check.

- For a portable Agent Plugins v1 install, including one active in VS Code, or
  a Claude Code, Codex, or Cursor bundled plugin install, the reference flow's
  registration-file fallback applies.
- For Grok Build, read `[mcp_servers.signoz]` from Grok's config scopes (or run
  `grok mcp list`) instead. Its bundled `.signoz_grok_mcp.json` ships a working
  default and is overridden by config, so it never reports the live state.
- For every other client, including native VS Code setup and Devin CLI, do not
  read or search for the plugin-root `mcp.json`, `.signoz_claude_mcp.json`,
  `.mcp.json`, or
  `.signoz_cursor_mcp.json`. Those are bundled files for a different plugin
  distribution and are irrelevant here even if a file-search tool happens to
  find them (for example when this skill is linked from a local checkout of
  the `agent-skills` source repo itself). This does not exclude native files
  such as `.vscode/mcp.json` or `.cursor/mcp.json`; check the identified
  client's own native config location per `client-configs.md`.

State outcomes:

- **working**: `signoz_list_services` succeeded; continue with the user's
  original SigNoz request.
- **not-setup**: run Step 3.
- **configured-but-not-working**: if the user provided a new region or MCP URL,
  run Step 3. Otherwise tell them the SigNoz MCP server is configured but not
  connected, then ask for the SigNoz Cloud region or MCP URL to repair it. If
  they believe the endpoint is already correct, tell them to complete the
  client authentication step in Step 5.

Do not fall back to raw HTTP calls for SigNoz data when MCP is unavailable.
The MCP server is the supported API surface for this plugin's live SigNoz
workflows.

The workflow skills assume the current SigNoz MCP server contract. If a
SigNoz tool reports schema or parameter errors that contradict the skill
instructions, repair or update the MCP server connection instead of inventing
alternate raw HTTP calls or teaching legacy parameters.

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

For a portable Agent Plugins v1 install or bundled Claude Code, Codex, and
Cursor plugin installs, edit the registration files using the reference editing
rules:

1. For Agent Plugins v1, apply the portable endpoint eligibility rules in
   `mcp-settings.md` and the canonical file shape in `client-configs.md`. When
   the endpoint is not portable, follow the reference routing to the identified
   client's native MCP configuration instead.
   When configuring an installed Agent Plugins v1 package in VS Code, the
   endpoint is portable, and the user did not explicitly request native config,
   update only the plugin-root `mcp.json`. Do not create a native `signoz`
   entry; it would register a second server alongside the plugin server. If the
   user explicitly reports that an earlier plugin setup created a duplicate
   native `signoz`, remove only that confirmed accidental entry from the VS Code
   workspace or user MCP config and preserve every unrelated server and setting.
   Never infer that an existing native entry is accidental solely because both
   registrations exist.
2. In `.signoz_claude_mcp.json` for Claude Code, replace only the `url` value
   with the resolved MCP endpoint. Preserve the existing server key and `type`:
   this file ships the server key `mcp`, and renaming it changes the tool
   namespace (`plugin:signoz:mcp`) and forces re-authentication.
3. In `.mcp.json` for Codex, replace only the `url` value with the resolved MCP
   endpoint, preserving the existing `signoz` server key.
4. In `.signoz_cursor_mcp.json` for Cursor, replace only the `url` value with the
   resolved MCP endpoint, preserving the existing `signoz` server key.
5. Preserve unrelated MCP servers and settings.

Claude Code target shape (keep the `mcp` server key and `type`):

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

Codex and Cursor target shape (keep the `signoz` server key):

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

Portable and client-specific registration files live inside the installed
plugin. Plugin updates can reset them to the placeholder; if that happens,
rerun this setup skill. For a more durable native-client setup, use the relevant
recipe in `client-configs.md`.

For Codex, if the user says the endpoint reset again, keeps resetting, or asks
for a durable/persistent setup, also create or update the native Codex MCP
server entry after resolving the endpoint:

```sh
codex mcp add signoz --url <resolved-mcp-url>
```

This writes the user-level `[mcp_servers.signoz]` entry in Codex config and
survives plugin cache updates. If editing TOML directly, preserve unrelated
config and only set `url` for `mcp_servers.signoz`.

For Grok Build, do not edit the bundled `.signoz_grok_mcp.json`. Write the
resolved endpoint to Grok's own config, which replaces the plugin-provided
`signoz` server and survives plugin updates:

```sh
grok mcp add signoz -t http <resolved-mcp-url> -s user
```

Use `-s project` instead when the user wants the endpoint committed with the
repo in `./.grok/config.toml`. Re-running the command updates the existing
entry rather than adding a second server. If `signoz` is already defined in
more than one scope, update the highest-precedence one
(`./.grok/config.toml` > `<repo-root>/.grok/config.toml` >
`~/.grok/config.toml`); editing a lower one would be silently shadowed. See
the Grok Build CLI recipe in `client-configs.md`.

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
- Keep the server name `signoz` in native client configs (the bundled Claude
  Code plugin file is the only one that uses the `mcp` key; do not rename it).

### Auth and role diagnosis

Backend RBAC classifies MCP failures from the API key's user role: reads need at
least viewer; alert/dashboard writes need editor or admin; notification-channel
management and API-key creation need admin. `401` / `UNAUTHORIZED` means the
credential is missing, invalid, or expired: check configuration/presence
first, then reauthenticate or reissue as appropriate. `403` /
`PERMISSION_DENIED` means credentials are valid but under-privileged. Have a
sufficiently privileged user act or issue a dedicated minimum-role key; never
paste elevated keys into chat or tracked config.

### Step 5: Tell the user how to finish

Tell the user that the SigNoz MCP endpoint has been configured, then give the
client-specific authentication step:

- **Agent Plugins v1 client**: reload the installed plugin if the client does
  not pick up the changed `mcp.json`, then use that client's MCP authentication
  flow for the `signoz` server. Agent Plugins v1 leaves OAuth interaction and
  credential storage to the client.
- **Cursor**: reload the window, then authenticate the `signoz` MCP server in
  Tools & MCP if prompted.
- **VS Code / GitHub Copilot**: open Copilot Chat in Agent mode, approve the
  `signoz` server if prompted, then complete the authentication flow for SigNoz
  Cloud. A self-hosted endpoint needs no OAuth unless its MCP server runs with
  `OAUTH_ENABLED=true`.
- **Codex**: restart Codex if the server does not appear. For SigNoz Cloud,
  run `codex mcp login signoz` to complete OAuth, then verify with `/mcp`. For a
  self-hosted HTTP endpoint (no OAuth unless the server runs with
  `OAUTH_ENABLED=true`), skip the login step and just verify with `/mcp` that the
  already-authenticated `signoz` server is connected.
- **Claude Code**: restart Claude Code if the server does not appear, then run
  `/mcp`, select `signoz`, and complete authentication.
- **Claude Desktop**: for SigNoz Cloud or publicly reachable self-hosted HTTP,
  reconnect the custom connector and complete authentication when prompted.
  Private-network or localhost endpoints need local stdio because remote
  connectors originate from Anthropic's cloud. Restart Claude Desktop after a
  local stdio change so it reloads `claude_desktop_config.json`; that file is
  only for command-based registration, not a hosted URL.
- **Grok Build**: run `/mcps` (or press Ctrl+L and open the MCP Servers tab),
  press `r` to reload after the config change, then select `signoz` and press
  `i` to complete the OAuth flow in the browser. Self-hosted endpoints need no
  OAuth unless the server runs with `OAUTH_ENABLED=true`. Diagnose with
  `grok mcp doctor signoz`.
- **Gemini CLI**: restart Gemini CLI if needed, then run `/mcp auth signoz`.
- **Devin CLI**: start a new session so the updated `.devin/config.json` is
  picked up. For SigNoz Cloud, run `devin mcp login signoz` to complete OAuth.
  For a self-hosted or header-based endpoint, no OAuth step is expected.
- **Windsurf**: reload Windsurf and complete authentication when prompted.
- **Zed**: reload Zed after config changes; self-hosted stdio mode reads the
  configured environment from the context server entry.
- **Antigravity CLI**: type `/mcp`, select the `signoz` server, and choose
  **Authenticate** to start the OAuth flow (complete it in the browser). Self-hosted
  endpoints need no OAuth unless the server runs with `OAUTH_ENABLED=true`. If
  authentication is stuck, clear cached dynamic auth providers and retry.
- **OpenCode**: run `opencode mcp auth signoz` if authentication does not
  start automatically, then verify with `opencode mcp list`.

Keep the response short. Do not expose registration file paths, placeholder
values, environment variable names, API keys, tokens, or file contents unless
the user explicitly asks for implementation details.
