#!/bin/bash
set -u
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

PYTHON_BIN="$ROOT_DIR/.venv-ios/bin/python"
if [ ! -x "$PYTHON_BIN" ]; then
    PYTHON_BIN="python3"
fi
SERVER_CLI="$ROOT_DIR/source/exvius/macos_ios_server.py"

START_SERVER=1
EXTRA_ARGS=()
for arg in "$@"; do
    if [ "$arg" = "--no-start" ]; then
        START_SERVER=0
    else
        EXTRA_ARGS+=("$arg")
    fi
done

pause_if_interactive() {
    if [ -t 0 ]; then
        printf '\nPress Return to close this window.\n'
        read -r _
    fi
}

printf '==> Stopping running iOS server (if any)...\n'
"$PYTHON_BIN" "$SERVER_CLI" stop ${EXTRA_ARGS[@]+"${EXTRA_ARGS[@]}"}
result=$?
if [ "$result" -ne 0 ]; then
    printf '\nFailed to stop the running iOS server.\n' >&2
    pause_if_interactive
    exit "$result"
fi

printf '\n==> Preparing iOS native data (--vortex-art --sounds)...\n'
"$PYTHON_BIN" "$SERVER_CLI" prepare-data --data "$DATA_DIR" --vortex-art --sounds ${EXTRA_ARGS[@]+"${EXTRA_ARGS[@]}"}
result=$?
if [ "$result" -ne 0 ]; then
    printf '\nData preparation failed.\n' >&2
    pause_if_interactive
    exit "$result"
fi

printf '\n==> Verifying prepared iOS native data...\n'
"$PYTHON_BIN" "$SERVER_CLI" verify-data --data "$DATA_DIR" ${EXTRA_ARGS[@]+"${EXTRA_ARGS[@]}"}
result=$?
if [ "$result" -ne 0 ]; then
    printf '\nData verification failed.\n' >&2
    pause_if_interactive
    exit "$result"
fi

if [ "$START_SERVER" -eq 0 ]; then
    printf '\nPrepared and verified iOS data (--no-start requested).\n'
    exit 0
fi

printf '\n==> Starting iOS gameplay server...\n'
"$PYTHON_BIN" "$SERVER_CLI" start --data "$DATA_DIR" ${EXTRA_ARGS[@]+"${EXTRA_ARGS[@]}"}
result=$?
if [ "$result" -ne 0 ]; then
    printf '\nFailed to start the iOS gameplay server.\n' >&2
    pause_if_interactive
fi
exit "$result"
