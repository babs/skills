#!/usr/bin/env bash
# Usage: watch-run.sh github <owner/repo> <run-id>
#        watch-run.sh gitlab <group/project> <pipeline-id>
#        watch-run.sh --selftest
# Stops at the FIRST failed job: a run stays in progress while a slower job runs, so waiting for
# the whole run hides a failure. Exit: 0 success, 1 failed or not successful, 2 usage,
# 3 CLI keeps failing, 4 waiting for an approval or a manual job.
set -euo pipefail
readonly POLL="${WATCH_RUN_POLL:-20}"
readonly MAX_ERRORS="${WATCH_RUN_MAX_ERRORS:-5}"

usage() {
  echo "usage: watch-run.sh github <owner/repo> <run-id> | gitlab <group/project> <pipeline-id> | --selftest" >&2
  exit 2
}

# needs CMD...: exits 3 when a command is missing, before any poll misreads it as a CLI failure.
needs() {
  local c
  for c in "$@"; do
    command -v "$c" >/dev/null || { echo "ERROR: ${c} not found"; exit 3; }
  done
}

needs jq mktemp
readonly OBJ='length == 1 and (.[0] | type == "object")' ARR='length > 0 and all(.[]; type == "array")'
errors=0
errf=$(mktemp)
trap 'rm -f "$errf"' EXIT
# fetch VAR SHAPE CMD...: stores CMD's stdout in VAR when it exits 0 with JSON whose slurped values
# pass the jq predicate SHAPE, else counts an error; exits 3 after MAX_ERRORS errors in a row.
# Runs in the main shell so the counter and the exit hold; the caller resets `errors` once every
# fetch of a poll succeeded.
fetch() {
  local var=$1 shape=$2 out
  shift 2
  if out=$("$@" 2>"$errf") && jq -es "$shape" >/dev/null 2>&1 <<<"$out"; then
    printf -v "$var" '%s' "$out"
    return 0
  fi
  [[ -s "$errf" ]] || printf 'unexpected output: %.200s' "$out" >"$errf"
  errors=$((errors + 1))
  echo "cli error ${errors}/${MAX_ERRORS}: $(<"$errf")" >&2
  if ((errors >= MAX_ERRORS)); then
    echo "ERROR: $1 kept failing: $(<"$errf")"
    exit 3
  fi
  return 1
}

watch_github() {
  local repo=$1 run=$2 j="" bad st url
  while true; do
    fetch j "$OBJ" gh run view "$run" -R "$repo" --json status,conclusion,jobs,url || { sleep "$POLL"; continue; }
    errors=0
    url=$(jq -r '.url' <<<"$j")
    st=$(jq -r '.status+" "+(.conclusion // "")' <<<"$j")
    # A continue-on-error job reports failure in a run that still succeeds: the run's verdict wins.
    [[ "$st" == "completed success" ]] && { echo "SUCCESS ${url}"; exit 0; }
    bad=$(jq -r '[(.jobs // [])[]|select(.conclusion=="failure" or .conclusion=="cancelled" or .conclusion=="timed_out")|"\(.name) \(.url)"]|join("\n")' <<<"$j")
    if [[ -n "$bad" ]]; then
      printf 'FAILED %s\n%s\n' "$url" "$bad"
      exit 1
    fi
    case "$st" in
      # A run awaiting approval (first-time contributor) completes with this conclusion.
      "completed action_required") echo "WAITING ${url}: approval needed"; exit 4 ;;
      "completed neutral" | "completed skipped" | "completed stale") echo "NOT-SUCCESS ${url}: ${st}"; exit 1 ;;
      completed*) echo "FAILED ${url}: ${st}"; exit 1 ;;
      waiting*) echo "WAITING ${url}: ${st} (environment protection: approval or wait timer)"; exit 4 ;;
    esac
    sleep "$POLL"
  done
}

