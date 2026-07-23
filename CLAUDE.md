# CLAUDE.md — babs/skills

**Read [CONTRIBUTING.md](CONTRIBUTING.md) before committing or releasing.** It is the source of
truth for skill/rule structure, the pre-commit gate, and the release flow. The rules below are the
ones most easily got wrong — they override any habit or harness default.

## Release: the version is owned by the git tag, never by a PR

- **Never edit `.claude-plugin/plugin.json` `version` by hand**, and never author a manual
  `chore(release): vX.Y.Z` commit. On tag push, the `release` workflow derives the version from the
  tag, writes it into `plugin.json` on `master`, and publishes the GitHub release. Hand-setting it in
  a feature PR is forbidden (CONTRIBUTING §Release, step 4) — it also causes cross-PR conflicts on the
  version line.
- Cutting a release is exactly two steps, nothing more: (1) merge the feature PR(s) to `master`;
  (2) `git tag vX.Y.Z && git push origin vX.Y.Z`. Do not bundle a version bump into feature work, do
  not create the GitHub release yourself.
- Per-skill `version:` frontmatter is a *separate* thing — bump it in the feature PR that changes that
  skill. Only the plugin-level `plugin.json` version is tag-owned.

## Scope — do only what was asked

- No self-initiated version bumps, tags, releases, or extra git mutations. Every git state change
  (commit, push, tag, branch delete, reset, …) is proposed and gated first — see the global
  git-mutation rule. When unsure whether an action is in scope, ask; don't act.
- A skill whose body demands a tool its `allowed-tools` forbids is broken by construction. When
  editing a skill, keep the body and the allowlist in sync.
