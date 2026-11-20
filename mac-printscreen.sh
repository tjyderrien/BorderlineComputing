#!/usr/bin/env bash
# Make the Print Screen key of a PC keyboard take screenshots on macOS, as on Windows.
#
#   Print Screen          whole screen          (macOS: Cmd+Shift+3)
#   Shift + Print Screen  an area, or an app's window: drag a rectangle, or press
#                         Space and click a window     (macOS: Cmd+Shift+4)
#
# Screenshots land where macOS puts them (the Desktop by default; Cmd+Shift+5 → Options to change).
#
# Usage:
#   ./mac-printscreen.sh            # add the two rules to Karabiner-Elements
#   ./mac-printscreen.sh --remove   # take them out again
#
# Needs Karabiner-Elements (https://karabiner-elements.pqrs.org), which turns the key into something
# macOS understands. The rules go into the selected profile of ~/.config/karabiner/karabiner.json,
# which Karabiner reloads by itself. A copy of the file is kept next to it first. Running it twice
# does not add the rules twice.

set -eu

CONFIG="${KARABINER_CONFIG:-$HOME/.config/karabiner/karabiner.json}"
ACTION="add"
case "${1:-}" in
    "") ;;
    --remove) ACTION="remove" ;;
    -h|--help) sed -n '2,17p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "unknown option: $1 (try --help)" >&2; exit 2 ;;
esac

if [ "$(uname)" != "Darwin" ]; then
    echo "This is for macOS; on Linux and Windows Print Screen already works." >&2; exit 1
fi
if [ ! -f "$CONFIG" ]; then
    echo "No Karabiner-Elements configuration at $CONFIG." >&2
    echo "Install it from https://karabiner-elements.pqrs.org (or: brew install --cask karabiner-elements)," >&2
    echo "open it once, allow its driver and input monitoring, then run this again." >&2
    exit 1
fi

backup="$CONFIG.$(date +%Y%m%d-%H%M%S).bak"
cp "$CONFIG" "$backup"

python3 - "$CONFIG" "$ACTION" <<'EOF'
import json, sys

path, action = sys.argv[1], sys.argv[2]
TAG = "[BorderlineComputing print screen]"


def rule(name, from_mods, to_key):
    frm = {"key_code": "print_screen"}
    if from_mods:
        frm["modifiers"] = {"mandatory": from_mods}
    return {"description": "%s %s" % (name, TAG),
            "manipulators": [{"type": "basic", "from": frm,
                              "to": [{"key_code": to_key, "modifiers": ["left_command", "left_shift"]}]}]}


RULES = [  # Shift first: Karabiner uses the first rule that matches
    rule("Shift+Print Screen → area or window screenshot (Cmd+Shift+4)", ["shift"], "4"),
    rule("Print Screen → whole-screen screenshot (Cmd+Shift+3)", [], "3"),
]

with open(path) as f:
    config = json.load(f)
profiles = config.get("profiles") or []
profile = next((p for p in profiles if p.get("selected")), profiles[0] if profiles else None)
if profile is None:
    sys.exit("No profile in %s: open Karabiner-Elements once first." % path)

rules = profile.setdefault("complex_modifications", {}).setdefault("rules", [])
before = len(rules)
rules[:] = [r for r in rules if TAG not in r.get("description", "")]
removed = before - len(rules)
if action == "add":
    rules[:0] = RULES

with open(path, "w") as f:
    json.dump(config, f, indent=4)
    f.write("\n")

name = profile.get("name", "?")
if action == "add":
    print("Print Screen now takes screenshots (Karabiner profile %r):" % name)
    print("  Print Screen          whole screen")
    print("  Shift + Print Screen  drag an area, or press Space and click a window")
else:
    print("Removed %d Print Screen rule(s) from Karabiner profile %r." % (removed, name))
EOF
echo "Backup of the previous configuration: $backup"
