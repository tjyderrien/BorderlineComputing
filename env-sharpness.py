#!/usr/bin/env python3
"""Measure how "sharp" this computer is for working on remote Linux servers.

A sharp machine gets you from intent to a working shell (or file, or desktop)
on a server with no passwords, no retyped hostnames, no dropped connections
and no tools that behave differently from the server's. This script checks
that, gives a score out of 100 per category and overall, and lists the fixes
that would raise it.

Only the Python standard library is used (Python 3.6+, Linux and macOS).
It only reads: the only network actions are TCP connects and
`ssh -o BatchMode=yes <host> true` to the hosts you are checking.

    ./env-sharpness.py                                  # hosts from ~/.ssh/config
    ./env-sharpness.py --hosts biatri-1,biatri-2,luzicka
    ./env-sharpness.py --offline                        # no network checks
    ./env-sharpness.py --json asus.json                 # also save the results
    ./env-sharpness.py --compare asus.json mac.json     # what one has, the other lacks
"""

import argparse
import json
import os
import platform
import re
import shutil
import socket
import stat
import subprocess
import sys
import threading
import time
from pathlib import Path

HOME = Path.home()
IS_MAC = platform.system() == "Darwin"
FORGES = ("github.com", "gitlab.com", "gitlab.org", "bitbucket.org")

# What a machine is for decides what it is judged on. A workstation is where you sit: it must reach,
# log in to and mount everything. A server is worked *on*: it needs a good shell and SSH, not a VNC
# viewer. An hpc machine is a shared computing centre you don't administer (IT4I...): no sudo, no
# daemons, so only what one user can set up in $HOME is checked.
ROLES = ("workstation", "server", "hpc")
TARGETS = {"workstation": 90, "server": 80, "hpc": 70}
ALL = ROLES
WS = ("workstation",)
NOT_HPC = ("workstation", "server")
ROLE = "workstation"  # set in main()
# Where `tailmon mount` puts the servers: macOS's system disk is read-only, so there it is in your home.
MOUNT_ROOT = HOME / "tailscale" if IS_MAC else Path("/media/tailscale")
MOUNT_ROOT_LABEL = "~/tailscale" if IS_MAC else "/media/tailscale"

CATEGORIES = [
    ("network", "Reaching the servers"),
    ("auth", "Logging in without friction"),
    ("ssh", "SSH ergonomics"),
    ("files", "Remote files"),
    ("tools", "Toolchain parity with the servers"),
    ("shell", "Shell"),
    ("toolkit", "Your toolkit (TailMon & co.)"),
]


# ---------------------------------------------------------------- helpers ----

def tailscale_cli():
    """The tailscale command; the Mac App Store app keeps it inside the app, off the PATH."""
    app = "/Applications/Tailscale.app/Contents/MacOS/Tailscale"
    return shutil.which("tailscale") or (app if IS_MAC and os.access(app, os.X_OK) else None)


def run(cmd, timeout=10):
    """Run cmd, return (exit code, stdout+stderr, seconds). Never raises."""
    t0 = time.monotonic()
    try:
        p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                           stdin=subprocess.DEVNULL, timeout=timeout, universal_newlines=True)
        return p.returncode, p.stdout, time.monotonic() - t0
    except subprocess.TimeoutExpired:
        return 124, "timeout", time.monotonic() - t0
    except OSError as e:
        return 127, str(e), time.monotonic() - t0


def have(name):
    return shutil.which(name) is not None


def ramp(x, good, bad):
    """1.0 when x <= good, 0.0 when x >= bad, linear in between."""
    if x is None:
        return 0.0
    if x <= good:
        return 1.0
    if x >= bad:
        return 0.0
    return (bad - x) / (bad - good)


def with_timeout(fn, seconds):
    """Run fn in a thread so a hung network mount cannot freeze the script."""
    box = {}

    def target():
        try:
            box["value"] = fn()
        except Exception as e:  # noqa: BLE001 - any failure just means "not working"
            box["error"] = e
    t = threading.Thread(target=target, daemon=True)
    t.start()
    t.join(seconds)
    if t.is_alive() or "error" in box:
        return None
    return box["value"]


def rc_text():
    """All shell startup files concatenated (bash and zsh)."""
    text = ""
    for name in (".bashrc", ".bash_profile", ".bash_aliases", ".profile",
                 ".zshrc", ".zprofile", ".zshenv"):
        try:
            text += (HOME / name).read_text(errors="replace") + "\n"
        except OSError:
            pass
    return text


class Report:
    def __init__(self):
        self.checks = []  # dicts: cat, name, weight, value, detail, fix

    def add(self, cat, name, weight, value, detail="", fix="", roles=ALL):
        if ROLE not in roles:
            return
        value = max(0.0, min(1.0, float(value)))
        self.checks.append(dict(cat=cat, name=name, weight=weight,
                                value=round(value, 3), detail=detail,
                                fix=fix if value < 0.999 else ""))

    def score(self, cat=None):
        return score(self.checks, cat)


