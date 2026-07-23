---
name: my-review
description: Thorough review of all project changes. Use BEFORE committing feature work — when an implementation is complete and changes are about to be committed, or when the user says "review this", "review my changes", "check the diff". Feature work must pass a review before committing — prefer this, /iterative-review, or /swarm-review when installed, otherwise an equivalent review skill; then commit via /smart-commit when installed, or an equivalent flow.
# Bash + Write unrestricted: the evidence bar below DEMANDS execution (run the suite, build the
# image, scaffold a throwaway) — a review skill that can only read ships hypotheses. Write is for
# scratch files; the review itself must not modify the tree under review.
allowed-tools: Bash, Write, Read, Grep, Glob, WebSearch, WebFetch, AskUserQuestion
version: "1.2.1"
---

## Context

Review the changes taking into consideration maintainability, security, resilience and performance. Seek and surface issues, search for unhappy paths problems (inc. but not limited to race conditions). Never hiding issues or caveats and never taking shortcut for easiness/laziness. Tend to operational excellence and reduced risks.

Review as if this code will run in production under heavy load at 3 AM with no one awake to fix it. Consider the impact on surrounding code, not just the diff in isolation. Prioritize findings by actual risk -- don't flood with style nits when there are logic bugs.

## Task

**Thoroughly** and **deeply** review all code changes:

- **Functionality**: check the code matches the functional requirement and solves the reason it exists
- **Logic**: Correctness, edge cases, error handling
- **Security**: Input validation, injection risks, auth/authz. Anchor findings to recognised standards where they apply — OWASP Top 10 (web) / OWASP API Security Top 10 (APIs), OWASP ASVS for verification depth, and CWE IDs for precise classification. Cover the usual suspects: injection (SQL/NoSQL/command/template), broken access control, SSRF, insecure deserialization, secrets in code or logs, weak/misused crypto, missing rate limiting, and vulnerable dependencies (CVEs) touched by the change.
- **Performance**: N+1 queries, complexity, resource cleanup
- **Coherence**: Naming, patterns, architecture alignment
- **Readability**: keep the cognitive load low, go simple but not naive
- **Language idiomacy**: check it's coherent with the ecosystem and the general instruction from CLAUDE.md
- **Check online**: in case of doubt or time inconsistency check online.
- **Documentation**: if documentation exists (README, guides, etc.), verify accuracy against actual code (endpoints, config, usage examples, CLI flags). Any inconsistency between documentation/specs and actual code or behavior is **High severity at minimum** — never rate it Medium or below
- **Test and codecov**: if defined in the project, run the test suite and coverage, analyse/complete tests and code cov focussing on functional code; report any failure as a finding
- **Pre-commit hooks**: if the project defines pre-commit hooks (or equivalent lint/format gates), run them on the changes and report any failure as a finding

<!-- block: review-doctrine -->
## The evidence bar — reading is not verification

A Critical or High finding must carry **evidence you produced**, not an argument you constructed:

- The command you ran and the output you saw. `curl` it, `pytest` it, `docker build` it, `issubclass()`
  it, `psql` it.
- If the defect is in code that can be executed, **execute it**. Scaffold a throwaway project if that is
  what it takes; it costs minutes.
- **Break it on purpose**: delete the fix and confirm the test goes red; inject the drift and confirm the
  check fails. A guard nobody has bypassed is a guard nobody has tested.
- Cannot run it? Say `[unverified]` in the finding. That is honest and useful. Silently implying you ran
  it is neither.

Findings from reading alone are hypotheses. Ship them as hypotheses.

## The fix bar — do not propose decoration

Every fix you propose is one of three tiers. Name the tier.

| Tier | What it is | Verdict |
|---|---|---|
| **T0 — decoration** | A promise: *"keep them in sync"*, *"remember to"*, *"document that"*, *"be careful"*, *"reviewers should check"* | **Never propose alone.** It is the bug wearing a hat |
| **T1 — instance fix** | Repairs this occurrence | Acceptable when no T2 exists, or T2 costs more than the bug |
| **T2 — class fix** | Makes the defect **un-shippable**: a test that fails without it, a lint rule, a CI gate, a type, a schema, an invariant, a deleted duplicate | **Prefer this whenever it exists and is cheap** |

If you propose T1 where a T2 exists, **say so explicitly and justify it** — name the cost of the T2 and
why it is not worth paying today. Let the human overrule you. Quietly choosing the cheap path and
presenting it as the fix is the failure this bar exists to prevent.

**The tells of a T0 masquerading as a fix**: it adds words to a document and changes no behaviour; it
relies on a future human remembering; it would not have caught the bug that just happened. Ask of every
fix: *"if this had been in place last week, would the defect have been impossible — or merely
discouraged?"*
<!-- /block -->

## Output

**Read [template.md](template.md) and print the report in exactly that format** — same sections,
same order, same heading text, same `C1/H1/M1/L1` ID scheme. It is a mandatory format, not a
suggestion: no freeform prose report, no invented sections, no severity table swapped in, no
findings listed only inside a tool call. Sections with nothing to report keep their heading and say
`None.`

**Print that full report as message text before anything else.** Every section, every finding,
written out as visible assistant text. It is the deliverable; the fix menu is not a substitute for
it. Do **not** condense it into an `AskUserQuestion` header, options, or descriptions, and do
**not** call `AskUserQuestion` in place of printing it. Only once the whole report is printed do
you move to the fix-scope step below.

## Fix scope — offer after the review

Once the review is printed **in full**, do **not** start fixing. Ask the user how far down the
severity ladder to go, via `AskUserQuestion` (single-select), so the choice is explicit:

1. **Fix everything** — from the first Critical to the last Low.
2. **Critical + High + Medium** — leave Lows.
3. **Critical + High** — leave Medium and Low.
4. **AI-proposed scope** — you propose the explicit list of findings worth addressing (by
   ID), cutting across severities on judgement rather than a clean severity band. The user
   approves the list before you fix it.
5. **Something else** — user names a subset (specific finding IDs, a single severity, or "none").

Drop any option that would be redundant or empty — when two options would cover the exact
same findings (e.g. no Lows makes 1 and 2 identical), keep only one. If the review found
nothing actionable, skip the menu entirely and say so.

**When invoked from another skill or loop** (`iterative-review`, `ship-feature`,
`implement-loop`, or any caller whose flow acts on findings by design): still print the full
report in the mandated format, then **skip the menu and hand back** — the caller already owns
the fix scope, and asking here stalls its loop. The menu is for direct `/my-review` invocations.

Apply exactly the selected scope, nothing beyond it. Findings left out of scope stay in the
printed review as the record of what was consciously waived.
