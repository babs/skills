---
name: md-to-html-clipboard
description: Render Markdown to HTML and load it into the system clipboard so it pastes as rich-formatted text in apps that don't accept Markdown (Teams, Slack, Outlook, Confluence WYSIWYG, Gmail, …). Use when the user asks to "copy as HTML", "paste this in Teams/Slack/Outlook", "convert markdown for clipboard", or hands over Markdown destined for a non-Markdown UI.
allowed-tools: Bash(md2clip *), Bash(bash *md2clip*), Bash(cat *), Bash(pandoc *), Bash(xclip *), Bash(wl-copy *), Bash(osascript *), Bash(uname *), Bash(command *), Bash(which *)
version: "1.2.1"
---

## Task

Take a Markdown snippet (inline from the user, or a file path they point to) and place an **HTML rendering** of it on the system clipboard, so the next paste in a rich-text app pastes formatted text instead of raw Markdown.

The user's Markdown is the source of truth — do not rewrite, summarize, or "fix" it. Only render.

## Steps

Prefer the **bundled `md2clip` wrapper** — it auto-detects the clipboard backend
(X11 `xclip` / Wayland `wl-copy` / macOS `osascript`) and renders GFM → HTML, so there is
no per-platform pipeline to remember.

1. **Capture the Markdown source** (inline from the request, or a file path). For inline, use a
   heredoc with a quoted delimiter (`<<'EOF'`) so backticks, `$`, etc. are preserved verbatim.

2. **Run the wrapper** (resolve its dir from this skill's path):
   ```bash
   cat <<'EOF' | bash <skill-dir>/md2clip
   ...markdown...
   EOF
   # or: bash <skill-dir>/md2clip file.md
   ```
   It's also symlinked to `~/.local/bin/md2clip` for direct CLI use. It errors (no silent
   plain-text fallback) if `pandoc` or a clipboard tool is missing.

3. **Microsoft Teams → add `--teams`.** Teams collapses `<p>` spacing. `--teams` turns each
   paragraph into a **single `<br>`** (NOT `<br><br>` = too much space) and keeps real
   `<ul>/<li>` lists untouched:
   ```bash
   cat <<'EOF' | bash <skill-dir>/md2clip --teams
   ...markdown...
   EOF
   ```

4. **Confirm.** One short line: *"Clipboard loaded — paste in <app / 'rich-text app'>."* Do not
   echo the HTML back unless asked — the artifact lives on the clipboard.

**Fallback (no wrapper available)** — pipe manually by platform:

| Platform | Command |
|---|---|
| Linux + X11 | `pandoc -f gfm -t html \| xclip -selection clipboard -t text/html -i` |
| Linux + Wayland | `pandoc -f gfm -t html \| wl-copy --type text/html` |
| macOS | `pandoc -f gfm -t html > /tmp/m.html && osascript -e 'on run argv' -e 'set the clipboard to (read (POSIX file (item 1 of argv)) as «class HTML»)' -e 'end run' /tmp/m.html` |

> **macOS — reject the hex one-liner.** The widely-circulated variant that hex-encodes the HTML and
> feeds it through `xargs` into an AppleScript data literal is broken: BSD `xargs` caps `-I`
> replacement at 255 bytes (`-S` default) and hex doubles the payload, so it silently fails above
> ~127 bytes of HTML. It also exposes the whole document in `argv` (visible via `ps`). Use the
> temp-file form above. (`scripts/validate-skills.sh` rejects the retired spelling on sight.)

## Notes

- **Format.** `gfm` covers fenced code blocks, tables, task lists, autolinks. Use plain `markdown` only if the input clearly relies on pandoc-only syntax.
- **Tables.** GFM tables paste correctly in Outlook / Confluence / Word but **not** in Slack (Slack strips tables). Warn the user if their input has a `|---` table and the destination is Slack.
- **Code blocks.** Pandoc emits `<pre><code>` — pastes cleanly in Teams / Slack / Confluence. No extra flags.
- **No round-trip.** Pasting HTML clipboard content into a Markdown-only app (code editor, terminal) pastes raw HTML. Re-render with `-t markdown` if a round-trip is needed.
- **Cheap to retry.** If wrong content lands on clipboard, just re-run with the corrected source — no destructive state.

## Example

User: *"convert this for Teams: # Hello\n- item 1\n- item 2"*

```bash
cat <<'EOF' | bash <skill-dir>/md2clip --teams
# Hello
- item 1
- item 2
EOF
```

Reply: *"Clipboard loaded — paste in Teams."*
