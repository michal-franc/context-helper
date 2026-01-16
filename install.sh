#!/bin/bash
# Install context-helper plugin for Claude Code

set -e

INSTALL_DIR="${HOME}/.claude/plugins/context-helper"

echo "Installing context-helper to $INSTALL_DIR"

# Create directory
mkdir -p "$INSTALL_DIR"

# Copy files
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cp "$SCRIPT_DIR/analyze_instructions.py" "$INSTALL_DIR/"
cp "$SCRIPT_DIR/statusline.sh" "$INSTALL_DIR/"

# Make executable
chmod +x "$INSTALL_DIR"/*.py "$INSTALL_DIR"/*.sh

echo "Files installed."
echo ""
echo "Add the following to ~/.claude/settings.json:"
echo ""
echo '  "statusLine": {'
echo '    "type": "command",'
echo "    \"command\": \"$INSTALL_DIR/statusline.sh\","
echo '    "padding": 0'
echo '  }'
echo ""
echo "Then restart Claude Code."