watch_gitlab() {
  local project=$1 pipeline=$2 enc p="" jobs="" bridges="" bad st url
  enc=$(jq -rn --arg p "$project" '$p|@uri')
  while true; do
    fetch p "$OBJ" glab api "projects/${enc}/pipelines/${pipeline}" || { sleep "$POLL"; continue; }
    fetch jobs "$ARR" glab api --paginate "projects/${enc}/pipelines/${pipeline}/jobs?per_page=100" || { sleep "$POLL"; continue; }
    # Trigger jobs are not in /jobs: a failed downstream pipeline shows up only here.
    fetch bridges "$ARR" glab api --paginate "projects/${enc}/pipelines/${pipeline}/bridges?per_page=100" || { sleep "$POLL"; continue; }
    errors=0
    url=$(jq -r '.web_url' <<<"$p")
    # allow_failure jobs do not fail the pipeline, so they do not stop the watch.
    bad=$(jq -rs '[.[]|(.[]? // empty)|select((.status=="failed" and (.allow_failure|not)) or .status=="canceled")|"\(.name) \(.web_url)"]|join("\n")' <<<"${jobs}${bridges}")
    if [[ -n "$bad" ]]; then
      printf 'FAILED %s\n%s\n' "$url" "$bad"
      exit 1
    fi
    st=$(jq -r '.status' <<<"$p")
    case "$st" in
      success) echo "SUCCESS ${url}"; exit 0 ;;
      skipped) echo "NOT-SUCCESS ${url}: ${st}"; exit 1 ;;
      failed | canceled) echo "FAILED ${url}: ${st}"; exit 1 ;;
      # waiting_for_resource and scheduled resolve by themselves: keep polling, the outer timeout bounds them.
      manual) echo "WAITING ${url}: manual job"; exit 4 ;;
    esac
    sleep "$POLL"
  done
}

# selftest: fake gh/glab on PATH, one case per exit path.
selftest() {
  local dir rc fails=0 self
  self=$(readlink -f "$0")
  dir=$(mktemp -d)
  trap 'rm -rf "$dir"' RETURN
  cat >"$dir/gh" <<'EOF'
#!/usr/bin/env bash
[[ -n "${FAKE_ERR:-}" ]] && { echo "$FAKE_ERR" >&2; exit 1; }
printf '%s' "$FAKE_OUT"
EOF
  cat >"$dir/glab" <<'EOF'
#!/usr/bin/env bash
case "$*" in
  *"/jobs"*) [[ -n "${FAKE_ERR_JOBS:-}" ]] && { echo "$FAKE_ERR_JOBS" >&2; exit 1; }; printf '%s' "$FAKE_JOBS" ;;
  *"/bridges"*) printf '%s' "${FAKE_BRIDGES:-[]}" ;;
  *) printf '%s' "$FAKE_OUT" ;;
