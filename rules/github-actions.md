---
paths: **/.github/workflows/*.yml,**/.github/workflows/*.yaml,**/.github/actions/**
---

# GitHub Actions Guidelines

> **Every version pin here is a floor, not a ceiling — check the current release and take it; never downgrade a project to match this file.**

## Docker Image Build & Push

- **Triggers**: tag push `v[0-9]+.[0-9]+.[0-9]+` (+ `-*` pre-releases), PR (build only, no push, amd64 only)
- **Build**: `docker/build-push-action@v7+` + `docker/setup-buildx-action@v3+`, GHA cache (`type=gha` / `mode=max`, scoped per-platform so amd64/arm64 don't evict each other). Emit supply-chain attestations: `provenance: mode=max`, `sbom: true` — note each build then pushes an OCI **index** (image + attestations), so the multi-platform merge MUST use `docker buildx imagetools create` (not `docker manifest`, which rejects indexes).
- **Signing**: cosign **keyless** (Fulcio + Rekor, via `sigstore/cosign-installer`), once, in the merge job. `cosign sign --yes --recursive` on the merged index digest covers the index (what a tag pull resolves to), each platform image and its attestation manifests; the per-platform build jobs don't sign. Order: `docker buildx imagetools create --metadata-file` under a scratch tag, read `."containerimage.descriptor".digest`, sign and `cosign verify` that digest, then move the public tags with a second `imagetools create` from the digest (a single source index is copied as is). A failed signature leaves the public tags untouched.
- **OCI metadata**: inject via build-args `VERSION`, `COMMIT_HASH`, `BUILD_TIMESTAMP`, `PROJECT_URL` (+ optional `BUILDER`)
- **Auth secrets**: GHCR uses `secrets.GITHUB_TOKEN`, Docker Hub uses `vars.DOCKERHUB_USERNAME` / `secrets.DOCKERHUB_TOKEN`, Quay uses `secrets.QUAY_USERNAME` / `secrets.QUAY_TOKEN`
- **Permissions**: `contents: read`, `packages: write`; `id-token: write` only on the merge job that signs. No `attestations: write`: it only serves `actions/attest`, which duplicates the buildx provenance the signed index already references by digest.
- **Pinning**: in a job holding `id-token: write`, pin every action by commit SHA (`@<sha> # vX.Y.Z`): any step there can request the signing OIDC token.
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

Build per platform, then merge manifests in a separate job. The merge job fails unless it got one digest per matrix platform: a partial re-run must not publish a single-arch image.

## Local testing

- Test workflows locally before pushing when possible: use [`act`](https://github.com/nektos/act)
- Caveats: GHA cache (`type=gha`), OIDC (`id-token`), and attestations are not fully emulated — scope dry runs to build/test steps
