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

python3 "$ROOT_DIR/source/exvius/macos_ios_server.py" check-update --data "$DATA_DIR" --summary "$@" >/dev/null
check_result=$?
if [ "$check_result" -eq 2 ]; then
    printf '\nUpdate now? [Y/n] ' >&2
    if ! read -r answer; then
        answer="n"
    fi
    case "$answer" in
        ""|[yY]|[yY][eE][sS])
            python3 "$ROOT_DIR/source/exvius/macos_ios_server.py" update --data "$DATA_DIR" "$@" >/dev/null
            update_result=$?
            if [ "$update_result" -ne 0 ]; then
                printf '\nUpdate failed.\n' >&2
                if [ -t 0 ]; then
                    printf '\nPress Return to close this window.\n'
                    read -r _
                fi
                exit "$update_result"
            fi
            ;;
        *)
            printf '\nUpdate skipped. To update manually, run:\n' >&2
            printf '  "%s/Update_Exvius_iOS_Data.command"\n' "$SCRIPT_DIR" >&2
            printf 'or:\n' >&2
            printf '  python3 "%s/source/exvius/macos_ios_server.py" update --data "%s"\n' "$ROOT_DIR" "$DATA_DIR" >&2
            if [ -t 0 ]; then
                printf '\nPress Return to close this window.\n'
                read -r _
            fi
            exit 0
            ;;
    esac
elif [ "$check_result" -ne 0 ]; then
    printf '\nGameplay needs an initialized iOS campaign and prepared assets.\n' >&2
    printf 'Setup instructions: %s/source/ios_server/README.md\n' "$ROOT_DIR" >&2
    if [ -t 0 ]; then
        printf '\nPress Return to close this window.\n'
        read -r _
    fi
    exit "$check_result"
fi

python3 "$ROOT_DIR/source/exvius/macos_ios_server.py" start --data "$DATA_DIR" "$@"
result=$?
if [ "$result" -ne 0 ]; then
    printf '\nGameplay needs an initialized iOS campaign and prepared assets.\n'
    printf 'Setup instructions: %s/source/ios_server/README.md\n' "$ROOT_DIR"
    printf '\nPress Return to close this window.\n'
    read -r _
fi
exit "$result"
