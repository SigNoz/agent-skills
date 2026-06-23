#!/usr/bin/env node

// Cursor port of self-hosted-nudge.js. Cursor runs plugin hooks too (since
// Cursor 1.7), but with a different contract than Claude Code:
//   - event key is `sessionStart` (camelCase), wired in hooks/cursor-hooks.json
//   - output schema is { "additional_context": "<text>" } on stdout
//   - there is no ${CLAUDE_PLUGIN_ROOT} and no CLAUDE_PLUGIN_OPTION_* env var
// So this script resolves the plugin root from its own location and detects the
// unconfigured/placeholder MCP URL directly, treating the SIGNOZ_SELF_HOSTED
// plugin variable as a best-effort hint when Cursor happens to pass it through.

const fs = require("fs");
const path = require("path");

function isTruthy(value) {
  if (typeof value !== "string") {
    return false;
  }
  return ["true", "1", "yes", "on"].includes(value.trim().toLowerCase());
}

// Cursor does not expose a plugin-root env var, so derive it from this script's
// location: hooks/scripts/ -> plugin root.
const pluginRoot = path.join(__dirname, "..", "..");
const registrationPath = path.join(pluginRoot, ".signoz_cursor_mcp.json");

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

// Cursor may forward the SIGNOZ_SELF_HOSTED plugin variable as an argv (when the
// hooks.json command interpolates ${SIGNOZ_SELF_HOSTED}) or as an env var. A
// literal "${...}" means it was not substituted, so treat that as unknown.
function selfHostedSignal() {
  for (const candidate of [process.argv[2], process.env.SIGNOZ_SELF_HOSTED]) {
    if (typeof candidate === "string" && !candidate.includes("${") && isTruthy(candidate)) {
      return true;
    }
  }
  return false;
}

const url = readMcpUrl(registrationPath);
const lowered = typeof url === "string" ? url.toLowerCase() : "";

// The Cursor MCP placeholder is `not-setup`; an empty/missing URL counts too.
const unconfigured =
  typeof url !== "string" || lowered.trim() === "" || lowered.includes("not-setup");
// Self-hosted users who left a Cloud region selected need to repoint the URL.
const selfHostedOnCloud = selfHostedSignal() && lowered.includes("signoz.cloud");

if (!unconfigured && !selfHostedOnCloud) {
  // Already pointed at a real endpoint with no self-hosted/Cloud mismatch.
  process.exit(0);
}

const context = selfHostedOnCloud
  ? "The SigNoz Cursor plugin is in self-hosted mode but its MCP server still " +
    "points at SigNoz Cloud. Tell the user to finish setup by running " +
    "/signoz-mcp-setup with their self-hosted MCP URL (for example " +
    "/signoz-mcp-setup http://localhost:8000/mcp), then reload Cursor."
  : "The SigNoz Cursor plugin's MCP server is not configured yet. Tell the user " +
    "to run /signoz-mcp-setup with their SigNoz Cloud region (us, us2, eu, eu2, " +
    "in, in2) or a self-hosted HTTP /mcp URL, then reload Cursor.";

process.stdout.write(JSON.stringify({ additional_context: context }));
