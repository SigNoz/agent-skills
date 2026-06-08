#!/usr/bin/env node

const fs = require("fs");
const path = require("path");

function isTruthy(value) {
  if (typeof value !== "string") {
    return false;
  }
  return ["true", "1", "yes", "on"].includes(value.trim().toLowerCase());
}

// The Claude Code registration still points at SigNoz Cloud (or the unset
// placeholder) until the user runs /signoz-mcp-setup with their own URL.
function needsSelfHostedSetup(registrationPath) {
  let raw;

  try {
    raw = fs.readFileSync(registrationPath, "utf8");
  } catch {
    // No registration file to inspect — stay quiet rather than guess.
    return false;
  }

  let url;

  try {
    url = JSON.parse(raw)?.mcpServers?.signoz?.url;
  } catch {
    return false;
  }

  if (typeof url !== "string" || url.trim() === "") {
    return true;
  }

  const lowered = url.toLowerCase();
  return lowered.includes("signoz.cloud") || lowered.includes("not-setup");
}

function emitContext(context) {
  process.stdout.write(
    JSON.stringify({
      hookSpecificOutput: {
        hookEventName: "SessionStart",
        additionalContext: context,
      },
    }),
  );
}

if (!isTruthy(process.env.CLAUDE_PLUGIN_OPTION_SIGNOZ_SELF_HOSTED)) {
  process.exit(0);
}

const pluginRoot = process.env.CLAUDE_PLUGIN_ROOT || path.join(__dirname, "..", "..");
const registrationPath = path.join(pluginRoot, ".signoz_claude_mcp.json");

if (!needsSelfHostedSetup(registrationPath)) {
  // Already pointed at a self-hosted endpoint — nothing to nudge about.
  process.exit(0);
}

emitContext(
  "The SigNoz plugin is set to self-hosted mode but its MCP server still " +
    "points at SigNoz Cloud. Tell the user to finish setup by running " +
    "/signoz-mcp-setup with their self-hosted MCP URL, for example: " +
    "/signoz-mcp-setup http://localhost:8000/mcp",
);
