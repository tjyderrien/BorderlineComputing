#!/usr/bin/env python3
"""Bring this machine above its sharpness target, with as few changes as possible.

env-sharpness.py measures the machine and gives it a role (workstation, server or hpc) and a
target score. This script picks, among the fixes it knows, the smallest set that lifts the score
above the target, biggest gain first, and stops there. A machine already above its target is left
alone: machines may differ on purpose, and only the gaps that hurt get closed.

Fixes come in layers; --layers picks which ones may be used:

    core          in your home directory only, no sudo, no service: also fine on shared computing
                  centres (IT4I...). ssh-defaults (ControlMaster, keep-alive), history (100,000
                  lines), user-bin (fzf and ripgrep, pinned and SHA-256 checked), aliases
    macos         Homebrew: GNU coreutils/sed/grep/find first in PATH, bash 5, rsync 3; FUSE-T +
                  sshfs and XQuartz (these two ask for your password, so only in a terminal)
    workstation   your toolkit: tailmon and claude-explorer cloned and linked, env-sharpness
                  linked; `tailmon mount` of every server

Each change to a file is a block between "# >>> setup-env: <name> >>>" markers, so you can see it,
and --undo removes it. Files are backed up before their first change.

    ./setup-env.py                     # plan: what would be done, and the predicted score
    ./setup-env.py --apply             # do it, then measure again
    ./setup-env.py --all --apply       # every fix that applies here, whatever the target
    ./setup-env.py --layers core       # home-directory fixes only (computing centres)
    ./setup-env.py --role hpc --target 75
    ./setup-env.py --undo              # remove every block, binary and link it added

Only the Python standard library is used (Python 3.6+, Linux and macOS).
"""

import argparse
import hashlib
import importlib.util
import io
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import time
import urllib.request
from pathlib import Path

HOME = Path.home()
HERE = Path(os.path.realpath(__file__)).parent
BIN = HOME / ".local" / "bin"
MANIFEST = HOME / ".local" / "share" / "setup-env" / "installed.json"
STAMP = time.strftime("%Y%m%d-%H%M%S")
IS_MAC = platform.system() == "Darwin"

sys.dont_write_bytecode = True  # no __pycache__ next to the scripts
spec = importlib.util.spec_from_file_location("env_sharpness", str(HERE / "env-sharpness.py"))
es = importlib.util.module_from_spec(spec)
spec.loader.exec_module(es)

# ------------------------------------------------------------------ blocks ----


def block_re(name):
    return re.compile(r"\n?# >>> setup-env: %s >>>\n.*?# <<< setup-env: %s <<<\n" % (name, name), re.S)


def backup(path):
    if path.exists() and not getattr(backup, "done", set()).__contains__(path):
        shutil.copy2(str(path), "%s.bak-setup-env-%s" % (path, STAMP))
        backup.done = getattr(backup, "done", set()) | {path}


