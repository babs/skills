---
name: fullstack-init
description: >-
  Initialize a production-shaped FastAPI + PostgreSQL + React project (single OCI image — the SPA is
  built and served by the backend), or align an existing one to the standard. Use when starting a
  full-stack app, when the user says "new app with a database", "FastAPI + React", "app with a UI and
  Postgres", or asks to align an existing full-stack project. For an API with no UI and no database,
  use python-init instead.
allowed-tools: Bash, Write, Edit, Read, Glob, Grep, AskUserQuestion
version: "2.1.1"
---

## Context

Scaffold a full-stack app: FastAPI backend, PostgreSQL via async SQLAlchemy + plain-SQL migrations
(babs/db_migrate), React SPA built into the same image and served by the backend.

**This skill is the procedure. The code is in the rules — read them before writing the matching
files, and copy their reference implementations verbatim** (they have been executed; do not improvise
variants):

| Rule | Owns |
|---|---|
| `${CLAUDE_PLUGIN_ROOT}/rules/design.md` | stateless-between-requests doctrine — where every kind of state lives |
| `${CLAUDE_PLUGIN_ROOT}/rules/python.md` | dependency floors, config/SecretStr, logging, run.sh, shutdown, httpx |
| `${CLAUDE_PLUGIN_ROOT}/rules/postgres.md` | engine/session (`db.py`), DB-unavailable handler, models, migrations, both test layers, the `test-e2e` Makefile recipe, the two-role split |
| `${CLAUDE_PLUGIN_ROOT}/rules/react.md` | frontend stack/layout, SPA guard + its five regression tests, vitest coverage floor |
| `${CLAUDE_PLUGIN_ROOT}/rules/dockerfile.md` | OCI labels, the `backend-build` stage (src/ layout, two-phase `uv sync`) |
| `${CLAUDE_PLUGIN_ROOT}/rules/agents-md.md` | AGENTS.md shape |
| `${CLAUDE_PLUGIN_ROOT}/rules/bash.md` | any shell script written or touched (`run.sh`, hooks) |

This skill needs the full plugin install (`rules/` present) — it is not standalone.

## 0. Ask first if not given — three questions, and the third is not optional

1. **Project name** (kebab-case; the Python package is its snake_case form).
2. **Does it need a React UI?** A UI is warranted by genuine interactivity — live state, complex
   forms, realtime. A form and a table = server-rendered HTML from FastAPI (§3b): no lockfile, no
   build, no CVE feed. Say so, then respect the decision.
3. **Who is allowed to use this, and how do they prove it?** This scaffold ships **no
   authentication** — every route is open to anyone who can reach the pod. Fine behind a private
   ingress with no personal data; catastrophic otherwise. Get an explicit answer — *"no auth, private
   ingress only"* is valid — and record it in `AGENTS.md` and `docs/ARCHITECTURE.md`. Personal data or
   internet-facing → stop and design auth before generating routes. The same answer decides **rate
   limiting**: the scaffold ships none (the ingress/gateway is the normal place); record where the
   limit lives, next to the auth decision.

## 1. Detect mode

- **Empty dir / no `pyproject.toml`** → new project, create everything.
- **Existing project** → audit and align. Never overwrite application logic; only align config,
  tooling, packaging. Report gaps as a checklist (Output section).

## 2. Layout

```
<project>/
├── AGENTS.md                 # rules/agents-md.md; records the auth + rate-limit decisions
├── Makefile
├── docker-compose.yml        # db + migrate + app, local only
├── Dockerfile                # 3 stages: frontend build → backend deps → runtime
├── db_migrate.py             # vendored at a pinned SHA (rules/postgres.md); deploy runs it as a Job
├── db/migrations/            # <YYYYMMDDHHMMSS>_<description>.sql, dbmate format
├── run.sh                    # rules/python.md — conditional OTel; entrypoint = python -m <pkg>
├── pyproject.toml            # + committed uv.lock
├── .env.example .gitignore .pre-commit-config.yaml .secrets.baseline
├── specs/README.md           # feature specs (spec-feature skill)
├── docs/ARCHITECTURE.md
├── src/<pkg>/                # __main__.py, main.py, config.py, db.py, models.py, schemas.py, routers/
├── tests/                    # conftest.py, test_api.py, test_e2e.py
└── frontend/                 # vite + react + ts (omit if no UI)
```

## 3. Backend

