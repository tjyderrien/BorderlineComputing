#!/usr/bin/env python3
"""Bring this machine above its sharpness target, with as few changes as possible.

env-sharpness.py measures the machine and gives it a role (workstation, server or hpc) and a
target score. This script picks, among the fixes it knows, the smallest set that lifts the score
above the target, biggest gain first, and stops there. A machine already above its target is left
alone: machines may differ on purpose, and only the gaps that hurt get closed.

Core layer only, for now: everything happens in your home directory, with no sudo and no
background service, so it is also allowed on shared computing centres (IT4I...):

    ssh-defaults  ControlMaster and keep-alive for every host, in ~/.ssh/config
    history       100,000-line shell history
    user-bin      fzf and ripgrep binaries in ~/.local/bin (pinned versions, SHA-256 checked)
    aliases       a few portable aliases (ll, la, .., h...)

Each change to a file is a block between "# >>> setup-env: <name> >>>" markers, so you can see it,
and --undo removes it. Files are backed up before their first change.

    ./setup-env.py                     # plan: what would be done, and the predicted score
    ./setup-env.py --apply             # do it, then measure again
    ./setup-env.py --all --apply       # every core fix, whatever the target
    ./setup-env.py --role hpc --target 75
    ./setup-env.py --undo              # remove every block and binary it added

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


def do_user_bin(missing):
    done = []
    for name in missing:
        done.append(install_binary(name))
    rc = shell_rc()
    sh = "zsh" if rc.name == ".zshrc" else "bash"
    # fzf >= 0.48 prints its own key bindings (Ctrl+R history, Ctrl+T files, Alt+C cd).
    put_block(rc, "user-bin", """case ":$PATH:" in *":$HOME/.local/bin:"*) ;; *) export PATH="$HOME/.local/bin:$PATH" ;; esac
