#!/bin/bash
#
# Big Brain File Sync Setup Script
# This script helps you set up the file sync service to run automatically on macOS.
#

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║         Big Brain File Sync - Setup Script                   ║${NC}"
echo -e "${BLUE}╚══════════════════════════════════════════════════════════════╝${NC}"
echo ""

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLIST_TEMPLATE="${SCRIPT_DIR}/com.bigbrain.filesync.plist"
PLIST_DEST="$HOME/Library/LaunchAgents/com.bigbrain.filesync.plist"

# Check if Python 3 is installed
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}Error: Python 3 is not installed.${NC}"
    echo "Please install Python 3 first: brew install python3"
    exit 1
fi

PYTHON_PATH=$(which python3)
echo -e "${GREEN}✓${NC} Found Python 3 at: $PYTHON_PATH"

# Step 1: Install dependencies
echo ""
echo -e "${YELLOW}Step 1: Installing Python dependencies...${NC}"
pip3 install watchdog httpx --quiet
echo -e "${GREEN}✓${NC} Dependencies installed"

# Step 2: Get configuration from user
echo ""
echo -e "${YELLOW}Step 2: Configuration${NC}"
echo ""

# Watch directory
DEFAULT_WATCH_DIR="/Users/danstern/Documents/New Roam"
read -p "Watch directory [$DEFAULT_WATCH_DIR]: " WATCH_DIR
WATCH_DIR=${WATCH_DIR:-$DEFAULT_WATCH_DIR}

if [ ! -d "$WATCH_DIR" ]; then
    echo -e "${RED}Error: Directory does not exist: $WATCH_DIR${NC}"
    exit 1
fi
echo -e "${GREEN}✓${NC} Watch directory: $WATCH_DIR"

# API URL
echo ""
echo "Enter your backend API URL (e.g., https://your-app.herokuapp.com/api/v1)"
read -p "API URL: " API_URL

if [ -z "$API_URL" ]; then
    echo -e "${RED}Error: API URL is required${NC}"
    exit 1
fi
echo -e "${GREEN}✓${NC} API URL: $API_URL"

# API Key
echo ""
echo -e "${BLUE}To get an API key, you need to:${NC}"
echo "  1. Log into your Big Brain web app"
echo "  2. Go to Settings > API Keys"
echo "  3. Create a new key named 'File Sync'"
echo "  4. Copy the key (it's only shown once!)"
echo ""
read -p "API Key (ak_...): " API_KEY

if [ -z "$API_KEY" ] || [[ ! "$API_KEY" == ak_* ]]; then
    echo -e "${RED}Error: Invalid API key. It should start with 'ak_'${NC}"
    exit 1
fi
echo -e "${GREEN}✓${NC} API Key: ${API_KEY:0:8}..."

# Step 3: Create the launchd plist
echo ""
echo -e "${YELLOW}Step 3: Creating launchd configuration...${NC}"

mkdir -p "$HOME/Library/LaunchAgents"

cat > "$PLIST_DEST" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.bigbrain.filesync</string>

    <key>ProgramArguments</key>
    <array>
        <string>${PYTHON_PATH}</string>
        <string>-m</string>
        <string>file_sync.watcher</string>
    </array>

    <key>WorkingDirectory</key>
    <string>${SCRIPT_DIR}</string>

    <key>EnvironmentVariables</key>
    <dict>
        <key>SYNC_WATCH_DIR</key>
        <string>${WATCH_DIR}</string>

        <key>SYNC_API_URL</key>
        <string>${API_URL}</string>

        <key>SYNC_API_KEY</key>
        <string>${API_KEY}</string>

        <key>SYNC_STATE_DB</key>
        <string>${HOME}/.file_sync_state.db</string>

        <key>SYNC_DEBOUNCE_DELAY</key>
        <string>10</string>
    </dict>

    <key>RunAtLoad</key>
    <true/>

    <key>KeepAlive</key>
    <dict>
        <key>SuccessfulExit</key>
        <false/>
    </dict>

    <key>ThrottleInterval</key>
    <integer>30</integer>

    <key>StandardOutPath</key>
    <string>/tmp/bigbrain-filesync.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/bigbrain-filesync.error.log</string>
</dict>
</plist>
EOF

echo -e "${GREEN}✓${NC} Created: $PLIST_DEST"

# Step 4: Load the service
echo ""
echo -e "${YELLOW}Step 4: Starting the service...${NC}"

# Unload if already running
launchctl unload "$PLIST_DEST" 2>/dev/null || true

# Load the new configuration
launchctl load "$PLIST_DEST"

echo -e "${GREEN}✓${NC} Service started!"

# Step 5: Verify
echo ""
echo -e "${YELLOW}Step 5: Verifying...${NC}"
sleep 2

if launchctl list | grep -q "com.bigbrain.filesync"; then
    echo -e "${GREEN}✓${NC} Service is running!"
else
    echo -e "${RED}✗${NC} Service may not be running. Check the logs."
fi

# Summary
echo ""
echo -e "${GREEN}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║                    Setup Complete!                           ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo "The file sync service is now running and will start automatically on login."
echo ""
echo -e "${BLUE}Useful commands:${NC}"
echo "  View logs:        tail -f /tmp/bigbrain-filesync.log"
echo "  View errors:      tail -f /tmp/bigbrain-filesync.error.log"
echo "  Stop service:     launchctl unload ~/Library/LaunchAgents/com.bigbrain.filesync.plist"
echo "  Start service:    launchctl load ~/Library/LaunchAgents/com.bigbrain.filesync.plist"
echo "  Check status:     launchctl list | grep bigbrain"
echo ""
echo -e "${BLUE}Watch directory:${NC} $WATCH_DIR"
echo -e "${BLUE}State database:${NC}  ~/.file_sync_state.db"
echo ""
