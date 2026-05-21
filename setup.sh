#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR="$PROJECT_ROOT/backend"
FRONTEND_DIR="$PROJECT_ROOT/frontend"

echo "=========================================="
echo "  PhoenixLoop Setup"
echo "=========================================="

# Check prerequisites
echo ""
echo "[1/8] Checking prerequisites..."

# Find a stable Python (3.11-3.13). Python 3.14 has ensurepip issues.
PYTHON_BIN=""
for candidate in python3.13 python3.12 python3.11; do
    if command -v "$candidate" &> /dev/null; then
        PYTHON_BIN="$candidate"
        break
    fi
done
if [ -z "$PYTHON_BIN" ]; then
    if command -v python3 &> /dev/null; then
        PYTHON_BIN="python3"
    else
        echo "ERROR: python3 not found. Install Python 3.11+"
        exit 1
    fi
fi

PYTHON_VERSION=$($PYTHON_BIN -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
echo "  Python: $PYTHON_VERSION ($PYTHON_BIN)"

if ! command -v node &> /dev/null; then
    echo "ERROR: node not found. Install Node.js 18+"
    exit 1
fi

NODE_VERSION=$(node --version)
echo "  Node: $NODE_VERSION"

if ! command -v npm &> /dev/null; then
    echo "ERROR: npm not found."
    exit 1
fi

# Create backend venv
echo ""
echo "[2/8] Creating Python virtual environment at backend/.venv..."
cd "$BACKEND_DIR"
$PYTHON_BIN -m venv .venv
source .venv/bin/activate
echo "  venv created and activated"

# Install backend dependencies
echo ""
echo "[3/8] Installing backend dependencies..."
pip install --upgrade pip -q
pip install -r requirements.txt -q
echo "  Backend dependencies installed"

deactivate

# Install frontend dependencies
echo ""
echo "[4/8] Installing frontend dependencies..."
cd "$FRONTEND_DIR"
npm install --silent
echo "  Frontend dependencies installed"

# Create .env
cd "$PROJECT_ROOT"
echo ""
echo "[5/8] Setting up environment..."
if [ ! -f .env ]; then
    cp .env.example .env
    echo "  Created .env from .env.example"
    echo "  >>> IMPORTANT: Edit .env with your API keys before running <<<"
else
    echo "  .env already exists, skipping"
fi

# Create data directories
echo ""
echo "[6/8] Creating data directories..."
mkdir -p data/policies data/tickets
echo "  Data directories created"

# Create SQLite database
echo ""
echo "[7/8] Initializing database..."
cd "$BACKEND_DIR"
source .venv/bin/activate
python -c "from src.db import init_db; import asyncio; asyncio.run(init_db('phoenixloop.db'))"
echo "  Database initialized"

# Install pre-commit hooks
echo ""
echo "[8/8] Installing pre-commit hooks..."
cd "$PROJECT_ROOT"
pre-commit install
deactivate
echo "  Pre-commit hooks installed"

echo ""
echo "=========================================="
echo "  Setup Complete!"
echo "=========================================="
echo ""
echo "BEFORE RUNNING — Get your API keys:"
echo ""
echo "  1. GOOGLE_API_KEY:"
echo "     → https://aistudio.google.com/apikey"
echo "     → Create API Key → copy into .env"
echo ""
echo "  2. PHOENIX_API_KEY + PHOENIX_BASE_URL:"
echo "     → https://app.phoenix.arize.com"
echo "     → Sign up → Create space → Settings → API Keys"
echo "     → Copy key and space URL into .env"
echo ""
echo "  3. Edit .env with your keys:"
echo "     \$ nano .env"
echo ""
echo "TO RUN THE APP:"
echo ""
echo "  Backend (terminal 1):"
echo "    cd $BACKEND_DIR"
echo "    source .venv/bin/activate"
echo "    uvicorn src.main:app --reload --port 8000"
echo ""
echo "  Frontend (terminal 2):"
echo "    cd $FRONTEND_DIR"
echo "    npm run dev"
echo ""
echo "  Then open: http://localhost:3000"
echo "=========================================="
