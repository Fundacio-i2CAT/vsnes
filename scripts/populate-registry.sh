#!/bin/bash
# populate-registry.sh — pull all images needed by k3s and push them to
# the vsnes-registry at 172.27.12.200:5000 (also reachable as localhost:5000).
#
# Run this ONCE after starting the registry:
#   docker compose up -d registry
#   bash scripts/populate-registry.sh
#
# k3s will then pull from the local registry instead of the internet.

set -euo pipefail

REGISTRY="${REGISTRY:-localhost:5001}"
K3S_VERSION="${K3S_VERSION:-v1.31.4+k3s1}"

# ── colours ──────────────────────────────────────────────────────────────────
G='\033[0;32m'; Y='\033[1;33m'; R='\033[0;31m'; NC='\033[0m'
ok()   { echo -e "${G}[ok]${NC}  $*"; }
info() { echo -e "${Y}[..]${NC}  $*"; }
err()  { echo -e "${R}[!!]${NC}  $*" >&2; }

# ── helpers ───────────────────────────────────────────────────────────────────

# push_image <full-source-ref>
# Tags the image preserving its original path under REGISTRY and pushes it.
# docker.io/rancher/coredns:1.12 → localhost:5000/rancher/coredns:1.12
# ghcr.io/kedacore/keda:2.16.0  → localhost:5000/kedacore/keda:2.16.0
push_image() {
    local src="$1"
    # Strip the registry prefix (everything up to the first /)
    # docker.io/foo/bar → foo/bar   ghcr.io/foo/bar → foo/bar
    local path_tag
    path_tag=$(echo "$src" | sed 's|^[^/]*/||')
    local dest="${REGISTRY}/${path_tag}"

    info "pulling  ${src}"
    docker pull "${src}" -q

    docker tag  "${src}" "${dest}"
    info "pushing  ${dest}"
    docker push "${dest}" -q
    ok "${dest}"
}

# ── wait for registry ─────────────────────────────────────────────────────────
info "waiting for registry at ${REGISTRY}..."
for i in $(seq 1 15); do
    curl -sf "http://${REGISTRY}/v2/" > /dev/null 2>&1 && break
    [ $i -eq 15 ] && { err "registry not up after 15s — is 'docker compose up -d registry' done?"; exit 1; }
    sleep 1
done
ok "registry is up"

# ── k3s internal images (v${K3S_VERSION}) ─────────────────────────────────────
echo ""
info "=== k3s internal images (${K3S_VERSION}) ==="

K3S_IMAGES=$(curl -sfL \
    "https://github.com/k3s-io/k3s/releases/download/${K3S_VERSION}/k3s-images.txt" \
    2>/dev/null) || { err "could not fetch k3s image list"; exit 1; }

while IFS= read -r img; do
    [ -z "$img" ] && continue
    push_image "$img"
done <<< "$K3S_IMAGES"

# ── KEDA ──────────────────────────────────────────────────────────────────────
echo ""
info "=== KEDA ==="
KEDA_VERSION="${KEDA_VERSION:-2.16.0}"
push_image "ghcr.io/kedacore/keda:${KEDA_VERSION}"
push_image "ghcr.io/kedacore/keda-metrics-apiserver:${KEDA_VERSION}"
push_image "ghcr.io/kedacore/keda-admission-webhooks:${KEDA_VERSION}"

# ── nginx ─────────────────────────────────────────────────────────────────────
echo ""
info "=== nginx ==="
push_image "docker.io/library/nginx:stable-alpine"
push_image "docker.io/library/nginx:alpine"

# ── registry (self-host the image so k3s can deploy it too) ──────────────────
echo ""
info "=== registry ==="
push_image "docker.io/library/registry:2"

# ── summary ───────────────────────────────────────────────────────────────────
echo ""
ok "=== all images pushed to ${REGISTRY} ==="
echo ""
info "repository list:"
curl -sf "http://${REGISTRY}/v2/_catalog" | python3 -m json.tool 2>/dev/null \
    || curl -sf "http://${REGISTRY}/v2/_catalog"
