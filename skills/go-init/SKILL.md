---
name: go-init
description: Initialize a new Go HTTP service or align an existing one to the standard. Use when starting any new Go service or project — when the user says "new Go service", "bootstrap/init a Go app", or asks to align an existing Go service to the standard. Never scaffold a Go service from habit; invoke this skill instead.
allowed-tools: Bash, Write, Edit, Read, Glob, Grep
version: "1.1.0"
---

## Context

You are setting up or aligning a Go HTTP service project to the production standard. Follow the rules from `${CLAUDE_PLUGIN_ROOT}/rules/golang.md` and `${CLAUDE_PLUGIN_ROOT}/rules/dockerfile.md`.

The user may provide a Go module path as argument (e.g. `github.com/org/project-name`). If not, use the current directory or ask.

## Task

### 1. Detect mode

- **No `go.mod` in current dir**: new project — create everything from scratch
- **Existing project detected**: audit and align — check each file below against the standard, report gaps, and fix them

Then pick the layout — **two independent axes** (see `${CLAUDE_PLUGIN_ROOT}/rules/golang.md`):

- **Entry point.** One binary (a long-running service counts as one) → `main.go` at the **repo root**. Several → `cmd/<binary>/main.go`. Never create `cmd/` for a single entry point.
- **Internal structure.** `pkg/<domain>/` only when a domain earns separate testing, not by default.

The axes do not interact: root `main.go` + `pkg/` is normal; `cmd/` is never a prerequisite for `pkg/`.

One knob encodes the choice: `PKG` in the Makefile, forwarded to the Dockerfile's `ARG PKG` by `make docker-build`. No other file below repeats it.

### 2. Audit / create each file

For **new projects**, create all files. For **existing projects**, check each item and only add/update what's missing or non-compliant. Never overwrite existing application logic — only align config and tooling.

#### main.go (new projects only)

At the repo root for a single binary, or `cmd/$APP_NAME/main.go` when there are several.

```go
package main

import (
	"context"
	"fmt"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/prometheus/client_golang/prometheus/promhttp"
	"go.uber.org/zap"
	"go.uber.org/zap/zapcore"
	"golang.org/x/term"
)

var (
	Version        = "v0.0.0"
	CommitHash     = "0000000"
	BuildTimestamp = "1970-01-01T00:00:00"
	Builder        = "unknown"
	ProjectURL     = "unknown"
)

func getEnv(key, fallback string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return fallback
}

func newLogger() (*zap.Logger, error) {
	level, err := zapcore.ParseLevel(getEnv("LOG_LEVEL", "info"))
	if err != nil {
		level = zapcore.InfoLevel
	}

	var cfg zap.Config
	format := getEnv("LOG_FORMAT", "auto")
	useConsole := format == "console" || (format == "auto" && term.IsTerminal(int(os.Stdout.Fd())))
	if useConsole {
		cfg = zap.NewDevelopmentConfig()
		cfg.EncoderConfig.EncodeLevel = zapcore.CapitalColorLevelEncoder
	} else {
		cfg = zap.NewProductionConfig()
	}
	cfg.Level = zap.NewAtomicLevelAt(level)
	cfg.EncoderConfig.TimeKey = "timestamp"
	cfg.EncoderConfig.EncodeTime = zapcore.ISO8601TimeEncoder
	return cfg.Build()
}

func main() {
	logger, err := newLogger()
	if err != nil {
		fmt.Fprintf(os.Stderr, "failed to init logger: %v\n", err)
		os.Exit(1)
	}
	defer logger.Sync()

	logger.Info("startup",
		zap.String("version", Version),
		zap.String("commit_hash", CommitHash),
		zap.String("build_timestamp", BuildTimestamp),
		zap.String("builder", Builder),
		zap.String("project_url", ProjectURL),
	)

	mux := http.NewServeMux()
	mux.HandleFunc("GET /healthz", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		if _, err := w.Write([]byte(`{"status":"ok"}`)); err != nil {
			logger.Warn("healthz_write_failed", zap.Error(err))
		}
	})

	// Metrics on a separate server/port: /metrics is never exposed on the public app
	// listener, and stays scrapeable even if the app mux is saturated.
	metricsMux := http.NewServeMux()
	metricsMux.Handle("GET /metrics", promhttp.Handler())

	host := getEnv("HOST", "0.0.0.0")
	appSrv := &http.Server{
		Addr:         fmt.Sprintf("%s:%s", host, getEnv("PORT", "8080")),
		Handler:      mux,
		ReadTimeout:  5 * time.Second,
		WriteTimeout: 10 * time.Second,
		IdleTimeout:  120 * time.Second,
	}
	metricsSrv := &http.Server{
		Addr:         fmt.Sprintf("%s:%s", host, getEnv("METRICS_PORT", "9090")),
		Handler:      metricsMux,
		ReadTimeout:  5 * time.Second,
		WriteTimeout: 10 * time.Second,
		IdleTimeout:  120 * time.Second,
	}

	serve := func(srv *http.Server) {
		logger.Info("listening", zap.String("addr", srv.Addr))
		if err := srv.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			logger.Fatal("server_failed", zap.String("addr", srv.Addr), zap.Error(err))
		}
	}
	go serve(appSrv)
	go serve(metricsSrv)

	quit := make(chan os.Signal, 1)
	signal.Notify(quit, syscall.SIGINT, syscall.SIGTERM)
	<-quit

	logger.Info("shutting_down")
	ctx, cancel := context.WithTimeout(context.Background(), 15*time.Second)
	defer cancel()
	for _, srv := range []*http.Server{appSrv, metricsSrv} {
		if err := srv.Shutdown(ctx); err != nil {
			// Drain deadline exceeded — force-close so we don't hang past the
			// orchestrator's termination grace period and get SIGKILLed mid-write.
			logger.Error("shutdown_failed", zap.String("addr", srv.Addr), zap.Error(err))
			if cerr := srv.Close(); cerr != nil {
				logger.Error("force_close_failed", zap.String("addr", srv.Addr), zap.Error(cerr))
			}
		}
	}
}
```

