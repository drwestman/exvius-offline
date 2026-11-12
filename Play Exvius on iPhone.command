#!/bin/bash
export PATH="/opt/homebrew/bin:$HOME/.local/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH"
SCRIPT_DIR="$(cd -- "$(dirname -- "$0")" && pwd)"
python3 "$SCRIPT_DIR/source/exvius/macos_ios_server.py" start --data "${FFBE_IOS_DATA:-$SCRIPT_DIR/data}" "$@"
result=$?
if [ "$result" -ne 0 ]; then
    printf '\nGameplay needs an initialized iOS campaign and prepared assets.\n'
    printf 'Setup instructions: %s/source/ios_server/README.md\n' "$SCRIPT_DIR"
    printf '\nPress Return to close this window.\n'
    read -r _
fi
exit "$result"
