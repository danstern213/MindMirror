#!/bin/bash
#
# Create an API key for the file sync service
#
# Usage: ./create_api_key.sh <jwt_token>
#
# To get your JWT token:
# 1. Log into your Big Brain web app
# 2. Open browser DevTools (F12)
# 3. Go to Application > Local Storage > your-app-url
# 4. Copy the value of 'sb-xxxxx-auth-token' (the access_token field inside it)
#

set -e

API_URL="${SYNC_API_URL:-https://mindmirror-production.up.railway.app/api/v1}"

if [ -z "$1" ]; then
    echo "Usage: $0 <jwt_token>"
    echo ""
    echo "To get your JWT token:"
    echo "  1. Log into your Big Brain web app in a browser"
    echo "  2. Open DevTools (F12 or Cmd+Option+I)"
    echo "  3. Go to Application tab > Local Storage"
    echo "  4. Find the key that looks like 'sb-xxxxx-auth-token'"
    echo "  5. Copy the 'access_token' value from inside the JSON"
    echo ""
    exit 1
fi

JWT_TOKEN="$1"

echo "Creating API key for File Sync service..."
echo "API URL: $API_URL"
echo ""

RESPONSE=$(curl -s -X POST "${API_URL}/api-keys" \
    -H "Authorization: Bearer ${JWT_TOKEN}" \
    -H "Content-Type: application/json" \
    -d '{"name": "File Sync Service"}')

# Check for error
if echo "$RESPONSE" | grep -q '"detail"'; then
    echo "Error creating API key:"
    echo "$RESPONSE" | python3 -m json.tool 2>/dev/null || echo "$RESPONSE"
    exit 1
fi

# Extract the key
API_KEY=$(echo "$RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin)['key'])" 2>/dev/null)

if [ -z "$API_KEY" ]; then
    echo "Failed to extract API key from response:"
    echo "$RESPONSE"
    exit 1
fi

echo "╔════════════════════════════════════════════════════════════════════╗"
echo "║                    API Key Created Successfully!                    ║"
echo "╚════════════════════════════════════════════════════════════════════╝"
echo ""
echo "Your API key (save this - it won't be shown again):"
echo ""
echo "    $API_KEY"
echo ""
echo "To set up file sync, run:"
echo ""
echo "    export SYNC_API_KEY='$API_KEY'"
echo "    ./setup.sh"
echo ""
