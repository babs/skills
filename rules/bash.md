---
paths: **/*.sh,**/*.bash
---

# Bash Script Guidelines

- Shebang: `#!/usr/bin/env bash`
- Always `set -euo pipefail`
- Temp files via `mktemp` + cleanup trap: `trap 'rm -f "$tmpfile"' EXIT`; several files / workspace → `mktemp -d` + `trap 'rm -rf "$tmpdir"' EXIT`
- Quote all variables: `"$var"`, `"${array[@]}"`
- Use `[[ ]]` over `[ ]`
- Prefer `$(command)` over backticks
- Use `readonly` for constants
- Functions: use `local` for all variables
- Error handling is part of the script, not an afterthought: anticipate failure points (missing command/file, bad args, failed network call), check them (`if ! cmd; then`), and fail with a clear message to stderr and a non-zero exit
- Silence errors (`cmd || true`, `2>/dev/null`) only when justified — handle the case explicitly and comment why
- Exit codes: 0 success, 1 general error, 2 usage error
