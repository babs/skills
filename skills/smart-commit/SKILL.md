---
name: smart-commit
description: Interactive branch, conventional commit, and push with user validation. Use for EVERY git commit in interactive sessions — whenever you are about to run `git commit`, the user says "commit", "commit this", "commit and push", "save this work", or a task ends with changes worth committing. Never run `git commit` directly; invoke this skill instead. In headless/non-interactive runs, commit only under an explicit standing authorization.
allowed-tools: Bash(git status *), Bash(git diff *), Bash(git log *), Bash(git branch *), Bash(git checkout *), Bash(git switch *), Bash(git stash *), Bash(git pull *), Bash(git remote *), Bash(git add *), Bash(git commit *), Bash(git push *), Bash(gh pr create *), Bash(pre-commit *), AskUserQuestion
version: "1.1.0"
---

## Task

Prepare and execute a clean git workflow: branch, commit, and optionally push -- with user validation at every decision point.

> **Review first.** For feature work, run a review pass and address (or consciously waive) its findings *before* committing — `/my-review` for a single thorough pass, `/iterative-review` to loop review+fix until clean, or `/swarm-review` for large/risk-sensitive changes. This skill assumes the diff has already been reviewed; it does not review code itself.

## Steps

1. **Analyse changes**: run `git status`, `git diff`, `git diff --cached`, `git log --oneline -5`, and `git branch --show-current`
2. **Decide branch strategy**: choose to stay on the current branch or propose a new one named `<type>/<short-description>` (e.g. `feat/add-auth-endpoint`, `fix/null-pointer-config`). Use conventional commit types: `feat`, `fix`, `docs`, `refactor`, `chore`, `test`, `ci`, `perf`, `style`.
   - **Ticket key in the name is optional.** Append one *only* when a ticket is genuinely in play (mentioned by the user, present in the conversation, or already encoded in the current branch): `<type>/<short-description>-<TICKET>` (e.g. `feat/add-auth-endpoint-PROJ-123`). No ticket mentioned ⇒ no ticket in the name, just `<type>/<slug>`. Never invent or guess a ticket key.
   - **Branch off an up-to-date mainline.** When the new branch comes off a mainline ref (`main`/`master`/`develop`/`trunk`), do not branch from the possibly-stale local state — sync first, carrying the working changes across. This is a *decision* here; it only *runs* at execution (step 6), after the gate. Stash the to-be-committed paths (use `-u` so untracked files come along), fast-forward the mainline, branch, then restore:

     ```bash
     git stash push -u -- <paths>
     git switch <mainline> && git pull --ff-only origin <mainline> --quiet
     git switch -c <new-branch>
     git stash pop
     ```

     This guards against a stale local mainline or leftover changes from a previous task polluting the new branch. Skip the whole dance when staying on an existing typed branch, or when the local mainline is already known up-to-date with a clean diverging point. If `git stash pop` reports a conflict, stop and surface it — never commit a half-applied tree.
   - If already on the repository's default branch (typically `main`/`master`), on a trunk-like ref (`develop`, `trunk`), or on a major version line matching `^v\d+$` (`v1`, `v2`) — these are sliding mainline refs, never commit directly. Propose a new typed sub-branch for the work.
   - If already on a typed feature branch (`feat/...`, `fix/...`, `refactor/...`, any name containing `/`) — the prefix signals a scoped intent. Ask the user: "stay on `<branch>` (piles this change onto the existing scope) or branch off into a new `<type>/...`?" Do not silently stay — unrelated work accumulating on a scoped branch defeats its purpose and muddies the eventual PR diff.
   - When in doubt, ask. Never create a new branch without explicit approval, never auto-stay on a typed branch for a change whose scope diverges from the branch's subject.
