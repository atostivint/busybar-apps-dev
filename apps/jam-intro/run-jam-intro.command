#!/bin/bash
# jam-intro — drive the BUSY Bar animation from macOS, with bash only.
#
# Everything a normal session needs lives in this one file: no Python helper to
# call, no AppleScript to edit, no build step. The animation itself stays
# app.py, which is Python because that is the BUSY Bar app contract (`app.py`
# plus manifest.yaml, launched by the manager with --host); this file is only
# the launcher around it.
#
#   ./run-jam-intro.command                   run the pool scene (default)
#   ./run-jam-intro.command run fire          another effect
#   ./run-jam-intro.command run pool "STUNJAM"    pool scene, other title
#   ./run-jam-intro.command check             is the bar answering?
#   ./run-jam-intro.command effects           list the effects
#   ./run-jam-intro.command banners           list banners, show the active one
#   ./run-jam-intro.command use <name>        switch the banner
#   ./run-jam-intro.command help
#
# Environment: BUSYBAR_HOST (default 10.0.4.20, the USB address),
# BUSYBAR_TOKEN (Wi-Fi password), BUSYBAR_FPS (default 15).
set -u

HERE="$(cd "$(dirname "$0")" && pwd)"
BAR_HOST="${BUSYBAR_HOST:-10.0.4.20}"
BAR_TOKEN="${BUSYBAR_TOKEN:-}"
FPS="${BUSYBAR_FPS:-15}"
DEFAULT_EFFECT="pool"
DEFAULT_TITLE="OCTOJAM"
# effects that draw their own title, so no banner image is layered on top
TITLE_EFFECTS=" pool "
BANNERS_EFFECTS=" auto starfield plasma fire sparkle "

say() { printf '%s\n' "$1"; }
blank() { printf '\n'; }

bar_version() { curl -s -m 4 "http://${BAR_HOST}/api/version"; }
bar_name()    { curl -s -m 4 "http://${BAR_HOST}/api/name"; }

bar_answering() { bar_version 2>/dev/null | grep -q api_semver; }

explain_no_bar() {
    blank
    say "No BUSY Bar answering at http://${BAR_HOST}/api/version"
    say "  - over USB the bar is always 10.0.4.20: plug it in, wait a few seconds"
    say "  - over Wi-Fi pass its LAN address:"
    say "      BUSYBAR_HOST=192.168.59.42 BUSYBAR_TOKEN=the_password $0"
    say "    (Wi-Fi also needs HTTP API access enabled on the bar)"
    blank
}

cmd_check() {
    say "python3 : $(python3 -V 2>&1)"
    if bar_answering; then
        say "bar     : OK  $(bar_name) $(bar_version)"
        return 0
    fi
    say "bar     : no answer"
    explain_no_bar
    return 1
}

cmd_effects() {
    say "Effects:"
    say "  pool       a pool seen from above: title and Stunfest logo take turns (default)"
    say "  auto       cycles starfield -> plasma -> fire -> sparkle"
    say "  starfield  stars rushing at you"
    say "  plasma     drifting colour sheets"
    say "  fire       flames along the bottom"
    say "  sparkle    coloured sparks"
    blank
    say "pool draws its own title; the others carry a banner image on top."
    say "On the bar, in pool: turn the wheel to push the toys aside,"
    say "click the wheel to throw a toy in, press START to switch"
    say "between the title and the logo."
}

cmd_banners() {
    say "Banners in ./banners (used by every effect except pool):"
    if [ -d "$HERE/banners" ]; then
        found=0
        for file in "$HERE"/banners/*.png; do
            [ -e "$file" ] || continue
            printf '  %s\n' "$(basename "$file")"
            found=$((found + 1))
        done
        [ "$found" -eq 0 ] && say "  (none)"
    else
        say "  (no banners directory)"
    fi
    blank
    if [ -f "$HERE/banner.png" ]; then
        say "active : banner.png ($(wc -c < "$HERE/banner.png" | tr -d ' ') bytes)"
    else
        say "active : none"
    fi
}

cmd_use() {
    wanted="${1:-}"
    if [ -z "$wanted" ]; then
        say "usage: $0 use <name>"
        blank
        cmd_banners
        return 1
    fi
    source="$HERE/banners/$wanted"
    [ -f "$source" ] || source="$HERE/banners/$wanted.png"
    if [ ! -f "$source" ]; then
        say "no such banner: $wanted"
        blank
        cmd_banners
        return 1
    fi
    cp "$source" "$HERE/banner.png" || return 1
    say "banner.png  <-  $(basename "$source")"
}

cmd_run() {
    effect="${1:-$DEFAULT_EFFECT}"
    title="${2:-$DEFAULT_TITLE}"

    if ! command -v python3 >/dev/null 2>&1; then
        say "python3 is missing. Install the Apple command line tools:"
        say "  xcode-select --install        (or: brew install python)"
        return 1
    fi
    if ! bar_answering; then
        explain_no_bar
        return 1
    fi

    say "bar    : $(bar_name) $(bar_version)"
    say "effect : $effect    title: $title    fps: $FPS"
    say "stop with Control-C; the display is cleared on the way out"
    blank

    if [ -n "$BAR_TOKEN" ]; then
        export BUSYBAR_TOKEN="$BAR_TOKEN"
    fi

    case "$TITLE_EFFECTS" in
        *" $effect "*)
            exec python3 "$HERE/app.py" --host "$BAR_HOST" --effect "$effect" \
                --title "$title" --fps "$FPS" ;;
        *)
            say "note: '$effect' shows the banner image, not the title"
            blank
            exec python3 "$HERE/app.py" --host "$BAR_HOST" --effect "$effect" \
                --fps "$FPS" ;;
    esac
}

cmd_help() {
    sed -n '2,20p' "$0" | sed 's/^# \{0,1\}//'
}

case "${1:-run}" in
    run)      shift; cmd_run "${1:-$DEFAULT_EFFECT}" "${2:-$DEFAULT_TITLE}" ;;
    check)    cmd_check ;;
    effects)  cmd_effects ;;
    banners)  cmd_banners ;;
    use)      shift; cmd_use "${1:-}" ;;
    help|-h|--help) cmd_help ;;
    *)        cmd_run "${1:-$DEFAULT_EFFECT}" "${2:-$DEFAULT_TITLE}" ;;
esac
