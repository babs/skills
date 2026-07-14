---
paths: **/*.py,**/*.go,**/*.ts,**/*.tsx
---

# Design Guidelines (language-agnostic)

## Stateless between requests

- **Nothing the app would miss after a mid-request restart may live in process memory or on the
  container filesystem** (app-level state, not the k8s StatefulSet sense). ≥2 replicas + rolling
  deploys: consecutive requests land on different pods
- Forbidden: module/package-level stores; in-memory sessions/login state; files under the app dir as
  storage (`./uploads/`, `./data.sqlite`); in-memory counters/queues/rate limits

| State | Home |
|---|---|
| Business data | PostgreSQL (`rules/postgres.md`) |
| Uploaded / generated files | NFS-class storage managed outside the cluster, or object storage |
| Sessions | signed stateless token, DB-backed row, or Redis |
| Durable job / message queues | DB (`SELECT … FOR UPDATE SKIP LOCKED` — claim the job quickly and commit, then process outside the lock, or a slow job pins a connection and an open transaction; outbox table); when volume outgrows it, RabbitMQ **consuming the outbox** (one transactional write — publishing to RabbitMQ directly alongside a DB write is the dual-write problem) — never Redis. Both transports are at-least-once: consumers dedupe by message id or stay idempotent |
| Locks, rate limits, coordination | Redis — losing one must only cost a re-election or a reset window; a security throttle (login/brute-force) whose reset reopens the attack window belongs in the DB |
| Leader election (one replica runs the singleton work) | Redis `SET NX` with a unique holder id + TTL, heartbeat-extend at TTL/2, compare-and-delete release (Lua) — a lost lock must only cost a re-election, and TTL locks give no fencing: two leaders can briefly overlap (GC pause, failover), so the protected work must be idempotent and safe under concurrent runs |
| Near-real-time events | outbox table + `LISTEN/NOTIFY` wake-up — NOTIFY is lossy, the table is the truth, keep a poll fallback |

- **Two tracks, no crossover**: durability escalates PostgreSQL → RabbitMQ; expendable
  process-shared state lives in Redis. Growth never moves data from one track to the other
- **Redis is expendable**: assume a flush at any moment — recomputable/re-login-able content only;
  anything worth keeping belongs in PostgreSQL
- Allowed per-process: wiring singletons (settings, DB engine/pool, shared HTTP client) — plumbing,
  not data; bounded loss-tolerant caches; `/tmp` scratch within a single request
