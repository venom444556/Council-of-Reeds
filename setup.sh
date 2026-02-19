#!/usr/bin/env bash
# ============================================================
#  Council-Powered OpenClaw — One-Click Setup
#  Usage: curl -fsSL https://your-server/setup.sh | bash
#    or:  chmod +x setup.sh && ./setup.sh
#    or:  ./setup.sh --update   (update existing installation)
# ============================================================

set -euo pipefail

# ── Colors ───────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'

log()     { echo -e "${CYAN}[council]${NC} $*"; }
success() { echo -e "${GREEN}[✓]${NC} $*"; }
warn()    { echo -e "${YELLOW}[!]${NC} $*"; }
error()   { echo -e "${RED}[✗]${NC} $*"; exit 1; }
header()  { echo -e "\n${BOLD}${BLUE}══ $* ══${NC}\n"; }

# ── Parse flags ──────────────────────────────────────────────
UPDATE_MODE=false
for arg in "$@"; do
    case "$arg" in
        --update) UPDATE_MODE=true ;;
    esac
done

# ── Banner ───────────────────────────────────────────────────
if $UPDATE_MODE; then
    echo -e "
${BOLD}${BLUE}
  LLM Council — Update Existing Installation
${NC}
  Pulls latest images, rebuilds, and restarts.
"
else
    echo -e "
${BOLD}${BLUE}
  LLM Council — OpenClaw One-Click Deploy
${NC}
  Multi-model AI deliberation on your own server.
  Free councilors + GPT-4o Chairman. ~\$0.02/query.
"
fi

# ── Preflight checks ─────────────────────────────────────────
header "Preflight"

command -v docker  >/dev/null 2>&1 || error "Docker not found. Install it first: https://docs.docker.com/engine/install/"
command -v curl    >/dev/null 2>&1 || error "curl not found. Run: apt-get install curl"

# Define docker_compose wrapper for v2 plugin or legacy standalone
if docker compose version >/dev/null 2>&1; then
    docker_compose() { docker compose "$@"; }
elif command -v docker-compose >/dev/null 2>&1; then
    docker_compose() { docker-compose "$@"; }
else
    error "Docker Compose v2 not found. Run: apt-get install docker-compose-plugin"
fi

success "Docker $(docker --version | awk '{print $3}' | tr -d ',')"
success "Docker Compose ready"

# ── Directories ──────────────────────────────────────────────
OPENCLAW_HOME="${HOME}/.openclaw"
WORKSPACE="${HOME}/openclaw/workspace"
SKILLS_DIR="${OPENCLAW_HOME}/skills/council"
DEPLOY_DIR="${HOME}/openclaw/deploy"

# ── Update mode: fast path ───────────────────────────────────
if $UPDATE_MODE; then
    header "Updating"

    [[ -d "$DEPLOY_DIR" ]] || error "No existing installation found at ${DEPLOY_DIR}. Run without --update for first-time setup."

    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

    # Update skill files
    for f in SKILL.md council.py council_pdf.py; do
        if [[ -f "${SCRIPT_DIR}/${f}" ]]; then
            cp "${SCRIPT_DIR}/${f}" "${SKILLS_DIR}/${f}"
            success "Updated: ${f}"
        fi
    done

    # Update compose files
    for f in Dockerfile docker-compose.yml; do
        if [[ -f "${SCRIPT_DIR}/${f}" ]]; then
            cp "${SCRIPT_DIR}/${f}" "${DEPLOY_DIR}/${f}"
        fi
    done

    cd "$DEPLOY_DIR"
    log "Pulling latest base image and rebuilding..."
    docker_compose build --pull 2>&1 | while IFS= read -r line; do
        echo "   $line"
    done
    success "Image rebuilt"

    log "Restarting gateway..."
    docker_compose down
    docker_compose up -d openclaw-gateway
    sleep 3

    if curl -sf http://localhost:18789/health >/dev/null 2>&1; then
        success "Gateway is up and healthy"
    else
        warn "Gateway started but health endpoint not responding yet (may still be initializing)"
    fi

    echo -e "\n${BOLD}${GREEN}  Update complete!${NC}\n"
    exit 0
fi

# ── Collect config ───────────────────────────────────────────
header "Configuration"

