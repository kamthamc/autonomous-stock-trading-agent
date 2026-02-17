#!/usr/bin/env bash
# ──────────────────────────────────────────────
# Autonomous Stock Trading Agent — Setup Script
# ──────────────────────────────────────────────
set -euo pipefail

PYTHON=${PYTHON:-python3}
VENV_DIR=".venv"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${GREEN}🤖 Autonomous Stock Trading Agent — Setup${NC}"
echo "────────────────────────────────────────"

# 1. Check Python version
echo -e "\n${YELLOW}1/5${NC} Checking Python version..."
PYTHON_VERSION=$($PYTHON --version 2>&1 | awk '{print $2}')
MAJOR=$(echo "$PYTHON_VERSION" | cut -d. -f1)
MINOR=$(echo "$PYTHON_VERSION" | cut -d. -f2)

if [ "$MAJOR" -lt 3 ] || ([ "$MAJOR" -eq 3 ] && [ "$MINOR" -lt 11 ]); then
    echo -e "${RED}❌ Python 3.11+ is required (found $PYTHON_VERSION)${NC}"
    echo "   Install Python 3.11+ from https://www.python.org/downloads/"
    exit 1
fi
echo -e "   ✅ Python $PYTHON_VERSION"

# 2. Create virtual environment
echo -e "\n${YELLOW}2/5${NC} Setting up virtual environment..."
if [ -d "$VENV_DIR" ]; then
    echo "   ✅ Virtual environment already exists at $VENV_DIR"
else
    $PYTHON -m venv "$VENV_DIR"
    echo "   ✅ Created virtual environment at $VENV_DIR"
fi

# Activate
source "$VENV_DIR/bin/activate"

# 3. Install dependencies
echo -e "\n${YELLOW}3/5${NC} Installing dependencies..."
pip install --upgrade pip -q
pip install -r requirements.txt -q
echo "   ✅ All dependencies installed"

# 4. Environment file
echo -e "\n${YELLOW}4/5${NC} Checking environment configuration..."
if [ -f ".env" ]; then
    echo "   ✅ .env file found"
else
    if [ -f ".env.example" ]; then
        cp .env.example .env
        echo "   ⚠️  Created .env from .env.example — please edit it with your credentials"
    else
        echo -e "   ${RED}❌ No .env or .env.example found${NC}"
    fi
fi

# 5. Verify imports
echo -e "\n${YELLOW}5/5${NC} Verifying installation..."
$PYTHON -c "
import sys
errors = []
modules = [
    ('pydantic_settings', 'pydantic-settings'),
    ('sqlmodel', 'sqlmodel'),
    ('structlog', 'structlog'),
    ('openai', 'openai'),
    ('yfinance', 'yfinance'),

    ('exchange_calendars', 'exchange_calendars'),
    ('pandas_ta', 'pandas_ta'),
    ('plotly', 'plotly'),
]
for mod, pkg in modules:
    try:
        __import__(mod)
    except ImportError:
        errors.append(pkg)

if errors:
    print(f'   ❌ Missing packages: {', '.join(errors)}')
    sys.exit(1)
else:
    print('   ✅ All core imports verified')
"

echo ""
echo -e "${GREEN}────────────────────────────────────────${NC}"
echo -e "${GREEN}✅ Setup complete!${NC}"
echo ""
echo "  Quick start:"
echo "    source .venv/bin/activate"
echo "    python main.py              # Start the trading agent"
echo "    python dashboard_api.py      # Launch the dashboard backend"
echo ""
echo "  📖 See docs/README.md for full documentation"
echo "  ⚠️  Edit .env with your API keys before running"
echo ""
