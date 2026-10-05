#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

DOMAIN="claritybs.in"
TARGET_DIR="/srv/claritybs-mvp"

usage() {
  cat <<'EOF'
Usage:
  sudo bash deploy_ubuntu_vps.sh /path/to/ClarityBS-MVP.zip \
    "Clarity Blood Sugar" support@claritybs.in [domain]

This is a first-deployment script for a clean Ubuntu VPS. It installs Docker
from Docker's official apt repository when Docker is absent, deploys the stack
with intake/payments paused, and installs the daily encrypted local backup job.

It deliberately stops if /srv/claritybs-mvp exists or ports 80/443 are busy.
Do not run it on a server where Coolify or another reverse proxy is running.
EOF
}

fail() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

[[ ${EUID:-$(id -u)} -eq 0 ]] || fail "Run this script with sudo."
[[ $# -ge 3 && $# -le 4 ]] || { usage; exit 64; }

ZIP_PATH="$(realpath "$1")"
BUSINESS_NAME="$2"
SUPPORT_EMAIL="$3"
DOMAIN="${4:-$DOMAIN}"

[[ -f "$ZIP_PATH" ]] || fail "ZIP not found: $ZIP_PATH"
[[ "$BUSINESS_NAME" != *$'\n'* && -n "$BUSINESS_NAME" ]] || fail "Business name is invalid."
[[ "$SUPPORT_EMAIL" =~ ^[^[:space:]@]+@[^[:space:]@]+\.[^[:space:]@]+$ ]] || fail "Support email is invalid."
[[ "$DOMAIN" =~ ^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+$ ]] || fail "Domain is invalid."
[[ ! -e "$TARGET_DIR" ]] || fail "$TARGET_DIR already exists. This first-deploy script will not overwrite it."

source /etc/os-release
[[ "${ID:-}" == "ubuntu" ]] || fail "This script supports Ubuntu only."

if ss -H -ltn 2>/dev/null | awk '{print $4}' | grep -Eq '(^|:)(80|443)$'; then
  fail "Ports 80 or 443 are already in use. Stop here and identify the existing proxy; do not stop Coolify automatically."
fi

export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y ca-certificates curl unzip python3

if ! command -v docker >/dev/null 2>&1; then
  conflicts="$(dpkg-query -W -f='${binary:Package}\n' docker.io docker-compose docker-compose-v2 podman-docker containerd runc 2>/dev/null || true)"
  [[ -z "$conflicts" ]] || fail "Conflicting container packages are installed: $conflicts. Follow Docker's official Ubuntu uninstall guidance, then rerun."

  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
  chmod a+r /etc/apt/keyrings/docker.asc
  ARCH="$(dpkg --print-architecture)"
  CODENAME="${UBUNTU_CODENAME:-$VERSION_CODENAME}"
  printf 'deb [arch=%s signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu %s stable\n' \
    "$ARCH" "$CODENAME" > /etc/apt/sources.list.d/docker.list
  apt-get update
  apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
fi

docker compose version >/dev/null
systemctl enable --now docker

STAGE_DIR="$(mktemp -d /tmp/claritybs-deploy.XXXXXX)"
cleanup() { rm -rf -- "$STAGE_DIR"; }
trap cleanup EXIT
unzip -q "$ZIP_PATH" -d "$STAGE_DIR"
SOURCE_DIR="$STAGE_DIR/claritybs-mvp"
[[ -f "$SOURCE_DIR/compose.yaml" && -f "$SOURCE_DIR/scripts/bootstrap_env.py" ]] || \
  fail "ZIP does not contain the expected claritybs-mvp project."

install -d -m 0750 "$(dirname "$TARGET_DIR")"
mv "$SOURCE_DIR" "$TARGET_DIR"
cd "$TARGET_DIR"
python3 scripts/bootstrap_env.py

python3 - "$BUSINESS_NAME" "$SUPPORT_EMAIL" "$DOMAIN" <<'PY'
from pathlib import Path
import sys

values = {
    "BUSINESS_NAME": sys.argv[1],
    "SUPPORT_EMAIL": sys.argv[2],
    "DOMAIN": sys.argv[3],
    "APP_ORIGIN": "https://" + sys.argv[3],
}
path = Path(".env")
lines = path.read_text().splitlines()
seen = set()
for index, line in enumerate(lines):
    key = line.partition("=")[0]
    if key in values:
        lines[index] = f"{key}={values[key]}"
        seen.add(key)
for key in values.keys() - seen:
    lines.append(f"{key}={values[key]}")
path.write_text("\n".join(lines) + "\n")
path.chmod(0o600)
PY

docker compose config --quiet
docker compose up -d --build

healthy=false
for _ in $(seq 1 60); do
  if docker compose exec -T api python -c \
    "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/live', timeout=3)" \
    >/dev/null 2>&1; then
    healthy=true
    break
  fi
  sleep 3
done
[[ "$healthy" == true ]] || {
  docker compose ps
  docker compose logs --tail=100 api worker caddy >&2
  fail "The API did not become healthy. DNS was not changed by this script."
}

install -m 0644 /dev/null /etc/cron.d/claritybs-backup
printf '0 2 * * * root cd %s && /bin/sh scripts/backup.sh >> /var/log/claritybs-backup.log 2>&1\n' \
  "$TARGET_DIR" > /etc/cron.d/claritybs-backup

docker compose ps
cat <<EOF

Clarity Blood Sugar is running on this VPS with intake and payments PAUSED.

Next steps:
1. In Hostinger DNS, point A record @ to this VPS IPv4.
2. Point A record www to this VPS IPv4, or CNAME www to $DOMAIN.
3. Keep all MX/TXT email records unchanged.
4. Allow inbound TCP 80/443 and your SSH port in the provider firewall.
5. After DNS resolves here, verify: curl -fsS https://$DOMAIN/health/live
6. Create staff accounts using the commands in docs/DEPLOYMENT.md.
7. Copy the DATA_ENCRYPTION_KEY to a secure off-server password manager and test backup restore.

Do not enable PUBLIC_INTAKE_ENABLED or payments yet.
Do not delete the old Hostinger website until HTTPS and the closed workflow pass on this VPS.
EOF
