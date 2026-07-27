---
paths: **/Dockerfile,**/Dockerfile.*,**/*.dockerfile
---

# Dockerfile Guidelines

## OCI Image Metadata

Always include build-time metadata ARGs and OCI labels:

```dockerfile
ARG BUILD_TIMESTAMP="1970-01-01T00:00:00+00:00"
ARG COMMIT_HASH="00000000-dirty"
ARG PROJECT_URL="project-name"
ARG VERSION="v0.0.0"

LABEL org.opencontainers.image.source=${PROJECT_URL}
LABEL org.opencontainers.image.created=${BUILD_TIMESTAMP}
LABEL org.opencontainers.image.version=${VERSION}
LABEL org.opencontainers.image.revision=${COMMIT_HASH}

# Re-export as ENV so the RUNNING app can read them — the startup log emits
# version/commit_hash/build_timestamp/project_url, which is how you know what is actually deployed.
ENV VERSION="${VERSION}" \
    COMMIT_HASH="${COMMIT_HASH}" \
    BUILD_TIMESTAMP="${BUILD_TIMESTAMP}" \
    PROJECT_URL="${PROJECT_URL}"
```

The `ARG` defaults exist only for local `docker build` — CI passes the real values as
`--build-arg` (and duplicates them as labels). Do not hand-maintain them: when the CI
OCI-build component auto-injects them, drop any pipeline-level build-arg block that
re-passes the same values. `VERSION` is typically injected on tag builds only — branch
images reporting `v0.0.0` is the expected convention, not a bug to work around.

The `ENV` re-export applies to all images, Go included: ldflags already bake the values
into the binary, but the `ENV` keeps them readable via `docker inspect` (or from inside
the container) without running anything.


## Python build — flat layout (canonical for `python-init` / `dockerfile-init`)

Flat `main.py`, no build-system: uv installs only the dependencies, never the project — a single
`uv sync`, no two-phase dance. The skills point here; do not carry copies.

```dockerfile
FROM python:3.14-slim-trixie AS builder
# pipefail: fail the build if any stage of a piped RUN fails (e.g. bootstrap below),
# instead of silently taking the exit code of the last command in the pipe.
SHELL ["/bin/bash", "-o", "pipefail", "-c"]
# Pinned, never :latest — a mutable tag in the build toolchain is unauditable and unrollbackable.
COPY --from=ghcr.io/astral-sh/uv:0.11.32 /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock ./
# `-a requirements | uv pip install`: a uv venv has no pip, so `bootstrap -a install` (which
# shells out to pip) would fail. Call the .venv binary directly, NOT `uv run` — `uv run` re-syncs
# the dev group back into this --no-dev venv that ships in the final image.
RUN uv sync --frozen --no-dev && \
    .venv/bin/opentelemetry-bootstrap -a requirements | uv pip install --requirement -

FROM python:3.14-slim-trixie
# ... ARGs + OCI LABELs (above) ...
WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
COPY *.py .
# `COPY *.py .` does NOT match run.sh — without this line the image dies at start.
COPY run.sh .
RUN useradd -r -s /usr/sbin/nologin -d /app app && chmod +x /app/run.sh && chown -R app:app /app
USER app
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1
EXPOSE 8000
# Comments NEVER trail an exec-form CMD — Docker silently turns the line into shell-form.
# Without OTel deps: CMD ["python", "main.py"], drop COPY run.sh + chmod + the bootstrap line.
CMD ["./run.sh"]
```

`run.sh` is canonical in `rules/python.md` (conditional OTel activation) — create it with the image,
`chmod +x`; a Dockerfile that `COPY`s a missing file fails the build.

## Python build — `src/` layout (packaged projects)

**Canonical for projects that install themselves** (a `[build-system]` + `packages = ["src/<pkg>"]` in
`pyproject.toml` — i.e. `fullstack-init`). `python-init` and `dockerfile-init` scaffold a **flat**
`main.py` with no build-system: uv installs only the dependencies, never the project, so the two-phase
sync below does not apply to them and they keep a single `uv sync` on purpose. That is a real
difference, not drift — do not "align" them.

Multi-stage. The runtime image carries the venv and the source, never the build toolchain.

```dockerfile
FROM python:3.14-slim-trixie AS backend-build
SHELL ["/bin/bash", "-o", "pipefail", "-c"]
# Pinned, never :latest — a mutable tag in the build toolchain is unauditable and unrollbackable.
# Version tags, not @sha256 digests: a deliberate trade of immutability for a bump you can read
# in a diff. Pin uniformity across the repo's files is enforced by scripts/validate-skills.sh.
COPY --from=ghcr.io/astral-sh/uv:0.11.32 /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock ./
# --no-install-project: the source is not here yet. Without this, uv builds and installs an EMPTY
# package (hatchling finds no modules under src/) and imports only work by accident at runtime.
RUN uv sync --frozen --no-dev --no-install-project
COPY src ./src
# Now the project itself is installed, against real source.
RUN uv sync --frozen --no-dev && \
    .venv/bin/opentelemetry-bootstrap -a requirements | uv pip install --requirement -
```

```dockerfile
FROM python:3.14-slim-trixie
# … ARGs + OCI LABELs (above) …
WORKDIR /app
COPY --from=backend-build /app/.venv .venv
COPY src ./src
COPY run.sh ./
# No PYTHONPATH: the two-phase sync above installs the package for real. If you find yourself
# adding one, the build order is wrong.
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1

# Security: non-root. chown before USER, or anything that ever writes under /app breaks.
RUN useradd -r -s /usr/sbin/nologin -d /app app && \
    chmod +x /app/run.sh && \
    chown -R app:app /app
USER app

EXPOSE 8000
CMD ["./run.sh"]
```

(The bootstrap/pip rationale is the same as in the flat-layout stage above.)

## Go build (canonical for `go-init` / `dockerfile-init`)

Static binary, distroless runtime. The skills point here; do not carry copies.

`PKG` = entry-point package: `.` for a root `main.go`, `./cmd/<binary>` otherwise. Set it via
`--build-arg`, never by editing the `go build` line — `make docker-build` forwards the Makefile's `PKG`.

```dockerfile
FROM golang:1.26-bookworm AS builder
WORKDIR /src
# go.sum* — glob, not a typo: a stdlib-only module has no go.sum and the build would fail hard.
COPY go.mod go.sum* ./
RUN go mod download
COPY . .
ARG VERSION="v0.0.0"
ARG COMMIT_HASH="00000000-dirty"
ARG BUILD_TIMESTAMP="1970-01-01T00:00:00+00:00"
ARG PROJECT_URL="project-name"
ARG PKG="."
# Builder=$(go version) must be evaluated HERE, not passed as a build arg: an arg reports the
# host's toolchain, not this image's.
RUN CGO_ENABLED=0 go build -ldflags="-s -w \
    -X 'main.Version=${VERSION}' \
    -X 'main.CommitHash=${COMMIT_HASH}' \
    -X 'main.BuildTimestamp=${BUILD_TIMESTAMP}' \
    -X 'main.Builder=$(go version)' \
    -X 'main.ProjectURL=${PROJECT_URL}'" \
    -o /app "${PKG}"

FROM gcr.io/distroless/static-debian12:nonroot

ARG BUILD_TIMESTAMP="1970-01-01T00:00:00+00:00"
ARG COMMIT_HASH="00000000-dirty"
ARG PROJECT_URL="project-name"
ARG VERSION="v0.0.0"

LABEL org.opencontainers.image.source=${PROJECT_URL}
LABEL org.opencontainers.image.created=${BUILD_TIMESTAMP}
LABEL org.opencontainers.image.version=${VERSION}
LABEL org.opencontainers.image.revision=${COMMIT_HASH}

ENV VERSION="${VERSION}" \
    COMMIT_HASH="${COMMIT_HASH}" \
    BUILD_TIMESTAMP="${BUILD_TIMESTAMP}" \
    PROJECT_URL="${PROJECT_URL}"

COPY --from=builder /app /app
# 8080 app + 9090 metrics (dual servers, rules/golang.md). No metrics server → 8080 only.
EXPOSE 8080 9090
ENTRYPOINT ["/app"]
```

`:nonroot` already runs as UID 65532 — no `useradd`, and there is no shell to add one with.

## .dockerignore (canonical for `go-init` / `dockerfile-init`)

One list, so two skills over the same repo cannot each rewrite the other's file. The skills point
here; do not carry copies. `python-init` / `fullstack-init` need none — their images copy selectively,
so there is no `COPY . .`.

```
.git/
.github/
.gitlab-ci.yml
*.md
.env*
.vscode/
.idea/
Dockerfile
.dockerignore
```

Plus the language's build output — regenerated inside the image, so it only bloats the context:

| Language | Add |
|---|---|
| Go | `bin/` |
| Python | `__pycache__/`, `.venv/` |
| Node.js | `node_modules/`, `dist/` |
| Rust | `target/` |

`.env*` is about secrets, not size: swept up by `COPY . .` it lands in an image layer, readable by
anyone who can pull it.
