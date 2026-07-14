---
paths: **/*.tsx,**/*.jsx,**/vite.config.*,**/package.json
---

# React / Frontend Guidelines

Reach for React only when the UI is genuinely interactive (live state, complex forms, realtime). A page
of server-rendered HTML from the backend is not a defeat — it is one less build, one less lockfile, one
less CVE feed.

## Stack

- **Vite + TypeScript**, scaffolded with `pnpm create vite@latest frontend --template react-ts`
- **pnpm** only (never npm/yarn). Commit `pnpm-lock.yaml`. Refuse post-install scripts by default —
  allowlist explicitly: `"pnpm": {"onlyBuiltDependencies": ["esbuild"]}`
- **TypeScript strict** (`"strict": true`) — `any` is a code review finding, not a shortcut
- Server state: **@tanstack/react-query**. Client state: `useState`/`useReducer`, or **zustand** when it
  genuinely spans routes. Do not put server data in a client store — that is a cache, and react-query is
  a better one
- Routing: **react-router-dom**
- Styling: **Tailwind**. Component primitives: **shadcn/ui** (copied in, not a dependency) when the UI
  needs more than buttons and inputs
- Icons: **lucide-react**

Let `pnpm add` resolve current versions at init time. Never copy a version list out of an existing
project — a pinned stack rots the day it is written.

## Layout

```
frontend/
├── src/
│   ├── main.tsx          # entry: QueryClientProvider + RouterProvider
│   ├── api/              # typed fetch wrappers — the ONLY place fetch() appears
│   ├── components/       # dumb, reusable, no data fetching
│   ├── pages/            # route-level components, own the queries
│   ├── hooks/
│   └── types/            # shared types, mirroring the backend schemas
├── vite.config.ts        # dev-only proxy: /api → http://localhost:8000
└── package.json
```

- `fetch` lives in `src/api/` behind typed functions. A component that calls `fetch` directly is a bug:
  it cannot be tested, mocked, or retried consistently
- Backend types are mirrored by hand in `src/types/` (or generated from the OpenAPI schema) — never
  `any` at the API boundary

## Packaging — one image

The SPA is a build artifact, not a service. Build it in a Docker stage and copy the static bundle into
the backend image; the backend serves it. One image, one deployment, one ingress, **no CORS**, and the
frontend can never be out of sync with its API.

```dockerfile
FROM node:24-alpine AS frontend-build
WORKDIR /src
RUN corepack enable
COPY frontend/package.json frontend/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile
COPY frontend/ ./
RUN pnpm build
# … later, in the runtime stage:
# COPY --from=frontend-build /src/dist /app/static
```

FastAPI serves it, with an SPA fallback so client-side routes survive a page refresh — the API routers
must be registered **before** the catch-all, and the catch-all must **refuse to answer for `/api`**:

```python
import posixpath
import re
from pathlib import Path

from fastapi import HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi_structured_logging import get_logger

log = get_logger()
STATIC = Path("static")

# Existence-guarded: the bundle exists in the image (COPY --from=frontend-build), but NOT in local
# dev, where vite builds to frontend/dist and nothing creates ./static. An unguarded StaticFiles()
# raises at import — `make dev` and the e2e server die before binding the port. API-only boot with
# a warning is the honest degradation; the SPA tests then fail loudly, pointing at the real cause.
if (STATIC / "assets").is_dir():
    app.mount("/assets", StaticFiles(directory=STATIC / "assets"), name="assets")
else:
    log.warning("spa_bundle_missing", hint="API-only mode; build the frontend to serve the SPA")


def _is_api_path(raw_path: str) -> bool:
    """True if the request targets /api, however it was spelled."""
    # Backslashes FIRST: posixpath does not treat "\\" as a separator, but browsers and many
    # proxies/CDNs normalise it to "/" before forwarding — so /\api/x and /api\x reach the SPA
    # while everything in front of you considers them API paths. (Verified: they returned 200.)
    normalised = raw_path.replace("\\", "/")
    # Then collapse "//", resolve "/./" and "/../": the catch-all's param KEEPS leading slashes
    # ("//api/x" -> "/api/x"), so startswith("api/") alone lets them through.
    collapsed = re.sub(r"/{2,}", "/", "/" + normalised.lstrip("/"))
    clean = posixpath.normpath(collapsed).lower()
    return clean == "/api" or clean.startswith("/api/")


@app.get("/{path:path}")
async def spa(path: str) -> FileResponse:
    # index check per request, not cached at import: in dev the bundle may appear after boot.
    if _is_api_path(path) or not (STATIC / "index.html").is_file():
        raise HTTPException(status_code=404)
    return FileResponse(STATIC / "index.html")
```