**Align**: don't overwrite existing application code. Check that:
- All five build-time vars (`Version`, `CommitHash`, `BuildTimestamp`, `Builder`, `ProjectURL`) exist
  and are in the startup log
- Logging uses `zap` with TTY auto-detection (`golang.org/x/term`)
- Timestamp config (`TimeKey`, `EncodeTime = ISO8601TimeEncoder`) applies to **both** console and JSON modes
- `LOG_FORMAT` env var is supported (`auto`/`console`/`json`)
- `/healthz` endpoint exists
- **Dual servers**: app + a separate metrics server exposing Prometheus `/metrics` (`METRICS_PORT`, default 9090)
- Graceful shutdown of **both** servers via signal+context, with a `srv.Close()` fallback when the drain deadline is exceeded
- HTTP servers have timeouts set

Report gaps.

#### main_test.go (new projects only)

Next to `main.go`, wherever the entry-point axis put it.

```go
package main

import (
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestHealthEndpoint(t *testing.T) {
	mux := http.NewServeMux()
	mux.HandleFunc("GET /healthz", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.Write([]byte(`{"status":"ok"}`))
	})

	req := httptest.NewRequest(http.MethodGet, "/healthz", nil)
	rec := httptest.NewRecorder()
	mux.ServeHTTP(rec, req)

	if rec.Code != http.StatusOK {
		t.Errorf("expected 200, got %d", rec.Code)
	}
	if body := rec.Body.String(); body != `{"status":"ok"}` {
		t.Errorf("unexpected body: %s", body)
	}
}
```

**Align**: if tests exist, don't overwrite. Check that `_test.go` files exist, report if missing.

#### Makefile

