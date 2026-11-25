#!/bin/bash
# Finder does not inherit your terminal's PATH.
export PATH="/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH"
SCRIPT_DIR="$(cd -- "$(dirname -- "$0")" && pwd)"
python3 "$SCRIPT_DIR/source/exvius/macos_emulator.py" launch
result=$?
if [ "$result" -ne 0 ]; then
    printf '\nPress Return to close this window.\n'
    read -r _
fi
exit "$result"
