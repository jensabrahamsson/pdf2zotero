#!/usr/bin/env bash
# setup-grobid.sh — start or remove the GROBID Docker service for pdf2zotero.
#
# Default image matches PREREQUISITES.md / GROBID Docker guide:
#   grobid/grobid:0.9.0-crf  (use --full for 0.9.0-full)
#
# Usage:
#   ./scripts/setup-grobid.sh              # start (pull + run + wait until alive)
#   ./scripts/setup-grobid.sh up
#   ./scripts/setup-grobid.sh up --full
#   ./scripts/setup-grobid.sh status
#   ./scripts/setup-grobid.sh down         # stop/remove container only
#   ./scripts/setup-grobid.sh purge        # stop container + delete GROBID images
#
# Requires: Docker (Docker Desktop or Colima + docker CLI).
# Copyright (c) 2026 Jens Abrahamsson. MIT License.

set -euo pipefail

NAME="${GROBID_NAME:-grobid}"
PORT="${GROBID_PORT:-8070}"
IMAGE_CRF="grobid/grobid:0.9.0-crf"
IMAGE_FULL="grobid/grobid:0.9.0-full"
IMAGE="$IMAGE_CRF"
WAIT_ATTEMPTS="${GROBID_WAIT_ATTEMPTS:-36}"  # ~3 min at 5s
WAIT_SLEEP=5

usage() {
  sed -n '2,18p' "$0" | sed 's/^# \{0,1\}//'
  exit "${1:-0}"
}

die() {
  echo "Error: $*" >&2
  exit 1
}

need_docker() {
  command -v docker >/dev/null 2>&1 || die "docker not found on PATH"
  if ! docker info >/dev/null 2>&1; then
    if command -v colima >/dev/null 2>&1; then
      echo "Docker daemon not reachable; starting Colima…"
      colima start
      # Prefer colima context when present
      if docker context ls --format '{{.Name}}' 2>/dev/null | grep -qx colima; then
        docker context use colima >/dev/null
      fi
    else
      die "Docker daemon not running. Start Docker Desktop or Colima, then retry."
    fi
  fi
  docker info >/dev/null 2>&1 || die "Docker still not reachable after Colima start"
}

isalive() {
  curl -sf "http://127.0.0.1:${PORT}/api/isalive" 2>/dev/null | grep -qi true
}

cmd_status() {
  need_docker
  echo "Container '${NAME}':"
  if docker ps -a --format '{{.Names}}' | grep -qx "$NAME"; then
    docker ps -a --filter "name=^/${NAME}$" --format '  {{.Status}}  image={{.Image}}  ports={{.Ports}}'
  else
    echo "  (not present)"
  fi
  echo -n "HTTP :${PORT}/api/isalive → "
  if isalive; then
    curl -s "http://127.0.0.1:${PORT}/api/isalive"
    echo
    echo -n "version → "
    curl -s "http://127.0.0.1:${PORT}/api/version" || true
    echo
  else
    echo "not reachable"
  fi
  echo "GROBID-related images:"
  docker images --format '  {{.Repository}}:{{.Tag}}\t{{.Size}}' \
    | grep -iE 'grobid|lfoppiano' || echo "  (none)"
}

cmd_up() {
  need_docker
  echo "Using image: $IMAGE"
  echo "Pulling (first time can be large)…"
  docker pull "$IMAGE"

  if docker ps -a --format '{{.Names}}' | grep -qx "$NAME"; then
    echo "Removing existing container '${NAME}'…"
    docker rm -f "$NAME" >/dev/null
  fi

  echo "Starting named container '${NAME}' on port ${PORT}…"
  docker run -d --name "$NAME" \
    --init \
    --ulimit core=0 \
    -p "${PORT}:8070" \
    "$IMAGE" >/dev/null

  echo "Waiting for GROBID to become alive (up to ~$((WAIT_ATTEMPTS * WAIT_SLEEP))s)…"
  for i in $(seq 1 "$WAIT_ATTEMPTS"); do
    if isalive; then
      echo "GROBID is up: http://127.0.0.1:${PORT}/api/isalive"
      curl -s "http://127.0.0.1:${PORT}/api/version" || true
      echo
      return 0
    fi
    printf '  attempt %s/%s…\n' "$i" "$WAIT_ATTEMPTS"
    sleep "$WAIT_SLEEP"
  done
  echo "Timed out waiting for GROBID. Recent logs:" >&2
  docker logs --tail 40 "$NAME" >&2 || true
  die "GROBID did not become ready"
}

cmd_down() {
  need_docker
  if docker ps -a --format '{{.Names}}' | grep -qx "$NAME"; then
    docker rm -f "$NAME"
    echo "Removed container '${NAME}'."
  else
    echo "Container '${NAME}' not present."
  fi
}

cmd_purge() {
  cmd_down
  echo "Removing GROBID Docker images…"
  # Official tags used by this project + common leftovers
  local imgs=(
    "$IMAGE_CRF"
    "$IMAGE_FULL"
    "grobid/grobid-crf:0.8.0"
    "grobid/grobid:0.8.2"
    "lfoppiano/grobid:0.8.1"
  )
  local id
  for id in "${imgs[@]}"; do
    if docker image inspect "$id" >/dev/null 2>&1; then
      docker rmi "$id" && echo "  removed $id" || echo "  could not remove $id (in use?)"
    fi
  done
  # Any other dangling grobid-related tags
  while read -r repo tag; do
    [[ -z "${repo:-}" ]] && continue
    local ref="${repo}:${tag}"
    [[ "$tag" == "<none>" ]] && ref=$(docker images -q "$repo" | head -1)
    if [[ -n "$ref" ]]; then
      docker rmi "$ref" 2>/dev/null && echo "  removed $ref" || true
    fi
  done < <(docker images --format '{{.Repository}} {{.Tag}}' | grep -iE 'grobid|lfoppiano' || true)

  echo "Done. Disk (docker system df):"
  docker system df 2>/dev/null || true
  echo
  echo "To start GROBID again later:"
  echo "  ./scripts/setup-grobid.sh up"
}

# --- parse args ---
ACTION="up"
while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help) usage 0 ;;
    up|start|setup) ACTION="up"; shift ;;
    down|stop) ACTION="down"; shift ;;
    purge|remove|clean) ACTION="purge"; shift ;;
    status) ACTION="status"; shift ;;
    --full) IMAGE="$IMAGE_FULL"; shift ;;
    --crf) IMAGE="$IMAGE_CRF"; shift ;;
    --port) PORT="${2:?}"; shift 2 ;;
    --name) NAME="${2:?}"; shift 2 ;;
    --image) IMAGE="${2:?}"; shift 2 ;;
    *) die "unknown argument: $1 (try --help)" ;;
  esac
done

case "$ACTION" in
  up) cmd_up ;;
  down) cmd_down ;;
  purge) cmd_purge ;;
  status) cmd_status ;;
  *) usage 1 ;;
esac