def put_block(path, name, body, mode=0o644):
    """Add or replace the named block at the end of path."""
    text = path.read_text() if path.exists() else ""
    new = block_re(name).sub("", text)
    if new and not new.endswith("\n"):
        new += "\n"
    new += "\n# >>> setup-env: %s >>>\n%s\n# <<< setup-env: %s <<<\n" % (name, body.strip("\n"), name)
    if new != text:
        backup(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(new)
        if mode is not None:
            os.chmod(str(path), mode)


def drop_blocks(path):
    if not path.exists():
        return False
    text = path.read_text()
    new = re.sub(r"\n?# >>> setup-env: [\w-]+ >>>\n.*?# <<< setup-env: [\w-]+ <<<\n", "", text, flags=re.S)
    if new != text:
        backup(path)
        path.write_text(new)
        return True
    return False


def shell_rc():
    """The startup file of the login shell (bash or zsh)."""
    return HOME / (".zshrc" if Path(os.environ.get("SHELL", "")).name == "zsh" else ".bashrc")


# ----------------------------------------------------------------- actions ----

def do_ssh_defaults():
    d = HOME / ".ssh"
    d.mkdir(mode=0o700, exist_ok=True)
    os.chmod(str(d), 0o700)
    mac = "\n\tIgnoreUnknown UseKeychain\n\tUseKeychain yes\n\tAddKeysToAgent yes" if IS_MAC else ""
    # Kept last in the file: ssh uses the first value it finds, so per-host settings above still win.
    put_block(d / "config", "ssh-defaults", """Host *
	ControlMaster auto
	ControlPath ~/.ssh/cm-%%C
	ControlPersist 10m
	ServerAliveInterval 30
	ServerAliveCountMax 4%s""" % mac, mode=0o600)
    return "~/.ssh/config: ControlMaster, keep-alive" + (", keychain" if IS_MAC else "")


def do_history():
    rc = shell_rc()
    if rc.name == ".zshrc":
        body = "HISTSIZE=100000\nSAVEHIST=100000\nsetopt APPEND_HISTORY"
    else:
        body = "HISTSIZE=100000\nHISTFILESIZE=100000\nshopt -s histappend"
    put_block(rc, "history", body)
    return "~/%s: 100,000-line history" % rc.name


# (version, {(system, machine): (url, sha256)}, name of the binary inside the archive)
RELEASES = {
    "fzf": ("0.56.3", {
        ("Linux", "x86_64"): ("https://github.com/junegunn/fzf/releases/download/v0.56.3/fzf-0.56.3-linux_amd64.tar.gz",
                              "78e96a88cecfbdb3ff65df89cc47c02573407aee0edd08c87e18a8033d498fef"),
        ("Linux", "aarch64"): ("https://github.com/junegunn/fzf/releases/download/v0.56.3/fzf-0.56.3-linux_arm64.tar.gz",
                               "3ef87d66484ea05b1f4765e527ca27e8416e187ed7eeca0b1a6cfee206435c2c"),
        ("Darwin", "x86_64"): ("https://github.com/junegunn/fzf/releases/download/v0.56.3/fzf-0.56.3-darwin_amd64.tar.gz",
                               "e884d810a9d168cf3aac12b02474bf9ef5a9daf72eae8c5fe8590256dd9015e5"),
        ("Darwin", "arm64"): ("https://github.com/junegunn/fzf/releases/download/v0.56.3/fzf-0.56.3-darwin_arm64.tar.gz",
                              "e626056343fd6814a13ab28b8530f771b80dca7c8393c56b82df4229a7424d63"),
    }, "fzf"),
    "rg": ("14.1.1", {
        ("Linux", "x86_64"): ("https://github.com/BurntSushi/ripgrep/releases/download/14.1.1/"
                              "ripgrep-14.1.1-x86_64-unknown-linux-musl.tar.gz",
                              "4cf9f2741e6c465ffdb7c26f38056a59e2a2544b51f7cc128ef28337eeae4d8e"),
        ("Linux", "aarch64"): ("https://github.com/BurntSushi/ripgrep/releases/download/14.1.1/"
                               "ripgrep-14.1.1-aarch64-unknown-linux-gnu.tar.gz",
                               "c827481c4ff4ea10c9dc7a4022c8de5db34a5737cb74484d62eb94a95841ab2f"),
        ("Darwin", "x86_64"): ("https://github.com/BurntSushi/ripgrep/releases/download/14.1.1/"
                               "ripgrep-14.1.1-x86_64-apple-darwin.tar.gz",
                               "fc87e78f7cb3fea12d69072e7ef3b21509754717b746368fd40d88963630e2b3"),
        ("Darwin", "arm64"): ("https://github.com/BurntSushi/ripgrep/releases/download/14.1.1/"
                              "ripgrep-14.1.1-aarch64-apple-darwin.tar.gz",
                              "24ad76777745fbff131c8fbc466742b011f925bfa4fffa2ded6def23b5b937be"),
    }, "rg"),
}


def install_binary(name):
    version, assets, member = RELEASES[name]
    key = (platform.system(), platform.machine())
    if key not in assets:
        raise RuntimeError("no %s build for %s %s" % (name, *key))
    url, sha = assets[key]
    with urllib.request.urlopen(url, timeout=60) as r:
        data = r.read()
    if hashlib.sha256(data).hexdigest() != sha:
        raise RuntimeError("%s: checksum mismatch, not installed" % url)
    with tarfile.open(fileobj=io.BytesIO(data)) as t:
        m = next((m for m in t.getmembers() if m.isfile() and Path(m.name).name == member), None)
        if m is None:
            raise RuntimeError("%s not found in %s" % (member, url))
        content = t.extractfile(m).read()
    BIN.mkdir(parents=True, exist_ok=True)
    dest = BIN / name
    tmp = dest.with_suffix(".setup-env-tmp")
    tmp.write_bytes(content)
    os.chmod(str(tmp), 0o755)
    os.replace(str(tmp), str(dest))
    record(str(dest))
    return "%s %s" % (name, version)


def record(path):
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    have = json.loads(MANIFEST.read_text()) if MANIFEST.exists() else []
    if path not in have:
        MANIFEST.write_text(json.dumps(have + [path], indent=1))


def is_zsh():
    return Path(os.environ.get("SHELL", "")).name == "zsh"


def shell_profile():
    """Where PATH changes go: ~/.zprofile for zsh (read by every login shell, even non-interactive ones
    such as tailmon's), ~/.bashrc for bash."""
    return HOME / (".zprofile" if is_zsh() else ".bashrc")


def local_bin_on_path():
    put_block(shell_profile(), "local-bin",
              'case ":$PATH:" in *":$HOME/.local/bin:"*) ;; *) export PATH="$HOME/.local/bin:$PATH" ;; esac')


def do_user_bin(missing):
    done = [install_binary(name) for name in missing]
    local_bin_on_path()
    # fzf >= 0.48 prints its own key bindings (Ctrl+R history, Ctrl+T files, Alt+C cd).
    put_block(shell_rc(), "user-bin", 'command -v fzf >/dev/null 2>&1 && eval "$(fzf --%s 2>/dev/null)"'
              % ("zsh" if is_zsh() else "bash"))
    return "~/.local/bin: " + (", ".join(done) or "nothing new") + "; PATH and fzf keys"


def do_aliases():
    rc = shell_rc()
    put_block(rc, "aliases", """alias ll='ls -alF'
alias la='ls -A'
alias l='ls -CF'
alias ..='cd ..'
alias ...='cd ../..'
alias grep='grep --color=auto'
alias h='history | grep'
alias dfh='df -h'
alias du1='du -h -d 1'
alias path='echo "$PATH" | tr : "\\n"'""")
    return "~/%s: portable aliases" % rc.name


# ------------------------------------------------------------ macOS layer ----

def brew_exe():
    exe = shutil.which("brew") or next((p for p in ("/opt/homebrew/bin/brew", "/usr/local/bin/brew")
                                        if os.access(p, os.X_OK)), None)
    if not exe:
        raise RuntimeError("Homebrew is missing: install it from https://brew.sh (asks your password once)")
    return exe


def brew(*args, interactive=False):
    """brew install ...; interactive=True lets an installer package ask for your password."""
    cmd = [brew_exe()] + list(args)
    if interactive:
        r = subprocess.run(cmd)
        out = ""
    else:
        r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)
        out = r.stdout
    if r.returncode != 0:
        raise RuntimeError("`%s` failed: %s" % (" ".join(cmd[1:]), (out.strip().splitlines() or ["see above"])[-1]))


