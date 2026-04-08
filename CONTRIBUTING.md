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

Conventions:
- `name` in SKILL.md frontmatter must exactly match the directory name.
- `description` should explain both what the skill does and when it should trigger.
- Keep `SKILL.md` concise; move deeper reference material into `references/`, `scripts/`, or `assets/` subdirectories.
- Keep plugin manifests in sync with shipped skills for Codex (`plugins/signoz/.codex-plugin/plugin.json`) and Cursor (`plugins/signoz/.cursor-plugin/plugin.json`) distribution.

## Plugin Versioning (CalVer)

This repository uses **CalVer** (`YYYY.MM.DD`, with an optional `.N` micro suffix for same-day releases) for plugin versions. The version field lives in three manifests per plugin:

- `plugins/signoz/.claude-plugin/plugin.json`
- `plugins/signoz/.codex-plugin/plugin.json`
- `plugins/signoz/.cursor-plugin/plugin.json`

Users of Claude Code, Codex, and Cursor receive updates based on these versions. If the version is not bumped, downstream users will not pick up the changes.

### Auto-bump workflow

A GitHub Actions workflow (`.github/workflows/auto-version-bump.yml`) automatically bumps all three manifests on push to `main`. It detects which plugins have changed files and sets the version to today's date (or appends a micro suffix for multiple bumps in the same day).

**You do not need to manually bump versions** — the workflow handles it when your PR is merged to `main`.

## Pull Request Checklist

- [ ] Skill follows the [Agent Skills specification](https://agentskills.io/specification)
- [ ] `name` in SKILL.md frontmatter matches the directory name
- [ ] `README.md` updated if a new skill was added
- [ ] **Plugin versions bumped** in all three manifests (auto-bumped on merge to `main`)
- [ ] Changes tested locally with the relevant tool (Claude Code, Codex, or Cursor)

## License

By contributing, you agree that your contributions will be licensed under the [MIT License](./LICENSE).
