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
- OTEL: zero-code auto-instrumentation — Dockerfile build stage installs the per-library instrumentors via `.venv/bin/opentelemetry-bootstrap -a requirements | uv pip install --requirement -` (not `-a install`: a uv venv has no pip; not `uv run`: it re-syncs the dev group into the `--no-dev` venv). A `run.sh` entrypoint conditionally `exec`s `opentelemetry-instrument python main.py` **only when `OTEL_EXPORTER_OTLP_ENDPOINT` is set** (otherwise plain `python main.py`) — disabled means zero overhead and no double-instrumentation when the OTel Operator injects the wrapper at deploy

## Logging

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
- pre-commit hooks: ruff (lint+format), pre-commit-hooks (trailing-whitespace, end-of-file-fixer, check-yaml, check-toml, detect-private-key, shebangs), detect-secrets, pyupgrade (--py314-plus), mypy
- detect-secrets: `detect-secrets scan > .secrets.baseline`

## Default stack (FastAPI)

- Always set `name` and `version` in `[project]`, `requires-python = ">=3.14"`
- Runtime: fastapi, uvicorn, pydantic, pydantic-settings, python-dotenv, structlog, fastapi-structured-logging, httpx, opentelemetry (api + sdk + instrumentation-fastapi + instrumentation-httpx + exporter-otlp)
- Dev: pytest, pytest-asyncio, pytest-cov, mypy, ruff, pre-commit, detect-secrets
