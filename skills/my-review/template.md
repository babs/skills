### Summary
<!-- 1-2 sentences, overall assessment. No recap of the diff. -->

---

### 🔴 Critical (must fix — blocks merge)

∙ **C1.** {defect, one sentence} `{file}:{line}` — {evidence: command → what you saw, or `[unverified]`}  
  → **Fix (T1|T2):** {the concrete change, one line}

<!-- numbered C1, C2, ...; delete unused findings, or replace whole section with "None." -->

---

### 🟠 High (should fix before merge)

∙ **H1.** {defect, one sentence} `{file}:{line}` — {evidence, or `[unverified]`}  
  → **Fix (T1|T2):** {the concrete change, one line}

<!-- numbered H1, H2, ...; delete unused findings, or replace whole section with "None." -->

---

### 🟡 Medium (fix soon)

∙ **M1.** {defect, one sentence} `{file}:{line}`  
  → **Fix (T1|T2):** {the concrete change, one line}

<!-- numbered M1, M2, ...; delete unused findings, or replace whole section with "None." -->

---

### 🔵 Low (nice to have)

∙ **L1.** {defect, one sentence} `{file}:{line}`  
  → **Fix (T1|T2):** {the concrete change, one line}

<!-- numbered L1, L2, ...; delete unused findings, or replace whole section with "None." -->

---

### 🟢 Positive

∙ {what was done well, one line each}

<!-- block: finding-format -->
<!--
Reproduce the typography verbatim — `-`/`*` markers are normalised to a hyphen by the terminal that
reads this report, so the glyph is placed by hand, and two of the three characters are invisible:
  1. `∙` is literal text, NOT a list marker: one blank line between findings, or they merge into one.
  2. the defect line ends with TWO trailing spaces — the hard break that keeps the fix on its own line.
  3. the fix line starts with two NBSP (U+00A0): plain spaces there are stripped as paragraph
     continuation, and the fix loses its indent.
Every finding carries a fix line. Two explicit exceptions:
  → **Fix:** none — trade-off owned: {why living with it is the decision}
  → **Fix (T1):** {change} — T2 exists ({what it is}) but costs {cost}; overrule me if you disagree
A finding whose only fix is T0 (document it, remember it, be careful) is not a finding: either find the
T1/T2 or drop it.
-->
<!-- /block -->