def score(checks, cat=None):
    """Score of one category, or overall (the mean of the categories, so no category dominates)."""
    if cat is None:
        s = [score(checks, k) for k, _ in CATEGORIES]
        s = [x for x in s if x is not None]
        return round(sum(s) / len(s), 1) if s else None
    cs = [c for c in checks if c["cat"] == cat]
    w = sum(c["weight"] for c in cs)
    return round(100 * sum(c["weight"] * c["value"] for c in cs) / w, 1) if w else None


def detect_role():
    """Best guess of what this machine is for; override with --role."""
    if IS_MAC or run(["systemctl", "is-active", "display-manager"], timeout=5)[1].strip() == "active":
        return "workstation"
    shared = os.environ.get("LMOD_CMD") or os.environ.get("MODULESHOME") or have("sbatch") or have("qsub")
    admin = set(run(["id", "-Gn"], timeout=5)[1].split()) & {"sudo", "wheel", "admin", "root"}
    return "hpc" if shared and not admin else "server"


# ------------------------------------------------------------- ssh config ----

def ssh_aliases():
    """First alias of every non-wildcard Host block in ~/.ssh/config."""
    out = []
    try:
        lines = (HOME / ".ssh" / "config").read_text(errors="replace").splitlines()
    except OSError:
        return out
    for line in lines:
        m = re.match(r"\s*Host\s+(.+)", line, re.I)
        if not m:
            continue
        names = [n for n in m.group(1).split() if not any(ch in n for ch in "*?!")]
        if names:
            out.append((names[0], names))
    return out


def ssh_effective(host):
    """Effective ssh options for host, from `ssh -G` (lower-case keys)."""
    rc, out, _ = run(["ssh", "-G", host], timeout=5)
    opts = {}
    if rc == 0:
        for line in out.splitlines():
            k, _, v = line.partition(" ")
            opts.setdefault(k.lower(), v.strip())
    return opts


def tailnet():
    """(this machine's name, [online Linux peers]) from Tailscale, or (None, []) without it."""
    if not tailscale_cli():
        return None, []
    rc, out, _ = run([tailscale_cli(), "status", "--json"], timeout=5)
    try:
        st = json.loads(out) if rc == 0 else {}
    except ValueError:
        return None, []

    def name(p):
        return (p.get("DNSName") or "").split(".")[0] or p.get("HostName", "")
    me = name(st.get("Self") or {}) or None
    peers = [name(p) for p in (st.get("Peer") or {}).values()
             if p.get("OS") == "linux" and p.get("Online")]
    return me, sorted(peers)


def default_hosts():
    """Online Linux machines of the tailnet; without Tailscale, the hosts in ~/.ssh/config."""
    _me, peers = tailnet()
    if peers:
        return peers
    hosts = []
    for first, _names in ssh_aliases():
        hn = ssh_effective(first).get("hostname", first)
        if not hn.endswith(FORGES) and first not in FORGES:
            hosts.append(first)
    return hosts


def find_agent():
    """Use the desktop session's ssh-agent when SSH_AUTH_SOCK is unset (e.g. run over ssh by tailmon)."""
    if os.environ.get("SSH_AUTH_SOCK"):
        return
    if IS_MAC:
        cands = [run(["launchctl", "getenv", "SSH_AUTH_SOCK"], timeout=5)[1].strip()]
    else:
        d = "/run/user/%d" % os.getuid()
        cands = [d + "/keyring/ssh", d + "/gcr/ssh", d + "/openssh_agent", d + "/ssh-agent.socket"]
    for c in cands:
        try:
            if c and stat.S_ISSOCK(os.stat(c).st_mode):
                os.environ["SSH_AUTH_SOCK"] = c
                return
        except OSError:
            pass


# ----------------------------------------------------------------- checks ----

def check_network(r, hosts, offline):
    ts = tailscale_cli()
    running = False
    if ts:
        rc, out, _ = run([ts, "status", "--json"], timeout=5)
        try:
            running = rc == 0 and json.loads(out).get("BackendState") == "Running"
        except ValueError:
            running = False
    vpn = any(have(x) for x in ("openconnect", "openvpn", "wg"))
    r.add("network", "Overlay network or VPN up", 3,
          1 if running else (0.5 if (ts or vpn) else 0),
          "tailscale running" if running else ("tailscale installed, not running" if ts
                                               else ("VPN client installed" if vpn else "none")),
          "Install Tailscale and log in (`tailscale up`): servers are then reachable "
          "from anywhere, by name, with no VPN to start.", roles=NOT_HPC)
    if offline:
        return
    for h in hosts:
        opts = ssh_effective(h)
        hn, port = opts.get("hostname", h), int(opts.get("port", 22) or 22)
        t0 = time.monotonic()
        try:
            socket.create_connection((hn, port), timeout=3).close()
            ms = 1000 * (time.monotonic() - t0)
            r.add("network", f"{h}: port {port} reachable", 2, ramp(ms, 30, 400),
                  f"TCP connect {ms:.0f} ms", f"{h} is slow to reach ({ms:.0f} ms): "
                  "check `tailscale status` shows a direct (not relayed) connection.")
        except OSError as e:
            r.add("network", f"{h}: port {port} reachable", 2, 0, f"unreachable ({e})",
                  f"{h} ({hn}) cannot be reached: VPN/Tailscale down, or wrong HostName.")


