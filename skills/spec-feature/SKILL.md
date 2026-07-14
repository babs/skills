---
name: spec-feature
description: >-
  Turn a feature request into a written spec at specs/NNN-slug.md — problem, scope, out-of-scope,
  acceptance criteria, and phases with a measurable definition-of-done — before any code is written.
  Use when the user proposes a feature, says "I want the app to do X", "add a feature", "spec this out",
  "write a spec", or hands a vague idea to implement. Never start coding a feature from a chat message
  alone; spec it first, get it validated, then implement (see ship-feature).
allowed-tools: Read, Write, Edit, Glob, Grep, AskUserQuestion
version: "1.0.2"
---

# Spec a feature before building it

The spec is the contract. Chat scrolls away and gets misremembered; a file in `specs/` is what the
implementation, the review, and the tests are all checked against. Writing it takes minutes and is the
single highest-leverage step in the loop — a wrong line in a spec costs a sentence to fix, the same
mistake in code costs a day.

## 1. Interrogate — do not invent scope

Read the request. Then read the codebase enough to know what already exists (`specs/README.md`,
`docs/`, `AGENTS.md`, the models, the routes). Now find the holes.

A feature request from a human is always underspecified — that is normal, not a failing. The
questions you must answer before writing anything:

- **Who** uses this, and what are they trying to accomplish? (Not "what button do they want" — *why*.)
- **What exactly changes** for them: what can they do after that they could not do before?
- **What data** does it touch? New tables/columns? Does existing data need backfilling?
- **What is explicitly NOT in scope** for this iteration?
- **What happens when it goes wrong** — empty input, no permission, no results, the third-party is down?
- **Who may see or change this data, and does this feature touch personal data?** The project's auth
  decision was made at init; a feature that starts storing names, emails or anything identifying a
  person **re-opens it**. Say so in the spec and stop for a human — do not inherit "no auth, private
  ingress" by default.
- **How do we know it works?** Something checkable, not a vibe.

Ask the open questions **in one batch** (`AskUserQuestion`) — do not drip-feed. If an answer is a
routine, reversible detail, decide it yourself, write it in the spec, and flag it as a decision the
user can overturn. Reserve questions for what genuinely changes the build.

## 2. Write `specs/NNN-slug.md`

`NNN` = next free 3-digit number, starting at `001`. `slug` = short kebab-case name. Create `specs/`
and `specs/README.md` (the index) if absent.

```markdown
# NNN — <Feature name>

**Status**: draft | approved | in progress | shipped
<!-- draft → approved (you) → in progress (ship-feature, on starting phase 1) → shipped (all phases done) -->
**Requested by**: <who>
**Date**: <YYYY-MM-DD>

## Problem

What hurts today, for whom, in one paragraph. No solution here.

## Solution

What the app does after this ships, in plain language. A user can read this and recognise their
request. No SQL, no class names.

## Scope

- Bullet list of what is included.

## Out of scope

- Bullet list of what is deliberately NOT built now. This section prevents scope creep during
  implementation and is quoted back when someone asks "why doesn't it also…".

## Acceptance criteria

Checkable statements. Each one becomes a test.

- [ ] Given <state>, when <action>, then <observable outcome>.
- [ ] An unauthenticated user gets a 401 on <route>.
- [ ] An empty result set renders "<empty message>", not a spinner or an error.

## Phases

Each phase is independently shippable and ends green. The DoD is a command or an observation — never
"looks good".

### Phase 1 — <name>
- Work: <what gets built>
- **Data model impact**: <none | the tables/columns THIS phase changes>
- **DoD**: <e.g. migration applies on a fresh DB; `pytest tests/test_model.py` green; `make coverage` passes its floor>

### Phase 2 — <name>
- Work: …
- **Data model impact**: <none | …>
- **DoD**: <e.g. `POST /export` returns 202 + a job id; error path returns 400 with a typed body>

### Phase 3 — <name>
- Work: …
- **Data model impact**: <none | …>   <!-- EVERY phase declares it — ship-feature keys on this field -->
- **DoD**: <e.g. clicking Export downloads a file; vitest covers the click and the failure toast>

## Data model impact (summary)

All tables/columns/indexes this feature touches. "None" is a valid, welcome answer. Each **phase** also
declares its own — that is the field `ship-feature` keys on to know when a migration is due.

## Open questions

- [ ] Anything still unresolved. An empty list here is required before implementation starts.

## Decisions

Routine calls made while writing this spec, so they are visible and overturnable.
- <decision> — because <reason>.
```

## 3. Small features

A one-line change does not need three phases and a data-model section. Keep Problem, Solution,
Acceptance criteria, and a single phase. Delete the rest — an honest four-section spec beats a padded
template. But **every** feature gets a file: "too small to spec" is how undocumented behaviour is born.

## 4. Get it validated

Show the user the spec (or its acceptance criteria at minimum) and **wait for approval** before any
code. Set `Status: approved`. Add the row to `specs/README.md`.

Implementation is `ship-feature` — it reads this file and works phase by phase against these DoDs.

## Output

Report: the file path, the acceptance criteria, and any open questions still blocking. If open
questions remain, say so plainly — the spec is not ready and implementation must not start.
