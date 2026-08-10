# Swarm Review — {scope}

**Scope**: base `{base-ref}` → head `{head-ref}` · {N} files changed
**Verdict**: {ship | ship-with-followups | block}

### Summary
<!-- 2-3 sentences: overall risk, the most load-bearing finding, and whether any lens flagged a blocker -->

---

### 🔴 Critical (must fix — blocks merge)

∙ **C1.** `[lens]` `cx:{S|M|L}` {defect, one sentence} `{file}:{line}` — {evidence, or `[unverified]`}  
  → **Fix (inst|class):** {the concrete change, one line}

<!-- numbered C1, C2, ...; IDs are stable so the user can reference them in follow-ups. Delete unused placeholder rows, or replace whole section with "None." -->

---

### 🟠 High (should fix before merge)

∙ **H1.** `[lens]` `cx:{S|M|L}` {defect, one sentence} `{file}:{line}` — {evidence, or `[unverified]`}  
  → **Fix (inst|class):** {the concrete change, one line}

---

### 🟡 Medium (fix soon)

∙ **M1.** `[lens]` `cx:{S|M|L}` {defect, one sentence} `{file}:{line}`  
  → **Fix (inst|class):** {the concrete change, one line}

---

### 🔵 Low (nice to have)

∙ **L1.** `[lens]` `cx:{S|M|L}` {defect, one sentence} `{file}:{line}`  
  → **Fix (inst|class):** {the concrete change, one line}

---

### 🟢 Positive

∙ `[lens]` {what was done well, one line each}

---

### Per-lens micro-summary
- **security**: {one line — verdict + finding count, or "clean"}
- **resiliency**: {one line}
- **code-quality**: {one line}
- **functional**: {one line}
- **documentation**: {one line}
- **global-coherence**: {one line}
- **tests-coverage**: {one line}

<!-- include: skills/my-review/template.md#finding-format -->
<!--
Reproduce the typography verbatim — `-`/`*` markers are normalised to a hyphen by the terminal that
reads this report, so the glyph is placed by hand, and two of the three characters are invisible:
  1. `∙` is literal text, NOT a list marker: one blank line between findings, or they merge into one.
  2. the defect line ends with TWO trailing spaces — the hard break that keeps the fix on its own line.
  3. the fix line starts with two NBSP (U+00A0): plain spaces there are stripped as paragraph
     continuation, and the fix loses its indent.
Every finding carries a fix line. Two explicit exceptions:
  → **Fix:** none — trade-off owned: {why living with it is the decision}
  → **Fix (inst):** {change} — a `class` fix exists ({what it is}) but costs {cost}; overrule me if you disagree
A finding whose only fix is `deco` (document it, remember it, be careful) is not a finding: either find the
`inst`/`class` fix or drop it.
-->
<!-- /include -->
