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

4. Bump `version` in `.claude-plugin/plugin.json` (semver) when releasing.

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
