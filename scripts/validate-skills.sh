#!/usr/bin/env bash
# Guardrails that `claude plugin validate` does NOT cover:
#   1. every skills/*/SKILL.md has non-empty `name:`, `description:` and `allowed-tools:` frontmatter,
#   2. every referenced rules/<file> or skills/<name>/SKILL.md exists (check 2), and every section
#      pointer `<path>` ("<Heading>") still resolves to exactly one heading there (2b),
#   2c. the Go build-time var set agrees between rules/golang.md and the go-init template,
#   3. shared rule/skill blocks have not drifted (scripts/sync_blocks.py, incl. its own unit tests),
#   4. version-pinned values duplicated across files are uniform (uv pin, python base image),
#      and no doc still prescribes a retired md2clip command form (plus md2clip's own --selftest),
#   5. a deps list naming OTel instrumentors also carries opentelemetry-distro,
#   6. the review templates keep their hand-placed finding typography (hard break + NBSP indent).
# Sources scanned for 2/2b: skills/**.md, rules/**.md, CONTRIBUTING.md.
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

# FENCE/FRONTMATTER POLICY — three consumers, three different answers. This differs on purpose; the
# policy flip-flopped twice before it was written down, so do not "align" them:
#
#   consumer     | question                          | fences   | frontmatter
#   check 2      | does this path exist?             | INCLUDED | included
#   2b source    | is this a pointer to enforce?     | excluded | excluded
#   2b target    | is this line a heading?           | excluded | excluded
#
# Existence is a property of the path — a typo is a typo wherever it is written, including inside a
# code example. Enforcement is a property of the *claim*: a pointer shown in a fence documents the
# form, it does not assert that the heading exists. Headings are a property of markdown structure:
# `#` in a fence is code, `#` in frontmatter is a YAML comment. Hash-counting cannot substitute for
# the latter — a shell comment and a single-hash H1 are both `# text`.
# One test per row pins this (test_validate_skills.py); two of the three flips went unnoticed
# because none of the rows was covered.
#
# md_prose serves the two "excluded" rows only.
md_prose() {
  awk 'NR==1 && $0=="---" { fm=1; next }
       fm { if ($0=="---") fm=0; next }
       /^[[:space:]]*(```|~~~)/ { fence=!fence; next }
       !fence' "$1"
}
md_headings() { md_prose "$1" | grep '^#' || true; }

# Section pointers in one file, as `<relpath>\t<target>\t<heading>`. Matched on the FLATTENED prose
# because a pointer may wrap across a line break — this repo hard-wraps at ~100 cols, so a purely
# cosmetic reflow used to disarm the check silently. Curly quotes are normalised first.
md_pointers() {   # $1 = absolute path, $2 = repo-relative label
  md_prose "$1" | sed 's/[“”]/"/g' | awk -v REL="$2" '
    { buf = buf " " $0 }
    END {
      while (match(buf, /(rules\/[A-Za-z0-9._-]+\.md|skills\/[A-Za-z0-9._-]+\/[A-Za-z0-9._-]+\.md)`?[ ]*\("[^"]+"\)/)) {
        p = substr(buf, RSTART, RLENGTH); buf = substr(buf, RSTART + RLENGTH)
        i = index(p, "(\"")
        path = substr(p, 1, i - 1); sub(/`?[ ]*$/, "", path)
        sec = substr(p, i + 2); sub(/"\)$/, "", sec)
        printf "%s\t%s\t%s\n", REL, path, sec
      }
    }'
}

# Every markdown file that may carry a reference or a pointer. CONTRIBUTING.md is in scope because it
# *teaches* the pointer form and carries live examples — the one file that must not rot.
ref_sources() {
  cd "$ROOT" || return
  find skills rules -name '*.md' -type f
  [[ -f CONTRIBUTING.md ]] && echo CONTRIBUTING.md
  return 0
}

# 2. Referenced rule AND skill files must exist. Covers the skill form
#    (${CLAUDE_PLUGIN_ROOT}/rules/<f>), the bare rule→rule form (rules/<f>), and skill references
#    (skills/<name>/SKILL.md) — the last is now a first-class pointer target, so it needs the same
#    existence guarantee. This check owns ALL existence reporting; 2b never repeats it.
#    Reads the RAW file per the policy above: a broken path inside a code example is still broken.
while IFS=$'\t' read -r src ref; do
  if [[ ! -f "$ROOT/$ref" ]]; then
    echo "ERROR: ${src}: references ${ref}, which does not exist"
    rc=1
  fi
#    Anchored on `.md`: without it the character class swallows a trailing sentence period
#    ("see rules/python.md." would look up "python.md." and false-fail).
done < <(while IFS= read -r rel; do
           # `|| true`: grep exits 1 when a file carries no reference, which under `set -e` would
           # abort this subshell and silently truncate the harvest.
           { grep -ohE '(rules/[A-Za-z0-9._-]+\.md|skills/[A-Za-z0-9._-]+/SKILL\.md)' "$ROOT/$rel" || true; } \
             | awk -v S="$rel" '{ printf "%s\t%s\n", S, $0 }'
         done < <(ref_sources) | sort -u)

# 2b. Section pointers — `<path>` ("<Heading>"), where <path> is a rule or a file inside a skill.
#    Pointing beats copying, but a pointer is only as good as the heading: check 2 proves the file
#    exists, not the section, so a rename leaves it dangling with CI green — it did, for "## Go build".
#    Anchored on the PATH deliberately: an earlier version inferred pointers from an English
#    possessive (`zap`'s "sugared") and false-failed ordinary prose. Substring match, because headings
#    carry a trailing "(canonical for …)" the pointer omits; -F keeps punctuation literal.
while IFS=$'\t' read -r src target section; do
  [[ -f "$ROOT/$target" ]] || continue   # existence is check 2's job, for both target kinds
  # `|| true`: grep -c exits 1 on zero matches, which under `set -e` would abort instead of
  # reporting. It still prints the count, so n is always a number.
  n=$(md_headings "$ROOT/$target" | grep -cF -- "$section" || true)
  if (( n == 0 )); then
    echo "ERROR: ${src}: pointer at ${target} section \"${section}\", but no heading there matches"
    rc=1
  elif (( n > 1 )); then
    echo "ERROR: ${src}: pointer at ${target} section \"${section}\" matches ${n} headings" \
         "— make the pointer unambiguous"
    rc=1
  fi
done < <(while IFS= read -r rel; do md_pointers "$ROOT/$rel" "$rel"; done < <(ref_sources) | sort -u)

# 2c. The Go build-time var SET must agree between the standard and its scaffolder. Not a sync_blocks
#     shared block: the skill's copy sits inside main.go's ```go fence, where `<!-- include: -->`
#     markers would land in the generated .go file. So compare identifier sets — agreement, not
#     byte-identity. This is the drift that lost `Builder` once.
#     The pairing is exactly one, hence two names rather than a discovered list.
readonly GO_STD="rules/golang.md" GO_SCAFFOLD="skills/go-init/SKILL.md"
go_build_vars() { awk '/^[[:space:]]*var \(/ { inb=1; next } inb && /^[[:space:]]*\)/ { exit } inb { print $1 }' "$1" | sort; }
# Runs when EITHER side exists. Requiring both was a silent disarm: renaming go-init turned the only
# guard against that drift off, with CI green. A repo with neither file is simply out of scope.
if [[ -f "$ROOT/$GO_STD" || -f "$ROOT/$GO_SCAFFOLD" ]]; then
  comparable=1
  for f in "$GO_STD" "$GO_SCAFFOLD"; do
    if [[ ! -f "$ROOT/$f" ]]; then
      echo "ERROR: ${f} is missing while its counterpart exists — the Go var drift check is disarmed"
      comparable=0
      rc=1
    elif [[ -z "$(go_build_vars "$ROOT/$f")" ]]; then
      # Empty extractions on BOTH sides compare equal, which would pass a tree whose var block was
      # restructured away entirely — a gate that stops gating.
      echo "ERROR: no Go build-time var block found in ${f} — check 2c cannot compare, fix the block"
      comparable=0
      rc=1
    fi
  done
  if (( comparable )); then
    # Captured, never piped bare: `diff` exits 1 on differences, and under `set -euo pipefail` that
    # killed the whole script here — every later check (block drift, pins, selftests) was silently
    # skipped whenever a Go var drift existed.
    report="$(diff <(go_build_vars "$ROOT/$GO_STD") <(go_build_vars "$ROOT/$GO_SCAFFOLD") || true)"
    if [[ -n "$report" ]]; then
      echo "ERROR: Go build-time var set differs between ${GO_STD} and ${GO_SCAFFOLD}:"
      printf '%s\n' "$report" | sed 's/^/  /'
      rc=1
    fi
  fi
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

# 5. The OTel dependency set is all-or-nothing. `opentelemetry-distro` is the SOLE carrier of the
#    `opentelemetry_configurator` entry point, so a deps list naming instrumentors WITHOUT it
#    scaffolds a service that exports nothing — and says nothing: under fastapi-structured-logging
#    its own logs still carry real trace ids, because that library installs an exporter-less
#    TracerProvider on the first log record. Only the empty trace store tells you. That shipped.
#    Matched on the quoted TOML form so prose ABOUT the packages (dockerfile-init's "OTel deps"
#    paragraph) is not a dependency declaration and does not trip the gate.
while IFS= read -r f; do
  if ! grep -q '"opentelemetry-distro' "$f"; then
    echo "ERROR: ${f#"$ROOT/"} declares opentelemetry instrumentors without \"opentelemetry-distro\":"
    echo "  no configurator entry point -> no TracerProvider -> nothing is ever exported."
    rc=1
  fi
  # `|| true`: zero matches is the common case (most files carry no deps list at all).
done < <(grep -rlE '"opentelemetry-instrumentation-' "$ROOT/rules" "$ROOT/skills" || true)

# 6. The review templates place their finding glyph and indent BY HAND — the terminal that renders
#    the report normalises `-`/`*` to a hyphen — and two of the three characters are invisible: the
#    trailing double space (hard break) and the two leading NBSP (indent). Any whitespace-eating
#    tool strips them without a trace. Counted per line, so ONE lost break is caught too.
# Escapes, not literal glyphs: a NBSP in THIS file would be as invisible as the ones it guards.
# Anchored on the bold ID: a Positive line carries no fix, so it needs no hard break either.
dot=$'\u2219'
nbsp=$'\u00a0'
while IFS= read -r -d '' tpl; do
  # `|| true`: grep -c exits 1 on zero matches, which `set -e` would treat as fatal.
  findings="$(grep -c "^${dot} \*\*" "$tpl" || true)"
  [[ "$findings" -eq 0 ]] && continue
  breaks="$(grep -c "^${dot} \*\*.*  $" "$tpl" || true)"
  fixes="$(grep -c "→ \*\*Fix (T1|T2):" "$tpl" || true)"
  indented="$(grep -c "^${nbsp}${nbsp}→ \*\*Fix (T1|T2):" "$tpl" || true)"
  if [[ "$findings" != "$breaks" || "$fixes" != "$indented" ]]; then
    echo "ERROR: ${tpl#"$ROOT/"}: finding typography lost (${findings} finding(s) / ${breaks} hard"
    echo "  break(s), ${fixes} fix line(s) / ${indented} indented) — restore the trailing double"
    echo "  space and the two NBSP; the report renders as one run-on line without them."
    rc=1
  fi
done < <(find "$ROOT/skills" -name 'template.md' -print0)

if [[ "$rc" -eq 0 ]]; then
  echo "skills validation passed"
fi
exit "$rc"