def check_auth(r, hosts, offline):
    sshdir = HOME / ".ssh"
    keys = [p for p in sshdir.glob("id_*") if not p.name.endswith(".pub")] if sshdir.is_dir() else []
    r.add("auth", "SSH key pair exists", 3, 1 if keys else 0,
          ", ".join(sorted(k.name for k in keys)) or "none",
          "Create a key: `ssh-keygen -t ed25519`, then `ssh-copy-id <host>` for each server.")
    bad = []
    if sshdir.is_dir() and stat.S_IMODE(sshdir.stat().st_mode) & 0o077:
        bad.append("~/.ssh")
    bad += [k.name for k in keys if stat.S_IMODE(k.stat().st_mode) & 0o077]
    r.add("auth", "Private key permissions strict", 1, 0 if bad else 1,
          "too open: " + ", ".join(bad) if bad else "ok",
          "`chmod 700 ~/.ssh && chmod 600 ~/.ssh/id_*` (ssh ignores keys others can read).")
    rc, out, _ = run(["ssh-add", "-l"], timeout=5)
    n = len([l for l in out.splitlines() if l.strip()]) if rc == 0 else 0
    usekc = IS_MAC and re.search(r"(?im)^\s*UseKeychain\s+yes", _read(sshdir / "config"))
    r.add("auth", "Keys loaded in an agent", 1, 1 if (n or usekc) else 0,
          f"{n} key(s) in agent" + (", UseKeychain yes" if usekc else ""),
          "Add `AddKeysToAgent yes`" + (" and `UseKeychain yes`" if IS_MAC else "") +
          " under `Host *` in ~/.ssh/config so a key passphrase is typed once per session.", roles=WS)
    if offline:
        return
    for h in hosts:
        rc, out, sec = run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5", h, "true"],
                           timeout=15)
        if rc == 0:
            r.add("auth", f"{h}: login with no password", 4, 1, f"ok in {sec:.2f} s")
            r.add("auth", f"{h}: time to shell", 2, ramp(sec, 0.4, 3.0), f"{sec:.2f} s",
                  f"Login to {h} takes {sec:.1f} s: enable ControlMaster (see SSH "
                  "ergonomics) and `GSSAPIAuthentication no` if the server doesn't use Kerberos.")
        else:
            why = out.strip().splitlines()[-1] if out.strip() else f"exit {rc}"
            hint = (f"Run `ssh-copy-id {h}` once." if "ermission denied" in why else
                    f"Connect once interactively (`ssh {h}`) to accept its host key."
                    if "verification" in why else f"Fix login to {h}: {why}")
            r.add("auth", f"{h}: login with no password", 4, 0, why[:80], hint)


def _read(p):
    try:
        return Path(p).read_text(errors="replace")
    except OSError:
        return ""