esac
EOF
  chmod +x "$dir/gh" "$dir/glab"
  # check WANT NAME VAR=VALUE...: runs ARGS with the fake env; TO bounds a case that must keep polling.
  check() {
    local want=$1 name=$2
    shift 2
    rc=0
    env PATH="$dir:$PATH" WATCH_RUN_POLL=0 WATCH_RUN_MAX_ERRORS=2 "$@" timeout "${TO:-10}" bash "$self" "${ARGS[@]}" >/dev/null 2>&1 || rc=$?
    if [[ "$rc" != "$want" ]]; then
      echo "selftest FAIL ${name}: rc=${rc}, want ${want}" >&2
      fails=$((fails + 1))
    fi
  }
  local ok='{"name":"a","conclusion":"success","url":"u"}' running='{"name":"b","conclusion":null,"url":"u"}'
  run() { printf '{"status":"%s","conclusion":%s,"url":"u","jobs":%s}' "$1" "$2" "$3"; }
  ARGS=(github o/r 1)
  check 0 "gh success" FAKE_OUT="$(run completed '"success"' "[${ok}]")"
  check 0 "gh success, jobs null" FAKE_OUT="$(run completed '"success"' null)"
  check 1 "gh job failed while run in progress" FAKE_OUT="$(run in_progress null "[${running},{\"name\":\"c\",\"conclusion\":\"failure\",\"url\":\"u\"}]")"
  check 1 "gh job cancelled" FAKE_OUT="$(run in_progress null '[{"name":"c","conclusion":"cancelled","url":"u"}]')"
  check 1 "gh job timed_out" FAKE_OUT="$(run in_progress null '[{"name":"c","conclusion":"timed_out","url":"u"}]')"
  check 1 "gh startup_failure, no jobs" FAKE_OUT="$(run completed '"startup_failure"' '[]')"
  check 0 "gh success with a failed continue-on-error job" FAKE_OUT="$(run completed '"success"' '[{"name":"x","conclusion":"failure","url":"u"}]')"
  check 3 "gh wrong shape" FAKE_OUT='[1]'
  check 1 "gh neutral" FAKE_OUT="$(run completed '"neutral"' "[${ok}]")"
  check 4 "gh action_required" FAKE_OUT="$(run completed '"action_required"' '[]')"
  check 4 "gh waiting for an environment" FAKE_OUT="$(run waiting null "[${ok}]")"
  TO=2 check 124 "gh requested keeps polling" FAKE_OUT="$(run requested null '[]')"
  check 3 "gh keeps failing" FAKE_ERR="HTTP 404: Not Found"
  check 3 "gh not JSON" FAKE_OUT="<html>"
  ARGS=(gitlab g/p 1)
  local gok='[{"name":"a","status":"success","allow_failure":false,"web_url":"u"}]'
  check 0 "glab success" FAKE_OUT='{"status":"success","web_url":"u"}' FAKE_JOBS="$gok"
  check 1 "glab job failed while running" FAKE_OUT='{"status":"running","web_url":"u"}' FAKE_JOBS='[{"name":"a","status":"failed","allow_failure":false,"web_url":"u"}]'
  check 1 "glab job canceled" FAKE_OUT='{"status":"running","web_url":"u"}' FAKE_JOBS='[{"name":"a","status":"canceled","allow_failure":false,"web_url":"u"}]'
  check 1 "glab bridge failed" FAKE_OUT='{"status":"running","web_url":"u"}' FAKE_JOBS="$gok" FAKE_BRIDGES='[{"name":"down","status":"failed","allow_failure":false,"web_url":"u"}]'
  check 0 "glab allow_failure job ignored" FAKE_OUT='{"status":"success","web_url":"u"}' FAKE_JOBS='[{"name":"a","status":"failed","allow_failure":true,"web_url":"u"}]'
  check 1 "glab skipped" FAKE_OUT='{"status":"skipped","web_url":"u"}' FAKE_JOBS='[]'
  check 4 "glab manual" FAKE_OUT='{"status":"manual","web_url":"u"}' FAKE_JOBS='[]'
  TO=2 check 124 "glab waiting_for_resource keeps polling" FAKE_OUT='{"status":"waiting_for_resource","web_url":"u"}' FAKE_JOBS='[]'
  TO=2 check 124 "glab scheduled keeps polling" FAKE_OUT='{"status":"scheduled","web_url":"u"}' FAKE_JOBS='[]'
  check 3 "glab jobs wrong shape" FAKE_OUT='{"status":"running","web_url":"u"}' FAKE_JOBS='{"message":"x"}'
  check 3 "glab jobs endpoint keeps failing" FAKE_OUT='{"status":"running","web_url":"u"}' FAKE_ERR_JOBS="403 Forbidden"
  ARGS=()
  check 2 "no args"
  ((fails == 0)) && echo "selftest ok"
  return "$fails"
}

case "${1:-}" in
  --selftest) needs jq timeout; selftest ;;
  github) (($# == 3)) || usage; needs jq gh; watch_github "$2" "$3" ;;
  gitlab) (($# == 3)) || usage; needs jq glab; watch_gitlab "$2" "$3" ;;
  *) usage ;;
esac
