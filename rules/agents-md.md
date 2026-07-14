---
paths: **/AGENTS.md
---

# AGENTS.md Standard

Follow the [AGENTS.md](https://agents.md/) open standard when creating or updating AGENTS.md files.

- Filename: `AGENTS.md` (uppercase) at repository root
- Format: plain Markdown, no schema or special syntax
- Purpose: agent-focused instructions (not a README for humans)
- Sections: setup, build commands, project structure, code style, key conventions, sensitive data
- Content: actionable commands and context that help coding agents work on the project
- Avoid: project introductions, contribution guidelines, or anything that belongs in README.md
- Nested: subprojects can have their own AGENTS.md — closest file takes precedence

## Effective content

- Only include what agents can't infer from reading the code
- Keep files to ~15-80 lines
- Add entries when agents fail a task, not preemptively
- Enforce constraints via linters, pre-commit hooks, or CI — not "don't do X" instructions
- Omit structure overviews, file listings, and obvious patterns
- Use nested AGENTS.md in subdirectories rather than one large root file
