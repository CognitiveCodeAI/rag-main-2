#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────────────
# NPR RAG — First-time setup script for Linux / macOS
#
# Usage:
#   ./setup.sh                         # Full setup
#   ./setup.sh --skip-docker           # Skip docker compose (remote infra)
#   ./setup.sh --openai-key=sk-...     # Non-interactive API key
#
# Every step is idempotent — safe to re-run.
# ──────────────────────────────────────────────────────────────────────────────
set -euo pipefail

# ── Paths ────────────────────────────────────────────────────────────────────
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
FRONTEND_DIR="$ROOT_DIR/frontend"
ENV_EXAMPLE="$BACKEND_DIR/.env.example"
ENV_FILE="$BACKEND_DIR/.env"
VENV_DIR="$BACKEND_DIR/venv"
VENV_PYTHON="$VENV_DIR/bin/python"
REQUIREMENTS="$BACKEND_DIR/requirements.txt"
NODE_MODULES="$FRONTEND_DIR/node_modules"

# ── Arguments ────────────────────────────────────────────────────────────────
SKIP_DOCKER=false
OPENAI_KEY=""

for arg in "$@"; do
    case $arg in
        --skip-docker)  SKIP_DOCKER=true ;;
        --openai-key=*) OPENAI_KEY="${arg#*=}" ;;
        *)
            echo "Unknown argument: $arg"
            echo "Usage: ./setup.sh [--skip-docker] [--openai-key=sk-...]"
            exit 1
            ;;
    esac
done

# ── Helpers ──────────────────────────────────────────────────────────────────
step()  { printf '\n\033[36m[%s/8] %s\033[0m\n' "$1" "$2"; }
ok()    { printf '  \033[32m[OK]\033[0m %s\n' "$1"; }
warn()  { printf '  \033[33m[WARN]\033[0m %s\n' "$1"; }
err()   { printf '  \033[31m[ERROR]\033[0m %s\n' "$1"; }
info()  { printf '  %s\n' "$1"; }

# Detect docker compose command (v2 plugin vs standalone v1)
get_docker_compose() {
    if docker compose version &>/dev/null; then
        echo "docker compose"
    elif docker-compose version &>/dev/null; then
        echo "docker-compose"
    else
        echo ""
    fi
}

# Detect python command (python3 preferred, then python)
get_python_cmd() {
    if command -v python3 &>/dev/null; then
        local ver
        ver=$(python3 --version 2>&1 | awk '{print $2}' | cut -d. -f1-2)
        echo "python3"
    elif command -v python &>/dev/null; then
        local ver
        ver=$(python --version 2>&1)
        if [[ "$ver" == *"Python 3"* ]]; then
            echo "python"
        else
            echo ""
        fi
    else
        echo ""
    fi
}

# Test minimum version: test_min_version "3.10" 3 10
test_min_version() {
    local ver="$1" major_min="$2" minor_min="$3"
    local major minor
    major=$(echo "$ver" | cut -d. -f1)
    minor=$(echo "$ver" | cut -d. -f2)
    if (( major > major_min )) || { (( major == major_min )) && (( minor >= minor_min )); }; then
        return 0
    fi
    return 1
}

# sed -i that works on both macOS and Linux
sed_inplace() {
    if [[ "$(uname)" == "Darwin" ]]; then
        sed -i '' "$@"
    else
        sed -i "$@"
    fi
}

# ── Banner ───────────────────────────────────────────────────────────────────
echo ""
echo "========================================================"
printf '\033[36m  NPR — Near-Perfect RAG  |  First-Time Setup\033[0m\n'
echo "========================================================"

# ═════════════════════════════════════════════════════════════════════════════
# Step 1: Check prerequisites
# ═════════════════════════════════════════════════════════════════════════════
step 1 "Checking prerequisites"
errors=()

# Docker
if [[ "$SKIP_DOCKER" == false ]]; then
    dc=$(get_docker_compose)
    if [[ -z "$dc" ]]; then
        errors+=("Docker not found. Install Docker: https://docs.docker.com/get-docker/")
    else
        ok "Docker Compose: $dc"
    fi
