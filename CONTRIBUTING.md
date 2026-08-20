# Contributing to SigNoz Agent Skills

Thanks for contributing! This guide covers the essentials for adding or updating skills in this repository.

## Getting Started

1. Fork and clone the repository.
2. Create a feature branch from `main`.
3. Make your changes following the conventions below.
4. Open a pull request.

## Adding a New Skill

1. Create a new directory under `plugins/signoz/skills/<skill-name>/`.
2. Add a `SKILL.md` file following the [Agent Skills specification](https://agentskills.io/specification).
3. Use Anthropic's [skill-creator](https://skills.sh/anthropics/skills/skill-creator) to draft, refine, and evaluate the skill.
4. Update the **Available Skills** table in `README.md`.

Install skill-creator with:

```sh
npx skills add https://github.com/anthropics/skills --skill skill-creator
```

### Conventions

- **Skill naming.** Domain action skills use gerund form prefixed with `signoz-`, lowercase with hyphens, e.g. `signoz-creating-alerts`, `signoz-modifying-dashboards`, `signoz-investigating-alerts`. Setup/maintenance skills may use precise object-action names such as `signoz-mcp-setup`; avoid broad command names like `signoz-setup`. Both Anthropic's best-practices doc and the SigNoz Skills/MCP spec recommend gerund form for action skills. The `name` in SKILL.md frontmatter must exactly match the directory name.
- **Descriptions.** Imperative, pushy, and third-person. State both what the skill does and when to trigger it, with explicit user-phrase examples and an "even if they don't say X explicitly" clause. Aim well under the 1024-char limit.
- **"Do NOT use" lists.** Only mention sibling skills that are genuinely similar or competing, i.e. ones a user could plausibly invoke instead. Don't enumerate every other skill in the plugin; rotting cross-references erode trust faster than any clarity they add.
- **MCP tool references.** Use the bare tool name (e.g. `` `signoz_get_alert` ``) in skill bodies. Every SigNoz tool is `signoz_`-prefixed, so the names are self-namespacing and resolve unambiguously even when other MCP servers are loaded. Bare names also stay correct regardless of the registration key: the Claude Code plugin keys the server `mcp`, so a `signoz:` qualifier no longer matches the live `mcp__plugin_signoz_mcp__*` namespace.
- **MCP vs skill split.** MCP is the API; skills are the playbook. Tool definitions, input schemas, schema validation, searchable corpora, live tenant data, and release-sensitive reference data belong in MCP tools/resources. Workflows, conventions, decision rules, interpretation hints, pitfalls, and curated examples belong in skills.
- **Schema reference.** The MCP server is the source of truth for tool input schemas, alert/dashboard JSON shape, and validation rules. Read the `signoz://*` resources rather than transcribing schema into a skill; duplicated schema rots out of sync.
- **Reference files.** Move material >300 lines into `references/`, `scripts/`, or `assets/`. Any reference file longer than 100 lines must start with a `## Contents` table-of-contents.
- **SKILL.md length.** Keep the body under 500 lines. Use progressive disclosure: link to specific reference files with a clear "read this when X" pointer rather than burying detail inline.
- **Plugin manifests.** Keep `plugins/signoz/.codex-plugin/plugin.json`, `plugins/signoz/.cursor-plugin/plugin.json`, and `plugins/signoz/.grok-plugin/plugin.json` in sync with the Claude manifest when adding or removing skills. **Grok Build** reads `.grok-plugin/plugin.json` in preference to `.claude-plugin/plugin.json`, which is exactly why it exists: Claude's manifest points at `.signoz_claude_mcp.json`, whose `${user_config.SIGNOZ_MCP_URL}` placeholder is Claude-only syntax that Grok cannot expand (it fails the handshake with `RelativeUrlWithoutBase`). The Grok manifest points at `.signoz_grok_mcp.json` instead, which uses `${SIGNOZ_MCP_URL:-https://mcp.us.signoz.cloud/mcp}`; Grok expands `${VAR}` and `${VAR:-default}` in MCP `url`, `command`, `args`, `env`, and `headers` at load time. Keep the Grok server key as `signoz`: Grok's `[mcp_servers]` config **replaces** a plugin-provided server of the same name, so the shared key is what makes `grok mcp add signoz` an override instead of a duplicate. Do not give it a unique key like `signoz-grok`; that would leave two live servers and duplicate every tool. The shared key matters for de-duplication too: Grok scans `~/.claude.json`, `~/.cursor/mcp.json`, and `.mcp.json` as compatibility sources, so a user with SigNoz already configured in Claude Code or Cursor gets a second `signoz` from there, and only a same-named `[mcp_servers.signoz]` entry outranks both it and the plugin. The **Antigravity** plugin is native to the **repo root**: `plugin.json` (marker) + `mcp_config.json` (MCP registration, remote key `serverUrl`) + the root `skills` symlink. This lets `agy plugin install https://github.com/SigNoz/agent-skills` stage the repo root as a native Antigravity plugin. Antigravity's `plugin.json` schema is strict (`name` + `description` only, `additionalProperties: false`), so it intentionally carries **no `version`** and is not part of the CalVer bump. Do not point the root `mcp_config.json` at `${...}` interpolation; Antigravity does not resolve it (unlike `gemini-extension.json`, which keeps its `${SIGNOZ_MCP_URL}` prompt for Gemini CLI).

### Writing style

Skill bodies are instructions an agent executes, not prose that persuades a reader. Keep them plain, concrete, and testable. Model-drafted text tends to arrive with a recognizable set of tics; strip them before opening the PR.

- **No em dashes.** Use a colon for a label gloss (`` `spec.variables`: dashboard-level filters ``), a semicolon or period between independent clauses, parentheses for an aside, or a comma for brief apposition. The skill tree is em-dash-free; keep it that way.
- **Banned words.** delve, foster, leverage, utilize, facilitate, empower, streamline, robust, seamless, cutting-edge, paradigm shift, game changer, transformative, elevate, embark, supercharge, harness, ever-evolving, meticulous, intricate, paramount, realm, tapestry, beacon, multifaceted. Say the plain thing instead: "use", "cut", "reliable".
- **Cut empty phrases.** it's worth noting, it's important to note, at the end of the day, when it comes to, at its core, in today's world, the reality is, in order to, going forward. Delete them and state the instruction.
- **No AI-slop rhetoric.** Skip binary contrasts ("it's not X, it's Y"), faux-insight setups ("what most people miss"), colon reveals ("the detail that makes it work: ..."), importance puffery ("plays a vital role"), weasel attribution ("experts agree"), rhetorical questions, and summary-recap endings. Make the claim directly.
- **No punchy fragments or aphorisms.** A rule the agent must follow has to be stated as a rule. "No chips beat wrong chips" became "Offering no follow-ups is better than offering wrong ones"; "They detonate the bill" became "They multiply the metric bill". Sentence fragments and mic-drop kickers read as filler and are easy to misapply.
- **No superficial `-ing` analysis.** Drop trailing "highlighting X", "underscoring Y", "showcasing Z" clauses. State the mechanism or the consequence.
- **Be concrete.** Name the tool, field, threshold, or number. "Verify the key with `signoz_get_field_keys`" beats "ensure attribute correctness".
- **Active voice, direct verbs.** "The server rejects a partial body", not "a partial body is rejected". "decide", not "make a decision".
- **Formatting follows content.** No emoji in headings, no bold sprinkled mid-sentence for emphasis, no bullet list where two sentences read better, no header over a two-sentence section.

Reviewers should treat any of the above in a diff as a change request. `grep -n '—'` over changed files is the fastest single check.

### Further reading

These guides and internal specs shape the conventions above. When in doubt, follow them:

- Anthropic: [Skill authoring best practices](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices)
- agentskills.io: [Best practices for skill creators](https://agentskills.io/skill-creation/best-practices)
- agentskills.io: [Evaluating skill output quality](https://agentskills.io/skill-creation/evaluating-skills)
- agentskills.io: [Optimizing skill descriptions](https://agentskills.io/skill-creation/optimizing-descriptions)
- Agent Skills [specification](https://agentskills.io/specification)
- SigNoz internal: [Skills & MCP Spec](https://www.notion.so/signoz/Skills-MCP-Spec-352fcc6bcd1980c89215deec882df42e#200b80ec35cb4012a246da1ccdc9d580)

## Plugin Versioning (CalVer)

This repository uses **CalVer** (`YYYY.MM.DD`, with an optional `.N` micro suffix for same-day releases) for plugin versions. The version field lives in four manifests per plugin:

- `plugins/signoz/.claude-plugin/plugin.json`
- `plugins/signoz/.codex-plugin/plugin.json`
- `plugins/signoz/.cursor-plugin/plugin.json`
- `plugins/signoz/.grok-plugin/plugin.json`

Users of Claude Code, Codex, Cursor, and Grok Build receive updates based on these versions. If the version is not bumped, downstream users will not pick up the changes.

### Auto-bump workflow

A GitHub Actions workflow (`.github/workflows/auto-version-bump.yml`) opens or updates a version-bump pull request after plugin changes land on `main`. It aggregates every plugin changed since the last successful bump and sets the version to today's date (or appends a micro suffix for multiple bumps in the same day). The root `gemini-extension.json` and `.devin-plugin/plugin.json` manifests mirror the `signoz` plugin and are bumped in lockstep with it. Root-only changes to the Gemini, Devin, or versionless Antigravity ports also trigger a `signoz` version bump.

Repository maintainers must enable **Settings → Actions → General → Allow GitHub Actions to create and approve pull requests** so the workflow's `GITHUB_TOKEN` can open the follow-up PR.

**You do not need to manually bump versions**: after your PR is merged to `main`, the workflow opens or refreshes a follow-up version-bump PR.

## Pull Request Checklist

- [ ] Skill follows the [Agent Skills specification](https://agentskills.io/specification)
- [ ] `name` in SKILL.md frontmatter matches the directory name
- [ ] `README.md` updated if a new skill was added
- [ ] Writing style respected: no em dashes, banned words, or AI-slop patterns (see **Writing style**)
- [ ] **Plugin versions left unchanged** for the follow-up auto-bump PR
- [ ] Changes tested locally with the relevant tool (Claude Code, Codex, Cursor, or Grok Build)

## License

By contributing, you agree that your contributions will be licensed under the [MIT License](./LICENSE).
