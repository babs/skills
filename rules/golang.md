---
paths: **/*.go,**/go.mod
---

# Go Project Guidelines

- Stateless between requests: `rules/design.md` — language-agnostic and mandatory. Go-specific note:
  the allowed per-process wiring singletons are the constructor-injected / `sync.Once` ones
  (e.g. config, DB pool, HTTP client — whichever of these the service actually wires)
- Latest stable Go (check <https://go.dev/dl/>) for new projects
- Logging: `zap` (`go.uber.org/zap`), auto-detect TTY → console (`NewDevelopmentConfig`), no TTY → JSON (`NewProductionConfig`), overridable via env/flag
- ISO8601 timestamps, log level from string (`zapcore.ParseLevel`), always `defer logger.Sync()`
- Event naming: `logger.Info("resource_created", zap.String("kind", kind), zap.Error(err))`
- Errors: `fmt.Errorf("context: %w", err)` — always wrap with context
- Config: env vars + helper func (`getEnv(key, default)`) + validation method on struct
- HTTP: dual servers (main + metrics), always set timeouts, graceful shutdown via signal+context
- Prometheus on `/metrics`
- Testing: table-driven tests, `httptest` for HTTP, constructor injection for mocking (`zap.NewNop()` in tests)
- Layout — two **independent** axes, decided separately:
  - **entry point**: a single binary (a long-running service counts as one) → `main.go` at the repo root; more than one binary → `cmd/<binary>/main.go`
  - **internal structure**: `pkg/<domain>/` at the discretion of the tool's complexity — add a package when a domain earns separate testing, not by default
  - the axes do not interact: root `main.go` + `pkg/` is a normal combination, and `cmd/` is never a prerequisite for `pkg/`
- Build: `CGO_ENABLED=0 go build -ldflags="-s -w"` for static binaries
- Build-time var injection via `-ldflags -X`:
  ```go
  var (
  	Version        = "v0.0.0"
  	CommitHash     = "0000000"
  	BuildTimestamp = "1970-01-01T00:00:00"
  	Builder        = "unknown"
  	ProjectURL     = "unknown"
  )
  ```
  Defaults must read as *not injected*: never a plausible-looking placeholder like
  `"https://github.com/..."` — startup logs get believed.

  Inject with `-X 'main.<Var>=<value>'`, **always against `main.`** whatever the layout — the linker
  names the entry-point package `main`, so `-X 'mod/cmd/app.Version=…'` is **silently ignored**: the
  build succeeds and the binary still reports `v0.0.0`. All five vars go in the startup log.
- `Builder` is the **toolchain**, not a person: `-X 'main.Builder=$(go version)'` — answers "which Go
  built this artifact" when one platform misbehaves or a stdlib CVE lands. Compute it where the compile
  happens (`$(shell go version)` in the Makefile, `$(go version)` in the Dockerfile `RUN`); a value
  passed from the host reports the host's toolchain, not the image's.
- Linting: `golangci-lint` with bodyclose, gocritic, gosec, misspell, noctx, revive, unconvert
