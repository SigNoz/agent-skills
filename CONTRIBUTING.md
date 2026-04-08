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

## Bumping the Plugin Version

**This is required.** Whenever a skill is added or an existing skill is updated, you must bump the `version` field in **all** plugin manifests:

- `plugins/signoz/.claude-plugin/plugin.json`
- `plugins/signoz/.codex-plugin/plugin.json`
- `plugins/signoz/.cursor-plugin/plugin.json`

Users of Claude Code, Codex, and Cursor receive updates based on the version in these manifests. If the version is not bumped, downstream users will not pick up the changes.

Use [semver](https://semver.org/) to decide the bump:

| Change | Bump |
|--------|------|
| New skill added | Minor (e.g. `1.0.1` -> `1.1.0`) |
| Skill content updated (fix, improvement) | Patch (e.g. `1.0.1` -> `1.0.2`) |
| Breaking change (skill renamed/removed, hook behavior change) | Major (e.g. `1.0.1` -> `2.0.0`) |

## Pull Request Checklist

- [ ] Skill follows the [Agent Skills specification](https://agentskills.io/specification)
- [ ] `name` in SKILL.md frontmatter matches the directory name
- [ ] `README.md` updated if a new skill was added
- [ ] **Plugin versions bumped** in all three manifests (`plugin.json`)
- [ ] Changes tested locally with the relevant tool (Claude Code, Codex, or Cursor)

## License

By contributing, you agree that your contributions will be licensed under the [MIT License](./LICENSE).
