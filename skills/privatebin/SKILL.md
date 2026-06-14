---
name: privatebin
description: Upload text or a file to a PrivateBin instance via the gearnode/privatebin CLI and emit one JSON object with both the shareable view URL and the delete URL. Use when the user asks to "paste to privatebin", "share via privatebin", "create a privatebin paste", or wants a quick self-destructing paste with revocation handle.
allowed-tools: Bash(privatebin *), Bash(ubi *), Bash(jq *), Bash(command *), Bash(which *)
version: "1.0.0"
---

## Task

Upload content to a PrivateBin instance and surface the two URLs the user actually needs:

- **share** — view URL with the embedded decryption key (fragment after `#`)
- **delete** — revocation URL built from `paste_id` + `delete_token`

Output as a single JSON object so it pipes / greps cleanly.

## Dependencies

| Tool | Purpose | Install |
|---|---|---|
| `privatebin` (gearnode/privatebin) | the CLI itself | `ubi -p gearnode/privatebin -i ~/.local/bin` |
| `ubi` | universal binary installer (only needed if `privatebin` is missing) | <https://github.com/houseabsolute/ubi> |
| `jq` | parse JSON output and build the delete URL | `apt install jq` / `brew install jq` |

Verify each is on `PATH` before running. If missing, print the install hint and stop — do **not** silently fall back.

## Configuration

`privatebin` reads `~/.config/privatebin/config.json`. Generate it once with:

```bash
privatebin init --host https://your-privatebin.example
```

The file has the shape:

```json
{
  "bin": [
    { "name": "", "host": "https://your-privatebin.example" }
  ],
  "expire": "1day",
  "formatter": "plaintext",
  "gzip": true
}
```

- The `bin` array holds one entry per known instance.
- The entry whose `name` is `""` (empty string) is the **default**. `privatebin` (and `--bin ""`) selects it without any flag.
- To target a non-default instance, add another entry with a non-empty `name` and pass `--bin <name>` on the command line.
- `expire`, `formatter`, `gzip` set the per-paste defaults; override per call with `--expire`, `--formatter`, `--gzip=false`.

## Steps

1. **Verify dependencies.** `command -v privatebin jq`. If `privatebin` is missing, install via `ubi -p gearnode/privatebin -i <bin-dir-on-PATH>`.

2. **Verify config.** If `~/.config/privatebin/config.json` does not exist, run `privatebin init --host <user-supplied-host>`. Do not invent a host.

3. **Capture the payload.** Either stdin (heredoc with quoted delimiter `<<'EOF'` to preserve `$`, backticks) or `--filename <path>` to read a file directly.

4. **Pick the options the user asked for** (otherwise leave defaults from config):
   - `--burn-after-reading` — delete on first read
   - `--expire 5min|10min|1hour|1day|1week|1month|1year|never` (instance-dependent)
   - `--formatter plaintext|markdown|syntaxhighlighting`
   - `--password <pw>` — symmetric password on top of the key in the URL
   - `--open-discussion` — enable comments
   - `--bin <name>` — target a non-default instance from the config
   - `--attachment` — treat the input as a binary attachment (use with `--filename`)

5. **Run with `-o json` and reshape via `jq`.** One-liner:

   ```bash
   privatebin create -o json <<'EOF' | jq '{
     share: .paste_url,
     delete: ((.paste_url | sub("\\?.*"; "")) + "/?pasteid=" + .paste_id + "&deletetoken=" + .delete_token)
   }'
   <payload>
   EOF
   ```

   Raw output of `privatebin create -o json`:

   ```json
   {
     "delete_token": "<hex>",
     "paste_id": "<hex>",
     "paste_url": "https://<host>?<id>#<key>"
   }
   ```

   Reshaped output:

   ```json
   {
     "share":  "https://<host>?<id>#<key>",
     "delete": "https://<host>/?pasteid=<id>&deletetoken=<token>"
   }
   ```

6. **Hand both URLs to the user.** Do not echo the payload back — they already have it.

## Notes

- **The decryption key lives in the URL fragment** (`#...`). Anyone with the share URL can decrypt; anyone with the delete URL can revoke. Treat both as secrets at rest.
- **Burn-after-reading + delete URL.** First view consumes the paste. The delete URL still works until that first read.
- **`--bin ""` is the same as omitting `--bin`** — both pick the entry whose `name` is empty in the config.
- **No round-trip with `--attachment`.** Attachments are uploaded as opaque blobs; `privatebin show` returns metadata, not the original file path.
- **Cheap to retry.** Wrong content → re-run with the corrected payload, then `curl -sL` the previous delete URL to revoke the bad one.
