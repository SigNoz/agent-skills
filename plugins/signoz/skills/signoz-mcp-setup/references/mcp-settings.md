# SigNoz MCP Registration Reference

Use this reference when checking the SigNoz MCP server state, locating plugin
registration files, editing the endpoint default, or mapping user input to a
hosted SigNoz Cloud MCP URL.

For native client config shapes such as VS Code, Gemini CLI, Windsurf, Zed,
Antigravity CLI, or OpenCode, read
[client-configs.md](client-configs.md) after resolving the endpoint.

## Contents

- [State Check](#state-check)
- [Registration Files](#registration-files)
- [Editing Rules](#editing-rules)
- [Endpoint Mapping](#endpoint-mapping)

## State Check

Silently determine `signoz-server-state`, **only after the client is known**
(see `SKILL.md` Step 1 — identify the client before checking state):

1. If `signoz_*` MCP tools are available, try a lightweight read-only
   call such as `signoz_search_docs` for `mcp setup` or
   `signoz_list_services` with a small lookback.
2. If the call returns SigNoz-specific content, state is **working**.
3. If the call fails, returns no tools, or only generic/empty content:
   - **Claude Code, Codex, or Cursor bundled plugin install** — read the
     plugin registration files below.
   - **Any other client** — do not read or file-search for the bundled
     registration files below. They belong to a different client's plugin
     distribution and can exist on disk for unrelated reasons — most
     notably, if this skill is running from a local checkout of the
     `agent-skills` source repo itself (e.g. a Devin CLI local-path plugin
     install), the bundled files genuinely exist a few directories up
     because that's where the *source* repo keeps them, not because they
     configure the current client. Check that client's own native config
     location from `client-configs.md` instead.
4. If any registration file consulted in step 3 contains `not-setup`, state is
   **not-setup**.
5. Otherwise state is **configured-but-not-working**.

Do not tell the user which checks ran or what file contents were found. Explain
only the plain outcome: working, not set up, or configured but not connected.

## Registration Files

These bundled registration files exist only for the Claude Code, Codex, and
Cursor plugin installs — never read or edit them for any other client, even if
a file search finds them:

- `.signoz_claude_mcp.json` for Claude Code
- `.mcp.json` for Codex
- `.signoz_cursor_mcp.json` for Cursor

This reference file lives at `skills/signoz-mcp-setup/references/mcp-settings.md`,
so the plugin root is two directories up from `skills/signoz-mcp-setup/`. That
relative path also happens to resolve inside the `agent-skills` source repo
itself (this plugin's own monorepo), which ships all three files side by side
for their respective bundled installs — resolving to a real file there does
not mean it is the active client's configuration.

Update every registration file that exists **for the identified client only**.
Replace only the `url` value and preserve each file's existing server key and
`type`: the Claude Code file (`.signoz_claude_mcp.json`) ships the server key
`mcp`, while the Codex and Cursor files ship `signoz`. Do not create duplicate
MCP server entries, and do not rename the existing server — renaming the
Claude Code key changes the tool namespace (`plugin:signoz:mcp`) and forces
re-authentication.

## Editing Rules

Use the client-specific shape for the registration file you are editing.

### Bundled plugin MCP files

The URL should use a concrete endpoint in all bundled registration files:

- `.signoz_claude_mcp.json` for Claude Code
- `.mcp.json` for Codex
- `.signoz_cursor_mcp.json` for Cursor

```json
"url": "https://mcp.us.signoz.cloud/mcp"
```

Replace the entire `url` value with the resolved MCP endpoint. Do not keep
`${SIGNOZ_MCP_URL:-...}` in bundled plugin MCP files; Codex treats it as a
literal URL, and Cursor documents interpolation syntax that does not include
shell-style defaults.

If either bundled file contains any legacy `SIGNOZ_MCP_URL` wrapper, replace
the full value with the concrete resolved URL.

Examples:

```text
https://mcp.eu.signoz.cloud/mcp
http://localhost:8000/mcp
```

If the user's client has an explicit plugin setting or environment override for
the endpoint, that value can override this default. If this setup skill updates
the default but the client still connects to the old endpoint, tell the user to
clear the explicit plugin setting and reload the client.

### Update behavior

These bundled files live inside the installed plugin. Plugin updates can reset
them to the placeholder. If the `signoz` server returns to **not-setup** after
an update, rerun `signoz-mcp-setup`. For durable native client configuration,
use the client-specific recipes in `client-configs.md`.

## Endpoint Mapping

SigNoz Cloud hosted MCP URLs use the same region code shown in
**Settings -> Ingestion** and documented in the SigNoz Cloud region reference.

| User input | MCP URL |
|---|---|
| `us`, `US`, United States, `ingest.us.signoz.cloud` | `https://mcp.us.signoz.cloud/mcp` |
| `us2`, `US2`, `ingest.us2.signoz.cloud` | `https://mcp.us2.signoz.cloud/mcp` |
| `eu`, `EU`, Europe, `ingest.eu.signoz.cloud` | `https://mcp.eu.signoz.cloud/mcp` |
| `eu2`, `EU2`, `ingest.eu2.signoz.cloud` | `https://mcp.eu2.signoz.cloud/mcp` |
| `in`, `IN`, India, `ingest.in.signoz.cloud` | `https://mcp.in.signoz.cloud/mcp` |
| `in2`, `IN2`, `ingest.in2.signoz.cloud` | `https://mcp.in2.signoz.cloud/mcp` |

Mapping rules:

- **Known region code** — map `us`, `us2`, `eu`, `eu2`, `in`, or `in2`
  case-insensitively.
- **Hosted MCP URL** — accept `https://mcp.<region>.signoz.cloud/mcp` as-is
  after normalizing the region to lowercase.
- **Hosted MCP host only** — add `https://` and `/mcp`.
- **Ingestion endpoint** — map `ingest.<region>.signoz.cloud` to the matching
  hosted MCP URL.
- **Self-hosted HTTP MCP URL** — accept any `http://.../mcp` or
  `https://.../mcp` URL that is not a SigNoz Cloud workspace URL. This plugin
  configuration path configures URL-based HTTP MCP. For stdio/local-binary
  mode, tell the user to register the SigNoz MCP server separately as
  `signoz`.
- **SigNoz workspace URL** — do not infer the region from
  `https://<workspace>.signoz.cloud`. Ask the user for the region from
  **Settings -> Ingestion**.
- **Unknown hosted region code** — ask for confirmation before using
  `https://mcp.<region>.signoz.cloud/mcp`. New SigNoz Cloud regions may exist
  before this skill is updated.

Do not ask for API keys for SigNoz Cloud endpoint setup. SigNoz Cloud
authentication happens after endpoint setup through the MCP client's OAuth
flow. Self-hosted HTTP mode expects the user to run the MCP server with its
SigNoz URL and API key configured on that server process. For self-hosted
stdio/local-binary mode, read `client-configs.md` and collect secrets only when
the user explicitly asks you to configure that mode.
