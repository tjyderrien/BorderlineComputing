#!/usr/bin/env bash
# Free space on the root partition (/dev/sda6).
#
# Usage:
#   ./free-disk-space.sh           # dry run: shows what would be reclaimed
#   ./free-disk-space.sh --apply   # actually do it (asks for sudo password)
#
# Only touches regenerable data: package/journal/conda caches, disabled snap
# revisions, unused apt packages (incl. the old 5.15 kernel), and the Trash.
# Nothing in ~/Documents or ~/Downloads is touched.

set -u
APPLY=0
[[ "${1:-}" == "--apply" ]] && APPLY=1

say()  { printf '\n\033[1m== %s\033[0m\n' "$*"; }
size() { du -sh "$@" 2>/dev/null | awk '{print "   current size: " $1 "\t" $2}'; }
run()  {
    if (( APPLY )); then echo "+ $*"; "$@"; else echo "   [dry-run] $*"; fi
}

echo "Root filesystem before:"; df -h / | tail -1
(( APPLY )) || echo "(dry run - pass --apply to execute)"
(( APPLY )) && sudo -v || true

say "1. apt package cache (~1.2G)"
size /var/cache/apt
run sudo apt-get clean

say "2. systemd journal (~1.8G) -> keep 200M"
journalctl --disk-usage 2>/dev/null | sed 's/^/   /'
run sudo journalctl --vacuum-size=200M

say "3. Disabled snap revisions (old versions kept by snap, several GB)"
snap list --all 2>/dev/null | awk '/disabled/{print "   " $1, $2, "(rev " $3 ")"}'
if (( APPLY )); then
    snap list --all | awk '/disabled/{print $1, $3}' | while read -r name rev; do
        echo "+ snap remove $name --revision=$rev"
        sudo snap remove "$name" --revision="$rev"
    done
else
    echo "   [dry-run] sudo snap remove <name> --revision=<rev>  (for each above)"
fi
# stop snap from hoarding old revisions again (default is 3)
run sudo snap set system refresh.retain=2

say "4. Unused apt packages, incl. old kernel 5.15 (running: $(uname -r))"
apt-get -s autoremove --purge 2>/dev/null | awk '/^Remv/{print "   " $2}' | head -20
run sudo apt-get autoremove --purge -y

say "5. Anaconda package cache (~2G, regenerable)"
size ~/anaconda3/pkgs
if [[ -x ~/anaconda3/bin/conda ]]; then
    run ~/anaconda3/bin/conda clean --all -y
fi

say "6. pip cache / Trash / thumbnails"
size ~/.cache/pip ~/.local/share/Trash ~/.cache/thumbnails
run pip cache purge
run rm -rf ~/.local/share/Trash/files ~/.local/share/Trash/info ~/.cache/thumbnails

say "Not automated (your call - see report)"
cat <<'EOF'
   ~/snap/firefox/common (1.9G) and ~/snap/chromium/common (1.9G): browser caches.
       Clear from inside each browser, or:  rm -rf ~/snap/*/common/.cache
   ~/Downloads/Softwares (551M): installers you may no longer need.
   ~/Android/Sdk/emulator (821M): only if you don't use the Android emulator.
   ~/.local/share/claude/versions: old Claude Code versions (keep the newest).
   Note: /media/thibault/Data (/dev/sda4) is also 100% full.
EOF

echo; echo "Root filesystem after:"; df -h / | tail -1
