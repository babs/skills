---
paths: **/.github/workflows/*.yml,**/.github/workflows/*.yaml,**/.github/actions/**
---

# GitHub Actions Guidelines

## Docker Image Build & Push

- **Triggers**: tag push `v[0-9]+.[0-9]+.[0-9]+` (+ `-*` pre-releases), PR (build only, no push, amd64 only)
- **Build**: `docker/build-push-action@v6+` + `docker/setup-buildx-action@v3+`, GHA cache (`type=gha` / `mode=max`, scoped per-platform so amd64/arm64 don't evict each other). Emit supply-chain attestations: `provenance: mode=max`, `sbom: true` — note each build then pushes an OCI **index** (image + attestations), so the multi-platform merge MUST use `docker buildx imagetools create` (not `docker manifest`, which rejects indexes).
- **Signing**: cosign **keyless** (Fulcio + Rekor, via `sigstore/cosign-installer`); sign the per-platform digests AND the merged index digest — consumers pull by tag → the index digest, so an unsigned index makes `cosign verify <repo>:<tag>` fail despite signed children.
- **OCI metadata**: inject via build-args `VERSION`, `COMMIT_HASH`, `BUILD_TIMESTAMP`, `PROJECT_URL` (+ optional `BUILDER`)
- **Auth secrets**: GHCR uses `secrets.GITHUB_TOKEN`, Docker Hub uses `vars.DOCKERHUB_USERNAME` / `secrets.DOCKERHUB_TOKEN`, Quay uses `secrets.QUAY_USERNAME` / `secrets.QUAY_TOKEN`
- **Permissions**: `contents: read`, `packages: write`, `id-token: write`, `attestations: write`
- **Tagging**: `latest` (apps only, not libraries), semver expansion (`:v1.0.0`, `:1.0`, `:1`), pre-release channel tags (`:alpha`, `:beta`, `:rc`)

## Multi-platform

Prefer matrix-per-platform with manifest merge over single buildx multi-platform:

```yaml
strategy:
  matrix:
    include:
      - platform: linux/amd64
        os: ubuntu-latest
      - platform: linux/arm64
        os: ubuntu-24.04-arm
```

Build per platform, then merge manifests in a separate job.

## Local testing

- Test workflows locally before pushing when possible: use [`act`](https://github.com/nektos/act)
- Caveats: GHA cache (`type=gha`), OIDC (`id-token`), and attestations are not fully emulated — scope dry runs to build/test steps
