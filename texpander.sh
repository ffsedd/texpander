
#!/usr/bin/env bash
# Description: Select and paste text snippets into the active X11 window.
# Dependencies: bash, find, sort, zenity, xsel, xdotool
# Supports: regular files, symlinks, and symlinked directories.

set -euo pipefail

readonly BASE_DIR="${TEXPANDER_DIR:-${HOME}/.texpander}"
readonly PASTE_DELAY="${TEXPANDER_PASTE_DELAY:-0.5}"
readonly RESTORE_CLIPBOARD="${TEXPANDER_RESTORE_CLIPBOARD:-1}"

target_window=""
clipboard_backup=""
had_clipboard=false

die() {
    printf 'texpander: %s\n' "$*" >&2
    exit 1
}

check_dependencies() {
    local cmd

    for cmd in find sort zenity xsel xdotool; do
        command -v "$cmd" >/dev/null 2>&1 ||
            die "Missing dependency: $cmd"
    done

    [[ -n "${DISPLAY:-}" ]] ||
        die "An X11 session is required."
}

get_target_window() {
    target_window=$(xdotool getwindowfocus) ||
        die "Cannot determine the active window."
}

find_snippets() {
    local -n result="$1"

    mkdir -p "$BASE_DIR"

    # Follow symlinks, including symlinked directories.
    # NUL delimiters preserve spaces, tabs, and special characters.
    mapfile -d '' -t result < <(
        find -L "$BASE_DIR" -type f -printf '%P\0' |
            sort -z
    )

    ((${#result[@]})) ||
        die "No snippets found in $BASE_DIR"
}

select_snippet() {
    local -n snippets="$1"
    local selection

    # Zenity uses newline-delimited output.
    # Reject filenames that cannot be represented unambiguously.
    local name
    for name in "${snippets[@]}"; do
        [[ "$name" != *$'\n'* ]] ||
            die "Newline in snippet filename is unsupported: $name"
    done

    selection=$(
        zenity --list \
            --title="Texpander" \
            --width=450 \
            --height=500 \
            --column="Abbreviation" \
            --print-column=1 \
            -- "${snippets[@]}"
    ) || return 1

    [[ -n "$selection" ]] || return 1

    printf '%s' "$selection"
}

backup_clipboard() {
    clipboard_backup=$(mktemp) ||
        die "Cannot create temporary clipboard file."

    if xsel --clipboard --output > "$clipboard_backup" 2>/dev/null; then
        had_clipboard=true
    fi
}

restore_clipboard() {
    [[ "$RESTORE_CLIPBOARD" == 1 ]] || return 0
    [[ "$had_clipboard" == true ]] || return 0
    [[ -f "$clipboard_backup" ]] || return 0

    xsel --clipboard --input < "$clipboard_backup" ||
        printf 'texpander: Could not restore clipboard\n' >&2
}

cleanup() {
    if [[ -n "$clipboard_backup" ]]; then
        rm -f -- "$clipboard_backup"
    fi
}

paste_snippet() {
    local path="$1"

    [[ -f "$path" ]] ||
        die "Snippet not found: $path"

    [[ -r "$path" ]] ||
        die "Snippet is not readable: $path"

    backup_clipboard

    # Redirect directly to preserve all bytes, including trailing newlines.
    xsel --clipboard --input < "$path" ||
        die "Failed to set clipboard."

    # Restore focus to the window active before Zenity appeared.
    xdotool windowactivate --sync "$target_window" ||
        die "Cannot activate target window."

    sleep 0.15

    # Clear held shortcut modifiers before pasting.
    xdotool key --clearmodifiers ctrl+v ||
        die "Failed to send paste shortcut."

    # Allow the target application time to consume clipboard contents.
    sleep "$PASTE_DELAY"

    restore_clipboard
}

main() {
    local snippets=()
    local name

    check_dependencies
    get_target_window
    find_snippets snippets

    # Canceling the dialog is normal, not an error.
    name=$(select_snippet snippets) || exit 0

    trap cleanup EXIT

    paste_snippet "$BASE_DIR/$name"
}

main "$@"