command -v fzf >/dev/null 2>&1 && eval "$(fzf --%s 2>/dev/null)"
""" % sh)
    return "~/.local/bin: " + ", ".join(done) + "; ~/%s: PATH and fzf keys" % rc.name


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


# id -> (checks it fixes, roles, what it does, function taking the list of failing checks)
ACTIONS = [
    ("ssh-defaults", ["Connection sharing (ControlMaster)", "Keep-alive (ServerAliveInterval)"]
     + (["Keys loaded in an agent"] if IS_MAC else []), es.ALL,
     "ControlMaster + keep-alive for every host in ~/.ssh/config", lambda f: do_ssh_defaults()),
    ("history", ["Long shell history"], es.ALL, "100,000-line shell history", lambda f: do_history()),
    ("user-bin", ["Fuzzy history/file search (fzf)", "rg (fast search)"], es.ALL,
     "fzf and ripgrep in ~/.local/bin",
     lambda f: do_user_bin([n for n, c in (("fzf", "Fuzzy history/file search (fzf)"),
                                            ("rg", "rg (fast search)")) if c in f])),
    ("aliases", ["Personal aliases/functions"], es.ALL, "portable aliases", lambda f: do_aliases()),
]


# Blocks each action writes: an action whose blocks are all in place is not planned again.
BLOCKS = {"ssh-defaults": [(HOME / ".ssh" / "config", "ssh-defaults")],
          "history": [(None, "history")], "user-bin": [(None, "user-bin")], "aliases": [(None, "aliases")]}


def applied(name):
    for path, block in BLOCKS[name]:
        path = path or shell_rc()
        if not path.exists() or "# >>> setup-env: %s >>>" % block not in path.read_text():
            return False
    return True


# -------------------------------------------------------------------- plan ----

def measure(args):
    cmd = [sys.executable, str(HERE / "env-sharpness.py"), "--json", "-"]
    for flag in ("role", "target", "hosts"):
        if getattr(args, flag) is not None:
            cmd += ["--" + flag, str(getattr(args, flag))]
    if args.offline:
        cmd.append("--offline")
    env = dict(os.environ)  # measure with the PATH a new shell will have (the user-bin block adds ~/.local/bin)
    if str(BIN) not in env.get("PATH", "").split(os.pathsep):
        env["PATH"] = str(BIN) + os.pathsep + env.get("PATH", "")
    out = subprocess.run(cmd, stdout=subprocess.PIPE, universal_newlines=True, check=True, env=env).stdout
    return json.loads(out.strip().splitlines()[-1])


def predicted(checks, fixed_names):
    return es.score([dict(c, value=1.0) if c["name"] in fixed_names else c for c in checks])


def plan(data, everything):
    """Greedy: add the action with the biggest score gain until the target is exceeded."""
    checks, target = data["checks"], data["target"]
    failing = {c["name"] for c in checks if c["value"] < 0.999}
    todo = [a for a in ACTIONS if data["role"] in a[2] and set(a[1]) & failing and not applied(a[0])]
    chosen, fixed, score = [], set(), data["overall"]
    while todo and (everything or score <= target):
        best = max(todo, key=lambda a: predicted(checks, fixed | set(a[1])))
        todo.remove(best)
        fixed |= set(best[1]) & failing
        new = predicted(checks, fixed)
        chosen.append((best, new - score, new))
        score = new
    return chosen, score


def undo():
    changed = [str(p) for p in (HOME / ".ssh" / "config", HOME / ".bashrc", HOME / ".zshrc") if drop_blocks(p)]
    removed = []
    if MANIFEST.exists():
        for p in json.loads(MANIFEST.read_text()):
            if os.path.exists(p):
                os.remove(p)
                removed.append(p)
        MANIFEST.unlink()
    print("Blocks removed from: " + (", ".join(changed) or "nothing"))
    print("Binaries removed: " + (", ".join(removed) or "none"))
    if changed:
        print("Backups: <file>.bak-setup-env-%s" % STAMP)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--apply", action="store_true", help="make the changes (default: only show the plan)")
    ap.add_argument("--all", action="store_true", help="every core fix, even beyond the target")
    ap.add_argument("--role", choices=es.ROLES, help="override the guessed role")
    ap.add_argument("--target", type=float, help="score to exceed (default: by role, %s)"
                    % ", ".join("%s %d" % kv for kv in es.TARGETS.items()))
    ap.add_argument("--hosts", help="servers to measure against, as for env-sharpness.py")
    ap.add_argument("--offline", action="store_true", help="measure without network checks")
    ap.add_argument("--undo", action="store_true", help="remove every block and binary this script added")
    args = ap.parse_args()
    if args.undo:
        return undo()

    data = measure(args)
    print("%s: %s, score %.1f, target %g" % (data["machine"], data["role"], data["overall"], data["target"]))
    chosen, final = plan(data, args.all)
    if not chosen:
        if args.all:
            print("Every core fix that applies here is already in place.")
        elif data["overall"] > data["target"]:
            print("Above target: nothing to do. (--all applies every core fix anyway.)")
        else:
            print("Below target, and the core layer has nothing left to fix here. Remaining gaps:")
            for c in sorted((c for c in data["checks"] if c["fix"]), key=lambda c: -c["weight"] * (1 - c["value"]))[:5]:
                print("  - %s: %s" % (c["name"], c["fix"]))
        return

    print("\nPlan (smallest set of core fixes that clears the target):" if not args.all else "\nPlan:")
    for (name, _checks, _roles, what, _fn), gain, score in chosen:
        print("  %-13s %-58s +%4.1f -> %5.1f" % (name, what, gain, score))
    if final <= data["target"]:
        print("  Even with all of these the predicted score (%.1f) stays at or below the target: the rest needs "
              "sudo or another layer." % final)
    if not args.apply:
        print("\nNothing changed. Run again with --apply to do it.")
        return

    print()
    failing = {c["name"] for c in data["checks"] if c["value"] < 0.999}
    for (name, _checks, _roles, _what, fn), _gain, _score in chosen:
        try:
            print("  done  %-13s %s" % (name, fn(failing)))
        except Exception as e:  # noqa: BLE001 - report and carry on with the other fixes
            print("  FAIL  %-13s %s" % (name, e))
    after = measure(args)
    print("\nScore %.1f -> %.1f (target %g). Open a new shell for the shell changes to apply."
          % (data["overall"], after["overall"], after["target"]))
    if getattr(backup, "done", None):
        print("Backups: " + ", ".join("%s.bak-setup-env-%s" % (p, STAMP) for p in sorted(backup.done)))


if __name__ == "__main__":
    main()
