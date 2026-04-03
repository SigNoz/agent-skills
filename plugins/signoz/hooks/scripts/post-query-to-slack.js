#!/usr/bin/env node

import { request } from "https";

const SKILL_NAME = "signoz-clickhouse-query";

function postToSlack(webhookUrl, message) {
  return new Promise((resolve) => {
    const url = new URL(webhookUrl);
    const body = JSON.stringify(message);

    const req = request(
      {
        hostname: url.hostname,
        path: url.pathname,
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Content-Length": Buffer.byteLength(body),
        },
      },
      () => resolve(),
    );

    req.on("error", () => resolve());
    req.setTimeout(5000, () => {
      req.destroy();
      resolve();
    });

    req.write(body);
    req.end();
  });
}

function extractQuery(toolResponse) {
  if (typeof toolResponse === "string") {
    return toolResponse;
  }

  if (toolResponse?.content) {
    return typeof toolResponse.content === "string"
      ? toolResponse.content
      : JSON.stringify(toolResponse.content);
  }

  return JSON.stringify(toolResponse);
}

const chunks = [];

process.stdin.setEncoding("utf8");
process.stdin.on("data", (chunk) => chunks.push(chunk));
process.stdin.on("end", async () => {
  const webhookUrl = process.env.SLACK_WEBHOOK_URL;
  if (!webhookUrl) {
    process.exit(0);
  }

  try {
    const payload = JSON.parse(chunks.join(""));

    if (payload?.tool_name !== "Skill") {
      process.exit(0);
    }

    const skillName = payload?.tool_input?.skill;
    if (skillName !== SKILL_NAME) {
      process.exit(0);
    }

    const query = extractQuery(payload?.tool_response);
    const slackMessage = {
      blocks: [
        {
          type: "header",
          text: {
            type: "plain_text",
            text: "ClickHouse Query Generated",
          },
        },
        {
          type: "section",
          text: {
            type: "mrkdwn",
            text: `*Skill:* \`${skillName}\`\n*Session:* \`${payload?.session_id || "unknown"}\``,
          },
        },
        {
          type: "section",
          text: {
            type: "mrkdwn",
            text: `*Generated Output:*\n\`\`\`\n${query.slice(0, 2900)}\n\`\`\``,
          },
        },
      ],
    };

    await postToSlack(webhookUrl, slackMessage);
  } catch {
    // Fail silently — monitoring should never block the workflow.
  }

  process.exit(0);
});
