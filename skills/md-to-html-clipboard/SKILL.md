---
name: md-to-html-clipboard
description: Render Markdown to HTML and load it into the system clipboard so it pastes as rich-formatted text in apps that don't accept Markdown (Teams, Slack, Outlook, Confluence WYSIWYG, Gmail, …). Use when the user asks to "copy as HTML", "paste this in Teams/Slack/Outlook", "convert markdown for clipboard", or hands over Markdown destined for a non-Markdown UI.
allowed-tools: Bash(pandoc *), Bash(xclip *), Bash(wl-copy *), Bash(osascript *), Bash(uname *), Bash(command *), Bash(which *)
version: "1.0.0"
---

## Task

Take a Markdown snippet (inline from the user, or a file path they point to) and place an **HTML rendering** of it on the system clipboard, so the next paste in a rich-text app pastes formatted text instead of raw Markdown.

The user's Markdown is the source of truth — do not rewrite, summarize, or "fix" it. Only render.

## Steps

1. **Capture the Markdown source.** Either inline content from the request, or a file path. Use a heredoc with a quoted delimiter (`<<'EOF'`) so backticks, `$`, and other shell metacharacters are preserved verbatim.

2. **Detect the platform** with `uname -s` and pick the pipeline:

   | Platform | Command |
   |---|---|
   | Linux + X11 (`xclip` available) | `pandoc -f gfm -t html \| xclip -selection clipboard -t text/html -i` |
   | Linux + Wayland (`wl-copy` available, no `xclip`) | `pandoc -f gfm -t html \| wl-copy --type text/html` |
   | macOS (`uname -s` = `Darwin`) | `pandoc -f gfm -t html \| hexdump -ve '1/1 "%.2x"' \| xargs -I{} osascript -e 'set the clipboard to «data HTML{}»'` |

   Verify `pandoc` and the clipboard helper exist before running. If missing, give the install hint (`apt install pandoc xclip`, `brew install pandoc`, …) and stop — do **not** silently fall back to plain text.

3. **Run the pipeline.** Pipe the Markdown into `pandoc -f gfm -t html`, then into the platform clipboard tool. Do not echo the rendered HTML back unless the user asked — the artifact lives on the clipboard.

4. **Confirm.** One short line: *"Clipboard loaded — paste in <app the user mentioned, or 'rich-text app'>."*

## Notes

- **Format.** `gfm` covers fenced code blocks, tables, task lists, autolinks. Use plain `markdown` only if the input clearly relies on pandoc-only syntax.
- **Tables.** GFM tables paste correctly in Outlook / Confluence / Word but **not** in Slack (Slack strips tables). Warn the user if their input has a `|---` table and the destination is Slack.
- **Code blocks.** Pandoc emits `<pre><code>` — pastes cleanly in Teams / Slack / Confluence. No extra flags.
- **No round-trip.** Pasting HTML clipboard content into a Markdown-only app (code editor, terminal) pastes raw HTML. Re-render with `-t markdown` if a round-trip is needed.
- **Cheap to retry.** If wrong content lands on clipboard, just re-run with the corrected source — no destructive state.

## Example

User: *"convert this for Teams: # Hello\n- item 1\n- item 2"*

```bash
cat <<'EOF' | pandoc -f gfm -t html | xclip -selection clipboard -t text/html -i
# Hello
- item 1
- item 2
EOF
```

Reply: *"Clipboard loaded — paste in Teams."*
