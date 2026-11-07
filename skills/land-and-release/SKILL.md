---
name: land-and-release
description: Use when the user orders a landing, such as "land", "land it", "go land", "land the feature", "land and release", "review, commit, land", "merge and release", "merge if confident", "up to the merge", "push, merge and release", "cut a release", "take it to prod", or hands over a reviewed branch or an open PR/MR to finish. Also when a watched PR goes green on work already delegated up to merge or beyond. Not for land as a plain verb or under a negation ("it will land", "no land without a go"), nor a commit, push or PR/MR with no merge asked (smart-commit). Unbuilt work goes through ship-feature or implement-loop first.
# ToolSearch: T3 tools are deferred and must be loaded before the first call.
allowed-tools: Bash, Read, Edit, Write, Grep, Glob, Agent, Skill, AskUserQuestion, ToolSearch, mcp__t3-code__unwatch_pull_request
version: "1.0.0"
---

# Land and release

## Inputs

- **Target**: current branch (default), or a PR/MR number or URL.
- **Scope**: the highest rung the user named, from `commit` < `push` < `pr` < `merge` < `release` < `prod`; each implies those below it. "if confident X" caps it by your confidence: below high, stop one rung lower and give the confidence and its reason. Not stated and not inferable: ask once, with your pick and confidence. The user's own delegation rules win.
- **"land", alone or with a rung above `merge`** ("review, commit, land", "land and release"): a voucher to deliver through dev (integration included), lab or local, no scope question. The `live` row joins the run. "land up to the merge" stops at `merge`, and so does "if confident" below high. The project's notes (memory, `CLAUDE.md`, `AGENTS.md`) name the environment or change the scope. Production only when the user names it or the notes say "land" reaches it. A merge or tag that itself deploys production counts as production: stop before it and give the command. Ask once, before anything else, only if something is deployed and the deploy path (Preflight 3) and the notes do not show where. Nothing deployed and no local instance, or only staging, preprod or production: merge, no question, and give the deploy command if there is one.

## Preflight

1. Forge from `git remote get-url origin`: `gh` for GitHub, `glab` for GitLab.
2. Review: the current tree passed `/my-review`, `/iterative-review` or `/swarm-review`. Not reviewed: run one now. Fix every finding and re-review; a finding needing the user's decision is a blocker. Never call a tree ready without it.
3. Read the repo's conventions, one line each, reused below:
   - merge method: repo settings or `git log --merges` on the default branch
   - release mechanism: release-please, goreleaser, tag-triggered workflow, `chore(release)` commits, CHANGELOG
   - deploy path: ArgoCD app, CI deploy job, compose, local instance (a running process of this repo: `ps -eo pid,lstart,cmd | grep -F "$(git rev-parse --show-toplevel)"`, ignoring shell wrappers and the grep itself), none
4. A sibling skill is missing (single-skill install): use any equivalent review skill, commit directly under Rules, and watch with `gh pr checks --watch` in the background.

## Rungs

Run in order and stop after the scope rung. Three rungs ride along: `issues` belongs to `merge`, `live` to a "land" order, and `cleanup` runs at the end of every run.

| Rung | Do | Proof it is reached |
|---|---|---|
| commit | dirty tree: commit via `/smart-commit`, except work left out under Rules. This order answers its branch and scope questions (scope 5, branch+commit) with no prompt; its gates still run | `git status` clean, apart from that work |
| push | push the branch | remote branch = local `HEAD` |
| pr | open the PR/MR, not draft, assignee per the user's instructions, `Closes #N` for linked issues | PR/MR URL |
| ci | a minute after the later of the PR opening and the last push (one `sleep 60; <read>` with Bash `run_in_background`, not in the foreground), read its checks. Any reported: `/babysit` the PR, one watcher per PR. None reported: nothing to wait for | every required check green; none required: every check green; no checks: nothing to wait for |
| merge | repo's merge method, delete the remote branch | state `merged` |
| issues | each linked issue closed, with a comment naming the merge | `gh issue view N --json state` / `glab issue view N` |
| release | the repo's mechanism. Semver from conventional commits since the last tag | tag/release exists, its workflow is green, artifacts published. A release that deploys by itself: the version read live |
| live | "land" only: get the merged commit running on that environment by its path (restart a local instance). Run `release` first only if the path needs a tag. An instance hosting this session is not restarted: give the command | version read there. A version that does not change per commit: process start time after the merge, and the merged commit checked out |
| prod | the deploy path: Argo bump, manual prod job, promotion | running version = released version, read live: pod image tag, version endpoint, `/healthz` |
| cleanup | always: unwatch the PR, this run's scratchpad files, test artifacts, test servers it started. A delivered instance stays. Once merged only: local branch and worktree. Unmerged or left-out work is never deleted, and its worktree stays | none of them left (`git worktree list`, `git branch`, `ss -ltn`) |

**Red CI or failed rollout**: read the failing job or pod log and fix the root cause. A flaky test gets fixed, never retried until green. Review the fix, push, watch again. It becomes a blocker only when the fix needs the user's decision.

## Rules

- Inside the scope: no proposals, no re-asking. The delegation is the go for every git mutation it implies.
- A delegation covers the work the user asked to ship and what shipping it takes (review and CI fixes). Unrequested or exploratory work in the tree stays uncommitted: say so in the final message.
- A spike is never committed or pushed to the project, whatever the scope. It stays out of git: say so in the final message.
- Before the first push, read the owner from `git remote get-url --push <remote>`, never from the remote's name. Not the user and not an org they belong to (`gh api user/memberships/orgs/<owner>`; GitLab: the namespaces in the user's instructions): ask.
- Public remote: before each push, scan `git log -p <base>..HEAD` and the PR and release text for private names, internal hosts and IPs, and remove them first.
- Stop only on a real blocker: CI or a rollout you cannot fix, a refused command, a trade-off the user owns, a push target outside the user's account and orgs.
- Above the scope rung: stop and give the exact next command.
- Several PRs: one watcher each, merge in dependency order.
- Silent during the run. The final message is 3 to 5 lines: the highest rung reached and its proof (URL, version seen live). Never say "done" on an intermediate rung.

## Example

"merge if confident and release" on a branch with an open PR: scope = `release` at high confidence, else `merge`. Babysit, merge, close issues, tag `v1.4.0`, watch the release workflow. Report the PR URL, tag and workflow run. Prod is not in scope, so give the prod command.
