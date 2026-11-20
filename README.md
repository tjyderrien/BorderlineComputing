# BorderlineComputing
Suite of tools that are necessary to prolong lifetime of computers to infinite.

## What I'm listening to

<!-- SPOTIFY:START -->
Nothing played recently.
<!-- SPOTIFY:END -->

## Tools

### `free-disk-space.sh`

Reclaims space on a full root partition on Ubuntu, without touching personal files.
It only removes data the system can regenerate: caches, logs, old package versions and the Trash.

#### Usage

```bash
./free-disk-space.sh           # dry run: shows sizes and what would be removed
./free-disk-space.sh --apply   # actually do it (asks for your sudo password once)
```

Always start with the dry run. It prints the root filesystem usage, each step with its current size,
and the exact command it would run. Nothing is deleted without `--apply`.

#### What it cleans

| # | Target | Command | Typical gain |
|---|--------|---------|--------------|
| 1 | apt package cache (`/var/cache/apt`) | `apt-get clean` | ~1.2 GB |
| 2 | systemd journal, trimmed to 200 MB | `journalctl --vacuum-size=200M` | ~1.8 GB |
| 3 | Disabled snap revisions | `snap remove <name> --revision=<rev>` | several GB |
| 4 | Unused apt packages, incl. old kernels | `apt-get autoremove --purge -y` | varies |
| 5 | Anaconda package cache (`~/anaconda3/pkgs`) | `conda clean --all -y` | ~2 GB |
| 6 | pip cache, Trash, thumbnail cache | `pip cache purge`, `rm -rf` | varies |

It also sets `snap set system refresh.retain=2` so snap keeps fewer old revisions in future (the default is 3).

Step 5 is skipped if `~/anaconda3/bin/conda` does not exist. `~/Documents` and `~/Downloads` are never touched.

#### What it leaves to you

At the end the script lists bigger items it does not remove automatically, because deleting them is a judgement call:

- Browser caches under `~/snap/firefox/common` and `~/snap/chromium/common`. Clear them from each browser, or with `rm -rf ~/snap/*/common/.cache`.
- Old installers in `~/Downloads/Softwares`.
- The Android emulator in `~/Android/Sdk/emulator`, if you don't use it.
- Old Claude Code versions in `~/.local/share/claude/versions` (keep the newest).

#### Requirements and caveats

- Ubuntu/Debian with `apt`, `systemd` and `snap`. Steps whose tools are missing just print an error and the script carries on.
- Needs `sudo` for the apt, journal and snap steps.
- Step 4 removes any package apt considers unused, including old kernels. Check the list in the dry run first; the running kernel (`uname -r`) is never removed.
- Emptying the Trash is permanent.
- Some sizes, paths and notes (the `/dev/sda6` root, `/media/thibault/Data`, the 5.15 kernel) are specific to the machine the script was written for. Adjust them before using it elsewhere.

### `TurnOffIPv6.sh`

Turns off IPv6 on the Wi-Fi interface. Useful when Google Scholar fails to load because of an IPv4/IPv6 conflict.

#### Usage

```bash
bash TurnOffIPv6.sh   # asks for your sudo password
```

It runs `sudo sysctl -w net.ipv6.conf.wlan0.disable_ipv6=1` on the `wlan0` interface.

#### Caveats

- The interface name is hard-coded to `wlan0`. Check yours with `ip link` and edit the script if it differs.
- The change lasts until the next reboot. To turn IPv6 back on before that:

  ```bash
  sudo sysctl -w net.ipv6.conf.wlan0.disable_ipv6=0
  ```

### Spotify integration

Two parts tell people what I am listening to:

- **Commit messages.** The `.githooks/commit-msg` hook adds a trailer with the track playing in the Spotify desktop app, for example
  `Listening-To: Daft Punk - Veridis Quo <https://open.spotify.com/track/...>`.
  It reads Spotify over D-Bus (MPRIS), so it needs no account setup. Nothing is added when Spotify is closed, paused or playing an ad, and the hook never blocks a commit.
- **README.** The `Spotify now playing` GitHub Action runs every 30 minutes, calls the Spotify Web API and rewrites the block between the `SPOTIFY` markers above with the current track and the last 5 played. It commits only when the block changes.

#### Setup

Turn on the commit hook in each clone (it needs `busctl` and `python3`):

```bash
git config core.hooksPath .githooks
SPOTIFY_TRAILER=off git commit ...   # skip it for one commit
```

