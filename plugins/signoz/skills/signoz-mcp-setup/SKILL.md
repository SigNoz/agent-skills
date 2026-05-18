---
name: signoz-mcp-setup
description: >
  Initialize or repair the SigNoz MCP server configuration for Claude Code,
  Codex, or Cursor. Use this skill before any SigNoz docs, query, dashboard,
  alert, or view workflow when `signoz:signoz_*` tools are unavailable, or when
  the user says "setup SigNoz MCP", "configure SigNoz plugin", "wrong region",
  "change SigNoz region", "MCP auth failed", or asks to connect SigNoz Cloud or
  a self-hosted MCP endpoint, even if they do not mention the plugin.
argument-hint: <SigNoz Cloud region, MCP URL, or self-hosted /mcp URL>
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

## Configuration procedure

### Step 1: Check state

Silently determine the SigNoz MCP server state using the reference flow:

- **working** — continue with the user's original SigNoz request.
- **not-setup** — run Step 2.
- **configured-but-not-working** — if the user provided a new region or MCP URL,
  run Step 2. Otherwise tell them the SigNoz MCP server is configured but not
  connected, then ask for the SigNoz Cloud region or MCP URL to repair it. If
  they believe the endpoint is already correct, tell them to complete the
  client authentication step in Step 4.

Do not fall back to raw HTTP calls for SigNoz data when MCP is unavailable.
The MCP server is the supported API surface for this plugin's live SigNoz
workflows.

### Step 2: Resolve the endpoint

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

Do not ask for an API key during plugin setup. For SigNoz Cloud, OAuth asks for
the instance URL and service account API key after the MCP URL is configured.
For self-hosted SigNoz, this plugin configuration path supports HTTP MCP mode.
If the user wants stdio/local-binary mode instead, tell them to register the
SigNoz MCP server separately as `signoz`; these skills will work once
`signoz:signoz_*` tools are available.

### Step 3: Apply the endpoint

Edit the plugin MCP registration files using the reference editing rule:

1. Replace only the default value inside the `SIGNOZ_MCP_URL` template.
2. Preserve the variable wrapper so users can still override the endpoint from
   client settings when they need to.
3. Update every SigNoz plugin registration file that exists in the plugin root.

Example target shape:

```json
{
  "mcpServers": {
    "signoz": {
      "url": "${SIGNOZ_MCP_URL:-https://mcp.us.signoz.cloud/mcp}"
    }
  }
}
```

If a registration file still uses the legacy no-default form
`${SIGNOZ_MCP_URL}`, convert it to the target shape with the resolved endpoint
as the default.

### Step 4: Tell the user how to finish

Tell the user that the SigNoz MCP endpoint has been configured, then give the
client-specific authentication step:

- **Cursor** — reload the window, then authenticate the `signoz` MCP server in
  Tools & MCP if prompted.
- **Codex** — restart Codex if the server does not appear, then run
  `codex mcp login signoz` and verify with `/mcp`.
- **Claude Code** — restart Claude Code if the server does not appear, then run
  `/mcp`, select `signoz`, and complete authentication.

Keep the response short. Do not expose registration file paths, placeholder
values, environment variable names, API keys, tokens, or file contents unless
the user explicitly asks for implementation details.
