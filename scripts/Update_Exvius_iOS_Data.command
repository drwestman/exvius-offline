#!/bin/bash
export PATH="/opt/homebrew/bin:$HOME/.local/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH"
SCRIPT_DIR="$(cd -- "$(dirname -- "$0")" && pwd)"
ROOT_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd)"
DATA_DIR="${FFBE_IOS_DATA:-$ROOT_DIR/data}"
# A release manifest alone is not an installed game-data tree.
if [ -z "${FFBE_IOS_DATA:-}" ] &&
   [ ! -e "$DATA_DIR/ios-current.json" ] && [ ! -L "$DATA_DIR/ios-current.json" ] &&
   [ ! -d "$DATA_DIR/static" ] && [ ! -d "$DATA_DIR/client" ] &&
   [ -f "$ROOT_DIR/source/out/browser-data/client/shared_prefs/gamedata.xml" ]; then
    DATA_DIR="$ROOT_DIR/source/out/browser-data"
fi
python3 "$ROOT_DIR/source/exvius/macos_ios_server.py" update --data "$DATA_DIR" "$@"
result=$?
if [ -t 0 ]; then
    printf '\nPress Return to close this window.\n'
    read -r _
fi
exit "$result"