def check_ssh(r, hosts):
    aliases = {n for _first, names in ssh_aliases() for n in names}
    if hosts:
        named = [h for h in hosts if h in aliases]
        r.add("ssh", "Servers have Host aliases in ~/.ssh/config", 3, len(named) / len(hosts),
              f"{len(named)}/{len(hosts)}: missing " + ", ".join(sorted(set(hosts) - set(named)))
              if len(named) < len(hosts) else f"{len(named)}/{len(hosts)}",
              "Add a `Host <short-name>` block with HostName, User and IdentityFile for each "
              "server: `ssh biatri-1` instead of `ssh user@10.26.212.34 -i ...`. Copy the "
              "blocks from your sharpest machine.")
    sample = ssh_effective(hosts[0] if hosts else "localhost")
    cm = sample.get("controlmaster", "false") not in ("false", "no")
    cp = sample.get("controlpersist", "no") not in ("no", "false", "0")
    r.add("ssh", "Connection sharing (ControlMaster)", 2, (cm + cp) / 2,
          f"ControlMaster {sample.get('controlmaster', '?')}, ControlPersist "
          f"{sample.get('controlpersist', '?')}",
          "Under `Host *`: `ControlMaster auto`, `ControlPath ~/.ssh/cm-%C`, "
          "`ControlPersist 10m`. Second ssh/scp/rsync/sshfs to a host then starts instantly.")
    sai = int(sample.get("serveraliveinterval", "0") or 0)
    r.add("ssh", "Keep-alive (ServerAliveInterval)", 2, 1 if 0 < sai <= 120 else 0,
          f"{sai} s" if sai else "off",
          "Under `Host *`: `ServerAliveInterval 30` and `ServerAliveCountMax 4`, so idle "
          "sessions survive NAT/Wi-Fi timeouts and dead ones fail fast instead of freezing.")
    r.add("ssh", "Resilient sessions (mosh, tmux or screen)", 1,
          1 if any(have(x) for x in ("mosh", "tmux", "screen")) else 0,
          ", ".join(x for x in ("mosh", "tmux", "screen") if have(x)) or "none",
          "Install tmux (and run long jobs inside tmux on the server); mosh survives "
          "sleep and network changes.")
    x11 = (Path("/opt/X11").exists() or Path("/Applications/Utilities/XQuartz.app").exists()) \
        if IS_MAC else bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))
    r.add("ssh", "X server for `ssh -X` graphics", 1, 1 if x11 else 0,
          "present" if x11 else "missing",
          "Install XQuartz (`brew install --cask xquartz`)" if IS_MAC else "Run from a graphical session.", roles=WS)
    vnc = [x for x in ("vncviewer", "remmina", "xtightvncviewer", "tigervnc") if have(x)]
    if IS_MAC:
        vnc.append("Screen Sharing (vnc://)")  # built in
    r.add("ssh", "Remote desktop client (VNC)", 1, 1 if vnc else 0, ", ".join(vnc) or "none",
          "Install a VNC viewer (TigerVNC or Remmina).", roles=WS)


def sshfs_mounts():
    """{mountpoint: source} for sshfs/FUSE network mounts."""
    rc, out, _ = run(["mount"], timeout=5)
    mounts = {}
    for line in out.splitlines():
        if IS_MAC:  # macFUSE: "(macfuse, ...)"; FUSE-T serves sshfs over a local NFS: "(nfs, ...)"
            m = re.match(r"(\S+:\S*) on (.+?) \((?:macfuse|osxfuse|fuse-t|nfs)\b", line)
        else:
            m = re.match(r"(\S+:\S*) on (.+?) type \S*sshfs", line)
        if m:
            mounts[m.group(2)] = m.group(1)
    return mounts


def check_files(r, hosts, offline):
    sshfs = have("sshfs")
    r.add("files", "sshfs installed", 2, 1 if sshfs else 0, shutil.which("sshfs") or "missing",
          "`brew install --cask macos-fuse-t/homebrew-cask/fuse-t && brew install "
          "macos-fuse-t/homebrew-cask/fuse-t-sshfs` (FUSE-T: no kernel extension, no reboot)."
          if IS_MAC else "`sudo apt install sshfs`", roles=WS)
    rc, out, _ = run(["rsync", "--version"], timeout=5)
    m = re.search(r"version\s+v?(\d+)\.(\d+)", out)
    ver = (int(m.group(1)), int(m.group(2))) if m else None
    r.add("files", "rsync 3.x", 2, 1 if ver and ver >= (3, 0) else (0.4 if rc == 0 else 0),
          "openrsync" if "openrsync" in out else (f"{ver[0]}.{ver[1]}" if ver else "missing"),
          "`brew install rsync` (macOS ships an old rsync/openrsync lacking --info=progress2, "
          "-A, -X...)." if IS_MAC else "`sudo apt install rsync`")
    mounts = sshfs_mounts()
    if not hosts:
        return
    for h in hosts:
        opts = ssh_effective(h)
        names = {h, opts.get("hostname", "")}
        mp = next((p for p, src in mounts.items()
                   if src.split("@")[-1].split(":")[0] in names), None)
        if not mp:
            r.add("files", f"{h}: mounted locally", 2, 0, "not mounted",
                  f"`tailmon mount` (every server under {MOUNT_ROOT_LABEL}), or `mkdir -p ~/mnt/{h} && "
                  f"sshfs {h}:/ ~/mnt/{h} -o reconnect` - then open server files in local apps.")
            continue
        if offline:
            r.add("files", f"{h}: mounted locally", 2, 1, mp)
            continue
        t0 = time.monotonic()
        ok = with_timeout(lambda: os.listdir(mp), 5) is not None
        sec = time.monotonic() - t0
        r.add("files", f"{h}: mounted locally", 2, ramp(sec, 0.3, 3.0) if ok else 0.2,
              f"{mp} ({sec:.2f} s to list)" if ok else f"{mp} (stale/hung)",
              f"Remount {mp}: `fusermount -u {mp}` (Linux) / `umount {mp}` (macOS), then "
              "sshfs again with `-o reconnect`.")