else
    info "Docker check skipped (--skip-docker)"
fi

# Python
PYTHON_CMD=$(get_python_cmd)
if [[ -z "$PYTHON_CMD" ]]; then
    errors+=("Python 3.10+ not found. Install from https://www.python.org/downloads/")
else
    py_ver=$($PYTHON_CMD --version 2>&1 | awk '{print $2}' | cut -d. -f1-2)
    if ! test_min_version "$py_ver" 3 10; then
        errors+=("Python 3.10+ required, found $py_ver")
    else
        ok "Python: $py_ver (command: $PYTHON_CMD)"
    fi
fi

# Node.js
if command -v node &>/dev/null; then
    node_ver=$(node --version | tr -d 'v' | cut -d. -f1-2)
    if ! test_min_version "$node_ver" 18 0; then
        errors+=("Node.js 18+ required, found $node_ver. Install from https://nodejs.org/")
    else
        ok "Node.js: $node_ver"
    fi
else
    errors+=("Node.js not found. Install from https://nodejs.org/")
fi

# npm
if command -v npm &>/dev/null; then
    npm_ver=$(npm --version)
    ok "npm: $npm_ver"
else
    errors+=("npm not found. It should come with Node.js — reinstall Node.")
fi

if [[ ${#errors[@]} -gt 0 ]]; then
    echo ""
    for e in "${errors[@]}"; do err "$e"; done
    echo ""
    err "Fix the above issues and re-run ./setup.sh"
    exit 1
fi

# ═════════════════════════════════════════════════════════════════════════════
# Step 2: Start infrastructure
# ═════════════════════════════════════════════════════════════════════════════
step 2 "Starting infrastructure (Docker)"

if [[ "$SKIP_DOCKER" == true ]]; then
    info "Skipped (--skip-docker flag)"
else
    dc=$(get_docker_compose)
    info "Running: $dc up -d"
    $dc -f "$ROOT_DIR/docker-compose.yml" up -d

    # Poll container health
    containers=("rag-postgres" "rag-milvus" "rag-minio" "rag-redis")
    timeout=180
    interval=5

    info "Waiting for containers to become healthy (timeout: ${timeout}s)..."

    for ctr in "${containers[@]}"; do
        elapsed=0
        healthy=false
        while [[ "$healthy" == false ]] && (( elapsed < timeout )); do
            status=$(docker inspect --format='{{.State.Health.Status}}' "$ctr" 2>/dev/null || echo "not_found")
            if [[ "$status" == "healthy" ]]; then
                healthy=true
                ok "$ctr is healthy"
                break
            fi
            sleep "$interval"
            elapsed=$((elapsed + interval))
        done
        if [[ "$healthy" == false ]]; then
            warn "$ctr did not become healthy within ${timeout}s (may still be starting)"
        fi
    done
fi

# ═════════════════════════════════════════════════════════════════════════════
# Step 3: Configure environment (.env)
# ═════════════════════════════════════════════════════════════════════════════
step 3 "Configuring environment"

if [[ -f "$ENV_FILE" ]]; then
    ok ".env already exists — skipping copy"
else
    if [[ ! -f "$ENV_EXAMPLE" ]]; then
        err ".env.example not found at $ENV_EXAMPLE"
        exit 1
    fi
    cp "$ENV_EXAMPLE" "$ENV_FILE"
    ok "Copied .env.example -> .env"
fi

# Check / set OPENAI_API_KEY
placeholder="your-openai-api-key-here"
if grep -qE "OPENAI_API_KEY\s*=\s*${placeholder}" "$ENV_FILE" || grep -qE "OPENAI_API_KEY\s*=\s*$" "$ENV_FILE"; then
    if [[ -n "$OPENAI_KEY" ]]; then
        sed_inplace "s|OPENAI_API_KEY=.*|OPENAI_API_KEY=$OPENAI_KEY|" "$ENV_FILE"
        ok "Set OPENAI_API_KEY from --openai-key parameter"
    else
        warn "OPENAI_API_KEY is still the placeholder value."
        printf '  Enter your OpenAI API key (or press Enter to skip): '
        read -r key
        if [[ -n "$key" ]]; then
            sed_inplace "s|OPENAI_API_KEY=.*|OPENAI_API_KEY=$key|" "$ENV_FILE"
            ok "OPENAI_API_KEY updated"
        else
            warn "Skipped — you'll need to edit backend/.env before embeddings work"
        fi
    fi
else
    ok "OPENAI_API_KEY is already configured"
fi

# ═════════════════════════════════════════════════════════════════════════════
# Step 4: Python virtual environment
# ═════════════════════════════════════════════════════════════════════════════
step 4 "Setting up Python virtual environment"

if [[ -f "$VENV_PYTHON" ]]; then
    ok "venv already exists at $VENV_DIR"
else
    info "Creating venv..."
    $PYTHON_CMD -m venv "$VENV_DIR"
    ok "Created venv at $VENV_DIR"
fi

info "Installing Python dependencies..."
"$VENV_PYTHON" -m pip install --upgrade pip --quiet 2>&1 | tail -n 0 || true
"$VENV_PYTHON" -m pip install -r "$REQUIREMENTS" --quiet
ok "Python dependencies installed"

# ═════════════════════════════════════════════════════════════════════════════
# Step 5: Database / collection / bucket setup
# ═════════════════════════════════════════════════════════════════════════════
step 5 "Running database setup (migrations, collections, buckets)"

cd "$BACKEND_DIR"
"$VENV_PYTHON" -m scripts.setup.setup_all || warn "setup_all.py reported issues (see above)"
cd "$ROOT_DIR"

# ═════════════════════════════════════════════════════════════════════════════
# Step 6: Frontend dependencies
# ═════════════════════════════════════════════════════════════════════════════
step 6 "Installing frontend dependencies"

if [[ -d "$NODE_MODULES" ]]; then
    ok "node_modules already exists — skipping npm install"
else
    info "Running npm install in frontend/..."
    cd "$FRONTEND_DIR"
    npm install
    cd "$ROOT_DIR"
    ok "Frontend dependencies installed"
fi

# ═════════════════════════════════════════════════════════════════════════════
# Step 7: Verify connections
# ═════════════════════════════════════════════════════════════════════════════
step 7 "Verifying service connections"

cd "$BACKEND_DIR"
"$VENV_PYTHON" -m scripts.setup.verify_connections || warn "Some connections failed (see above)"
cd "$ROOT_DIR"

# ═════════════════════════════════════════════════════════════════════════════
# Step 8: Summary
# ═════════════════════════════════════════════════════════════════════════════
step 8 "Setup complete!"

echo ""
printf '\033[32m========================================================\033[0m\n'
printf '\033[32m  Setup finished. Next steps:\033[0m\n'
printf '\033[32m========================================================\033[0m\n'
echo ""
echo "  Start everything with:"
echo "    python run.py"
echo ""
echo "  Or start services manually on Linux/macOS:"
echo ""
printf '\033[33m  Terminal 1 (Backend):\033[0m\n'
echo "    cd backend && source venv/bin/activate"
echo "    uvicorn main:app --reload --host 0.0.0.0 --port 8000"
echo ""
printf '\033[33m  Terminal 2 (Celery worker):\033[0m\n'
echo "    cd backend && source venv/bin/activate"
echo "    celery -A app.worker worker --loglevel=info --pool=solo"
echo ""
printf '\033[33m  Terminal 3 (Frontend):\033[0m\n'
echo "    cd frontend && npm run dev"
echo ""
echo "  Then open:"
printf '\033[33m    http://localhost:3000          \033[0m(App UI)\n'
printf '\033[33m    http://localhost:8000/docs     \033[0m(API docs)\n'
echo ""
echo "  Upload a document and start chatting!"
echo ""
