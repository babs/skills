#!/usr/bin/env bash
# Guardrails that `claude plugin validate` does NOT cover:
#   1. every skills/*/SKILL.md has non-empty `name:`, `description:` and `allowed-tools:` frontmatter,
#   2. every ${CLAUDE_PLUGIN_ROOT}/rules/<file> referenced by a skill actually exists,
#   3. shared rule/skill blocks have not drifted (scripts/sync_blocks.py, incl. its own unit tests),
#   4. version-pinned values duplicated across files are uniform (uv pin, python base image).
# Exit 0 = clean, 1 = violations found.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
readonly ROOT
rc=0

# 1. Frontmatter completeness.
while IFS= read -r -d '' skill; do
  # Extract the leading `---` … `---` block (empty if the file lacks one).
  # Limit: values must start on the key's line (`key: value` or `key: >-`); a plain-style
  # multiline value would false-negative — repo convention is folded scalars, which pass.
  fm="$(awk 'NR==1 && $0!="---"{exit} NR>1 && $0=="---"{exit} NR>1{print}' "$skill")"
  for field in name description allowed-tools; do
    if ! grep -qE "^${field}:[[:space:]]*[^[:space:]]" <<<"$fm"; then
      echo "ERROR: $skill: missing or empty frontmatter field '${field}'"
      rc=1
    fi
  done
done < <(find "$ROOT/skills" -name SKILL.md -print0)

# 2. Referenced rule files must exist.
while IFS= read -r ref; do
  if [[ ! -f "$ROOT/rules/$ref" ]]; then
    echo "ERROR: skill references \${CLAUDE_PLUGIN_ROOT}/rules/${ref}, but rules/${ref} is missing"
    rc=1
  fi
#    Anchored on `.md`: without it the character class swallows a trailing sentence period
#    ("see rules/python.md." would look up "python.md." and false-fail).
done < <(grep -rhoE '\$\{CLAUDE_PLUGIN_ROOT\}/rules/[A-Za-z0-9._-]+\.md' "$ROOT/skills" \
           | sed 's#.*/rules/##' | sort -u)

# 3. Shared blocks must not have drifted (the canonical block wins). Run unconditionally:
#    a missing rule reference must not mask a drift report — surface both in one pass.
#    Both gates' behaviors are pinned by unit tests — a gate that stops gating is invisible to CI
#    otherwise. VALIDATE_SKILLS_NO_SELFTEST breaks the recursion when the tests run THIS script
#    on scratch trees.
if [[ -n "${VALIDATE_SKILLS_NO_SELFTEST:-}" ]]; then
  echo "note: gate self-tests SKIPPED (VALIDATE_SKILLS_NO_SELFTEST set)"
fi
if [[ -z "${VALIDATE_SKILLS_NO_SELFTEST:-}" ]]; then
  if ! python3 "$ROOT/scripts/test_sync_blocks.py" 2>/dev/null; then
    echo "ERROR: sync_blocks.py unit tests failed — run: python3 scripts/test_sync_blocks.py"
    rc=1
  fi
  if ! python3 "$ROOT/scripts/test_validate_skills.py" 2>/dev/null; then
    echo "ERROR: validate-skills.sh unit tests failed — run: python3 scripts/test_validate_skills.py"
    rc=1
  fi
fi
if ! python3 "$ROOT/scripts/sync_blocks.py"; then
  rc=1
fi

# Bundled-script regression checks: a skill shipping an executable must keep its fragile logic
# under test, or the gate stops gating it. md2clip's Teams HTML transform is pure text — the
# --selftest path exercises it with no pandoc/clipboard, so it runs headless in CI too.
md2clip="$ROOT/skills/md-to-html-clipboard/md2clip"
if [[ -f "$md2clip" ]] && ! bash "$md2clip" --selftest >/dev/null; then
  echo "ERROR: md2clip --selftest failed — the Teams transform drifted"
  rc=1
fi

# 4. Pinned values that live outside any block must at least be UNIFORM across the repo
#    (the historical drift class: same pin bumped in one file, stale in three).
# One pattern per DISTINCT image: distroless static (Go) and cc (Rust) are different images,
# not two spellings of one pin — a shared pattern would false-flag them as divergence.
for pin in 'astral-sh/uv:[0-9][A-Za-z0-9._-]*' 'python:3\.[0-9]+-slim-[a-z]+' \
           'node:[0-9]+' 'golang:[0-9][0-9.]*' 'gcr.io/distroless/static-debian[0-9]+' \
           'gcr.io/distroless/cc-debian[0-9]+' 'postgres:[0-9]+' 'rust:[0-9][0-9.]*'; do
  # `|| true`: under `set -e` a pattern with ZERO matches (grep rc=1) must not kill the script.
  # (It also masks grep rc=2 — unreadable dir — acceptable: rules/ and skills/ always exist here.)
  found="$(grep -rhoE "$pin" "$ROOT/rules" "$ROOT/skills" | sort -u || true)"
  [[ -z "$found" ]] && continue
  if [[ "$(wc -l <<<"$found")" -gt 1 ]]; then
    echo "ERROR: pinned value diverges across files — bump them together:"
    grep -rnE "$pin" "$ROOT/rules" "$ROOT/skills" | sed 's/^/  /'
    rc=1
  fi
done

if [[ "$rc" -eq 0 ]]; then
  echo "skills validation passed"
fi
exit "$rc"