TOOLS = [  # (command, weight, why, how on mac, how on linux[, roles])
    ("git", 2, "version control", "xcode-select --install", "sudo apt install git"),
    ("vim", 1, "same editor as on the servers", "built in", "sudo apt install vim"),
    ("python3", 2, "scripting/analysis", "brew install python", "sudo apt install python3"),
    ("conda", 1, "same Python environments as the servers",
     "install Miniforge", "install Miniforge", NOT_HPC),
    ("gnuplot", 1, "quick plots of server output", "brew install gnuplot", "sudo apt install gnuplot", NOT_HPC),
    ("rg", 1, "fast search", "brew install ripgrep", "sudo apt install ripgrep"),
    ("jq", 1, "JSON on the command line", "brew install jq", "sudo apt install jq"),
    ("htop", 1, "watching jobs", "brew install htop", "sudo apt install htop"),
    ("gh", 1, "GitHub from the terminal", "brew install gh", "sudo apt install gh", WS),
    ("claude", 1, "Claude Code", "npm i -g @anthropic-ai/claude-code", "npm i -g @anthropic-ai/claude-code", WS),
]


def check_tools(r):
    for cmd, w, why, mac, lin, *roles in TOOLS:
        r.add("tools", f"{cmd} ({why})", w, 1 if have(cmd) else 0,
              shutil.which(cmd) or "missing", f"`{mac if IS_MAC else lin}`", roles=roles[0] if roles else ALL)
    gnu = []
    for cmd in ("sed", "grep", "find", "date", "readlink", "stat"):
        rc, out, _ = run([cmd, "--version"], timeout=5)
        gnu.append(cmd if rc == 0 and ("GNU" in out or "Free Software" in out) else None)
    good = [c for c in gnu if c]
    r.add("tools", "GNU coreutils/sed/grep/find (as on the servers)", 4, len(good) / len(gnu),
          f"GNU: {len(good)}/{len(gnu)}" + ("" if len(good) == len(gnu) else
                                            " (BSD versions behave differently: sed -i, date -d...)"),
          "`brew install coreutils gnu-sed grep findutils` and put their `gnubin` dirs first "
          "in PATH, so commands copied from the servers work unchanged.")
    rc, out, _ = run(["bash", "--version"], timeout=5)
    m = re.search(r"version (\d+)", out)
    bv = int(m.group(1)) if m else 0
    r.add("tools", "bash >= 4 (as on the servers)", 2, 1 if bv >= 4 else 0, f"bash {bv or '?'}",
          "`brew install bash` (macOS ships bash 3.2 from 2007: no associative arrays, "
          "no `mapfile`, `${x,,}`...).")


def check_shell(r):
    rc = rc_text()
    shell = Path(os.environ.get("SHELL", "")).name
    r.add("shell", "Same login shell as the servers (bash)", 1, 1 if shell == "bash" else 0.5,
          shell or "?", "Either `chsh -s /bin/bash`, or keep zsh but port your bash "
          "aliases/functions to ~/.zshrc.")
    m = re.findall(r"(?:HISTSIZE|SAVEHIST)=(\d+)", rc)
    hs = max((int(x) for x in m), default=500)
    r.add("shell", "Long shell history", 2, ramp(-hs, -50000, -1000), f"{hs} lines",
          "Set `HISTSIZE=100000` and `HISTFILESIZE=100000` (bash) or `SAVEHIST=100000` "
          "(zsh): Ctrl+R then finds the long command you ran on that server weeks ago.")
    hist = _read(HOME / ".bash_history") + _read(HOME / ".zsh_history")
    n = len([l for l in hist.splitlines() if re.search(r"\bssh\b", l)])
    r.add("shell", "History actually holds remote work", 1, ramp(-n, -100, 0),
          f"{n} ssh commands in history",
          "Nothing to install: this rises as you use the machine. Copying your history "
          "file from the sharper machine gives Ctrl+R its memory at once.", roles=WS)
    aliases = len(re.findall(r"(?m)^\s*alias\s+\w", rc))
    funcs = len(re.findall(r"(?m)^\s*(?:function\s+\w+|\w[\w-]*\s*\(\)\s*\{)", rc))
    r.add("shell", "Personal aliases/functions", 2, ramp(-(aliases + funcs), -10, 0),
          f"{aliases} aliases, {funcs} functions",
          "Copy your aliases from the sharper machine; better, keep them in one file in a "
          "git repo and source it from both ~/.bashrc and ~/.zshrc.")
    fz = have("fzf")
    r.add("shell", "Fuzzy history/file search (fzf)", 1, 1 if fz else 0, "yes" if fz else "no",
          "`brew install fzf`" if IS_MAC else "`sudo apt install fzf`")


REPOS = "https://github.com/tjyderrien/"


