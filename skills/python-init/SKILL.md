---
name: python-init
description: Initialize a new Python FastAPI project or align an existing one to the standard. Use when starting any new Python service or project — when the user says "new Python project", "bootstrap FastAPI", "init a Python service", or asks to align an existing Python project to the standard. Never scaffold a Python service from habit; invoke this skill instead.
allowed-tools: Bash, Write, Edit, Read, Glob, Grep
version: "1.0.1"
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

**Standard config:**
```toml
[project]
name = "project-name"
version = "0.1.0"
requires-python = ">=3.14"
dependencies = [
    "fastapi>=0.115.0",
    "uvicorn[standard]>=0.32.0",
    "pydantic>=2.0",
    "pydantic-settings>=2.0",
    "python-dotenv>=1.0.0",
    "structlog>=24.0.0",
    "fastapi-structured-logging>=0.5.0",
    "httpx>=0.28.0",
    "opentelemetry-api>=1.20.0",
    "opentelemetry-sdk>=1.20.0",
    "opentelemetry-instrumentation-fastapi>=0.44b0",
    "opentelemetry-instrumentation-httpx>=0.44b0",
    "opentelemetry-exporter-otlp>=1.20.0",
]

[dependency-groups]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.24.0",
    "pytest-cov>=5.0",
    "mypy>=1.13.0",
    "ruff>=0.8.0",
    "pre-commit>=4.0.0",
    "detect-secrets>=1.5.0",
]

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
addopts = "-v --tb=short"
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

  - repo: https://github.com/asottile/pyupgrade
    rev: v3.21.2
    hooks:
      - id: pyupgrade
        args: [--py314-plus]

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
.secrets.baseline
```

**Align**: merge missing entries into existing `.gitignore`.

#### .env.example

```
APP_HOST=0.0.0.0
APP_PORT=8000
APP_LOG_LEVEL=INFO
APP_JSON_LOGS=
```

**Align**: create if missing. If exists, add missing `APP_*` vars.

#### Makefile

```makefile
.PHONY: install run lint test docker-build docker-run clean

install:
	uv sync

run:
	uv run ./run.sh

lint:
	pre-commit run --all-files

test:
	uv run pytest

docker-build:
	docker build -t app:local .

docker-run:
	docker run --rm -p 8000:8000 app:local

clean:
	rm -rf __pycache__ .mypy_cache .pytest_cache .ruff_cache .coverage htmlcov
```

**Align**: create if missing. If exists, ensure `lint`, `test`, `install` targets exist.

#### Dockerfile

```dockerfile
FROM python:3.14-slim-trixie AS builder
# pipefail: fail the build if any stage of a piped RUN fails (e.g. bootstrap below),
# instead of silently taking the exit code of the last command in the pipe.
SHELL ["/bin/bash", "-o", "pipefail", "-c"]
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock ./
# `-a requirements | uv pip install`: a uv venv has no pip, so `bootstrap -a install`
# (which shells out to pip) would fail — emit the instrumentor list and let uv install it.
# Call the .venv binary directly, NOT `uv run`: `uv run` re-syncs the dev group, which
# would pull dev tooling back into this --no-dev venv that ships in the final image.
RUN uv sync --frozen --no-dev && \
    .venv/bin/opentelemetry-bootstrap -a requirements | uv pip install --requirement -

FROM python:3.14-slim-trixie

ARG BUILD_TIMESTAMP="1970-01-01T00:00:00+00:00"
ARG COMMIT_HASH="00000000-dirty"
ARG PROJECT_URL="project-name"
ARG VERSION="v0.0.0"

ENV BUILD_TIMESTAMP=${BUILD_TIMESTAMP}
ENV COMMIT_HASH=${COMMIT_HASH}
ENV PROJECT_URL=${PROJECT_URL}
ENV VERSION=${VERSION}

LABEL org.opencontainers.image.source=${PROJECT_URL}
LABEL org.opencontainers.image.created=${BUILD_TIMESTAMP}
LABEL org.opencontainers.image.version=${VERSION}
LABEL org.opencontainers.image.revision=${COMMIT_HASH}

WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
COPY *.py .
COPY run.sh .

RUN useradd -ms /bin/bash -d /app app && chown -R app:app /app && chmod +x /app/run.sh
USER app

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

EXPOSE 8000
CMD ["./run.sh"]
```

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

Entrypoint that **conditionally activates** OpenTelemetry, keyed on `OTEL_EXPORTER_OTLP_ENDPOINT`. `opentelemetry-bootstrap` (Dockerfile build stage) only *installs* the per-library instrumentors; this wrapper launches the app through `opentelemetry-instrument` to activate them — but only when an OTLP endpoint is configured. Without an endpoint it runs plain: no wrapper overhead, no exporter connection errors, and no double-instrumentation if the OTel Operator injects the wrapper itself at deploy time.

```bash
#!/usr/bin/env bash
set -euo pipefail

if [ -n "${OTEL_EXPORTER_OTLP_ENDPOINT:-}" ]; then
    echo "OpenTelemetry enabled (endpoint: ${OTEL_EXPORTER_OTLP_ENDPOINT})"
    export OTEL_SERVICE_NAME="${OTEL_SERVICE_NAME:-project-name}"
    export OTEL_EXPORTER_OTLP_PROTOCOL="${OTEL_EXPORTER_OTLP_PROTOCOL:-grpc}"
    export OTEL_TRACES_EXPORTER="${OTEL_TRACES_EXPORTER:-otlp}"
    export OTEL_METRICS_EXPORTER="${OTEL_METRICS_EXPORTER:-otlp}"
    export OTEL_LOGS_EXPORTER="${OTEL_LOGS_EXPORTER:-none}"
    # exec → opentelemetry-instrument execs python, so the app is PID 1 (clean SIGTERM).
    exec opentelemetry-instrument python main.py
fi

echo "OpenTelemetry disabled (no OTEL_EXPORTER_OTLP_ENDPOINT set)"
exec python main.py
```

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

**Align**: if `tests/` exists, don't overwrite. Check that a test directory + `conftest.py` exist, that the async client uses `httpx.ASGITransport` (not a live server), and that at least `/healthz` and one error path are covered. Report gaps.

### 3. Run tooling

```bash
uv sync
detect-secrets scan > .secrets.baseline  # only if missing
pre-commit install
pre-commit run --all-files
chmod +x main.py run.sh  # if present
```

### 4. AGENTS.md

Create or update `AGENTS.md` following the AGENTS.md standard.

## Output

### New project
Report files created and issues from `pre-commit run --all-files`.

### Existing project
Report as a checklist:
- [x] Item already compliant
- [~] Item updated/fixed (describe change)
- [ ] Item needs manual attention (explain why)
