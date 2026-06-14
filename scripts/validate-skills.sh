#!/usr/bin/env bash
# Guardrails that `claude plugin validate` does NOT cover:
#   1. every skills/*/SKILL.md has non-empty `name:` and `description:` frontmatter
#      (the only fields skills.sh discovery requires), and
#   2. every ${CLAUDE_PLUGIN_ROOT}/rules/<file> referenced by a skill actually exists.
# Exit 0 = clean, 1 = violations found.
set -euo pipefail

readonly ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
rc=0

# 1. Frontmatter completeness.
while IFS= read -r -d '' skill; do
  # Extract the leading `---` … `---` block (empty if the file lacks one).
  fm="$(awk 'NR==1 && $0!="---"{exit} NR>1 && $0=="---"{exit} NR>1{print}' "$skill")"
  for field in name description; do
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
done < <(grep -rhoE '\$\{CLAUDE_PLUGIN_ROOT\}/rules/[A-Za-z0-9._-]+' "$ROOT/skills" \
           | sed 's#.*/rules/##' | sort -u)

if [[ "$rc" -eq 0 ]]; then
  echo "skills validation passed"
fi
exit "$rc"