def check_toolkit(r):
    tm = shutil.which("tailmon")
    r.add("toolkit", "tailmon (monitor, search, grep, mount the tailnet)", 3, 1 if tm else 0,
          tm or "missing",
          "`git clone %sTailScale-Monitor ~/Documents/Tail-Monitor.main && ln -s "
          "~/Documents/Tail-Monitor.main/tailmon.py ~/.local/bin/tailmon`" % REPOS, roles=WS)
    try:
        exe = json.loads(_read(HOME / ".config" / "tailmon.json") or "{}").get("claude_explorer")
    except ValueError:
        exe = None
    ce = os.path.expanduser(exe) if exe and os.access(os.path.expanduser(exe), os.X_OK) \
        else shutil.which("claude-explorer")
    r.add("toolkit", "claude-explorer (`tailmon claude|todo|dispatch`)", 2, 1 if ce else 0,
          ce or "missing",
          "`git clone %sClaudeXplorer` and link its claude_explorer.py into ~/.local/bin as "
          "claude-explorer (or set \"claude_explorer\" in ~/.config/tailmon.json)." % REPOS, roles=WS)
    es = shutil.which("env-sharpness")
    r.add("toolkit", "env-sharpness on the PATH (`tailmon sharpness`)", 1, 1 if es else 0,
          es or "missing", "`ln -s ~/BorderlineComputing/env-sharpness.py ~/.local/bin/env-sharpness`", roles=WS)
    ok = MOUNT_ROOT.is_dir() and os.access(str(MOUNT_ROOT), os.W_OK)
    r.add("toolkit", "Mount root for `tailmon mount` (%s)" % MOUNT_ROOT_LABEL, 1, 1 if ok else 0,
          "ready" if ok else ("not writable" if MOUNT_ROOT.exists() else "missing"),
          "`tailmon mount` creates it" if IS_MAC else "`sudo install -d -o $USER -g $(id -gn) /media/tailscale`",
          roles=WS)
    check_keyboard(r)


# One keyboard for every machine: a PC AZERTY keyboard (ISO, with the extra <> key),
# typed as French first and Czech second, as on the Asus. (XKB name, macOS input source ID)
KEYBOARD = [("fr", "com.apple.keylayout.French-PC"), ("cz", "com.apple.keylayout.Czech")]
KEYBOARD_LABEL = "Keyboard layouts as on your other machines (French AZERTY PC, Czech)"
KEYBOARD_TYPE_LABEL = "Keyboard type ISO (PC AZERTY keyboard, with the <> key)"


def gnome_env():
    """Environment reaching the desktop session's settings, also from ssh or cron."""
    env = dict(os.environ)
    bus = "/run/user/%d/bus" % os.getuid()
    if not env.get("DBUS_SESSION_BUS_ADDRESS") and os.path.exists(bus):
        env["DBUS_SESSION_BUS_ADDRESS"] = "unix:path=" + bus
    return env


def keyboard_layouts():
    """(enabled layouts with the default first, as XKB names like 'fr' or 'fr+oss', where they come from)."""
    if IS_MAC:
        rc, out, _ = run(["defaults", "read", "com.apple.HIToolbox", "AppleEnabledInputSources"])
        names = re.findall(r'"KeyboardLayout Name" = "?([^";]+)"?;', out) if rc == 0 else []
        rc, sel, _ = run(["defaults", "read", "com.apple.HIToolbox", "AppleSelectedInputSources"])
        cur = re.findall(r'"KeyboardLayout Name" = "?([^";]+)"?;', sel) if rc == 0 else []
        xkb = {"frenchpc": "fr", "french": "fr(mac)", "czech": "cz", "czechqwerty": "cz(qwerty)",
               "abc": "us", "us": "us"}
        conv = [xkb.get(re.sub(r"[^a-z]", "", n.lower()), n) for n in cur + [n for n in names if n not in cur]]
        return conv, "macOS input sources"
    for cmd in (["dconf", "read", "/org/gnome/desktop/input-sources/sources"],
                ["gsettings", "get", "org.gnome.desktop.input-sources", "sources"]):
        if shutil.which(cmd[0]):
            p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, universal_newlines=True,
                               env=gnome_env())
            found = re.findall(r"\('xkb', '([^']+)'\)", p.stdout)
            if found:
                return found, "GNOME input sources"
    rc, out, _ = run(["localectl", "status"])
    m = re.search(r"X11 Layout:\s*(\S+)", out)
    return (m.group(1).split(",") if m else []), "localectl"