For the README action:

1. Create an app at <https://developer.spotify.com/dashboard> and add `http://127.0.0.1:8888/callback` as a redirect URI.
2. Get a refresh token (opens a browser, read-only scopes):

   ```bash
   python3 spotify/get_refresh_token.py
   ```

3. Store the three values as repository secrets:

   ```bash
   gh secret set SPOTIFY_CLIENT_ID
   gh secret set SPOTIFY_CLIENT_SECRET
   gh secret set SPOTIFY_REFRESH_TOKEN
   ```

4. Run it once from the Actions tab (`Spotify now playing` > Run workflow) or with `gh workflow run spotify-now-playing.yml`.

#### Caveats

- The bot pushes to `main`, so run `git pull --rebase` before pushing your own work.
- GitHub may delay scheduled runs by several minutes, so "Now playing" can lag.
- Until the secrets are set, the action only logs a warning.

### `env-sharpness.py`

Measures how "sharp" a computer is for working on remote Linux servers (FZU workstations, clusters), and lists what to fix. A sharp machine gets you from intent to a working shell, file or remote desktop with no password, no retyped IP address, no dropped connection and no command that behaves differently from the server.

It uses only the Python standard library and runs on Linux and macOS.

#### Usage

```bash
./env-sharpness.py --hosts biatri-1,biatri-2,luzicka   # servers to check (default: online Linux tailnet machines)
./env-sharpness.py --role server                        # judge it as a server (default: guessed)
./env-sharpness.py --check                              # exit status 1 if not above the target (for scripts)
./env-sharpness.py -v                                   # also list the checks that pass
./env-sharpness.py --offline                            # no network checks
./env-sharpness.py --json asus.json                     # save the results
./env-sharpness.py --compare asus.json mac.json         # differences between two machines, largest first
```

Without `--hosts` it checks the online Linux machines of your tailnet, or the hosts in `~/.ssh/config` when Tailscale is not running. `--json -` prints only the JSON; `tailmon sharpness` uses it to score every machine of the tailnet at once.

To compare two machines, run it on each one with the same `--hosts` and `--json`, copy one JSON file to the other machine, and run `--compare`. Run it from a normal terminal, not through `ssh`, so it sees your real ssh-agent, PATH and mounts.

#### What it measures

Each check scores 0-100 %. Checks are weighted inside seven categories, and the overall score is the mean of the categories.

| Category | Checks |
|---|---|
| Reaching the servers | Tailscale/VPN running; TCP connect time to each server |
| Logging in without friction | SSH key, key permissions, agent; `ssh -o BatchMode=yes <host> true` works with no password, and how long it takes |
| SSH ergonomics | Host aliases for every server, ControlMaster, ServerAliveInterval, tmux/screen/mosh, X server, VNC viewer |
| Remote files | sshfs, rsync 3.x, each server mounted locally and how fast the mount answers |
| Toolchain parity | git, vim, python3, conda, gnuplot, rg, jq, htop, gh, claude; GNU (not BSD) sed/grep/find/date; bash 4 or later |
| Shell | bash as login shell, history size, ssh commands in history, personal aliases, fzf, vim with colours |
| Your toolkit | tailmon, claude-explorer, env-sharpness on the PATH; `/media/tailscale` ready for `tailmon mount`; the same keyboard layouts everywhere (French AZERTY PC first, Czech) and, on macOS, an ISO keyboard type |

#### Roles and targets

Machines do not need to be identical, so each is judged on what it is for, and has a score to exceed:

| Role | What it is | Judged on | Target |
|---|---|---|---|
| `workstation` | where you sit | everything, including reaching, logging in to and mounting the other machines | 90 |
| `server` | a machine you work *on* | SSH settings, keys, tools, shell; not VNC, X or mounts | 80 |
| `hpc` | a shared computing centre you don't administer (IT4I...) | only what one user can set up in `$HOME`: no Tailscale, no conda/gnuplot (they come from modules) | 70 |

The role is guessed: a Mac or a machine running a display manager is a workstation; a machine with modules or a batch scheduler (`sbatch`, `qsub`) where you are not in `sudo`/`wheel` is `hpc`; anything else is a server. Override it with `--role`, and the target with `--target`.

The network checks only open a TCP connection and run `true` on each server. Nothing on the computer is changed.

#### Typical Mac weaknesses it finds