- **pyproject.toml** — dependency floors from `rules/python.md` ("Default stack (FastAPI)"), **plus
  the database stack this scaffold cannot boot without**:

  ```toml
      "sqlalchemy[asyncio]>=2.0",
      "asyncpg>=0.30",
  ```

  Dev group: the base one from the rule **plus `aiosqlite>=0.20`** (SQLite fast test layer). Tooling
  config (`[tool.ruff]`, `[tool.mypy]` incl. `check_untyped_defs`, `[tool.pytest.ini_options]` with
  `--strict-markers` and the `e2e` marker, coverage over `src`): per `rules/python.md`. Build system:
  hatchling, `packages = ["src/<pkg>"]`.
- **config.py** — pydantic-settings per `rules/python.md` (Configuration): `env_prefix="APP_"`,
  `database_url: SecretStr = Field(validation_alias="DATABASE_URL")` with **no default**.
- **db.py** — the engine/session block from `rules/postgres.md` (Connection), verbatim.
- **main.py** — in this order: `setup_logging` + `AccessLogMiddleware` (fastapi-structured-logging);
  the guarded `lifespan` dispose (postgres.md); the **DB-unavailable handler** (postgres.md — all
  four failure modes); `/healthz` (returns ok, touches nothing) and `/readyz` (`SELECT 1`); routers
  under `/api`; **last, after every API route**, the SPA guard from `rules/react.md`.
- **`__main__.py`** — `uvicorn.run(..., log_config=None, access_log=False,
  timeout_graceful_shutdown=25)` per `rules/python.md` (Shutdown — the 25 is
  `pool_timeout + command_timeout + margin`, not `statement_timeout`).
- **run.sh** — from `rules/python.md`, entrypoint `python -m <pkg>`. `chmod +x`.
- **Migrations** — vendor `db_migrate.py` at a pinned SHA and write migrations by hand, both per
  `rules/postgres.md` (Migrations). The deploy runs it as a Job **before** the new pods start; that
  ordering comes from the deploy tooling (Helm hook / Argo sync wave / CI stage), not from this
  scaffold — verify there that a failed migration blocks the rollout.

**Which probe points where — this matters more than it looks:**

| Probe | Endpoint | Why |
|---|---|---|
| liveness | `/healthz` | "Is the process wedged?" A DB-dependent liveness check turns a 2s blip into a rolling restart of every replica. |
| readiness | `/healthz` | Deliberately **not** DB-aware: one DB blip must degrade to honest 503s, not pull every replica out of the Service at once. |
| startup | `/readyz` | A pod that can never reach its database should never take traffic. Failing at startup is contained. |

Wire them exactly so, and say so in `AGENTS.md` — the name `/readyz` invites pointing readinessProbe
at it, which is the cascading-outage mode the split exists to avoid. `/readyz` stays off the public
ingress.

## 3b. No UI? Omit ALL of it

| Omit | Otherwise |
|---|---|
| the `frontend-build` Dockerfile stage + its `COPY --from` | `COPY frontend/package.json` fails — no such directory |
| every `cd frontend …` line (Makefile **and** §6) | each command fails |
| the SPA guard block in `main.py` | boots (existence-guarded) but warns `spa_bundle_missing` forever — dead code |
| `frontend/`, `static/` | — |

To serve pages instead: add `"jinja2>=3.1"` and `"python-multipart>=0.0.20"` (FastAPI needs the
latter for any `<form>` POST), `templates/` dir, POST-redirect-GET on mutations. `/api` stays
reserved for JSON routes.

## 4. Frontend (only if a UI was requested)

Stack, layout, and rules per `rules/react.md`. Scaffold with current versions — never copy a version
list from another project:

```bash
pnpm create vite@latest frontend --template react-ts
cd frontend && pnpm add @tanstack/react-query react-router-dom lucide-react
pnpm add -D tailwindcss @tailwindcss/postcss postcss autoprefixer vitest @vitest/coverage-v8 \
            jsdom @testing-library/dom @testing-library/react @testing-library/jest-dom \
            @testing-library/user-event
# @testing-library/dom is a real peer of @testing-library/react v16+ — omit it and every test
# fails with "Cannot find module '@testing-library/dom'" (verified).
```

- `vite.config.ts`: dev proxy `/api` → `http://localhost:8000`, and the **enforced** coverage
  thresholds from `rules/react.md`.
- `package.json`: scripts `dev`, `build` (`tsc -b && vite build`), `lint`, `typecheck`, `test`
  (`vitest run`), and **`"test:coverage": "vitest run --coverage"`** — without `--coverage` vitest
  never evaluates the thresholds and the floor is decoration. Add
  `"pnpm": {"onlyBuiltDependencies": ["esbuild"]}`.