def connected_keyboards():
    """macOS: {"<product>-<vendor>-0": name} for the keyboards plugged in now (keys of com.apple.keyboardtype)."""
    rc, out, _ = run(["ioreg", "-r", "-c", "IOHIDDevice", "-d", "1", "-l"])
    kbs = {}
    for dev in out.split("+-o ")[1:]:
        f = dict(re.findall(r'"(Product|VendorID|ProductID|PrimaryUsage|PrimaryUsagePage|Transport)" = "?([^"\n]*)"?', dev))
        name = f.get("Product", "?")
        if (f.get("PrimaryUsagePage") == "1" and f.get("PrimaryUsage") == "6" and f.get("VendorID", "0") != "0"
                and not re.search(r"mouse|trackpad|virtual", name, re.I)):
            kbs["%s-%s-0" % (f.get("ProductID"), f.get("VendorID"))] = name
    return kbs


def keyboard_types():
    """macOS: {"<product>-<vendor>-0": 40 ANSI | 41 ISO | 42 JIS} as chosen in the Keyboard Setup Assistant."""
    rc, out, _ = run(["defaults", "read", "/Library/Preferences/com.apple.keyboardtype", "keyboardtype"])
    return {k: int(v) for k, v in re.findall(r'"([\d-]+)" = (\d+);', out)} if rc == 0 else {}


def check_keyboard(r):
    lay, src = keyboard_layouts()
    first = 1 if lay and lay[0].split("+")[0] == "fr" else 0
    cz = 1 if "cz" in [l.split("+")[0] for l in lay] else 0
    r.add("toolkit", KEYBOARD_LABEL, 2, 0.6 * first + 0.4 * cz,
          "%s: %s" % (src, ", ".join(lay) or "none found"),
          ("Enable 'French - PC' (not Apple's 'French') and 'Czech' in System Settings > Keyboard > "
           "Text Input, or run setup-env.py." if IS_MAC else
           "`gsettings set org.gnome.desktop.input-sources sources \"[('xkb', 'fr'), ('xkb', 'cz')]\"`, "
           "or run setup-env.py."), roles=WS)
    if IS_MAC:
        kar = karabiner_keyboard_type()
        if kar:  # Karabiner grabs the keyboards and types through its virtual one: that one's type counts
            r.add("toolkit", KEYBOARD_TYPE_LABEL, 1, 1 if kar == "iso" else 0,
                  "Karabiner virtual keyboard: %s" % kar.upper(),
                  "Karabiner-Elements > Virtual Keyboard > Keyboard type: ISO; "
                  "otherwise macOS swaps the <> and ² keys.", roles=WS)
            return
        kbs, types = connected_keyboards(), keyboard_types()
        names = {40: "ANSI", 41: "ISO", 42: "JIS"}
        ok = [k for k in kbs if types.get(k) == 41]
        r.add("toolkit", KEYBOARD_TYPE_LABEL, 1, len(ok) / len(kbs) if kbs else 1,
              ", ".join("%s: %s" % (kbs[k], names.get(types.get(k), "not set")) for k in kbs) or "no keyboard plugged in",
              "Plug the keyboard in, then System Settings > Keyboard > Keyboard Type... > ISO; "
              "otherwise macOS swaps the <> and ² keys.", roles=WS)


def karabiner_keyboard_type():
    """'iso'/'ansi'/'jis' when Karabiner-Elements is running (it then types through its virtual keyboard)."""
    rc, out, _ = run(["pgrep", "-f", "Karabiner-Core-Service"])
    path = HOME / ".config" / "karabiner" / "karabiner.json"
    if rc != 0 or not path.exists():
        return None
    try:
        profiles = json.loads(path.read_text()).get("profiles", [])
    except ValueError:
        return None
    prof = next((p for p in profiles if p.get("selected")), profiles[0] if profiles else {})
    vk = prof.get("virtual_hid_keyboard", {})
    return vk.get("keyboard_type_v2") or vk.get("keyboard_type") or "ansi"


# ----------------------------------------------------------------- output ----

C = sys.stdout.isatty() and os.environ.get("NO_COLOR") is None


def color(s, v):
    if not C:
        return s
    code = "32" if v >= 0.999 else ("33" if v > 0.3 else "31")
    return f"\033[{code}m{s}\033[0m"


def bar(score, width=20):
    n = round(width * score / 100)
    return "#" * n + "." * (width - n)


def print_report(data, verbose):
    print(f"\nEnvironment sharpness: {data['machine']} ({data['os']})")
    print(f"Role: {data['role']} (target {data['target']:g})   "
          f"Hosts checked: {', '.join(data['hosts']) or 'none'}\n")
    checks = data["checks"]
    for key, title in CATEGORIES:
        cs = [c for c in checks if c["cat"] == key]
        if not cs:
            continue
        s = data["scores"][key]
        print(f"{title:<36} {bar(s)} {color(f'{s:5.1f}', s / 100)}")
        for c in cs:
            if verbose or c["value"] < 0.999:
                mark = "ok" if c["value"] >= 0.999 else f"{100 * c['value']:.0f}%"
                print(f"    {color(f'{mark:>4}', c['value'])}  {c['name']}  [{c['detail']}]")
    ok = data["overall"] > data["target"]
    print(f"\n{'OVERALL':<36} {bar(data['overall'])} {data['overall']:5.1f} / 100   "
          + color(f"{'above' if ok else 'below'} target {data['target']:g}", 1 if ok else 0) + "\n")
    fixes = sorted((c for c in checks if c["fix"]),
                   key=lambda c: -c["weight"] * (1 - c["value"]))
    if fixes:
        print("Biggest gains first:")
        for i, c in enumerate(fixes[:12], 1):
            print(f"  {i:2}. {c['fix']}")
        print()


