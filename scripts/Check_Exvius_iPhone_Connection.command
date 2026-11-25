#!/bin/bash
export PATH="/opt/homebrew/bin:$HOME/.local/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH"
SCRIPT_DIR="$(cd -- "$(dirname -- "$0")" && pwd)"
python3 "$SCRIPT_DIR/source/exvius/macos_ios_server.py" serve
result=$?
if [ "$result" -ne 0 ]; then
    printf '\nFirst-time setup: python3 "%s/source/exvius/macos_ios_server.py" setup\n' "$SCRIPT_DIR"
    printf '\nPress Return to close this window.\n'
    read -r _
fi
exit "$result"
