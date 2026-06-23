#!/usr/bin/env node

// Cursor port of self-hosted-nudge.js. Cursor runs plugin hooks too (since
// Cursor 1.7), but with a different contract than Claude Code:
//   - event key is `sessionStart` (camelCase), wired in hooks/cursor-hooks.json
//   - output schema is { "additional_context": "<text>" } on stdout
//   - per the Cursor plugins reference, a hook command's relative path resolves
//     "relative to the plugin root", so this script is invoked directly and
//     locates its own bundled files from __dirname (Cursor exposes no
//     plugin-root variable, unlike Claude's ${CLAUDE_PLUGIN_ROOT}).
//
// Detection is intentionally limited to what the docs support: nudge while the
// bundled Cursor MCP URL is still unconfigured — the `not-setup` placeholder, an
// empty URL, or the `self-hosted` sentinel produced when the user picks
// "self-hosted" at the region prompt. Once /signoz-mcp-setup rewrites it to a
// real Cloud or self-hosted endpoint, the hook goes quiet.

const fs = require("fs");
const path = require("path");

// hooks/scripts/ -> plugin root. Independent of the hook's working directory.
const registrationPath = path.join(__dirname, "..", "..", ".signoz_cursor_mcp.json");

function readMcpUrl(registration) {
  let raw;

  try {
    raw = fs.readFileSync(registration, "utf8");
  } catch {
    // No registration file to inspect — report it as unconfigured so we nudge.
    return undefined;
  }

  try {
    // Read the single bundled MCP server's URL regardless of its key.
    const servers = JSON.parse(raw)?.mcpServers ?? {};
    return Object.values(servers)[0]?.url;
  } catch {
    return undefined;
  }
}

const url = readMcpUrl(registrationPath);
const lowered = typeof url === "string" ? url.toLowerCase() : "";

// Unconfigured states: the `not-setup` placeholder, an empty/missing URL, or the
// `self-hosted` sentinel from picking "self-hosted" at the region prompt. Real
// Cloud regions (us, us2, eu, ...) match none of these.
const isSelfHosted = lowered.includes("self-hosted");
const unconfigured =
  typeof url !== "string" ||
  lowered.trim() === "" ||
  lowered.includes("not-setup") ||
  isSelfHosted;

if (!unconfigured) {
  // Already pointed at a real endpoint — nothing to nudge about.
  process.exit(0);
}

const additional_context = isSelfHosted
  ? "The SigNoz Cursor plugin is set to self-hosted, so its MCP server is not " +
    "configured yet. Tell the user to run /signoz-mcp-setup with their " +
    "self-hosted HTTP /mcp URL (for example /signoz-mcp-setup " +
    "http://localhost:8000/mcp), then reload Cursor."
  : "The SigNoz Cursor plugin's MCP server is not configured yet. Tell the user " +
    "to run /signoz-mcp-setup with their SigNoz Cloud region (us, us2, eu, eu2, " +
    "in, in2) or a self-hosted HTTP /mcp URL, then reload Cursor.";

process.stdout.write(JSON.stringify({ additional_context }));