**`/api` is reserved for FastAPI.** Every path under it is answered by a route or by FastAPI's own 404 —
never by the SPA fallback. A fallback that answers an API path returns HTML where the caller expected
JSON, which surfaces as a frontend parse error and sends you debugging the wrong file.

Regression tests. Five, and each catches a breakage the others cannot:

```python
@pytest.mark.parametrize(
    "path",
    ["api/x", "/api/x", "/api", "//api/x", "///api/x", "/./api/x", "/foo/../api/x",
     "/API/x", r"/\api/x", r"/api\x"],   # backslash vectors: proxies normalise them, posixpath does not
)
def test_api_paths_are_reserved(path):
    assert _is_api_path(path) is True


@pytest.mark.parametrize("path", ["", "some/route", "apiary/x"])   # must NOT over-match
def test_non_api_paths_reach_the_spa(path):
    assert _is_api_path(path) is False


async def test_route_order_real_api_route_not_shadowed(client):
    """Route ORDER, not the guard: a router registered AFTER the catch-all is silently shadowed —
    the catch-all answers first and every real /api route 404s. Only probing a route that EXISTS
    catches that (an unknown path returns 404 in both the correct and the broken ordering).
    Use the project's simplest real GET route here."""
    resp = await client.get("/api/items")
    assert resp.status_code == 200


async def test_unknown_api_route_is_json_404_not_spa(client):
    """The guard through the app: an unknown /api path is FastAPI's JSON 404, never SPA HTML."""
    resp = await client.get("/api/definitely-not-a-route")
    assert resp.status_code == 404
    assert "text/html" not in resp.headers.get("content-type", "")


async def test_spa_served_when_bundle_present(client, tmp_path, monkeypatch):
    """The existence guard's happy path — deleting the guard OR the fallback breaks this."""
    (tmp_path / "static").mkdir()
    (tmp_path / "static" / "index.html").write_text("<html>SPA</html>")
    monkeypatch.chdir(tmp_path)
    resp = await client.get("/some/client/route")
    assert resp.status_code == 200
    assert "SPA" in resp.text
```

Test the guard function directly, not only through `httpx.ASGITransport` — the transport normalises
`//api/x` away, so an end-to-end-only test passes while a real uvicorn serves the SPA.

A separate nginx image + its own ingress is the exception: justify it (independent scaling, separate
teams, a CDN in front) or don't do it.

## Testing

- **Vitest + @testing-library/react**. Test behaviour through the DOM (what a user sees and clicks),
  never component internals or state shape
- Mock at the network boundary (`src/api/` or MSW), not by stubbing children
- `pnpm test` must run offline, headless, and green in CI
- Every interactive feature ships at least one test that clicks the thing and asserts what appears
- **Coverage has a floor, and it is enforced** — a threshold the backend has and the frontend usually
  doesn't, which is exactly why frontend coverage rots. Configure it so `pnpm test:coverage` *fails*:

```ts
// vite.config.ts
test: {
  coverage: {
    provider: "v8",
    thresholds: { lines: 80, functions: 80, branches: 70, statements: 80 },
  },
}
```

The script must actually collect coverage — **`"test:coverage": "vitest run --coverage"`**. Vitest only
evaluates `thresholds` when collection is on, so `vitest run` alone makes the whole block silently
inert and the command "passes" with zero enforcement.

An unenforced coverage number is a decoration. If it cannot fail the build, it does not exist.

## Rendering untrusted content

JSX escapes by default, which handles the common case. The one reliable way back into XSS is
`dangerouslySetInnerHTML` — and the name is the whole warning.

- **Never** pass unsanitised data to `dangerouslySetInnerHTML`. If you must render HTML (a rich-text
  field, user-authored markdown), sanitise it first with **DOMPurify**, at render time, every time
- Rendering markdown? Use a renderer that escapes HTML by default, and do not enable a `rawHtml`/
  `allowDangerousHtml` option because a heading looked wrong
- Never build a URL for `href`/`src` straight from user input without checking the scheme
  (`javascript:` is a payload)

## Tooling

- `pnpm lint` (eslint, `--max-warnings 0`), `pnpm typecheck` (`tsc --noEmit`), `pnpm test` — all three in
  the `Makefile` and in CI. A build that type-checks is not a build that works; a build that does not
  type-check is not a build
