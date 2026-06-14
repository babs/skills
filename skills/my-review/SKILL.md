---
name: my-review
description: Thorough review of all project changes
allowed-tools: Bash(git diff *), Bash(git status *), Bash(git log *), Read, Grep, Glob, WebSearch, WebFetch
version: "1.0.0"
---

## Context

Review the changes taking into consideration maintainability, security, resilience and performance. Seek and surface issues, search for unhappy paths problems (inc. but not limited to race conditions). Never hiding issues or caveats and never taking shortcut for easiness/laziness. Tend to operational excellence and reduced risks.

Review as if this code will run in production under heavy load at 3 AM with no one awake to fix it. Consider the impact on surrounding code, not just the diff in isolation. Prioritize findings by actual risk -- don't flood with style nits when there are logic bugs.

## Task

**Thoroughly** and **deeply** review all code changes:

- **Functionality**: check the code matches the functional requirement and solves the reason it exists
- **Logic**: Correctness, edge cases, error handling
- **Security**: Input validation, injection risks, auth/authz
- **Performance**: N+1 queries, complexity, resource cleanup
- **Coherence**: Naming, patterns, architecture alignment
- **Readability**: keep the cognitive load low, go simple but not naive
- **Language idiomacy**: check it's coherent with the ecosystem and the general instruction from CLAUDE.md
- **Check online**: in case of doubt or time inconsistency check online.
- **Documentation**: if documentation exists (README, guides, etc.), verify accuracy against actual code (endpoints, config, usage examples, CLI flags)
- **Test and codecov**: if defined in the project, analyse/complete tests and code cov focussing on functional code

## Output

Use the template from [template.md](template.md) to format your review output.