def do_gnu_tools():
    brew("install", "coreutils", "gnu-sed", "grep", "findutils")
    put_block(shell_profile(), "gnu-tools", """# GNU sed/grep/find/date... first, as on the Linux servers (macOS's own stay in /usr/bin)
for _d in coreutils gnu-sed grep findutils; do
  _p="${HOMEBREW_PREFIX:-/opt/homebrew}/opt/$_d/libexec/gnubin"
  [ -d "$_p" ] && PATH="$_p:$PATH"
done
unset _d _p; export PATH""")
    return "coreutils, gnu-sed, grep, findutils; gnubin first in PATH (~/%s)" % shell_profile().name


def do_fuse_sshfs():
    brew("install", "--cask", "macos-fuse-t/homebrew-cask/fuse-t", interactive=True)
    brew("install", "macos-fuse-t/homebrew-cask/fuse-t-sshfs", interactive=True)
    return "FUSE-T and sshfs"


# ------------------------------------------------------- workstation layer ----

# command, GitHub repository, folder in ~/Documents (as on the Asus), program inside it
TOOLKIT = [("tailmon", "TailScale-Monitor", "Tail-Monitor.main", "tailmon.py"),
           ("claude-explorer", "ClaudeXplorer", "ClaudeExplorer", "claude_explorer.py")]


def link(target, name):
    BIN.mkdir(parents=True, exist_ok=True)
    dest = BIN / name
    if dest.exists():
        return                                  # a working link or program: leave it
    if dest.is_symlink():                       # a broken link (its target moved): replace it
        print("  replacing broken link %s -> %s" % (dest, os.readlink(str(dest))))
        dest.unlink()
    dest.symlink_to(target)
    record(str(dest))


