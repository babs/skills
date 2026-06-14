---
paths: **/*.go,**/go.mod
---

# Go Project Guidelines

- Go 1.26.3 (latest stable to date, check <https://go.dev/dl/> for updates) for new projects
- Logging: `zap` (`go.uber.org/zap`), auto-detect TTY → console (`NewDevelopmentConfig`), no TTY → JSON (`NewProductionConfig`), overridable via env/flag
- ISO8601 timestamps, log level from string (`zapcore.ParseLevel`), always `defer logger.Sync()`
- Event naming: `logger.Info("resource_created", zap.String("kind", kind), zap.Error(err))`
- Errors: `fmt.Errorf("context: %w", err)` — always wrap with context
- Config: env vars + helper func (`getEnv(key, default)`) + validation method on struct
- HTTP: dual servers (main + metrics), always set timeouts, graceful shutdown via signal+context
- Prometheus on `/metrics`
- Testing: table-driven tests, `httptest` for HTTP, constructor injection for mocking (`zap.NewNop()` in tests)
- Layout: `cmd/` + `pkg/` for modular projects, flat root for simple CLI tools, pkg + root `main.go` if single entry point
- Build: `CGO_ENABLED=0 go build -ldflags="-s -w"` for static binaries
- Build-time var injection via `-ldflags -X`:
  ```go
  var (
      Version        = "v0.0.0"
      CommitHash     = "0000000"
      BuildTimestamp = "1970-01-01T00:00:00"
      Builder        = "unknown"
      ProjectURL     = "https://github.com/..."
  )
  ```
  Inject with: `-X 'main.Version=${VERSION}' -X 'main.CommitHash=${COMMIT_HASH}' ...`
- Linting: `golangci-lint` with bodyclose, gocritic, gosec, misspell, noctx, revive, unconvert
