---
name: go-init
description: Initialize a new Go HTTP service or align an existing one to the standard
allowed-tools: Bash, Write, Edit, Read, Glob, Grep
version: "1.0.0"
---

## Context

You are setting up or aligning a Go HTTP service project to the production standard. Follow the rules from `${CLAUDE_PLUGIN_ROOT}/rules/golang.md` and `${CLAUDE_PLUGIN_ROOT}/rules/dockerfile.md`.

The user may provide a Go module path as argument (e.g. `github.com/org/project-name`). If not, use the current directory or ask.

## Task

### 1. Detect mode

- **No `go.mod` in current dir**: new project — create everything from scratch
- **Existing project detected**: audit and align — check each file below against the standard, report gaps, and fix them

### 2. Audit / create each file

For **new projects**, create all files. For **existing projects**, check each item and only add/update what's missing or non-compliant. Never overwrite existing application logic — only align config and tooling.

#### cmd/$APP_NAME/main.go (new projects only)

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
- Build-time vars (`Version`, `CommitHash`, `BuildTimestamp`, `ProjectURL`) exist
- Logging uses `zap` with TTY auto-detection (`golang.org/x/term`)
- Timestamp config (`TimeKey`, `EncodeTime = ISO8601TimeEncoder`) applies to **both** console and JSON modes
- `LOG_FORMAT` env var is supported (`auto`/`console`/`json`)
- `/healthz` endpoint exists
- **Dual servers**: app + a separate metrics server exposing Prometheus `/metrics` (`METRICS_PORT`, default 9090)
- Graceful shutdown of **both** servers via signal+context, with a `srv.Close()` fallback when the drain deadline is exceeded
- HTTP servers have timeouts set

Report gaps.

#### cmd/$APP_NAME/main_test.go (new projects only)

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
VERSION     ?= v0.0.0
COMMIT_HASH := $(shell git rev-parse --short HEAD 2>/dev/null || echo "0000000")
BUILD_TS    := $(shell date -Iseconds)
PROJECT_URL ?= $(MODULE)
LDFLAGS     := -s -w \
  -X '$(MODULE)/cmd/$(APP_NAME).Version=$(VERSION)' \
  -X '$(MODULE)/cmd/$(APP_NAME).CommitHash=$(COMMIT_HASH)' \
  -X '$(MODULE)/cmd/$(APP_NAME).BuildTimestamp=$(BUILD_TS)' \
  -X '$(MODULE)/cmd/$(APP_NAME).ProjectURL=$(PROJECT_URL)'

.PHONY: build run test lint clean docker-build docker-run

build:
	CGO_ENABLED=0 go build -ldflags="$(LDFLAGS)" -o bin/$(APP_NAME) ./cmd/$(APP_NAME)

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
	  -t $(APP_NAME):local .

docker-run:
	docker run --rm -p 8080:8080 $(APP_NAME):local
```

**Align**: if Makefile exists, ensure `build`, `test`, `lint` targets exist and `LDFLAGS` inject build-time vars. Add missing targets.

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

```dockerfile
FROM golang:1.26-bookworm AS builder
WORKDIR /src
COPY go.mod go.sum ./
RUN go mod download
COPY . .
ARG VERSION="v0.0.0"
ARG COMMIT_HASH="00000000-dirty"
ARG BUILD_TIMESTAMP="1970-01-01T00:00:00+00:00"
ARG PROJECT_URL="project-name"
RUN CGO_ENABLED=0 go build -ldflags="-s -w \
    -X 'main.Version=${VERSION}' \
    -X 'main.CommitHash=${COMMIT_HASH}' \
    -X 'main.BuildTimestamp=${BUILD_TIMESTAMP}' \
    -X 'main.ProjectURL=${PROJECT_URL}'" \
    -o /app ./cmd/project-name

FROM gcr.io/distroless/static-debian12:nonroot

ARG BUILD_TIMESTAMP="1970-01-01T00:00:00+00:00"
ARG COMMIT_HASH="00000000-dirty"
ARG PROJECT_URL="project-name"
ARG VERSION="v0.0.0"

LABEL org.opencontainers.image.source=${PROJECT_URL}
LABEL org.opencontainers.image.created=${BUILD_TIMESTAMP}
LABEL org.opencontainers.image.version=${VERSION}
LABEL org.opencontainers.image.revision=${COMMIT_HASH}

COPY --from=builder /app /app
EXPOSE 8080 9090
ENTRYPOINT ["/app"]
```

**Align**: if Dockerfile exists, check for: multi-stage build, OCI labels/ARGs, ldflags injection, distroless/nonroot runtime, `CGO_ENABLED=0`. Report what's missing and fix.

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

Create or update `AGENTS.md` following the AGENTS.md standard.

## Output

### New project
Report files created and issues from `go test` or `golangci-lint run`.

### Existing project
Report as a checklist:
- [x] Item already compliant
- [~] Item updated/fixed (describe change)
- [ ] Item needs manual attention (explain why)