macOS ships BSD `sed`/`date`/`find`, bash 3.2 and an old rsync, so commands copied from the servers behave differently. It has no sshfs without macFUSE or FUSE-T, uses zsh by default (bash aliases do not carry over), and starts with an empty shell history. The script prints the `brew` command for each of these.

### `setup-env.py`

Brings a machine above its sharpness target with as few changes as possible. It measures the machine with `env-sharpness.py` (which must sit next to it), then picks, among the fixes it knows, the smallest set that lifts the score above the role's target, biggest gain first, and stops there. A machine already above its target is left alone: machines may differ on purpose, and only the gaps that hurt get closed.

#### Usage

```bash
./setup-env.py                          # plan: what would be done, and the predicted score
./setup-env.py --apply                  # do it, then measure again
./setup-env.py --all --apply            # every fix that applies here, whatever the target
./setup-env.py --only vim,gnu-tools --apply   # just these fixes, whatever the target
./setup-env.py --layers core            # home-directory fixes only (computing centres)
./setup-env.py --role hpc --target 75   # same options as env-sharpness.py
./setup-env.py --undo                   # remove every block, binary and link it added
```

Nothing changes without `--apply`.

#### What it can fix

Fixes come in three layers. All of them are allowed by default; `--layers` restricts them.

| Layer | Fix | What it does |
|---|---|---|
| core | `ssh-defaults` | `Host *` block at the end of `~/.ssh/config`: ControlMaster, ControlPersist 10m, ServerAliveInterval 30 (plus keychain on macOS) |
| core | `history` | 100,000-line shell history |
| core | `user-bin` | fzf 0.56.3 and ripgrep 14.1.1 in `~/.local/bin`, downloaded from their GitHub releases and checked against pinned SHA-256 sums, plus the fzf key bindings |
| core | `aliases` | ten portable aliases (`ll`, `la`, `..`, `h`, `path`...) |
| core | `vim` | `~/.vimrc` with `syntax on` and Vim's own defaults (incremental search, ruler, filetype indent), as Ubuntu has them; macOS's vim has neither |
| macos | `gnu-tools` | `brew install coreutils gnu-sed grep findutils`, and their `gnubin` directories first in PATH |
| macos | `bash`, `rsync` | bash 5 and rsync 3 from Homebrew (macOS ships bash 3.2 and openrsync) |
| macos | `fuse-sshfs` | FUSE-T and its sshfs: no kernel extension, no reboot. Asks for your password |
| macos | `xquartz` | XQuartz, for `ssh -X`. Asks for your password |
| workstation | `toolkit` | clones TailScale-Monitor and ClaudeXplorer into `~/Documents` (if missing) and links `tailmon`, `claude-explorer` and `env-sharpness` into `~/.local/bin` |
| workstation | `mounts` | `tailmon mount`: every server under `/media/tailscale`, or `~/tailscale` on macOS. Needs `fuse-sshfs` on macOS and `toolkit`, which are planned with it |
| workstation | `keyboard` | French AZERTY (PC) as default layout plus Czech: GNOME input sources on Linux; on macOS the *French – PC* input source instead of Apple's *French*, which places symbols differently |

The core layer touches only your home directory, with no sudo and no background service, so it is meant for shared computing centres too. The macos layer needs [Homebrew](https://brew.sh), which asks for your password once when you install it. Fixes that ask for a password are skipped, with a note, when the script is not run from a terminal.

Each change to a file is a block between `# >>> setup-env: <name> >>>` and `# <<< setup-env: <name> <<<` (`"` instead of `#` in `~/.vimrc`), so you can see it, and `--undo` removes it with the links and binaries. Homebrew packages and cloned repositories stay. Every file is backed up as `<file>.bak-setup-env-<date>` before it is changed. PATH changes go to `~/.zprofile` with zsh, so that non-interactive login shells, such as `tailmon sharpness`, see them too.

#### Caveats

- Run it from a normal terminal on the machine itself, from a clone of this repository. It needs Python 3.6 or later.
- With `gnu-tools`, `sed`, `grep`, `find`, `date`... are the GNU ones in your shells. macOS's own stay in `/usr/bin` for scripts that call them by full path.
- Mounts do not survive a reboot: run `tailmon mount` again.
- `user-bin` needs to reach github.com. On a cluster without Internet access that fix fails and the others still apply.
- Not yet tried on IT4I. It only writes to `$HOME`, but check the plan there before `--apply`.
