---
paths: **/models.py,**/models/**,**/migrations/**,**/db_migrate.py,**/db.py
---

# PostgreSQL Guidelines

Async SQLAlchemy 2.x + asyncpg, with plain-SQL migrations run by [babs/db_migrate](https://github.com/babs/db_migrate).
Postgres is the only supported RDBMS.

## Connection

- Driver: `asyncpg`. URL scheme is `postgresql+asyncpg://user:pass@host:5432/dbname`
- The URL comes from config, never hardcoded: **`DATABASE_URL`** — the same variable `db_migrate` reads (see `rules/python.md`)
- One `AsyncEngine` + one `async_sessionmaker` per process — built **lazily**, never at import time
- Sessions are request-scoped and injected — `Depends(get_session)`, never a global session

```python
from collections.abc import AsyncIterator
from functools import lru_cache

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from .config import get_settings


@lru_cache
def get_engine() -> AsyncEngine:
    return create_async_engine(
        # SecretStr per rules/python.md — unwrap only here, at the point of use.
        get_settings().database_url.get_secret_value(),
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=5,
        pool_timeout=10,
        connect_args={
            "command_timeout": 10,                              # asyncpg: cap any single query
            "server_settings": {"statement_timeout": "15000"},  # Postgres-side backstop, ms
        },
    )


@lru_cache
def get_session_factory() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(get_engine(), expire_on_commit=False, class_=AsyncSession)


async def get_session() -> AsyncIterator[AsyncSession]:
    async with get_session_factory()() as session:
        yield session
```

**Lazy, not module-level.** `engine = create_async_engine(settings.database_url)` at module scope means
importing the module requires a valid `DATABASE_URL` — so on a fresh clone with no `.env`, `pytest`
dies at *collection*, before a single test runs. Build the engine on first use.

**`pool_pre_ping=True` is mandatory**: managed Postgres drops idle connections, and a stale pooled
connection surfaces as a random 500 on the next request.

**Timeouts are mandatory too.** Without them a single hung query holds its pool slot forever; once the
pool is drained every subsequent request blocks, and a two-second database hiccup becomes a total
outage. `command_timeout` bounds the client, `statement_timeout` bounds the server — set both, because
either one alone leaves a gap (a connection stuck in the network never reaches the server's timer).

Keep `command_timeout` (10s) **below** `statement_timeout` (15s), deliberately: the client gives up
first and asyncpg cancels the query on that connection before returning it to the pool, so the caller
gets a clean error. The server-side timer is the backstop for the case where the cancellation itself
does not land.

**Pool sizing is a budget, not a default.** Each replica opens up to `pool_size + max_overflow`
connections. Multiply by the replica count and compare against the server's `max_connections` *before*
scaling up — exceeding it takes down every app on a shared cluster, not just yours. Past a handful of
replicas, put a pooler (PgBouncer / RDS Proxy) in front rather than raising the numbers.

**The `@lru_cache` binds the engine to one event loop** — the one that first touches it. That is
correct for a served app (uvicorn = one loop per process) and a trap everywhere else: a second
`asyncio.run()` or a per-function pytest event loop reaching the *real* engine gets cross-loop pool
corruption. The test layer must therefore override `get_session` (as the scaffolded `conftest.py`
does) — that override is a load-bearing invariant, not a convenience. A CLI that needs the DB runs
inside a single `asyncio.run()` for the same reason.

Dispose the engine on shutdown so connections drain cleanly on SIGTERM — guarded, because calling
`get_engine()` here would *construct* an engine at shutdown if no request ever touched the DB:

```python
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    yield
    if get_engine.cache_info().currsize:   # only if one was actually created
        await get_engine().dispose()
```

## The DB-unavailable handler — five failure modes, five different exceptions

Measured against live Postgres; a handler that misses one returns an unhandled 500 with no
`Retry-After`, and 5xx alerting can no longer separate "DB down" from "code broken":

| Failure | Raises |
|---|---|
| pool exhaustion | `sqlalchemy.exc.TimeoutError` (sibling of `DBAPIError`, not child) |
| `statement_timeout` | `sqlalchemy.exc.DBAPIError` (asyncpg QueryCanceled, wrapped) |
| `command_timeout` | `builtins.TimeoutError` — asyncpg raises it **raw**, never wrapped |
| DB down / refused | `ConnectionRefusedError` — raw, `ConnectionError` subclass, same reason |
| `max_connections` hit / DB starting | `asyncpg.PostgresError` (e.g. `TooManyConnectionsError`, 53300) — **raw**: SQLAlchemy only wraps errors raised inside statement execution; connect-phase errors (incl. `pool_pre_ping`'s) propagate unwrapped |

```python
import asyncpg

# IntegrityError is a DBAPIError child but a CLIENT bug, not an outage — re-raise it so it stays
# a 500 in front of a fixable stack trace, not a retryable 503.
async def _db_unavailable(request: Request, exc: Exception) -> JSONResponse:
    if isinstance(exc, IntegrityError):
        raise exc
    return JSONResponse(
        {"detail": "database unavailable"}, status_code=503, headers={"Retry-After": "5"}
    )


# ConnectionError + TimeoutError, NOT the OSError base: OSError also covers FileNotFoundError,
# PermissionError and disk-full — a missing static file reported as "database unavailable" sends
# the on-call to a healthy DB and tells clients to retry a non-retryable fault.
# asyncpg.PostgresError: raw only on the CONNECT phase (connection storm, pooler restart, DB in
# recovery) — execution-phase Postgres errors arrive wrapped as DBAPIError and never reach it raw.
for _exc in (DBAPIError, SATimeoutError, ConnectionError, TimeoutError, asyncpg.PostgresError):
    app.add_exception_handler(_exc, _db_unavailable)
```

Known limit: once a response has **started streaming**, Starlette can no longer swap in the 503
(`response already started`). Buffered `JSONResponse` endpoints — this whole scaffold — are fine; a
future `StreamingResponse` loses the contract mid-stream, silently.

Test it by injecting all five types through a `get_session` override (503 + `Retry-After` each),
**plus two negative cases that pin the tuple's boundaries**: `IntegrityError` and `FileNotFoundError`
must both propagate, asserted via `pytest.raises` — `ASGITransport` re-raises app exceptions instead
of rendering them (real uvicorn turns them into 500s). The `FileNotFoundError` case is what goes red
if someone "simplifies" the tuple back to `OSError`; without it the narrowing is unguarded. **And** in
the e2e layer provoke one real timeout (`SELECT pg_sleep(30)`) and one real refusal (DB stopped):
injection only ever confirms the types you already thought of.

## Models

- SQLAlchemy 2.x declarative with `Mapped[...]` / `mapped_column()` — never the legacy `Column()` style
- Primary keys: **UUIDv7**, generated client-side — `mapped_column(Uuid, primary_key=True, default=uuid.uuid7)`
  (stdlib since Python 3.14) — unless a natural key exists.

  **v7, not v4.** A v4 key is pure randomness, so every insert lands in a random leaf of the primary
  key's btree: constant page splits, a working set that never fits in cache, and an index that bloats
  and fragments as the table grows. v7 is time-ordered, so inserts append near the right edge — far
  fewer splits, hot pages stay hot, less WAL. You also get creation-order sorting for free, and range
  scans over "recent rows" become possible. The cost is that a v7 id leaks its creation timestamp; if
  an id is exposed to untrusted users *and* the creation time is sensitive, use v4 for that table and
  say why in a comment.

  Generate it in Python rather than with a server default: it is portable (no dependency on Postgres 18's
  `uuidv7()` or the `pg_uuidv7` extension), it works identically on the SQLite test layer, and the object
  has its id before `flush()`.
- Timestamps: `datetime` with `timezone=True`, `server_default=func.now()` — always tz-aware, always UTC
- Every FK gets an index; every column that appears in a `WHERE` gets one too
- `JSONB` (not `JSON`) for schemaless columns

## Querying — the two defaults that decide whether 3am happens

**Relationships: never lazy.** Async SQLAlchemy cannot lazy-load — a lazy attribute touched outside the
session raises `MissingGreenlet`, and inside one it silently fires a query *per row* (the N+1). Both are
avoided by the same rule: declare loading explicitly.

```python
items: Mapped[list[Item]] = relationship(lazy="raise")          # a lazy access is now a loud bug
rows = await session.scalars(select(Order).options(selectinload(Order.items)))   # one extra query, not N
```

`lazy="raise"` turns an invisible performance bug into an immediate, obvious error at development time.
That is the trade you want: N+1 is the single most common way a demo-fast endpoint dies under real data.

**Every list endpoint is paginated. No exceptions.** `SELECT * FROM items` is fine with 50 rows and an
outage with 5 million — it will load them all into memory, serialise them all, and take the pod with it.

```python
@app.get("/api/items")
async def list_items(limit: int = Query(50, le=200), offset: int = 0, ...):
    rows = await session.scalars(select(Item).order_by(Item.id).limit(limit).offset(offset))
```

The `le=200` cap is the point: without an upper bound, `?limit=1000000` is a denial-of-service anyone can
type. Order by something stable, or pagination silently repeats and skips rows.

## Migrations — plain SQL, dbmate format

**Hand-written SQL. No ORM autogeneration.** The migration you read in review is byte-for-byte the SQL
that runs against production. Autogenerated migrations are a diff of your *models*, not a plan for your
*data* — and the diff cannot see a rename, so it cheerfully emits `DROP COLUMN` + `ADD COLUMN` and
destroys the data it was supposed to move. Writing the `ALTER TABLE` yourself takes thirty seconds and
removes that entire class of accident.

One file per change, `db/migrations/<YYYYMMDDHHMMSS>_<description>.sql`, applied in filename order:

```sql
-- migrate:up
ALTER TABLE items ADD COLUMN exported_at timestamptz;
CREATE INDEX idx_items_exported_at ON items (exported_at);

-- migrate:down
DROP INDEX idx_items_exported_at;
ALTER TABLE items DROP COLUMN exported_at;
```

### The runner: `db_migrate.py`

Use **[babs/db_migrate](https://github.com/babs/db_migrate)** — a single-file, zero-framework async
runner (asyncpg + structlog + python-dotenv — asyncpg comes with this stack, the other two with the
base API floor). Do **not** hand-roll a
copy per project, and do not fork it silently.

Vendor it into the project root, **pinned to a commit, never to `master`** — this file executes DDL
with the migration credential, and an unpinned fetch is code you did not review running as your DBA
(CWE-494). Resolve the ref once, at vendor time, and record it:

```bash
# Resolve HEAD once; the SHA in the command below is the audit trail.
REF=$(git ls-remote https://github.com/babs/db_migrate.git HEAD | cut -f1)
curl -fsSL "https://raw.githubusercontent.com/babs/db_migrate/${REF}/db_migrate.py" -o db_migrate.py
chmod +x db_migrate.py
echo "db_migrate.py vendored at ${REF}" # goes in the commit message and AGENTS.md
```

The file is committed into the project, so the version you ship is whatever your repo holds. To
upgrade: re-run the two lines above, `git diff db_migrate.py` like any other code, commit with the new
SHA. Never edit the vendored copy in place — a silent fork is unupgradeable.

**Usage reference for the agent**: the tool ships
[`llms.txt`](https://github.com/babs/db_migrate/blob/master/llms.txt) (TL;DR: commands, file format, env
vars) and `llms-full.txt` (full source + API). Read those rather than guessing at flags.

```bash
uv run ./db_migrate.py --create "add export flag"   # generates db/migrations/<timestamp>_add_export_flag.sql
uv run ./db_migrate.py                              # apply all pending
uv run ./db_migrate.py --status                     # applied / pending
uv run ./db_migrate.py --rollback                   # undo the last one (local iteration)
```

| Env var | Default | Note |
|---|---|---|
| `DATABASE_URL` | *required* | SQLAlchemy-style `postgresql+asyncpg://` URLs are normalised automatically |
| `MIGRATIONS_DIR` | `db/migrations` | |
| `SCHEMA_NAME` | `public` | the schema holding the `schema_migrations` tracking table |

It tracks applied versions in `schema_migrations` and runs **each migration inside a transaction**
(together with its tracking-table insert), so a migration that fails halfway leaves nothing behind and
is safe to re-run — which is what makes a retried deploy Job harmless.

### Rules

- Migrations run as a **step before the app starts** — a deploy Job/hook, never in the app's startup
  path. Replicas all boot at once; each one racing to migrate is a corruption bug waiting to happen.
  **The ordering is not automatic**: a Job and a Deployment applied side by side do not gate each other.
  It comes from the deploy tooling — a Helm pre-upgrade hook, an ArgoCD sync wave, or a CI stage — and
  that is where you verify a failed migration actually blocks the rollout. This repo does not provide it
- **Forward-only**, and safe while the **previous** app version still serves traffic during the rolling
  update: add a nullable column → deploy → backfill → make it non-null in a *later* release. Never drop
  or rename a column in the same release that stops using it
- `-- migrate:down` exists for local iteration. In production, roll *forward* — a down-migration on live
  data is a second untested change applied during an incident
- **`CREATE INDEX CONCURRENTLY` is the one case where "safe to retry" is FALSE.** It cannot run inside a
  transaction, and the runner wraps every migration in one — so you get *"CREATE INDEX CONCURRENTLY
  cannot run inside a transaction block"* at deploy time. It therefore needs its own file, run outside
  the transactional path, which **voids the atomicity guarantee above**: if the Job dies after the index
  is built but before the tracking row is written, a retry re-runs the file and fails with
  *"relation already exists"* — or, if the first attempt died mid-build, Postgres leaves an **INVALID**
  index behind and the retry fails the same way.

  Recovery is manual and you must know it in advance: `DROP INDEX CONCURRENTLY <name>;` then re-run. Make
  the migration itself idempotent (`CREATE INDEX CONCURRENTLY IF NOT EXISTS`) — note that even
  `IF NOT EXISTS` does **not** save you from an INVALID leftover, which still has to be dropped by hand.

  A plain `CREATE INDEX` (no CONCURRENTLY) stays transactional and retry-safe, but holds a write lock on
  the table for its whole duration — which is the outage the deploy Job was supposed to prevent. On a
  small table, take the lock. On a large live one, take CONCURRENTLY *and* the manual recovery burden.
- The runner takes **no advisory lock**: concurrency safety comes from running it exactly once per
  deploy. "Run it as a single Job" is a convention, and conventions lose to a retriggered pipeline at
  3am — so enforce it mechanically: a `resource_group:` in GitLab CI (or the equivalent deploy-level
  mutex) so two deploys of the same app cannot run migrations concurrently. Never invoke it from the
  app's replicas and hope

**The trade-off you are accepting**: SQL migrations and `models.py` are two sources of truth, and
nothing automatically proves they agree. The E2E layer is what catches the drift — which is precisely
why it must actually run (see Testing).

## Testing

Two layers, both required, and **both must actually run**.

### Layer 1 — fast tests (no database server)

In-memory SQLite (`sqlite+aiosqlite:///:memory:`) with `create_all`. Postgres-only constructs must be
shimmed, or the models in this rule will not even create:

```python
# JSONB has no SQLite equivalent — render it as JSON.
@compiles(JSONB, "sqlite")
def _jsonb_sqlite(element: Any, compiler: Any, **kw: Any) -> str:
    return "JSON"
```

Client-side UUIDv7 defaults (`default=uuid.uuid7`) need **no** shim — they are plain Python and behave
identically on both engines. This is a second reason to prefer them over a `server_default`: a
`server_default=text("uuidv7()")` would fail on SQLite with *"no such function"*, forcing you to
register a fake one and to test against a default that is not the one production uses.

(The migration-idempotency check belongs to Layer 2 — see below.)

Prefer SQLite over `AsyncMock(spec=AsyncSession)`. A mocked session asserts the *call shape*
(`session.execute().scalars().all()`), so it breaks on harmless refactors and passes on real bugs —
it can only ever return what you told it to.

**What this layer cannot prove**: that the SQL runs on Postgres. SQLite silently diverges on JSONB
operators (`@>`, `?`, `->>`), `ON CONFLICT` upserts, GIN indexes, `RETURNING`, row locking, isolation
levels, and constraint enforcement. The moment a feature touches any of those, it needs layer 2 — no
exceptions.

It also **builds the schema from `models.py`** (`create_all`), not from the migrations. So it cannot see
the one failure this stack is structurally exposed to: a model and a migration that disagree. Every
test can pass here while production has no such column.

### The drift test — mandatory, not optional

"The E2E layer catches drift" is only true if something checks. Drift no test happens to touch ships
silently. One standing e2e test, against **live Postgres**:

```python
@pytest.fixture
async def pg_engine():
    """Live Postgres. NOT the SQLite fast-layer fixture (`sqlite_engine`): binding this test to a
    schema that create_all() built FROM models.py would compare models against themselves —
    tautological, can never fail."""
    url = os.environ.get("E2E_DATABASE_URL")
    if not url:
        if os.environ.get("CI"):
            pytest.fail("E2E_DATABASE_URL not set in CI — the drift test MUST run here")
        pytest.skip("E2E_DATABASE_URL not set")  # laptop convenience only
    eng = create_async_engine(url)
    try:
        yield eng
    finally:
        await eng.dispose()


@pytest.mark.e2e
async def test_models_match_migrations(pg_engine) -> None:
    async with pg_engine.connect() as conn:
        tables = await conn.run_sync(lambda c: inspect(c).get_table_names())
        for table in Base.metadata.sorted_tables:
            assert table.name in tables, f"{table.name}: in models.py, no migration creates it"
            live = await conn.run_sync(
                lambda c, t=table.name: {col["name"] for col in inspect(c).get_columns(t)}
            )
            missing = {c.name for c in table.columns} - live
            assert not missing, f"{table.name}: in models.py but NOT in the database: {missing}"
```

`lambda c, t=table.name:` — bind the loop variable as a default arg, or every iteration inspects the
last table.

**Limits, stated honestly**: this compares column *names* in one direction (model → database). It does
not catch a type mismatch (`TEXT` where the model says `timestamptz`), a nullability difference, or a
column that exists only in the database. It catches the common case — a forgotten migration — and that
is worth the twelve lines.

This is the price of hand-written migrations, and it is worth paying — but only if you actually pay it.

### Layer 2 — E2E against real Postgres

Real server, real migrations. Mandatory here: the **migration-idempotency check** — a second apply on
an already-migrated database must succeed and change nothing; a non-idempotent or double-registered
migration fails here instead of at 2am on a retried deploy Job:

```python
@pytest.mark.e2e
def test_migrations_are_idempotent() -> None:
    env = {**os.environ, "DATABASE_URL": os.environ["E2E_DATABASE_URL"]}
    # First apply happened in the Makefile; a second must be a clean no-op.
    subprocess.run(["uv", "run", "./db_migrate.py"], env=env, check=True)
```

Mark `@pytest.mark.e2e`; skip when the target is unset so the default run
stays green offline (fail instead of skip when `CI` is set, as in the drift-test fixture above):

```python
pytestmark = pytest.mark.e2e


@pytest.fixture
def base_url() -> str:
    url = os.environ.get("APP_E2E_URL")
    if not url:
        pytest.skip("APP_E2E_URL not set — skipping e2e suite")
    return url
```

**A skipped test is not a passing test.** That `pytest.skip()` is a convenience for laptops, and it is
also how an entire test layer quietly never runs for a year. It is only acceptable because the layer has
a real execution path, which you must ship:

```makefile
# All three lines are one mechanism. .ONESHELL is GLOBAL (every recipe in the file) and make only
# checks the LAST command of a .ONESHELL recipe: without -e, a failing `pytest` followed by a
# passing command turns the target green — disarming `test` and the coverage floor silently.
SHELL := bash
.SHELLFLAGS := -eu -o pipefail -c
.ONESHELL:

E2E_PORT ?= 8099
DB_PORT  ?= 5432
MIGRATE_URL := postgresql+asyncpg://migrator:migrator@localhost:$(DB_PORT)/<pkg>   # DDL
DB_URL      := postgresql+asyncpg://app:app@localhost:$(DB_PORT)/<pkg>           # DML

test:                  # fast layer — offline, seconds. The default.
	uv run pytest -m "not e2e"

```

The `test-e2e` target is copied verbatim into `fullstack-init` projects (canonical here — it only
references the `$(E2E_PORT)`/`$(MIGRATE_URL)`/`$(DB_URL)` variables, which stay per-project):

```makefile
# trap: cleanup must run on EVERY exit path, including failures BEFORE the server launches —
# `$${SRV:-}` because under `set -u` an unset SRV would kill the trap itself and leak everything.
# setsid + negative PID = kill the whole process group: `kill $$!` signals only the `uv` wrapper,
# leaving the python child holding the port. TERM first, KILL after 1s — a server that drains for
# its full graceful-shutdown window would otherwise keep the port bound after make returns.
# compose -p <dir>-e2e: an isolated project, so `down -v` cannot wipe the `make up` dev volume.
test-e2e:
	@trap '[ -n "$${SRV:-}" ] && { kill -TERM -$$SRV 2>/dev/null; sleep 1; kill -KILL -$$SRV 2>/dev/null; } || true; \
	  docker compose -p "$$(basename "$$PWD")-e2e" down -v >/dev/null 2>&1 || true' EXIT
	# Busy-port check via bash /dev/tcp — `ss` does not exist on macOS or slim CI images, and a
	# missing checker must not silently pass. Connect succeeds = someone already answers there.
	@if (exec 3<>/dev/tcp/127.0.0.1/$(E2E_PORT)) 2>/dev/null; then \
		echo "port $(E2E_PORT) in use — set E2E_PORT=<free port>"; exit 1; fi
	docker compose -p "$$(basename "$$PWD")-e2e" up -d --wait db
	DATABASE_URL=$(MIGRATE_URL) uv run ./db_migrate.py
	setsid env APP_PORT=$(E2E_PORT) DATABASE_URL=$(DB_URL) uv run ./run.sh & SRV=$$!
	# kill -0 inside the loop: a server that crashed at import fails here in ~0.3s with its own
	# log on screen, instead of 30 silent seconds followed by a timeout.
	timeout 30 bash -c "until curl -sf http://127.0.0.1:$(E2E_PORT)/healthz >/dev/null; do \
	  kill -0 $$SRV 2>/dev/null || { echo 'server died before becoming healthy'; exit 1; }; sleep 0.3; done"
	APP_E2E_URL=http://127.0.0.1:$(E2E_PORT) E2E_DATABASE_URL=$(DB_URL) uv run pytest -m e2e
```

Parallel runs (CI matrix, sibling checkouts): override **both** `E2E_PORT` and `DB_PORT` — the
host-published DB port is fixed per invocation, and the compose project name derives from the
directory *basename*, so two same-named checkouts share a project. Known limits, stated.

The compose service is named **`db`** and carries a `pg_isready` healthcheck (`--wait` blocks on it;
without it the migration races the database's startup). Ports are overridable (`make test-e2e
E2E_PORT=9001`) — a fixed port collides with whatever else the machine is already running.

Run `make test-e2e` before every merge request, and wire it into CI if the runner can start service
containers. **If it is not in CI, say so in the README** rather than letting people assume it is.

## Two roles, not one

The app and the migrations use **different database users**. In **production** this is enforced (the
platform grants the privileges); **locally** it is an identity split only — same shape, no enforcement.
Enforcing it locally would need `ALTER DEFAULT PRIVILEGES FOR ROLE migrator …`, where the `FOR ROLE`
is load-bearing (default privileges apply only to objects created *by the named role* — omit it and
the app gets `permission denied` on every migrated table). That buys a dev-only simulation of a
boundary the platform already enforces in production — not worth the trap.

**What the split does NOT buy, be honest**: if production hands the app pod the DDL credential by
mistake, nothing detects it — the app boots and behaves identically. Catch it by reviewing the secret
wiring, or make it loud with a startup warning:
`SELECT has_schema_privilege(current_user, 'public', 'CREATE')` → `log.warning("app_has_ddl_privileges")`.
Locally this fires by design (unenforced split) — warn, never fail the boot.

| Role | Used by | Privileges |
|---|---|---|
| `app` | the running application | DML only — `SELECT/INSERT/UPDATE/DELETE`. **No `CREATE`/`ALTER`/`DROP`** |
| `migrate` / `dba` | `db_migrate.py`, in the deploy Job | owns the schema; DDL |

Both read **`DATABASE_URL`** — they are handed *different values*. The privilege boundary lives in the
credential, not in the variable name.

This is not ceremony. It means a bug — or an injection — in the running app **cannot drop a table**,
because the credential it is holding is not permitted to. Two env var names that resolve to the same
superuser give you the paperwork of a privilege boundary with none of the protection.

## Credentials

- Never in git. Local dev: `.env` (gitignored) or compose defaults. Deployed: injected as env vars from
  the platform's secret store
- The password is a distinct env var and the URL is composed from it where the platform requires it — when
  a runtime substitutes `$(VAR)` inside another var, **declaration order matters**: the password must be
  declared before the URL that references it