```makefile
APP_NAME    := project-name
MODULE      := module-path
# Entry-point axis: "." for a root main.go, "./cmd/<binary>" when the module ships several.
# Passed to docker build too, so the image and the local binary share one entry point.
PKG         := .
VERSION     ?= v0.0.0
COMMIT_HASH := $(shell git rev-parse --short HEAD 2>/dev/null || echo "0000000")
BUILD_TS    := $(shell date -Iseconds)
# Which Go built it. Fallback, or a $(shell) failure injects "" — reads as a broken log.
BUILDER     := $(shell go version 2>/dev/null || echo "unknown")
PROJECT_URL ?= $(MODULE)
# Always `main.`, never the import path — see rules/golang.md for why the other spelling
# silently does nothing.
LDFLAGS     := -s -w \
  -X 'main.Version=$(VERSION)' \
  -X 'main.CommitHash=$(COMMIT_HASH)' \
  -X 'main.BuildTimestamp=$(BUILD_TS)' \
  -X 'main.Builder=$(BUILDER)' \
  -X 'main.ProjectURL=$(PROJECT_URL)'

.PHONY: build run test lint clean docker-build docker-run

build:
	CGO_ENABLED=0 go build -ldflags="$(LDFLAGS)" -o bin/$(APP_NAME) $(PKG)

run: build
	./bin/$(APP_NAME)

test:
	go test -v -race ./...

lint:
	golangci-lint run

clean:
	rm -rf bin/

docker-build:
	docker build \
	  --build-arg VERSION="$(VERSION)" \
	  --build-arg COMMIT_HASH="$(COMMIT_HASH)" \
	  --build-arg BUILD_TIMESTAMP="$(BUILD_TS)" \
	  --build-arg PROJECT_URL="$(PROJECT_URL)" \
	  --build-arg PKG="$(PKG)" \
	  -t $(APP_NAME):local .

docker-run:
	# Metrics bound to loopback: /metrics is for you, not for the coffee-shop LAN.
	docker run --rm -p 8080:8080 -p 127.0.0.1:9090:9090 $(APP_NAME):local
```

Builds **one** binary. Several → one `PKG`/`build`/`-o bin/<name>` triplet each, or a `foreach` over a `BINARIES` list.

**Align**: ensure `build`, `test`, `lint` exist, `LDFLAGS` inject **against `main.`** (`rules/golang.md`), and `docker-build` forwards `PKG`.

#### .golangci.yml

```yaml
linters:
  enable:
    - bodyclose
    - gocritic
    - gosec
    - misspell
    - noctx
    - revive
    - unconvert

linters-settings:
  revive:
    rules:
      - name: exported
```

**Align**: if file exists, ensure all listed linters are enabled. Add missing ones.

#### Dockerfile

Copy the **Go build** template from `${CLAUDE_PLUGIN_ROOT}/rules/dockerfile.md` ("Go build") verbatim. Leave `ARG PKG="."` as written — the Makefile passes the entry point at build time.

**Align**: check multi-stage, OCI labels/ARGs **and the `ENV` re-export**, ldflags against `main.` (not the import path), `ARG PKG` wired to the build target, distroless/nonroot, `CGO_ENABLED=0`.

`main.Builder` comes from `$(go version)` **inside the builder stage**, never a `--build-arg` — an arg bakes the host's toolchain into an image built by a different one (a wrong `Builder` is worse than `unknown`).

#### .dockerignore

Copy the canonical list from `${CLAUDE_PLUGIN_ROOT}/rules/dockerfile.md` (".dockerignore"), plus the Go
row `bin/` — `make build` writes there and `COPY . .` would ship it into every build context.

**Align**: merge missing entries into existing `.dockerignore`.

#### .gitignore

```
bin/
*.exe
*.test
*.out
coverage.txt
.env
```

**Align**: merge missing entries into existing `.gitignore`.

### 3. Run tooling

```bash
go mod tidy
go test ./...
```

### 4. AGENTS.md

Create or update `AGENTS.md` per `${CLAUDE_PLUGIN_ROOT}/rules/agents-md.md`.

## Output

### New project
Report files created and issues from `go test` or `golangci-lint run`.

### Existing project
Report as a checklist:
- [x] Item already compliant
- [~] Item updated/fixed (describe change)
- [ ] Item needs manual attention (explain why)
