#!/bin/bash
# update.sh — Pin ado-backup to a specific git tag and rebuild the container.
#
# Usage (over SSH on the NAS):
#     ./update.sh v0.2.0
#
# Uses git from a docker container, so no `git` install is required on the
# NAS host — only docker (which you already have for ado-backup itself).
#
# Prerequisites (one-time setup):
#   - app/ must be a git working copy. Bootstrap once with:
#       cd /share/Almacen/BACKUPs/ado
#       mv app app.old      # if it exists as a plain copy
#       docker run --rm -v /share/Almacen/BACKUPs/ado:/work alpine/git \
#         clone https://github.com/mainmind83/ado-backup.git /work/app
#       # then verify any local customizations and delete app.old
#   - The production docker-compose file (the one with your real PAT inlined)
#     must live OUTSIDE app/ so `git checkout` does not overwrite it.
#     Default location: /share/Almacen/BACKUPs/ado/docker-compose.qnap.yml
#
# Tweak these paths if your layout differs:
APP_DIR="/share/Almacen/BACKUPs/ado/app"
COMPOSE_FILE="/share/Almacen/BACKUPs/ado/docker-compose.qnap.yml"
LOG_FILE="/share/Almacen/BACKUPs/ado/logs/backup.log"
GIT_IMAGE="alpine/git:latest"

set -eu

TAG="${1:-}"
if [ -z "$TAG" ]; then
    echo "Usage: $0 <tag>   e.g.: $0 v0.2.0"
    exit 1
fi

# `git` here is a wrapper that runs the official alpine/git image with the
# working copy mounted, so host git is not required.
git() {
    docker run --rm -v "$APP_DIR:/work" -w /work "$GIT_IMAGE" "$@"
}

if [ ! -d "$APP_DIR/.git" ]; then
    echo "ERROR: $APP_DIR is not a git working copy."
    echo "See the prerequisites at the top of this script."
    exit 1
fi

if [ ! -f "$COMPOSE_FILE" ]; then
    echo "ERROR: compose file not found at $COMPOSE_FILE"
    echo "Edit COMPOSE_FILE at the top of this script to match your layout."
    exit 1
fi

echo "==> Fetching tags from origin..."
git fetch --tags --prune

if ! git rev-parse --verify "refs/tags/$TAG" >/dev/null 2>&1; then
    echo "ERROR: tag '$TAG' does not exist in origin."
    echo "Recent tags:"
    git tag -l | sort -V | tail -10
    exit 1
fi

CURRENT="$(git describe --tags --always 2>/dev/null || echo 'unknown')"
echo "==> Currently at: $(echo "$CURRENT" | tr -d '\r')"
echo "==> Checking out $TAG..."
git checkout "$TAG"

echo "==> Rebuilding image and recreating container..."
docker compose -f "$COMPOSE_FILE" up -d --build

echo "==> Done. Last 30 log lines:"
sleep 2
if [ -f "$LOG_FILE" ]; then
    tail -n 30 "$LOG_FILE"
else
    echo "(no log file at $LOG_FILE yet — first run after rebuild will create it)"
fi

echo ""
echo "==> Update to $TAG complete. To watch live: tail -f $LOG_FILE"
