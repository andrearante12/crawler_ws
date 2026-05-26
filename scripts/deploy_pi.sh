#!/usr/bin/env bash
# Sync the pi/ directory to the Raspberry Pi and restart the crawler-node
# systemd service. Assumes the systemd unit is already installed (see
# pi/README.md for the one-time install step).
#
# Usage:
#   scripts/deploy_pi.sh
#   PI_HOST=pi@192.168.1.19 scripts/deploy_pi.sh
#   PI_HOST=pi@raspberrypi.local PI_DEST=~/crawler_ws/pi scripts/deploy_pi.sh
#
# Override PI_HOST or PI_DEST via env vars if your setup differs from the
# defaults below.

set -euo pipefail

PI_HOST="${PI_HOST:-pi@raspberrypi.local}"
PI_DEST="${PI_DEST:-~/crawler_ws/pi}"

# Resolve repo root from this script's location so it works from any cwd.
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "==> rsync ${REPO_ROOT}/pi/ -> ${PI_HOST}:${PI_DEST}/"
rsync -avz --delete \
    --exclude='.venv/' \
    --exclude='venv/' \
    --exclude='__pycache__/' \
    --exclude='*.pyc' \
    "${REPO_ROOT}/pi/" "${PI_HOST}:${PI_DEST}/"

echo "==> restart crawler-node on ${PI_HOST}"
ssh "${PI_HOST}" 'sudo systemctl restart crawler-node && sudo systemctl --no-pager --lines=10 status crawler-node'

echo "==> done. Tail logs with:"
echo "    ssh ${PI_HOST} 'journalctl -u crawler-node -f'"