# OpenRouter API key
if [[ -z "${OPENROUTER_API_KEY:-}" ]]; then
    echo -e "${YELLOW}Get a key at https://openrouter.ai${NC}"
    echo -e "${YELLOW}Free tier for councilors, paid credits needed for GPT-4o Chairman (~\$0.02/query)${NC}"
    read -rp "  OpenRouter API key (sk-or-v1-...): " OPENROUTER_API_KEY
    [[ -z "$OPENROUTER_API_KEY" ]] && error "OpenRouter key required."
fi

# Validate key format
if [[ ! "$OPENROUTER_API_KEY" =~ ^sk-or-v1- ]]; then
    error "Invalid API key format. OpenRouter keys start with 'sk-or-v1-'. Got: ${OPENROUTER_API_KEY:0:12}..."
fi
success "OpenRouter key validated (sk-or-v1-...)"

# Gateway token (generate if not provided)
if [[ -z "${OPENCLAW_GATEWAY_TOKEN:-}" ]]; then
    if command -v openssl >/dev/null 2>&1; then
        OPENCLAW_GATEWAY_TOKEN=$(openssl rand -hex 32)
    elif [[ -r /dev/urandom ]]; then
        OPENCLAW_GATEWAY_TOKEN=$(head -c 32 /dev/urandom | od -An -tx1 | tr -d ' \n')
    else
        error "Cannot generate secure random token. Set OPENCLAW_GATEWAY_TOKEN manually."
    fi
    log "Generated gateway token: ${OPENCLAW_GATEWAY_TOKEN}"
fi
success "Gateway token ready"

# ── Directory structure ──────────────────────────────────────
header "Directories"

mkdir -p "$OPENCLAW_HOME" "$WORKSPACE" "$SKILLS_DIR" "$DEPLOY_DIR"
success "Created: $OPENCLAW_HOME"
success "Created: $WORKSPACE"
success "Created: $SKILLS_DIR (council skill)"

# ── Write .env ───────────────────────────────────────────────
header "Environment"

ENV_FILE="${DEPLOY_DIR}/.env"
cat > "$ENV_FILE" <<EOF
OPENCLAW_GATEWAY_TOKEN=${OPENCLAW_GATEWAY_TOKEN}
OPENROUTER_API_KEY=${OPENROUTER_API_KEY}
EOF
chmod 600 "$ENV_FILE"
success "Wrote ${ENV_FILE} (mode 600)"

# ── Write/merge openclaw.json ────────────────────────────────
OPENCLAW_JSON="${OPENCLAW_HOME}/openclaw.json"
COUNCIL_SKILL_JSON='{
  "council": {
    "enabled": true,
    "env": {
      "OPENROUTER_API_KEY": "'"${OPENROUTER_API_KEY}"'"
    }
  }
}'

if [[ ! -f "$OPENCLAW_JSON" ]]; then
    # Fresh install — create the file
    cat > "$OPENCLAW_JSON" <<EOF
{
  "skills": {
    "entries": {
      "council": {
        "enabled": true,
        "env": {
          "OPENROUTER_API_KEY": "${OPENROUTER_API_KEY}"
        }
      }
    }
  }
}
EOF
    success "Created openclaw.json with council skill enabled"