def do_toolkit():
    done = []
    for cmd, repo, folder, prog in TOOLKIT:
        if shutil.which(cmd) or (BIN / cmd).exists():
            continue
        d = HOME / "Documents" / folder
        if not (d / prog).exists():
            if d.exists():
                raise RuntimeError("%s exists but has no %s" % (d, prog))
            r = subprocess.run(["git", "clone", "-q", "https://github.com/tjyderrien/%s" % repo, str(d)],
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)
            if r.returncode != 0:
                raise RuntimeError("git clone %s: %s" % (repo, r.stdout.strip()[-120:]))
            done.append("cloned %s" % repo)
        link(d / prog, cmd)
        done.append(cmd)
    if not (shutil.which("env-sharpness") or (BIN / "env-sharpness").exists()):
        link(HERE / "env-sharpness.py", "env-sharpness")
        done.append("env-sharpness")
    local_bin_on_path()
    return "~/.local/bin: " + (", ".join(done) or "already linked")


def do_mounts():
    tm = shutil.which("tailmon") or str(BIN / "tailmon")
    r = subprocess.run([sys.executable, tm, "mount"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                       universal_newlines=True, env=dict(os.environ, PATH=str(BIN) + os.pathsep + os.environ["PATH"]))
    lines = [l for l in r.stdout.splitlines() if l.strip()]
    bad = [l for l in lines if "ERROR" in l]
    if r.returncode != 0 or bad:
        raise RuntimeError("; ".join(bad or lines[-1:])[:200])
    return "tailmon mount: %d machine(s); run it again after a reboot" % len(lines)


# ------------------------------------------------------------- the list ----

class Action:
    def __init__(self, name, layer, checks, what, fn, roles=es.ALL, os=None, needs=(), password=False,
                 blocks=()):
        self.name, self.layer, self.checks, self.what, self.fn = name, layer, checks, what, fn
        self.roles, self.os, self.needs, self.password, self.blocks = roles, os, needs, password, blocks

    def runs_here(self, role, layers):
        return (role in self.roles and self.layer in layers
                and (self.os is None or self.os == ("mac" if IS_MAC else "linux")))

    def fixes(self, failing):
        """The failing checks this action fixes ("*suffix" matches every host's check)."""
        return {n for n in failing for c in self.checks
                if n == c or (c.startswith("*") and n.endswith(c[1:]))}

    def applied(self):
        """True when every block it writes is already in place (some checks never reach 100 %)."""
        if not self.blocks:
            return False
        for path, block in self.blocks:
            path = path() if callable(path) else path
            if not path.exists() or "# >>> setup-env: %s >>>" % block not in path.read_text():
                return False
        return True


FZF, RG = "Fuzzy history/file search (fzf)", "rg (fast search)"
ACTIONS = [
    Action("ssh-defaults", "core", ["Connection sharing (ControlMaster)", "Keep-alive (ServerAliveInterval)"]
           + (["Keys loaded in an agent"] if IS_MAC else []),
           "ControlMaster + keep-alive for every host in ~/.ssh/config", lambda f: do_ssh_defaults(),
           blocks=[(HOME / ".ssh" / "config", "ssh-defaults")]),
    Action("history", "core", ["Long shell history"], "100,000-line shell history", lambda f: do_history(),
           blocks=[(shell_rc, "history")]),
    Action("user-bin", "core", [FZF, RG], "fzf and ripgrep in ~/.local/bin",
           lambda f: do_user_bin([n for n, c in (("fzf", FZF), ("rg", RG)) if c in f]),
           blocks=[(shell_rc, "user-bin")]),
    Action("aliases", "core", ["Personal aliases/functions"], "portable aliases", lambda f: do_aliases(),
           blocks=[(shell_rc, "aliases")]),
    Action("gnu-tools", "macos", ["GNU coreutils/sed/grep/find (as on the servers)"],
           "GNU coreutils/sed/grep/findutils, first in PATH", lambda f: do_gnu_tools(), os="mac"),
    Action("bash", "macos", ["bash >= 4 (as on the servers)"], "bash 5 (macOS has 3.2)",
           lambda f: brew("install", "bash") or "bash", os="mac"),
    Action("rsync", "macos", ["rsync 3.x"], "rsync 3 (macOS has openrsync)",
           lambda f: brew("install", "rsync") or "rsync", os="mac"),
    Action("fuse-sshfs", "macos", ["sshfs installed"], "FUSE-T + sshfs (no kernel extension)",
           lambda f: do_fuse_sshfs(), os="mac", roles=es.WS, password=True),
    Action("xquartz", "macos", ["X server for `ssh -X` graphics"], "XQuartz, for `ssh -X`",
           lambda f: brew("install", "--cask", "xquartz", interactive=True) or "XQuartz",
           os="mac", roles=es.WS, password=True),
    Action("toolkit", "workstation", ["tailmon (monitor, search, grep, mount the tailnet)",
                                      "claude-explorer (`tailmon claude|todo|dispatch`)",
                                      "env-sharpness on the PATH (`tailmon sharpness`)"],
           "clone + link tailmon, claude-explorer; link env-sharpness", lambda f: do_toolkit(), roles=es.WS),
    Action("mounts", "workstation", ["*: mounted locally", "Mount root for `tailmon mount` (%s)" % es.MOUNT_ROOT_LABEL],
           "`tailmon mount`: every server under %s" % es.MOUNT_ROOT_LABEL, lambda f: do_mounts(),
           roles=es.WS, needs=("fuse-sshfs", "toolkit")),
]
BY_NAME = {a.name: a for a in ACTIONS}
LAYERS = ("core", "macos", "workstation")


# -------------------------------------------------------------------- plan ----

def measure(args):
    cmd = [sys.executable, str(HERE / "env-sharpness.py"), "--json", "-"]
    for flag in ("role", "target", "hosts"):
        if getattr(args, flag) is not None:
            cmd += ["--" + flag, str(getattr(args, flag))]
    if args.offline:
        cmd.append("--offline")
    env = dict(os.environ)  # measure with the PATH a new shell will have
    extra = [str(BIN)]
    if IS_MAC:  # what the gnu-tools block puts first
        prefix = os.environ.get("HOMEBREW_PREFIX", "/opt/homebrew")
        extra = ["%s/opt/%s/libexec/gnubin" % (prefix, d) for d in ("coreutils", "gnu-sed", "grep", "findutils")
                 ] + [prefix + "/bin"] + extra
    have = env.get("PATH", "").split(os.pathsep)
    env["PATH"] = os.pathsep.join([d for d in extra if d not in have and os.path.isdir(d)] + have)
    out = subprocess.run(cmd, stdout=subprocess.PIPE, universal_newlines=True, check=True, env=env).stdout
    return json.loads(out.strip().splitlines()[-1])


def predicted(checks, fixed_names):
    return es.score([dict(c, value=1.0) if c["name"] in fixed_names else c for c in checks])


def plan(data, everything, layers):
    """Greedy: take the action (with the actions it needs) that raises the score most, until the target
    is exceeded. Returns [(action, gain, score after)], final score."""
    checks, target = data["checks"], data["target"]
    failing = {c["name"] for c in checks if c["value"] < 0.999}
    here = {a.name for a in ACTIONS if a.runs_here(data["role"], layers)}

    def bundle(a, taken):
        out = []
        for n in a.needs:
            dep = BY_NAME[n]
            if n in taken or not dep.fixes(failing) or (dep.os and dep.os != ("mac" if IS_MAC else "linux")):
                continue  # already planned, already fine, or not needed on this OS
            if n not in here:
                return None
            sub = bundle(dep, taken)
            if sub is None:
                return None
            out += [x for x in sub if x not in out]
        return out + [a]

    todo = [BY_NAME[n] for n in here if BY_NAME[n].fixes(failing) and not BY_NAME[n].applied()]
    chosen, fixed, score = [], set(), data["overall"]
    while todo and (everything or score <= target):
        taken = {a.name for a, _, _ in chosen}
        options = [(b, predicted(checks, fixed.union(*(x.fixes(failing) for x in b))))
                   for b in (bundle(a, taken) for a in todo) if b]
        if not options:
            break
        best, _ = max(options, key=lambda o: (o[1], -len(o[0])))
        for a in best:
            fixed |= a.fixes(failing)
            new = predicted(checks, fixed)
            chosen.append((a, new - score, new))
            score = new
            if a in todo:
                todo.remove(a)
    return chosen, score


def undo():
    files = (HOME / ".ssh" / "config", HOME / ".bashrc", HOME / ".zshrc", HOME / ".zprofile")
    changed = [str(p) for p in files if drop_blocks(p)]
    removed = []
    if MANIFEST.exists():
        for p in json.loads(MANIFEST.read_text()):
            if os.path.lexists(p):
                os.remove(p)
                removed.append(p)
        MANIFEST.unlink()
    print("Blocks removed from: " + (", ".join(changed) or "nothing"))
    print("Binaries and links removed: " + (", ".join(removed) or "none"))
    print("Homebrew packages and cloned repositories are kept (`brew uninstall ...` to remove them).")
    if changed:
        print("Backups: <file>.bak-setup-env-%s" % STAMP)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--apply", action="store_true", help="make the changes (default: only show the plan)")
    ap.add_argument("--all", action="store_true", help="every fix that applies here, even beyond the target")
    ap.add_argument("--layers", default=",".join(LAYERS),
                    help="comma-separated layers to use (default: %(default)s; `core` alone on a cluster)")
    ap.add_argument("--role", choices=es.ROLES, help="override the guessed role")
    ap.add_argument("--target", type=float, help="score to exceed (default: by role, %s)"
                    % ", ".join("%s %d" % kv for kv in es.TARGETS.items()))
    ap.add_argument("--hosts", help="servers to measure against, as for env-sharpness.py")
    ap.add_argument("--offline", action="store_true", help="measure without network checks")
    ap.add_argument("--undo", action="store_true", help="remove every block, binary and link this script added")
    args = ap.parse_args()
    if args.undo:
        return undo()
    layers = [l for l in args.layers.split(",") if l]
    unknown = set(layers) - set(LAYERS)
    if unknown:
        ap.error("unknown layer(s): %s (choose from %s)" % (", ".join(sorted(unknown)), ", ".join(LAYERS)))

    data = measure(args)
    print("%s: %s, score %.1f, target %g" % (data["machine"], data["role"], data["overall"], data["target"]))
    chosen, final = plan(data, args.all, layers)
    if not chosen:
        if args.all:
            print("Every fix that applies here is already in place.")
        elif data["overall"] > data["target"]:
            print("Above target: nothing to do. (--all applies every fix anyway.)")
        else:
            print("Below target, and these layers (%s) have nothing left to fix here. Remaining gaps:"
                  % ", ".join(layers))
            for c in sorted((c for c in data["checks"] if c["fix"]), key=lambda c: -c["weight"] * (1 - c["value"]))[:5]:
                print("  - %s: %s" % (c["name"], c["fix"]))
        return

    print("\nPlan (smallest set of fixes that clears the target):" if not args.all else "\nPlan:")
    for a, gain, score in chosen:
        print("  %-11s %-12s %-56s +%4.1f -> %5.1f%s" % (a.layer, a.name, a.what, gain, score,
                                                       "  (asks your password)" if a.password else ""))
    if final <= data["target"]:
        print("  Even with all of these the predicted score (%.1f) stays at or below the target." % final)
    if not args.apply:
        print("\nNothing changed. Run again with --apply to do it.")
        return

    print()
    failing = {c["name"] for c in data["checks"] if c["value"] < 0.999}
    tty = sys.stdin.isatty() and sys.stdout.isatty()
    failed = set()
    for a, _gain, _score in chosen:
        if failed & set(a.needs):
            print("  SKIP  %-12s needs %s" % (a.name, ", ".join(sorted(failed & set(a.needs)))))
            failed.add(a.name)
            continue
        if a.password and not tty:
            print("  SKIP  %-12s asks for your password: run setup-env.py in a terminal on this machine" % a.name)
            failed.add(a.name)
            continue
        try:
            print("  done  %-12s %s" % (a.name, a.fn(failing)))
        except Exception as e:  # noqa: BLE001 - report and carry on with the other fixes
            print("  FAIL  %-12s %s" % (a.name, e))
            failed.add(a.name)
    after = measure(args)
    print("\nScore %.1f -> %.1f (target %g). Open a new shell for the shell changes to apply."
          % (data["overall"], after["overall"], after["target"]))
    if getattr(backup, "done", None):
        print("Backups: " + ", ".join("%s.bak-setup-env-%s" % (p, STAMP) for p in sorted(backup.done)))


if __name__ == "__main__":
    main()
