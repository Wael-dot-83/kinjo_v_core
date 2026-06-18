#!/usr/bin/env bash
# =============================================================================
# scripts/setup-local.sh
# First-time local development setup helper.
# Run once from the project root:  bash reqMd/scripts/setup-local.sh
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'
info()  { echo -e "${GREEN}[setup]${NC} $*"; }
warn()  { echo -e "${YELLOW}[warn] ${NC} $*"; }
step()  { echo -e "${CYAN}──────────────────────────────────────────${NC}"; echo -e "${CYAN}$*${NC}"; }

cd "$PROJECT_ROOT"

step "1/6  Check prerequisites"

for cmd in python3 pip docker; do
  if command -v "$cmd" &>/dev/null; then
    info "$cmd … found ($(${cmd} --version 2>&1 | head -1))"
  else
    warn "$cmd … NOT found (required)"
  fi
done

step "2/6  Create virtual environment"
if [ ! -d ".venv" ]; then
  python3 -m venv .venv
  info ".venv created"
else
  info ".venv already exists"
fi
# shellcheck disable=SC1091
source .venv/bin/activate

step "3/6  Install dependencies"
pip install -q --upgrade pip
pip install -q -r requirements.txt
info "Dependencies installed"

step "4/6  Create .env.local"
if [ ! -f ".env.local" ]; then
  cp reqMd/.env.local.example .env.local
  # Generate a real SECRET_KEY
  SK=$(python3 -c "import secrets; print(secrets.token_hex(32))")
  sed -i "s|local-dev-secret-key-change-before-any-public-deployment|${SK}|g" .env.local
  info ".env.local created with a fresh SECRET_KEY"
else
  info ".env.local already exists — skipping"
fi

step "5/6  Create required data directories"
mkdir -p data/attachments data/uploads logs
info "data/ and logs/ directories ready"

step "6/6  Copy local docker-compose override to project root"
if [ ! -f "docker-compose.local.yml" ]; then
  cp reqMd/docker-compose.local.yml .
  info "docker-compose.local.yml copied to project root"
else
  info "docker-compose.local.yml already in project root — skipping"
fi

echo ""
info "Setup complete. Next steps:"
echo "  1. Review .env.local"
echo "  2. docker compose -f docker-compose.yml -f docker-compose.local.yml up"
echo "  OR just run:  bash reqMd/run-local.sh"
echo "  OR on Windows: .\\reqMd\\run-local.ps1"
