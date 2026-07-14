---
paths: **/*.py
---

# Python Project Guidelines

- Use uv for dependency management
- New projects: deps in `pyproject.toml [project.dependencies]` + `uv lock`, dev deps in `[dependency-groups]`
- Existing projects with `requirements.txt`: keep as-is, use `uv pip`
- All scripts: `#!/usr/bin/env python3` + executable (`chmod +x`)
- In documentation/README, use `uv run ./script.py` syntax
- Config via .env files (python-dotenv) + Pydantic settings (`env_prefix = "APP_"`)
- Modern type hints only: `list[str]`, `str | None`, `dict[str, Any]` — never `List`, `Optional`, `Dict`
- Dockerfiles must be multi-stage: build with uv, run with `.venv/bin/python3` binary
- Base image: `python:3.14-slim-trixie`
- OTEL: zero-code auto-instrumentation — Dockerfile build stage installs the per-library instrumentors via `.venv/bin/opentelemetry-bootstrap -a requirements | uv pip install --requirement -` (not `-a install`: a uv venv has no pip; not `uv run`: it re-syncs the dev group into the `--no-dev` venv). The canonical `run.sh` entrypoint (`<entrypoint>` = `python main.py` flat / `python -m <pkg>` src-layout):

  ```bash
  #!/usr/bin/env bash
  set -euo pipefail

  # Activate instrumentors ONLY when an endpoint is configured: zero overhead when disabled, no
  # double-instrumentation when the platform's OTel Operator injects the wrapper itself.
  if [ -n "${OTEL_EXPORTER_OTLP_ENDPOINT:-}" ]; then
      export OTEL_SERVICE_NAME="${OTEL_SERVICE_NAME:-<project>}"
      # Logs stay on stdout as JSON (see Logging); without this the SDK log exporter double-emits.
      export OTEL_LOGS_EXPORTER="${OTEL_LOGS_EXPORTER:-none}"
      exec opentelemetry-instrument <entrypoint>   # exec → app is PID 1, gets SIGTERM
  fi

  exec <entrypoint>
  ```

## Logging

**Two requirements, both mandatory, and satisfying one does not satisfy the other.**

**1. Wire format — JSONL / NDJSON: exactly ONE JSON object per line, terminated by `\n`.** This is what makes a log *ingestible*. Never pretty-print (`indent=`), never emit a bare multi-line string, never let a traceback span lines: log collectors (Loki, Elasticsearch/Fluent Bit, `kubectl logs | jq`) are line-oriented, so one multi-line record does not produce one ugly log — it produces N corrupt records, and the exception you most needed to read is the one that shredded itself across them. Exceptions go in a **field** (`exc_info` → a single escaped string), not across lines.

**2. Structured content — fields, not prose.** This is what makes a log *queryable*. The event is a short stable identifier and every variable is its own key:

```python
log.info("resource_created", kind=kind, name=name, user_id=user.id, duration_ms=elapsed)   # yes
log.info(f"created {kind} {name} for {user.email} in {elapsed}ms")                          # no
```

Both lines can end up as valid NDJSON — and the second one is still worthless. `{"message": "created item 42 for user bob"}` cannot be filtered by `user_id`, grouped by `kind`, or averaged over `duration_ms`, because it has no such fields: it is prose in a box. You only discover this at 2am, when the query you need cannot be written. If a value would change between two occurrences of the same event, it is a **field**; the message itself never interpolates.

- **stdout only.** No log files, no rotation, no syslog — the container writes to stdout and the platform collects it
- **Never log a secret, a token, a full connection string, or a raw body that may contain credentials or personal data.** The "every variable is its own key" rule above makes this easy to get wrong: `log.info("request_failed", **ctx)` will happily serialise an `Authorization` header. Redact at the field level, and treat the log collector as a system that keeps whatever you send it, forever
- **FastAPI apps**: use `fastapi-structured-logging` — `setup_logging(json_logs=, log_level=)`, `AccessLogMiddleware`, `get_logger()`
- **uvicorn logging**: `setup_logging()` sets `propagate=True` on `uvicorn`/`uvicorn.error` so errors reach the root JSON handler instead of uvicorn's plain-text default. Pass `log_config=None, access_log=False` to `uvicorn.run()` because `AccessLogMiddleware` already emits access logs as JSON — leaving uvicorn's access logger on produces duplicate, format-inconsistent lines.
- **CLI apps**: use `structlog` with TTY detection — `ConsoleRenderer()` for TTY, `JSONRenderer()` for non-TTY
- **Event naming**: semantic actions with structured context — `log.info("resource_created", kind=kind, name=name)`
- **Startup log**: always emit version, commit_hash, build_timestamp, project_url from env vars

## Testing

- Structure: `tests/conftest.py`, `tests/test_api.py`, `tests/test_e2e.py`, `tests/fixtures/`
- Use `httpx.ASGITransport` + `AsyncClient` for FastAPI tests
- Extract dependencies for mocking (`patch.object` on factory functions)
- E2E tests: mark with `@pytest.mark.e2e`, skip with `pytest.skip()` when infra unavailable
- pytest config: `asyncio_mode = "auto"`, `addopts = "-v --tb=short"`

## Tooling

- ruff: `line-length = 110`, `target-version = "py314"`, select `["E", "W", "F", "I", "B", "C4", "UP"]`
- mypy: strict (`disallow_untyped_defs`, `disallow_any_generics`, `strict_optional`, `warn_return_any`)
- pre-commit hooks: ruff (lint+format), pre-commit-hooks (trailing-whitespace, end-of-file-fixer, check-yaml, check-toml, detect-private-key, shebangs), detect-secrets, mypy. No separate pyupgrade hook — ruff's `UP` rules with `--fix` already do that job; two tools rewriting the same syntax is drift waiting to happen
- detect-secrets: `detect-secrets scan > .secrets.baseline`

## Default stack (FastAPI) — the source of truth

**These floors are canonical.** `python-init` and `fullstack-init` both scaffold them; when a skill and
this file disagree, this file wins. Bump them here, not in a skill.

<!-- block: fastapi-deps -->
```toml
dependencies = [
    "fastapi>=0.118",
    "uvicorn[standard]>=0.34",
    "pydantic>=2.10",
    "pydantic-settings>=2.7",
    "python-dotenv>=1.0",
    "structlog>=24.0",
    "fastapi-structured-logging>=0.6",
    "httpx>=0.28",
    "opentelemetry-api>=1.29",
    "opentelemetry-sdk>=1.29",
    "opentelemetry-instrumentation-fastapi>=0.50b0",
    "opentelemetry-instrumentation-httpx>=0.50b0",
    "opentelemetry-exporter-otlp>=1.29",
]
```
<!-- /block -->

The base dev group (a project that needs more — e.g. `aiosqlite` for a DB test layer — extends this
list *in its own file* and says why; a block boundary must never cut through a TOML value):

<!-- block: fastapi-dev-deps -->
```toml
[dependency-groups]
dev = [
    "pytest>=8", "pytest-asyncio>=0.24", "pytest-cov>=6", "httpx>=0.28",
    "mypy>=1.13", "ruff>=0.8", "pre-commit>=4", "detect-secrets>=1.5",
]
```
<!-- /block -->

Always set `name` and `version` in `[project]`, `requires-python = ">=3.14"`.

## Configuration

- pydantic-settings, `env_prefix = "APP_"` for the app's own settings (`APP_LOG_LEVEL`, `APP_PORT`…)
- **`DATABASE_URL` is the exception, and deliberately so**: it is the 12-factor contract shared with the
  migration runner (`db_migrate`, which strips the `+asyncpg` suffix itself). One variable name; the
  migration Job simply receives a *different value* — the DDL credential — than the app, which gets the
  DML-only one. Two names for one thing would be a naming boundary pretending to be a privilege one:

  ```python
  database_url: SecretStr = Field(validation_alias="DATABASE_URL")
  ```
- No default for anything that must be provided: a missing DB URL must crash at startup, not silently
  point at localhost
- **Credentials are `SecretStr`**, never `str`. A plain `str` password ends up in a `repr()`, a
  `model_dump()`, or a traceback — and from there in the log collector. Call `.get_secret_value()` only
  where the value is actually consumed

## Shutdown

```python
uvicorn.run(app, host=s.host, port=s.port, log_config=None, access_log=False,
            timeout_graceful_shutdown=25)   # >= pool_timeout + command_timeout (10+10) + margin
```

- `timeout_graceful_shutdown=N` where **N ≥ the longest request you permit** — and that is NOT
  `statement_timeout`: a single-query request can legally block `pool_timeout` (10s) on checkout and
  *then* run for `command_timeout` (10s), so the floor is their sum, plus margin. uvicorn's default
  is 5s: shorter than one legitimate slow query, so a rolling deploy kills in-flight requests that
  were going to succeed. Kubernetes' `terminationGracePeriodSeconds` must in turn be ≥ N (default 30
  barely clears 25 — say so in the deploy manifest)
- Dispose the DB engine in the FastAPI `lifespan` shutdown so the pool drains cleanly

## Outbound HTTP (httpx)

- **Always set a timeout** — `httpx.AsyncClient(timeout=httpx.Timeout(10.0, connect=5.0))`. httpx's
  default is *no* timeout, so one slow upstream hangs a worker forever, which is the same
  pool-exhaustion outage as an untimed-out query, one hop further out
- One shared `AsyncClient` per process (connection reuse), created in `lifespan`, not per request
- Retries only for idempotent calls, with backoff and a cap
