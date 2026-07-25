---
name: dockerfile-init
description: Generate a production Dockerfile or align an existing one to the standard. Use whenever creating or substantially reworking a Dockerfile — when the user says "write a Dockerfile", "containerize/dockerize this", or asks to align an existing Dockerfile to the standard. Never write a Dockerfile from habit; invoke this skill instead.
allowed-tools: Bash, Write, Edit, Read, Glob, Grep
version: "1.4.0"
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

The `ARG` defaults exist only for local `docker build`. When the CI pipeline uses an
OCI-build component that auto-injects these values as `--build-arg` + `--label`
(check the component before assuming), do **not** re-pass them via pipeline-level
build-arg inputs — drop such blocks when aligning. `VERSION` is typically injected on
tag builds only: branch images reporting `v0.0.0` is the expected convention, not a
bug to work around.

### 3. Language-specific templates

#### Python (FastAPI/uvicorn)

Copy the **flat-layout** template from `${CLAUDE_PLUGIN_ROOT}/rules/dockerfile.md` ("Python build — flat layout") verbatim. For packaged `src/` projects (a `[build-system]` in pyproject.toml), use the src-layout template from the same rule instead.

**OTel is all-or-nothing.** `opentelemetry-bootstrap` only *installs* the instrumentors; nothing activates
them unless the process is launched through `opentelemetry-instrument`. So either:

- **No OTel deps** in `pyproject.toml` → drop the `opentelemetry-bootstrap` line, drop `COPY run.sh`, and
  use `CMD ["python", "main.py"]`.
- **OTel deps present** → **create `run.sh` as part of this skill** (a Dockerfile that `COPY`s a missing file fails the build): copy the canonical script from `${CLAUDE_PLUGIN_ROOT}/rules/python.md` (OTEL bullet) with `<entrypoint>` = `python main.py`, `chmod +x`, keep `CMD ["./run.sh"]`.

Shipping the bootstrap without `run.sh` gives you the weight of instrumentation and none of the traces.

**Align checklist**: multi-stage, uv (not pip), OCI labels, non-root user, `PYTHONUNBUFFERED=1`, `PYTHONDONTWRITEBYTECODE=1`, base image `python:3.14-slim-trixie`.

#### Go

Copy the **Go build** template from `${CLAUDE_PLUGIN_ROOT}/rules/dockerfile.md` ("Go build") verbatim.

Entry point is `ARG PKG`: `.` for a root `main.go` (the single-binary default, per the entry-point axis
in `${CLAUDE_PLUGIN_ROOT}/rules/golang.md`), `./cmd/<binary>` for several. Set the default to match the
project; never hardcode a `cmd/` path into the `go build` line.

Two that look cosmetic and are not: ldflags inject against `main.`, never the import path (the other
spelling is silently ignored); and the `ENV` re-export applies to Go too — ldflags bake values into the
binary, only `ENV` makes them readable via `docker inspect`.

**Align checklist**: multi-stage, `CGO_ENABLED=0`, ldflags against `main.`, `ENV` re-export, distroless nonroot runtime, OCI labels, builder Go version consistent with `go.mod` (bump `go.mod` + CI test image + Dockerfile together — never the Dockerfile alone).

#### Node.js

```dockerfile
FROM node:24-slim AS builder
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM node:24-slim
# ... ARGs, LABELs ...
WORKDIR /app
COPY --from=builder /app/dist ./dist
COPY --from=builder /app/node_modules ./node_modules
COPY package.json .
RUN useradd -r -s /usr/sbin/nologin -d /app app && chown -R app:app /app
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

Copy the canonical list from `${CLAUDE_PLUGIN_ROOT}/rules/dockerfile.md` (".dockerignore") verbatim,
plus the row for the detected language from the table there.

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
