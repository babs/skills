---
name: python-init
description: Initialize a new Python FastAPI service — no database, no UI — or align an existing one to the standard. Use when starting a plain Python service or API, when the user says "new Python project", "bootstrap FastAPI", "init a Python service", or asks to align an existing Python project to the standard. If the app needs PostgreSQL or a React UI, use fullstack-init instead. Never scaffold a Python service from habit; invoke this skill instead.
allowed-tools: Bash, Write, Edit, Read, Glob, Grep
version: "1.2.0"
---

## Context

You are setting up or aligning a Python FastAPI project to the production standard. Follow the rules from `${CLAUDE_PLUGIN_ROOT}/rules/python.md` and `${CLAUDE_PLUGIN_ROOT}/rules/dockerfile.md`.

The user may provide a project name as argument. If not, use the current directory or ask.

## Task

### 1. Detect mode

- **No `pyproject.toml` or `*.py` in current dir**: new project — create everything from scratch
- **Existing project detected**: audit and align — check each file below against the standard, report gaps, and fix them

### 2. Audit / create each file

For **new projects**, create all files. For **existing projects**, check each item and only add/update what's missing or non-compliant. Never overwrite existing application logic — only align config and tooling.

#### pyproject.toml

**Runtime + dev dependency floors are canonical in `${CLAUDE_PLUGIN_ROOT}/rules/python.md`** ("Default
stack (FastAPI) — the source of truth"); the copies below are injected mechanically by `scripts/sync_blocks.py` — never edit
them here, edit the rule and run `--fix`. A hand-maintained second copy is exactly how
`fastapi>=0.115` and `fastapi>=0.118` came to coexist.

```toml
[project]
name = "project-name"
version = "0.1.0"
requires-python = ">=3.14"
```

<!-- include: rules/python.md#fastapi-deps -->
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
<!-- /include -->

<!-- include: rules/python.md#fastapi-dev-deps -->
```toml
[dependency-groups]
dev = [
    "pytest>=8", "pytest-asyncio>=0.24", "pytest-cov>=6", "httpx>=0.28",
    "mypy>=1.13", "ruff>=0.8", "pre-commit>=4", "detect-secrets>=1.5",
]
```
<!-- /include -->

Then the tool config:

```toml
[tool.ruff]
line-length = 110
target-version = "py314"

[tool.ruff.lint]
select = ["E", "W", "F", "I", "B", "C4", "UP"]

[tool.ruff.lint.isort]
known-first-party = ["project_name"]

[tool.mypy]
python_version = "3.14"
check_untyped_defs = true
disallow_untyped_defs = true
disallow_any_generics = true
strict_optional = true
warn_return_any = true
warn_unused_configs = true
ignore_missing_imports = true

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
# --strict-markers: a typo'd/renamed marker must ERROR — otherwise e2e tests silently join the fast layer
addopts = "-v --tb=short --strict-markers"
markers = ["e2e: end-to-end tests requiring external services"]
```

**Align**: if `pyproject.toml` exists, ensure `[tool.ruff]`, `[tool.mypy]`, `[tool.pytest.ini_options]` sections match. Add missing deps to `[dependency-groups] dev`. Don't remove existing project dependencies. If project uses `requirements.txt`, keep it — don't migrate unless asked.

#### .pre-commit-config.yaml

```yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.14.9
    hooks:
      - id: ruff
        args: [--fix, --exit-non-zero-on-fix]
      - id: ruff-format

  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v6.0.0
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
      - id: check-yaml
        args: [--allow-multiple-documents]
      - id: check-toml
      - id: detect-private-key
      - id: check-executables-have-shebangs
      - id: check-shebang-scripts-are-executable

  - repo: https://github.com/Yelp/detect-secrets
    rev: v1.5.0
    hooks:
      - id: detect-secrets
        args: [--baseline, .secrets.baseline]

  # No pyupgrade hook: ruff's UP rules (with --fix) already cover it.
  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.18.1
    hooks:
      - id: mypy
        additional_dependencies: [pydantic]
```

**Align**: if file exists, ensure all repos/hooks above are present. Add missing ones without removing project-specific hooks.

#### .gitignore

```
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
build/
dist/
*.egg-info/
.venv/
venv/
.env.local
.mypy_cache/
.ruff_cache/
.pytest_cache/
.coverage
htmlcov/
*.log
```

`.secrets.baseline` is **committed, never gitignored** — the detect-secrets hook errors out without
it, breaking the gate on every fresh clone and in CI.

**Align**: merge missing entries into existing `.gitignore`.

#### .env.example

```
APP_HOST=0.0.0.0
APP_PORT=8000
APP_LOG_LEVEL=INFO
# APP_JSON_LOGS=true|false — leave COMMENTED for auto-detect: `APP_JSON_LOGS=` (empty string) is not
# "unset", pydantic rejects it as a bool and the app dies at boot

```

**Align**: create if missing. If exists, add missing `APP_*` vars.

#### Makefile

```makefile
.PHONY: install run lint test test-e2e coverage docker-build docker-run clean

install:
	uv sync

run:
	uv run ./run.sh

lint:
	pre-commit run --all-files

test:                  # fast layer — the default
	uv run pytest -m "not e2e"

test-e2e:
	uv run pytest -m e2e

coverage:              # the enforced floor. Raise it as the project matures; never lower it.
	uv run pytest -m "not e2e" --cov --cov-report=term-missing --cov-fail-under=80

docker-build:
	docker build -t app:local .

docker-run:
	docker run --rm -p 8000:8000 app:local

clean:
	rm -rf __pycache__ .mypy_cache .pytest_cache .ruff_cache .coverage htmlcov
```

**Align**: create if missing. If exists, ensure `lint`, `test`, `install` targets exist.

#### Dockerfile

Copy the **flat-layout** template from `${CLAUDE_PLUGIN_ROOT}/rules/dockerfile.md` ("Python build — flat layout") verbatim — builder with pinned uv + OTel bootstrap, runtime with OCI labels, non-root, `COPY run.sh`.

**Align**: if Dockerfile exists, check for: multi-stage build, OCI labels/ARGs, non-root user, `PYTHONUNBUFFERED`, `PYTHONDONTWRITEBYTECODE`. Report what's missing and fix.

#### main.py (new projects only)

```python
#!/usr/bin/env python3
import os

import fastapi_structured_logging
import uvicorn
from fastapi import FastAPI
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    host: str = "0.0.0.0"
    port: int = 8000
    log_level: str = "INFO"
    json_logs: bool | None = None

    model_config = {"env_prefix": "APP_"}


settings = Settings()
log = fastapi_structured_logging.get_logger()

app = FastAPI(title="Service")
app.add_middleware(fastapi_structured_logging.AccessLogMiddleware)


@app.get("/healthz")
async def health() -> dict[str, str]:
    return {"status": "ok"}


def main() -> None:
    if settings.json_logs is True:
        fastapi_structured_logging.setup_logging(json_logs=True, log_level=settings.log_level)
    elif settings.json_logs is False:
        fastapi_structured_logging.setup_logging(json_logs=False, log_level=settings.log_level)
    else:
        fastapi_structured_logging.setup_logging(log_level=settings.log_level)

    log.info(
        "startup",
        version=os.getenv("VERSION", "v0.0.0"),
        commit_hash=os.getenv("COMMIT_HASH", "00000000-dirty"),
        build_timestamp=os.getenv("BUILD_TIMESTAMP", "1970-01-01T00:00:00+00:00"),
        project_url=os.getenv("PROJECT_URL", "unknown"),
    )

    # log_config=None + access_log=False: AccessLogMiddleware already emits JSON
    # access logs; leaving uvicorn's loggers on duplicates them in plain text.
    uvicorn.run(
        app,
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level.lower(),
        log_config=None,
        access_log=False,
    )


if __name__ == "__main__":
    main()
```

**Align**: don't overwrite existing application code. Check that `/healthz` endpoint exists, structured logging is configured, and `Settings` uses pydantic-settings. Report gaps.

#### run.sh (new projects only)

Copy the canonical `run.sh` from `${CLAUDE_PLUGIN_ROOT}/rules/python.md` (OTEL bullet) with `<entrypoint>` = `python main.py`. Conditional OTel activation keyed on `OTEL_EXPORTER_OTLP_ENDPOINT`; assumes single-process uvicorn (multi-worker needs OTel multiprocess handling).

**Align**: create if missing and `chmod +x`. Wire it as the Dockerfile `CMD` (`["./run.sh"]`) and the Makefile `run` target (`uv run ./run.sh`). Assumes single-process uvicorn (the standard `main.py`); multi-worker setups need OTel multiprocess handling.

#### tests/ (new projects only)

`tests/__init__.py` is empty. `tests/conftest.py` wires an in-process async client (no network, no running server) via `httpx.ASGITransport`:

```python
import pytest
from httpx import ASGITransport, AsyncClient

from main import app


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
```

`tests/test_e2e.py` **must exist and must contain at least one `@pytest.mark.e2e` test** — `pytest -m e2e`
with nothing collected exits **5**, which is a red build, not a pass, and `ship-feature` runs
`make test-e2e` on every feature. Scaffold one that self-skips when its target is unset:

```python
import os

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.e2e


@pytest.fixture
def base_url() -> str:
    url = os.environ.get("APP_E2E_URL")
    if not url:
        pytest.skip("APP_E2E_URL not set — skipping e2e suite")
    return url


async def test_healthz_live(base_url: str) -> None:
    async with AsyncClient(base_url=base_url) as ac:
        assert (await ac.get("/healthz")).status_code == 200
```

`tests/test_api.py` covers the happy path and an error path (`asyncio_mode = "auto"` auto-collects async tests):

```python
async def test_healthz(client):
    resp = await client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


async def test_unknown_route_returns_404(client):
    resp = await client.get("/does-not-exist")
    assert resp.status_code == 404
```

**Align**: if `tests/` exists, don't overwrite. **Check `tests/test_e2e.py` exists and holds at least one
`@pytest.mark.e2e` test** — the `test-e2e` target exits 5 ("no tests collected") without one, which is a
red build. Check that a test directory + `conftest.py` exist, that the async client uses `httpx.ASGITransport` (not a live server), and that at least `/healthz` and one error path are covered. Report gaps.

### 3. Run tooling

```bash
uv sync
detect-secrets scan > .secrets.baseline  # only if missing
pre-commit install
pre-commit run --all-files
chmod +x main.py run.sh  # if present
```

### 4. AGENTS.md

Create or update `AGENTS.md` per `${CLAUDE_PLUGIN_ROOT}/rules/agents-md.md`.

## Output

### New project
Report files created and issues from `pre-commit run --all-files`.

### Existing project
Report as a checklist:
- [x] Item already compliant
- [~] Item updated/fixed (describe change)
- [ ] Item needs manual attention (explain why)
