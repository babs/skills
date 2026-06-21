# Contributing

## Add a skill

1. Create `skills/<name>/SKILL.md` with frontmatter:

   ```yaml
   ---
   name: <name>
   description: <when the agent should trigger it — verbs + trigger phrases>
   allowed-tools: <optional tool allowlist>
   version: 0.1.0
   ---
   ```

   `name` and `description` are the only fields required for skills.sh discovery.

2. Body = the instructions the agent follows. Extra assets (templates, scripts)
   live next to `SKILL.md` in the same directory so they travel with the skill.
   Note: a single-skill skills.sh install carries only that directory — don't rely
   on sibling top-level dirs like `rules/` unless you target the full plugin
   install.

3. Update the skills table in [README.md](README.md).

4. **Do not touch `.claude-plugin/plugin.json` `version`** in a feature PR — the plugin
   version is set automatically from the release tag (see [Release](#release)). Leaving it
   out of feature PRs avoids cross-PR conflicts on the version line.

## Release

The plugin version is owned by the release **tag**, not by PRs. To cut a release:

1. Merge the feature PR(s) to `master`.
2. Push a semver tag: `git tag v1.2.0 && git push origin v1.2.0`.

The `release` workflow then writes `1.2.0` into `.claude-plugin/plugin.json` on `master`
(`chore(release): v1.2.0`) and publishes a GitHub release. Consumers with `autoUpdate: true`
pick up the new `master` at next Claude Code startup.

## Test before opening a PR

```bash
# Load the plugin from your working tree in a throwaway session
claude --plugin-dir .

# Validate the marketplace + plugin manifests (offline, no API key)
claude plugin validate .

# Validate SKILL.md frontmatter + ${CLAUDE_PLUGIN_ROOT}/rules references (what CI runs)
bash scripts/validate-skills.sh
```

## PR flow

Branch, commit ([Conventional Commits](https://www.conventionalcommits.org/)), push,
open a PR. CI runs `claude plugin validate .` on every push and PR. Once merged to
`master`, consumers with `autoUpdate: true` pick it up at next Claude Code startup.
