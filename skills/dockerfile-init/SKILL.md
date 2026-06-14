---
name: dockerfile-init
description: Generate a production Dockerfile or align an existing one to the standard
allowed-tools: Bash, Write, Edit, Read, Glob, Grep
version: "1.0.0"
---

## Context

You are adding or aligning a Dockerfile to the production standard. Follow the rules from `${CLAUDE_PLUGIN_ROOT}/rules/dockerfile.md` and the language-specific rule file (`${CLAUDE_PLUGIN_ROOT}/rules/python.md`, `${CLAUDE_PLUGIN_ROOT}/rules/golang.md`, etc.).

The user may specify a language/framework as argument. If not, detect it from project files.

## Task

### 1. Detect project type and mode

Inspect the project root:

| File                                         | Language |
| -------------------------------------------- | -------- |
| `pyproject.toml`, `requirements.txt`, `*.py` | Python   |
| `go.mod`, `*.go`                             | Go       |
| `package.json`                               | Node.js  |
| `Cargo.toml`                                 | Rust     |

- **No Dockerfile**: create one from scratch
- **Dockerfile exists**: audit and align to the standard

### 2. Standard requirements (all languages)

Every Dockerfile must have:

- Multi-stage build (builder + runtime)
- OCI labels and build-time ARGs:
  ```dockerfile
  ARG BUILD_TIMESTAMP="1970-01-01T00:00:00+00:00"
  ARG COMMIT_HASH="00000000-dirty"
  ARG PROJECT_URL="project-name"
  ARG VERSION="v0.0.0"

  LABEL org.opencontainers.image.source=${PROJECT_URL}
  LABEL org.opencontainers.image.created=${BUILD_TIMESTAMP}
  LABEL org.opencontainers.image.version=${VERSION}
  LABEL org.opencontainers.image.revision=${COMMIT_HASH}
  ```
- Non-root user in runtime stage
- Only necessary files copied to runtime stage
- Application port exposed

### 3. Language-specific templates

#### Python (FastAPI/uvicorn)

```dockerfile
FROM python:3.14-slim-trixie AS builder
# pipefail so a failing bootstrap below fails the build instead of being masked.
SHELL ["/bin/bash", "-o", "pipefail", "-c"]
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock ./
# `-a requirements | uv pip install`, not `-a install` (a uv venv has no pip), and the
# .venv binary directly, not `uv run` (which would re-sync the dev group).
RUN uv sync --frozen --no-dev && \
    .venv/bin/opentelemetry-bootstrap -a requirements | uv pip install --requirement -

FROM python:3.14-slim-trixie
# ... ARGs, LABELs ...
WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
COPY *.py .
RUN useradd -ms /bin/bash -d /app app && chown -R app:app /app
USER app
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1
EXPOSE 8000
CMD ["python", "main.py"]
```

If OTEL deps are not in `pyproject.toml`, skip the `opentelemetry-bootstrap` line. Bootstrap only *installs* instrumentors; to *activate* them at runtime see the conditional `run.sh` in the `python-init` skill (gated on `OTEL_EXPORTER_OTLP_ENDPOINT`).

**Align checklist**: multi-stage, uv (not pip), OCI labels, non-root user, `PYTHONUNBUFFERED=1`, `PYTHONDONTWRITEBYTECODE=1`, base image `python:3.14-slim-trixie`.

#### Go

```dockerfile
FROM golang:1.26-bookworm AS builder
WORKDIR /src
COPY go.mod go.sum ./
RUN go mod download
COPY . .
ARG VERSION COMMIT_HASH BUILD_TIMESTAMP PROJECT_URL
RUN CGO_ENABLED=0 go build -ldflags="-s -w \
    -X 'main.Version=${VERSION}' \
    -X 'main.CommitHash=${COMMIT_HASH}' \
    -X 'main.BuildTimestamp=${BUILD_TIMESTAMP}' \
    -X 'main.ProjectURL=${PROJECT_URL}'" \
    -o /app ./cmd/app-name

FROM gcr.io/distroless/static-debian12:nonroot
# ... ARGs, LABELs ...
COPY --from=builder /app /app
EXPOSE 8080
ENTRYPOINT ["/app"]
```

Adapt the build path (`./cmd/app-name`) to match the project's actual entrypoint.

**Align checklist**: multi-stage, `CGO_ENABLED=0`, ldflags with build-time vars, distroless nonroot runtime, OCI labels.

#### Node.js

```dockerfile
FROM node:22-slim AS builder
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM node:22-slim
# ... ARGs, LABELs ...
WORKDIR /app
COPY --from=builder /app/dist ./dist
COPY --from=builder /app/node_modules ./node_modules
COPY package.json .
RUN groupadd -r app && useradd -r -g app -d /app app && chown -R app:app /app
USER app
EXPOSE 3000
CMD ["node", "dist/index.js"]
```

Adapt `dist/`, build command, and entrypoint to the actual project.

**Align checklist**: multi-stage, `npm ci` (not `npm install`), non-root user, OCI labels.

#### Rust

```dockerfile
FROM rust:1.84-slim-bookworm AS builder
WORKDIR /src
COPY Cargo.toml Cargo.lock ./
RUN mkdir src && echo 'fn main(){}' > src/main.rs && cargo build --release && rm -rf src
COPY . .
RUN cargo build --release

FROM gcr.io/distroless/cc-debian12:nonroot
# ... ARGs, LABELs ...
COPY --from=builder /src/target/release/app-name /app
EXPOSE 8080
ENTRYPOINT ["/app"]
```

**Align checklist**: multi-stage, dep caching trick, distroless nonroot runtime, OCI labels.

### 4. Generate .dockerignore

Create or update `.dockerignore` with:

```
.git/
.github/
.gitlab-ci.yml
*.md
LICENSE
.env*
.vscode/
.idea/
```

Plus language-specific entries (e.g. `__pycache__/`, `.venv/`, `node_modules/`, `target/`, `bin/`).

**Align**: merge missing entries into existing `.dockerignore`.

### 5. Validate

Run `docker build -t app:local .` to verify the Dockerfile builds. Report any issues.

## Output

### New Dockerfile
Report the files created and the detected project type.

### Existing Dockerfile
Report as a checklist:
- [x] Item already compliant
- [~] Item updated/fixed (describe change)
- [ ] Item needs manual attention (explain why)