def compare(a_path, b_path):
    a, b = (json.loads(Path(p).read_text()) for p in (a_path, b_path))
    print(f"\n{'':<50} {a['machine'][:14]:>14} {b['machine'][:14]:>14}")
    for key, title in CATEGORIES:
        print(f"{title:<50} {a['scores'].get(key) or 0:>14.1f} {b['scores'].get(key) or 0:>14.1f}")
    print(f"{'OVERALL':<50} {a['overall']:>14.1f} {b['overall']:>14.1f}\n")
    av = {c["name"]: c for c in a["checks"]}
    bv = {c["name"]: c for c in b["checks"]}
    rows = []
    for name in list(av) + [n for n in bv if n not in av]:
        x, y = av.get(name), bv.get(name)
        vx, vy = (x or {}).get("value"), (y or {}).get("value")
        if vx != vy and (vx is None or vy is None or abs(vx - vy) > 0.15):
            w = (x or y)["weight"]
            rows.append((w * abs((vx or 0) - (vy or 0)), name, x, y))
    if not rows:
        print("No meaningful differences.")
        return
    print("Differences (largest impact first):")
    for _, name, x, y in sorted(rows, key=lambda t: -t[0]):
        fx = "-" if x is None else f"{100 * x['value']:.0f}%"
        fy = "-" if y is None else f"{100 * y['value']:.0f}%"
        print(f"  {name[:48]:<48} {fx:>14} {fy:>14}")
        worse = y if (y and (x is None or y["value"] < x["value"])) else x
        if worse and worse.get("fix"):
            print(f"      -> {worse['fix']}")
    print()


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--hosts", help="comma-separated servers to check "
                    "(default: Host aliases in ~/.ssh/config, minus GitHub/GitLab/Bitbucket)")
    ap.add_argument("--offline", action="store_true", help="skip all network checks")
    ap.add_argument("--json", metavar="FILE", help="also save the results as JSON (`-`: print only the JSON, for tailmon)")
    ap.add_argument("--compare", nargs=2, metavar=("A.json", "B.json"),
                    help="compare two saved results and stop")
    ap.add_argument("--role", choices=ROLES, help="what this machine is for (default: guessed; "
                    "workstation if it has a desktop, hpc on a shared cluster without sudo, else server)")
    ap.add_argument("--target", type=float, help="score to exceed (default: %s)"
                    % ", ".join("%s %d" % kv for kv in TARGETS.items()))
    ap.add_argument("--check", dest="min_exit", action="store_true",
                    help="exit with status 1 when the score does not exceed the target (for scripts, cron)")
    ap.add_argument("-v", "--verbose", action="store_true", help="also list passed checks")
    args = ap.parse_args()

    if args.compare:
        compare(*args.compare)
        return
    global ROLE
    ROLE = args.role or detect_role()
    target = args.target if args.target is not None else TARGETS[ROLE]
    # Only a workstation is judged on reaching the others; servers and clusters are reached.
    if ROLE != "workstation":
        hosts = []
    else:
        hosts = [h.strip() for h in args.hosts.split(",") if h.strip()] if args.hosts else default_hosts()
    find_agent()

    r = Report()
    check_network(r, hosts, args.offline)
    check_auth(r, hosts, args.offline)
    check_ssh(r, hosts)
    check_files(r, hosts, args.offline)
    check_tools(r)
    check_shell(r)
    check_toolkit(r)

    me, _peers = tailnet()
    data = dict(machine=me or socket.gethostname().split(".")[0], os=f"{platform.system()} {platform.release()}",
                date=time.strftime("%Y-%m-%d %H:%M"), hosts=hosts, offline=args.offline,
                role=ROLE, target=target,
                scores={k: r.score(k) for k, _ in CATEGORIES}, overall=r.score(),
                checks=r.checks)
    if args.json == "-":  # machine-readable only, for `tailmon sharpness` and setup-env.py
        print(json.dumps(data))
    else:
        print_report(data, args.verbose)
        if args.json:
            Path(args.json).write_text(json.dumps(data, indent=1))
            print(f"Saved to {args.json}")
    if args.min_exit and (data["overall"] or 0) <= target:
        sys.exit(1)


if __name__ == "__main__":
    main()