else
    # File exists — check if council skill is already registered
    if command -v python3 >/dev/null 2>&1; then
        MERGE_OUTPUT=$(python3 -c "
import json, sys
with open('${OPENCLAW_JSON}', 'r') as f:
    config = json.load(f)
skills = config.setdefault('skills', {})
entries = skills.setdefault('entries', {})
if 'council' not in entries:
    entries['council'] = {
        'enabled': True,
        'env': {'OPENROUTER_API_KEY': '${OPENROUTER_API_KEY}'}
    }
    with open('${OPENCLAW_JSON}', 'w') as f:
        json.dump(config, f, indent=2)
    print('merged')
else:
    print('exists')
" 2>&1)
        if [[ $? -eq 0 ]]; then
            if [[ "$MERGE_OUTPUT" == "merged" ]]; then
                success "Council skill merged into existing openclaw.json"
            else
                success "Council skill already registered in openclaw.json"
            fi
        else
            warn "Could not merge into openclaw.json: ${MERGE_OUTPUT} — add council skill config manually"
        fi
    else
        warn "openclaw.json exists but python3 not available for merge — add council skill manually"
    fi
fi

# ── Install council skill files ──────────────────────────────
header "Council Skill"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Copy skill files if they're alongside this script
for f in SKILL.md council.py council_pdf.py; do
    if [[ -f "${SCRIPT_DIR}/${f}" ]]; then
        cp "${SCRIPT_DIR}/${f}" "${SKILLS_DIR}/${f}"
        success "Installed skill file: ${f}"
    elif [[ -f "${SCRIPT_DIR}/skill/${f}" ]]; then
        cp "${SCRIPT_DIR}/skill/${f}" "${SKILLS_DIR}/${f}"
        success "Installed skill file: ${f}"
    else
        warn "Skill file not found locally: ${f} — you'll need to copy it manually to ${SKILLS_DIR}/"
    fi
done

# ── Copy compose files ───────────────────────────────────────
for f in Dockerfile docker-compose.yml; do
    if [[ -f "${SCRIPT_DIR}/${f}" ]]; then
        cp "${SCRIPT_DIR}/${f}" "${DEPLOY_DIR}/${f}"
    fi
done
success "Deploy files ready in ${DEPLOY_DIR}"

# ── Build Docker image ───────────────────────────────────────
header "Building Image"

log "Building openclaw-council:latest (pulls base image + installs Python deps)..."
log "This takes 2-4 minutes on first run. Subsequent runs use cache."

cd "$DEPLOY_DIR"

# Copy .env to deploy dir root for compose
cp "$ENV_FILE" "${DEPLOY_DIR}/.env"

docker compose build --pull 2>&1 | while IFS= read -r line; do
    echo "   $line"
done
success "Image built: openclaw-council:latest"

# ── OpenClaw onboarding ──────────────────────────────────────
header "OpenClaw Onboarding"

log "Running OpenClaw onboard wizard..."
log "(This sets up your messaging channel — Telegram, WhatsApp, etc.)"
echo ""

docker_compose run --rm openclaw-cli onboard

# ── Start the gateway ────────────────────────────────────────
header "Launch"

log "Starting OpenClaw gateway..."
docker_compose up -d openclaw-gateway
sleep 3

# Health check
if curl -sf http://localhost:18789/health >/dev/null 2>&1; then
    success "Gateway is up and healthy"
else
    warn "Gateway started but health endpoint not responding yet (may still be initializing)"
fi

# ── Dashboard URL ────────────────────────────────────────────
header "Dashboard"

DASHBOARD_URL=$(docker_compose run --rm openclaw-cli dashboard --no-open 2>/dev/null | grep -o 'http://[^ ]*' | head -1 || echo "http://localhost:18789/?token=${OPENCLAW_GATEWAY_TOKEN}")
success "Dashboard: ${DASHBOARD_URL}"

# ── Final summary ────────────────────────────────────────────
echo -e "
${BOLD}${GREEN}
  Council-Powered OpenClaw is live!
${NC}
  ${BOLD}Dashboard:${NC}    ${DASHBOARD_URL}
  ${BOLD}Deploy dir:${NC}   ${DEPLOY_DIR}
  ${BOLD}Skills dir:${NC}   ${SKILLS_DIR}
  ${BOLD}Workspace:${NC}    ${WORKSPACE}  <- PDFs land here

  ${BOLD}Usage (from your chat app):${NC}
    /council Should I use Postgres or MongoDB?

  ${BOLD}Useful commands:${NC}
    docker compose -f ${DEPLOY_DIR}/docker-compose.yml logs -f      # Live logs
    docker compose -f ${DEPLOY_DIR}/docker-compose.yml restart       # Restart
    docker compose -f ${DEPLOY_DIR}/docker-compose.yml down          # Stop
    ./setup.sh --update                                              # Update

  ${BOLD}Cost:${NC}
    Councilors: Free (200 req/day on OpenRouter free tier)
    Chairman (GPT-4o): ~\$0.02/query
    ~22 council queries/day on free councilor limit

  ${BOLD}Upgrade:${NC} Add credits at https://openrouter.ai for higher rate limits
"