- One vitest test that renders the app and asserts something a user would see.

## 5. Dockerfile — one image, three stages

1. `frontend-build` (omit if no UI): the node/pnpm stage from `rules/react.md` (Packaging).
2. `backend-build`: the two-phase `uv sync` stage from `rules/dockerfile.md` (src/ layout), verbatim.
3. Runtime:

```dockerfile
FROM python:3.14-slim-trixie
# ARGs + OCI LABELs + the ENV re-export of VERSION/COMMIT_HASH/... — per rules/dockerfile.md,
# verbatim. The startup log reads those ENV vars; CI supplies the real values as --build-arg.
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PATH="/app/.venv/bin:$PATH"
WORKDIR /app
COPY --from=backend-build /app/.venv .venv
COPY --from=frontend-build /src/dist /app/static   # omit if no UI (with its stage)
COPY src ./src
COPY db_migrate.py pyproject.toml run.sh ./
COPY db/ ./db/
# Security: non-root; chown before USER — anything that later writes under /app breaks otherwise.
RUN useradd -r -s /usr/sbin/nologin -d /app app && \
    chmod +x /app/run.sh /app/db_migrate.py && \
    chown -R app:app /app
USER app
EXPOSE 8000
# Comments NEVER trail an exec-form CMD — Docker would silently turn it into shell-form.
CMD ["./run.sh"]
```

## 6. Local dev — docker-compose.yml

Three services, same **shape** as production. Two roles, one variable (`DATABASE_URL`, different
values) per `rules/postgres.md` ("Two roles, not one"):

```yaml
services:
  db:
    image: postgres:17-alpine
    # POSTGRES_USER/DB=<pkg> is load-bearing: the init SQL's `IN ROLE <pkg>` and both URLs
    # reference that role and database — the image's default `postgres` breaks all of them.
    environment:
      POSTGRES_USER: <pkg>
      POSTGRES_PASSWORD: <pkg>
      POSTGRES_DB: <pkg>
    # 127.0.0.1: — never bare "5432:5432", which binds ALL interfaces: on shared wifi that is a
    # LAN-reachable Postgres with trivial dev credentials.
    ports: ["127.0.0.1:${DB_PORT:-5432}:5432"]
    volumes:
      - ./db/init:/docker-entrypoint-initdb.d:ro
      - pgdata:/var/lib/postgresql/data
    # NOT pg_isready alone: initdb runs a TRANSIENT bootstrap server that answers pg_isready
    # BEFORE the init scripts have created the roles — on a slow machine `depends_on:
    # service_healthy` then releases `migrate` against a role that does not exist yet. Checking
    # the LAST role the init script creates proves the real server + completed bootstrap.
    healthcheck:   # `make test-e2e`'s `--wait` blocks on this
      test: ["CMD-SHELL", "psql -U <pkg> -d <pkg> -tAc \"SELECT 1 FROM pg_roles WHERE rolname='app'\" | grep -q 1"]
      interval: 2s
      timeout: 2s
      retries: 15
      start_period: 10s

  migrate:
    build: .
    command: ["./db_migrate.py"]
    environment:
      DATABASE_URL: postgresql+asyncpg://migrator:migrator@db:5432/<pkg>
    depends_on:
      db: {condition: service_healthy}

  app:
    build: .
    ports: ["127.0.0.1:8000:8000"]
    environment:
      DATABASE_URL: postgresql+asyncpg://app:app@db:5432/<pkg>
    depends_on:
      migrate: {condition: service_completed_successfully}

volumes:
  pgdata:
```

```sql
-- db/init/01-roles.sql (runs once at first initdb, as <pkg>, the owner)
CREATE ROLE migrator LOGIN PASSWORD 'migrator' IN ROLE <pkg>;
CREATE ROLE app      LOGIN PASSWORD 'app'      IN ROLE <pkg>;
```

`IN ROLE <pkg>` makes both roles INHERIT the bootstrap owner — locally they are effectively
superuser. Acceptable for a laptop compose (the split is shape, not enforcement — see
`rules/postgres.md`); never reproduce this grant in a deployed environment.

## 7. Makefile

```makefile
.PHONY: install dev test test-e2e coverage lint up down docker-build clean

# All three lines are one mechanism (rules/postgres.md explains the failure they prevent).
SHELL := bash
.SHELLFLAGS := -eu -o pipefail -c
.ONESHELL:

E2E_PORT ?= 8099
DB_PORT  ?= 5432
# Two credentials, one variable — exactly as in production.
MIGRATE_URL := postgresql+asyncpg://migrator:migrator@localhost:$(DB_PORT)/<pkg>
DB_URL      := postgresql+asyncpg://app:app@localhost:$(DB_PORT)/<pkg>

```

Targets → recipe bodies (write them as real tab-indented recipes, one command per line;
`;` below just separates them):

| Target | Recipe |
|---|---|
| `install` | `uv sync` ; `cd frontend && pnpm install` (omit if no UI) |
| `dev` | `uv run ./run.sh` — API only: the SPA is served from the built bundle; for live UI dev run `cd frontend && pnpm dev` in a second terminal (vite proxies `/api`) |
| `test` | `uv run pytest -m "not e2e"` ; `cd frontend && pnpm test` (omit if no UI) |
| `coverage` | `uv run pytest -m "not e2e" --cov --cov-report=term-missing --cov-fail-under=80` ; `cd frontend && pnpm test:coverage` (omit if no UI) |
| `lint` | `pre-commit run --all-files` ; `cd frontend && pnpm lint && pnpm typecheck` |
| `up` / `down` | `docker compose up --build` / `docker compose down -v` |
| `docker-build` | `docker build -t <project>:local .` |

`test-e2e`: copy the recipe from `rules/postgres.md` verbatim — every line of it is a fix for a
measured failure (trap under `set -u`, TERM→KILL, `/dev/tcp` port check, isolated compose project,
dead-server fast-fail). Do not re-derive it.

**Coverage floors are ratchets** (backend `--cov-fail-under`, frontend vitest thresholds): raise them
in the same commit when comfortably above; never lower one to turn a red build green. Note the known
gap: the fast layer never exercises `db.py`'s real engine (conftest overrides `get_session`) — that
path is e2e-only; say so in the README instead of mocking it into "coverage".

## 8. Supporting files

- **.pre-commit-config.yaml** — ruff (lint+format), pre-commit-hooks, detect-secrets
  (`--baseline .secrets.baseline`), mypy — per `rules/python.md`.
- **.env.example** — `DATABASE_URL=…app:app…` (the app credential) + `APP_LOG_LEVEL=INFO`. Never ship
  `APP_JSON_LOGS=`: empty string is not "unset", pydantic rejects it at boot — document it as a
  comment (`# APP_JSON_LOGS=true|false (unset = auto-detect)`).
- **.gitignore** — caches, `.venv/`, `.env`, `node_modules/`, `dist/`, coverage artifacts.
  **`.secrets.baseline` is committed, never ignored** — the hook errors without it on fresh clones/CI.
- **tests/test_api.py** — `/healthz` + one error path; `/readyz`; the **five SPA regression tests**
  from `rules/react.md` verbatim; the **DB-unavailable matrix** from `rules/postgres.md` (four
  injected types → 503; `IntegrityError` asserted via `pytest.raises` — ASGITransport re-raises it,
  uvicorn renders the 500).
- **tests/test_e2e.py** — at least one `@pytest.mark.e2e` test (`pytest -m e2e` with nothing
  collected exits 5 = red build): the model↔migration **drift test**, the **idempotency check**, one
  HTTP case — all from `rules/postgres.md`, including the skip-locally-**fail-in-CI** guard.
- **tests/conftest.py** — `os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")`
  **before importing the app**; `httpx.ASGITransport` client; SQLite engine fixture named
  **`sqlite_engine`** (never `engine`/`pg_engine` — the drift test's validity depends on it); JSONB→
  JSON via `@compiles`; override `get_session` through `app.dependency_overrides`.
- **README.md** — what the app is, `make` commands, and **whether `make test-e2e` runs in CI**; if
  not, say so.
- **specs/README.md**, **docs/ARCHITECTURE.md**, **AGENTS.md** (15–80 lines; records the auth,
  rate-limit and probe-wiring decisions).

## 9. Run the tooling

```bash
uv sync
cd frontend && pnpm install && cd ..     # omit if no UI
detect-secrets scan > .secrets.baseline  # only if missing — then COMMIT it
pre-commit install
pre-commit run --all-files
uv run pytest -m "not e2e"
```

## Output

**New project**: files created, `pre-commit` result, test result, the recorded auth/rate-limit
decision, and the exact start commands (`make up`, then the URL).

**Existing project**: a checklist — [x] compliant / [~] updated (what changed) / [ ] needs manual
attention (why).
