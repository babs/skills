#!/usr/bin/env bash
# Claude Code status line — adapts to terminal width:
#   wide:   ~/current/dir (git::branch) | model | ctx: Nk/Nk (N%) | q: 5hN% ⟳HH:MM
#   narrow: ~/current/dir (git::branch)
#           ctx: Nk/Nk (N%) | q: 5hN% ⟳HH:MM | model

input=$(cat)
raw_cwd=$(echo "$input" | jq -r '.workspace.current_dir // .cwd')

# Collapse $HOME to ~
home="${HOME:-/root}"
if [[ "$raw_cwd" == "$home"* ]]; then
    cwd="~${raw_cwd#"$home"}"
else
    cwd="$raw_cwd"
fi

# Profile badge: only when CLAUDE_CONFIG_DIR points at a custom "$HOME/.claude-<profile>"
config_part=""
if [[ -n "${CLAUDE_CONFIG_DIR:-}" && "$CLAUDE_CONFIG_DIR" == "$home/.claude-"* ]]; then
    config_part=" ($(printf '\xe2\x9c\xb3') ${CLAUDE_CONFIG_DIR#"$home"/.claude-})"
fi

# Git branch via __git_ps1 if available, else fallback to plain git
git_part=""
git_part=$(
    cd "$raw_cwd" 2>/dev/null || exit
    if declare -f __git_ps1 >/dev/null 2>&1; then
        __git_ps1 ' (git::%s)' 2>/dev/null
    else
        branch=$(git symbolic-ref --short HEAD 2>/dev/null \
                 || git rev-parse --short HEAD 2>/dev/null)
        [ -n "$branch" ] && printf ' (git::%s)' "$branch"
    fi
)

# Model display name, shortened to fit the status line
model=$(echo "$input" | jq -r '.model.display_name // .model.id // empty')
model=${model//(1M context)/1M}
model=${model//Opus /O}
model=${model//Sonnet /S}
model=${model//Haiku /H}

# Context usage: "26k/200k" format
used_pct=$(echo "$input" | jq -r '.context_window.used_percentage // empty')
ctx_size=$(echo "$input" | jq -r '.context_window.context_window_size // empty')
if [ -n "$used_pct" ] && [ -n "$ctx_size" ]; then
    used_tokens=$(awk -v pct="$used_pct" -v size="$ctx_size" 'BEGIN{printf "%.0f", pct / 100 * size}')
    # Format both as Nk
    used_fmt=$(awk -v v="$used_tokens" 'BEGIN{if(v>=1000) printf "%.0fk",v/1000; else printf "%.0f",v}')
    total_fmt=$(awk -v v="$ctx_size" 'BEGIN{if(v>=1000) printf "%.0fk",v/1000; else printf "%.0f",v}')
    used_int=$(printf '%.0f' "$used_pct")
    ctx_part=" | ctx: ${used_fmt}/${total_fmt} (${used_int}%)"
else
    ctx_part=""
fi

# Quota usage: "q: 5h24% ⟳17:32" — 5-hour window used %% plus its local reset
# time. rate_limits is present only for Pro/Max subscribers and only after the
# first API response; absent → empty segment.
q5=$(echo "$input" | jq -r '.rate_limits.five_hour.used_percentage // empty')
if [ -n "$q5" ]; then
    q5i=$(printf '%.0f' "$q5")
    quota_inner="5h${q5i}%"
    # Append reset clock only if resets_at is present and parses to a valid time.
    reset5=$(echo "$input" | jq -r '.rate_limits.five_hour.resets_at // empty')
    if [ -n "$reset5" ]; then
        reset_fmt=$(date -d "@${reset5}" +%H:%M 2>/dev/null)
        [ -n "$reset_fmt" ] && quota_inner="${quota_inner} $(printf '\xe2\x9f\xb3')${reset_fmt}"
    fi
    quota_part=" | q: ${quota_inner}"
    # Color by how close the 5h window is to its cap: red near cap, yellow high.
    if [ "$q5i" -ge 90 ]; then
        quota_color=$'\e[1;31m'
    elif [ "$q5i" -ge 75 ]; then
        quota_color=$'\e[0;33m'
    else
        quota_color=$'\e[2;37m'
    fi
else
    quota_part=""
    quota_color=""
fi

# Model part (only if available)
[ -n "$model" ] && model_part=" | ${model}" || model_part=""

# Override terminal title with Claude Code indicator and working directory
printf '\e]0;\xe2\x9c\xb3 [CC] %s\a' "$cwd" > /dev/tty

term_width=$(stty size </dev/tty 2>/dev/null | awk '{print $2}')
: "${term_width:=80}"
max_width=$((term_width - 4))

# Truncate cwd from the left, keeping the deepest path segments
trunc_cwd() {
    local m=$1
    [ "$m" -le 1 ] && { printf '…'; return; }
    [ "${#cwd}" -le "$m" ] && printf '%s' "$cwd" || printf '…%s' "${cwd: -$((m - 1))}"
}

plain="${cwd}${git_part}${model_part}${config_part}${ctx_part}${quota_part}"

if [ "${#plain}" -gt "$max_width" ]; then
    # Line 1: path (left-truncated if needed) + git branch
    line1_cwd=$(trunc_cwd $((max_width - ${#git_part})))
    printf '\e[0;36m%s\e[0;33m%s\e[0m\n' "$line1_cwd" "$git_part"

    # Line 2: ctx + quota + model + profile badge (preserve original colors)
    line2_ctx="${ctx_part# | }"
    line2_model="$model_part"
    line2_len=$(( ${#line2_ctx} + ${#quota_part} + ${#line2_model} + ${#config_part} ))
    if [ "$line2_len" -gt "$max_width" ]; then
        model_max=$((max_width - ${#line2_ctx} - ${#quota_part} - ${#config_part} - 1))
        [ "$model_max" -gt 0 ] && line2_model="${line2_model:0:$model_max}…" || line2_model=""
    fi
    printf '\e[2;37m%s%s%s\e[0;35m%s\e[38;5;208m%s\e[0m' \
        "$line2_ctx" "$quota_color" "$quota_part" "$line2_model" "$config_part"
else
    printf '\e[0;36m%s\e[0;33m%s\e[0;35m%s\e[38;5;208m%s\e[2;37m%s%s%s\e[0m' \
        "$cwd" "$git_part" "$model_part" "$config_part" "$ctx_part" "$quota_color" "$quota_part"
fi
