#!/usr/bin/env bash
# Guardrails that `claude plugin validate` does NOT cover:
#   1. every skills/*/SKILL.md has non-empty `name:`, `description:` and `allowed-tools:` frontmatter,
#   2. every ${CLAUDE_PLUGIN_ROOT}/rules/<file> referenced by a skill actually exists — and, where the
#      reference names a section, that heading still exists in it,
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

# Markdown headings only. A `# comment` inside a ``` fence is NOT one — otherwise "# Go build stage"
# in a Dockerfile example satisfies check 2b for a heading that was renamed away. Hash-counting
# cannot substitute: a shell comment and a single-hash H1 are both `# text`.
md_headings() { awk '/^```/ { fence = !fence; next } !fence && /^#/' "$1"; }

# 2. Referenced rule files must exist — both the skill form (${CLAUDE_PLUGIN_ROOT}/rules/<f>) and the
#    bare rule→rule form (rules/<f>), so a sibling pointer cannot rot either.
while IFS= read -r ref; do
  if [[ ! -f "$ROOT/rules/$ref" ]]; then
    echo "ERROR: rules/${ref} is referenced but does not exist"
    rc=1
  fi
#    Anchored on `.md`: without it the character class swallows a trailing sentence period
#    ("see rules/python.md." would look up "python.md." and false-fail).
done < <({ grep -rhoE '\$\{CLAUDE_PLUGIN_ROOT\}/rules/[A-Za-z0-9._-]+\.md' "$ROOT/skills" || true
           grep -rhoE 'rules/[A-Za-z0-9._-]+\.md' "$ROOT/rules" || true; } \
           | sed 's#.*/rules/##; s#^rules/##' | sort -u)

# 2b. Referenced rule SECTIONS must exist too — `rules/<file>.md` ("<Heading>").
#    A skill that POINTS at a heading instead of carrying a copy is only as good as that heading:
#    rename the heading and the pointer silently aims at nothing. Check 2 above only proves the
#    file exists, so before this check a rename of "## Go build" left two skills dangling and this
#    script still exited 0. Substring match, because headings carry a trailing "(canonical for …)"
#    the pointer omits; -F so punctuation in a heading stays literal.
while IFS=$'\t' read -r ref section; do
  [[ -f "$ROOT/rules/$ref" ]] || continue   # missing file already reported by check 2
  # `|| true`: grep -c exits 1 on zero matches, which under `set -e` would abort instead of
  # reporting. It still prints the count, so n is always a number.
  n=$(md_headings "$ROOT/rules/$ref" | grep -cF -- "$section" || true)
  if (( n == 0 )); then
    echo "ERROR: skill points at rules/${ref} section \"${section}\", but no heading there matches"
    rc=1
  elif (( n > 1 )); then
    echo "ERROR: skill points at rules/${ref} section \"${section}\", which matches ${n} headings" \
         "— make the pointer unambiguous"
    rc=1
  fi
done < <(grep -rhoE '\$\{CLAUDE_PLUGIN_ROOT\}/rules/[A-Za-z0-9._-]+\.md`? \("[^"]+"\)' "$ROOT/skills" \
           | sed -E 's#.*/rules/([A-Za-z0-9._-]+\.md)`? \("(.*)"\)#\1\t\2#' | sort -u)

# 2c. The Go build-time var SET must agree between rules/golang.md and the go-init template.
#    Not a sync_blocks shared block: the skill's copy sits inside main.go's ```go fence, where
#    `<!-- include: -->` markers would land in the generated .go file. So compare identifier sets —
#    agreement, not byte-identity. This is the drift that lost `Builder` once.
go_build_vars() { awk '/^[[:space:]]*var \(/ { inb=1; next } inb && /^[[:space:]]*\)/ { exit } inb { print $1 }' "$1" | sort; }
if ! diff <(go_build_vars "$ROOT/rules/golang.md") \
          <(go_build_vars "$ROOT/skills/go-init/SKILL.md") >/dev/null; then
  echo "ERROR: Go build-time var set differs between rules/golang.md and skills/go-init/SKILL.md:"
  diff <(go_build_vars "$ROOT/rules/golang.md") \
       <(go_build_vars "$ROOT/skills/go-init/SKILL.md") | sed 's/^/  /'
  rc=1
fi

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

# Known-bad command forms must not survive in prose. A skill's fallback table is copy-paste
# material: when a bundled script abandons a construct as broken, the doc that still prescribes it
# is the failure mode, not a cosmetic lag. One entry per retired form, with why it is retired.
#   «data HTML / hexdump -ve : BSD xargs caps -I replacement at 255 bytes, so the hex-through-xargs
#   macOS clipboard one-liner silently fails above ~127 bytes of HTML (and leaks the doc via argv).
while IFS= read -r hit; do
  echo "ERROR: retired command form referenced in docs (see validate-skills.sh): $hit"
  rc=1
  # `|| true`: zero matches is the GOOD case here, but grep exits 1 for it and `set -e` would kill us.
done < <(grep -rnE '«data HTML|hexdump -ve' "$ROOT/skills" "$ROOT/rules" || true)

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
