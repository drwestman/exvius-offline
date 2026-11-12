#!/bin/bash
export PATH="/opt/homebrew/bin:$HOME/.local/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH"
SCRIPT_DIR="$(cd -- "$(dirname -- "$0")" && pwd)"
DATA_DIR="${FFBE_IOS_DATA:-$SCRIPT_DIR/data}"
# A release manifest alone is not an installed game-data tree.
if [ -z "${FFBE_IOS_DATA:-}" ] &&
   [ ! -e "$DATA_DIR/ios-current.json" ] && [ ! -L "$DATA_DIR/ios-current.json" ] &&
   [ ! -d "$DATA_DIR/static" ] && [ ! -d "$DATA_DIR/client" ] &&
   [ -f "$SCRIPT_DIR/source/out/browser-data/client/shared_prefs/gamedata.xml" ]; then
    DATA_DIR="$SCRIPT_DIR/source/out/browser-data"
fi
python3 "$SCRIPT_DIR/source/exvius/macos_ios_server.py" start --data "$DATA_DIR" "$@"
result=$?
if [ "$result" -ne 0 ]; then
    printf '\nGameplay needs an initialized iOS campaign and prepared assets.\n'
    printf 'Setup instructions: %s/source/ios_server/README.md\n' "$SCRIPT_DIR"
    printf '\nPress Return to close this window.\n'
    read -r _
fi
exit "$result"
