#!/usr/bin/env node

function emitDecision(decision, reason) {
  process.stdout.write(
    JSON.stringify({
      hookSpecificOutput: {
        hookEventName: "PreToolUse",
        permissionDecision: decision,
        permissionDecisionReason: reason,
      },
    }),
  );
}

function shouldAllowUrl(rawUrl) {
  if (typeof rawUrl !== "string" || rawUrl.trim() === "") {
    return false;
  }

  let parsedUrl;

  try {
    parsedUrl = new URL(rawUrl);
  } catch {
    return false;
  }

  const hostname = parsedUrl.hostname.toLowerCase();
  const isSigNozHost =
    hostname === "signoz.io" || hostname.endsWith(".signoz.io");

  return parsedUrl.protocol === "https:" && isSigNozHost;
}

const chunks = [];

process.stdin.setEncoding("utf8");
process.stdin.on("data", (chunk) => chunks.push(chunk));
process.stdin.on("end", () => {
  try {
    const payload = JSON.parse(chunks.join(""));
    const rawUrl = payload?.tool_input?.url;

    if (shouldAllowUrl(rawUrl)) {
      emitDecision("allow", "Allowlisted SigNoz HTTPS URL");
      return;
    }
  } catch {
    // Malformed input — exit silently, let other hooks or default behavior handle it.
  }

  // Non-SigNoz URL — exit silently (no output = no decision).
  // Previously returned "ask" for non-SigNoz or malformed requests in bypassPermissions mode.
  process.exit(0);
});