3. **Prepare a commit message**: follow [Conventional Commits](https://www.conventionalcommits.org/) format. Subject line under 72 chars. Match the style of recent commits in the repo. Write the message from the diff perspective only -- do not rely on conversation context that a future reader wouldn't have. State only the final facts of the change -- do not narrate the development process or intermediate steps unless critically relevant to understanding the diff.
   - **Default to subject-only.** Add a body only when there is a non-obvious "why" that won't survive in the diff or upstream changelogs.
   - **Mechanical changes** (version bumps, dependency updates, formatter applications, generated code, lint fixes) usually warrant subject + a terse bullet list of the bumps and nothing else. Migration notes, breaking-change explanations, runner requirements etc. live in the upstream changelogs — don't duplicate them.
   - **Substantive changes** (logic decisions, behavior changes, design trade-offs) earn a body explaining the *why* the diff doesn't show: the constraint, deadline, incident, or invariant that drove the choice.
   - **Ticket reference**: when a ticket key is in play, add it as a footer line (a bare `PROJ-123` or `Refs: PROJ-123`). Omit entirely when no ticket exists — never invent one.
   - **Never add validation/process notes** ("verified locally", "tests pass", "act dry-run green", "230/230"). Those belong in the PR description, not durable history — and they rot.
   - **No attribution trailers.** Never add a `Co-Authored-By:` line or any AI/tool attribution (`Generated with …`, `Co-Authored-By: Claude`, signatures, footers) to the commit — not in subject, body, or footer. The same applies to any PR/MR title or description you create in step 6.
   - **Self-check each line:** "could someone derive this from `git show` + the upstream changelog?" — if yes, delete it. Don't restate what the diff already says.
4. **Pre-flight gates — if the project defines one, it MUST be run and it MUST pass.** Not "if it seems relevant", not "the diff is small", not "it was green earlier". Before proposing anything in step 5, go and look for both gates, and say what you found:
   - **Lint/format gate** — `.pre-commit-config.yaml` (or the project's equivalent: `lefthook.yml`, `husky`, a `lint` target). Present ⇒ run it (`pre-commit run --all-files`).
   - **Test gate** — a test command declared anywhere the project declares one: a `test` target in the `Makefile`, `scripts.test` in `package.json`, pytest config in `pyproject.toml`/`pytest.ini`, `*_test.go`, `cargo test`… Present ⇒ run it.

   **Not finding a gate is a finding, and you must state it** ("no pre-commit config; no test command declared") — a silent skip is indistinguishable from a gate you chose not to run, and that is the shortcut this step exists to remove.

   **Read the report, not just the exit status.** An aggregate target can return 0 while a suite inside it failed (a `.ONESHELL` Makefile without `set -e` does exactly that, and so does any `a && b` chain that ends on a passing command). If the exit code and the output disagree, the output wins — and say so, because the project's gate is then itself broken.

   Distinguish three outcomes:
   - **Auto-fix applied** (e.g. ruff-format reformatted files): review the modifications, then re-stage and proceed.
   - **Project-code failure** (lint error, type error, broken test): fix the root cause before proceeding.
   - **Hook itself broken upstream** (e.g. tool incompatible with current Python/Node): stop and ask the user how to proceed. Never use `SKIP=<hook>`, `--no-verify`, `--no-gpg-sign` etc. without explicit user authorization in the same turn.

   **A red gate blocks the commit.** Fix the root cause. Committing over a failing lint gate or a failing test needs the user's explicit authorization *in the same turn*, and the reason is surfaced in the step-5 proposal — never waved through, never deferred to "I'll fix it in the next commit". "The failure is unrelated to my diff" is a claim to verify (stash the change, re-run), not a licence to proceed.

   When the project is set up for coverage (e.g. `pytest-cov`, `go test -cover`, `nyc`/`c8`), run it too, report the figure, and flag functional code paths in the diff left uncovered.
5. **Ask for validation**: present the proposed branch name (or current branch if staying), the commit message, and any PR/MR metadata resolved from your agent instructions (see "PR/MR metadata" below). Then ask the user to approve, adjust, or choose scope [1) branch+commit+push / 2) branch+commit+push + open PR/MR / 3) branch+commit+push + open **draft** PR/MR / 4) branch+commit only / 5) adjust]. The create-PR/MR mechanism is resolved from the remote's forge (`git remote get-url origin`): **GitHub** → `gh pr create` (`--draft` for draft); **GitLab** → `git push` with `-o merge_request.create` (`-o merge_request.draft` for draft). This is the approval gate for the chosen scope -- do not re-prompt for the operations covered by that scope in step 6.

   **Out-of-scope operations require a fresh per-turn gate.** If after step 6 the conversation expands to operations beyond the originally-approved scope -- force-push, `commit --amend`, tag creation, tag push, PR/MR merge, branch deletion, `git reset` -- those each need their own explicit "yes/go/proceed" in the same turn they run, per your global git-mutation rule (if your agent instructions define one). The step-5 gate does not cover them.
6. **Execute**: only after the user approves in step 5, create the branch if needed (following the step-2 strategy, including the branch-off-mainline stash dance when it applies), stage relevant files, commit, and push if requested. Stage files explicitly by name -- never use `git add -A` or `git add .`. When opening a PR/MR, apply every metadata value resolved in step 5 through the forge's mechanism — GitLab push options (`-o merge_request.assign=<user>`, `-o merge_request.label=<label>`, repeated per value) or GitHub `gh pr create` flags (`--assignee <user>`, `--label <label>`, repeatable).

## PR/MR metadata

Before step 5, scan your loaded agent instructions (project- and user-level `CLAUDE.md` / `AGENTS.md` or equivalent, plus any user rules) for a directive that matches the current repository and specifies PR/MR defaults — commonly **assignee**, but also labels, draft status, target/base branch, etc. Such rules are usually scoped by host/group (e.g. "for any repo under `gitlab.com/yourorg/` or `github.com/yourorg/`, assignee is `@someone`"). Match against the push remote (`git remote get-url origin`). When a match exists:

- Surface the resolved values in the step-5 proposal so the user can veto them (e.g. `Assignee: jane.doe (from your global notes)`).
- Apply them in step 6 via the forge's mechanism: GitLab `-o merge_request.*` push options (`assign`, `label`, `draft`, `target`, `milestone`, …) or GitHub `gh pr create` flags (`--assignee`, `--label`, `--draft`, `--base`, `--milestone`). Repeat per value for multi-valued fields (assignees, labels).
- If no rule matches, say nothing — do not invent defaults.

Independently of any matched rule, set title and target/base explicitly when opening a PR/MR so it's unambiguous:

- **target/base** = the resolved default branch (`master`/`main`), not whatever the remote's `HEAD` happens to be — GitLab `-o merge_request.target=<default-branch>`, GitHub `gh pr create --base <default-branch>`.
- **title** = the commit subject, suffixed with the ticket key in brackets when one is in play (e.g. `feat(auth): add oauth login endpoint [PROJ-123]`) — GitLab `-o merge_request.title=<…>`, GitHub `gh pr create --title <…>`.
