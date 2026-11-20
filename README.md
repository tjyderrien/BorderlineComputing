# BorderlineComputing

Suite of tools that are necessary to prolong lifetime of computers to infinite.

Small scripts that keep computers usable for longer: they free disk space, work around network quirks, make a PC keyboard behave on a Mac, show what you're listening to on Spotify, and check and fix a machine's setup for working on remote Linux servers.

> *Inspiration: in 2024, after a memory chip failed in Voyager 1's 1970s flight computer, NASA engineers moved its code to other parts of memory, from 24 billion km away. Every command took 22.5 hours to arrive. I wish I could bring back Voyager I to Earth with that code.*

## Contents

- [Tools at a glance](#tools-at-a-glance)
- [What I'm listening to](#what-im-listening-to)
- [Disk and network](#disk-and-network)
  - [`free-disk-space.sh`](#free-disk-spacesh): reclaim space on a full Ubuntu root partition
  - [`TurnOffIPv6.sh`](#turnoffipv6sh): turn off IPv6 on Wi-Fi
- [Keyboard and devices](#keyboard-and-devices)
  - [`mac-printscreen.sh`](#mac-printscreensh): the Print Screen key on a Mac
  - [`bluetooth-switch.sh`](#bluetooth-switchsh): Bluetooth on/off with auto-reconnect
- [Working on remote servers](#working-on-remote-servers)
  - [`env-sharpness.py`](#env-sharpnesspy): score a machine for remote work
  - [`setup-env.py`](#setup-envpy): apply the smallest set of fixes
- [Spotify integration](#spotify-integration)
- [Related projects](#related-projects)
- [License](#license)

## Tools at a glance

| Tool | Runs on | What it does | Changes anything? |
|---|---|---|---|
| [`free-disk-space.sh`](#free-disk-spacesh) | Ubuntu/Debian | Clears caches, logs, old packages and the Trash | Only with `--apply` |
| [`TurnOffIPv6.sh`](#turnoffipv6sh) | Linux | Turns off IPv6 on `wlan0` until the next reboot | Yes (sudo) |
| [`mac-printscreen.sh`](#mac-printscreensh) | macOS + Karabiner-Elements | Print Screen and Shift+Print Screen take screenshots | Yes; `--remove` undoes it |
| [`bluetooth-switch.sh`](#bluetooth-switchsh) | Linux (BlueZ) | Toggles Bluetooth and keeps chosen devices connected | Yes (sudo) |
| [`env-sharpness.py`](#env-sharpnesspy) | Linux, macOS | Scores how ready a machine is for remote work | No, read-only |
| [`setup-env.py`](#setup-envpy) | Linux, macOS | Closes the gaps `env-sharpness.py` finds | Only with `--apply`; `--undo` |
| [Spotify integration](#spotify-integration) | GitHub, Linux | Now-playing in this README and in commit messages | — |

## What I'm listening to

<!-- SPOTIFY:START -->
Nothing played recently.
<!-- SPOTIFY:END -->

---

## Disk and network

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

- It also sets `snap set system refresh.retain=2`, so snap keeps fewer old revisions in future (the default is 3).
- Step 5 is skipped if `~/anaconda3/bin/conda` does not exist.
- `~/Documents` and `~/Downloads` are never touched.

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

---

## Keyboard and devices

### `mac-printscreen.sh`

Makes the Print Screen key of a PC keyboard take screenshots on macOS, as it does on Windows.

| Key | Takes | macOS equivalent |
|---|---|---|
| Print Screen | the whole screen | ⌘⇧3 |
| Shift + Print Screen | an area: drag a rectangle; or a window: press Space, then click the app | ⌘⇧4 |

Screenshots go where macOS puts them: the Desktop by default (⌘⇧5 → Options to change it).

#### Usage

```bash
./mac-printscreen.sh            # add the two rules
./mac-printscreen.sh --remove   # take them out again
```

#### How it works

macOS has no action for Print Screen, so the script adds two rules to [Karabiner-Elements](https://karabiner-elements.pqrs.org), which rewrites the key into the macOS shortcut.

- The rules go into the selected profile of `~/.config/karabiner/karabiner.json`. Karabiner reloads the file by itself.
- The file is copied to `karabiner.json.<date>.bak` first.
- Running the script twice does not add the rules twice: they are tagged `[BorderlineComputing print screen]`, and old copies are replaced.

#### Requirements

- macOS with Karabiner-Elements installed and opened once (driver and input monitoring allowed): `brew install --cask karabiner-elements`.
- `python3` (comes with the Xcode command line tools).

> **Geek corner.** On the Mac this was written on, the Karabiner profile holds **4,034 rules but only 65 distinct ones**: the 63 Windows-style shortcuts (Ctrl+C, Home/End, Win+L…) are each present exactly **64 = 2⁶ times**, plus the 2 Print Screen rules. That is 98.4 % duplicates in a 10.9 MB `karabiner.json`. A rule set that got imported again and again, apparently doubling each time. Karabiner doesn't mind: the first matching rule wins and the other 63 copies are never reached.

### `bluetooth-switch.sh`

Turns Bluetooth on or off with one command, and keeps chosen devices connected while it is on.

#### Usage

```bash
./bluetooth-switch.sh             # toggle: on (and open blueman-manager) or off
./bluetooth-switch.sh --monitor   # power on, then reconnect the devices every 15 s
```

#### How it works

- **Off**: blocks the radio with `rfkill`, stops the `bluetooth` service and closes blueman.
- **On**: unblocks the radio, starts the service, opens `blueman-manager`, and every 15 s reconnects any device in `DEVICES` that has dropped, for as long as blueman stays open.

#### Caveats

- Linux with BlueZ (`bluetoothctl`), `rfkill`, systemd and blueman. Needs `sudo` to start or stop the service.
- The device list (an audio mixer and a speaker) and the 15 s interval are set at the top of the script: edit `DEVICES` and `RECONNECT_INTERVAL` for your own devices.

---

## Working on remote servers

Two scripts that work together: `env-sharpness.py` measures, `setup-env.py` fixes.

### `env-sharpness.py`

Measures how "sharp" a computer is for working on remote Linux servers (workstations, clusters), and lists what to fix. A sharp machine gets you from intent to a working shell, file or remote desktop with:

- no password,
- no retyped IP address,
- no dropped connection,
- no command that behaves differently from the server.

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

- Without `--hosts` it checks the online Linux machines of your tailnet, or the hosts in `~/.ssh/config` when Tailscale is not running.
- `--json -` prints only the JSON; `tailmon sharpness` uses it to score every machine of the tailnet at once.
- **Comparing two machines:** run it on each one with the same `--hosts` and `--json`, copy one JSON file to the other machine, and run `--compare`.
- Run it from a normal terminal, not through `ssh`, so it sees your real ssh-agent, PATH and mounts.

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

The network checks only open a TCP connection and run `true` on each server. Nothing on the computer is changed.

#### Roles and targets

Machines do not need to be identical, so each is judged on what it is for, and has a score to exceed:

| Role | What it is | Judged on | Target |
|---|---|---|---|
| `workstation` | where you sit | everything, including reaching, logging in to and mounting the other machines | 90 |
| `server` | a machine you work *on* | SSH settings, keys, tools, shell; not VNC, X or mounts | 80 |
| `hpc` | a shared computing centre you don't administer (IT4I...) | only what one user can set up in `$HOME`: no Tailscale, no conda/gnuplot (they come from modules) | 70 |

The role is guessed, and can be overridden with `--role` (and the target with `--target`):

- a Mac, or a machine running a display manager → `workstation`;
- a machine with modules or a batch scheduler (`sbatch`, `qsub`) where you are not in `sudo`/`wheel` → `hpc`;
- anything else → `server`.

#### Typical Mac weaknesses it finds

| Weakness | Why it hurts |
|---|---|
| BSD `sed`/`date`/`find`, bash 3.2, an old rsync | commands copied from the servers behave differently |
| no sshfs without macFUSE or FUSE-T | servers can't be mounted |
| zsh by default | bash aliases do not carry over |
| empty shell history | nothing to search back through |

The script prints the `brew` command for each of these.

### `setup-env.py`

Brings a machine above its sharpness target with as few changes as possible:

1. It measures the machine with `env-sharpness.py` (which must sit next to it).
2. Among the fixes it knows, it picks the smallest set that lifts the score above the role's target, biggest gain first, and stops there.
3. A machine already above its target is left alone: machines may differ on purpose, and only the gaps that hurt get closed.

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

**Layer `core`**: only your home directory, with no sudo and no background service, so it is meant for shared computing centres too.

| Fix | What it does |
|---|---|
| `ssh-defaults` | `Host *` block at the end of `~/.ssh/config`: ControlMaster, ControlPersist 10m, ServerAliveInterval 30 (plus keychain on macOS) |
| `history` | 100,000-line shell history |
| `user-bin` | fzf 0.56.3 and ripgrep 14.1.1 in `~/.local/bin`, with the fzf key bindings. Downloaded from their GitHub releases and checked against pinned SHA-256 sums |
| `aliases` | ten portable aliases (`ll`, `la`, `..`, `h`, `path`...) |
| `vim` | `~/.vimrc` with `syntax on` and Vim's own defaults (incremental search, ruler, filetype indent), as on Ubuntu |

**Layer `macos`**: needs [Homebrew](https://brew.sh), which asks for your password once when you install it.

| Fix | What it does |
|---|---|
| `gnu-tools` | GNU coreutils, sed, grep and findutils, first in PATH |
| `bash` | bash 5 (macOS ships 3.2) |
| `rsync` | rsync 3 (macOS ships openrsync) |
| `fuse-sshfs` | FUSE-T and its sshfs: no kernel extension, no reboot. Asks for your password |
| `xquartz` | XQuartz, for `ssh -X`. Asks for your password |

**Layer `workstation`**: the machine you sit at.

| Fix | What it does |
|---|---|
| `toolkit` | clones TailScale-Monitor and ClaudeXplorer into `~/Documents` (if missing) and links `tailmon`, `claude-explorer` and `env-sharpness` into `~/.local/bin` |
| `mounts` | `tailmon mount`: every server under `/media/tailscale` (`~/tailscale` on macOS). Brings in `toolkit`, and `fuse-sshfs` on macOS |
| `keyboard` | French AZERTY (PC) as default layout, plus Czech. GNOME input sources on Linux; on macOS the *French – PC* input source, not Apple's *French*, which places symbols differently |

Fixes that ask for a password are skipped, with a note, when the script is not run from a terminal.

Customizations, such as other fixes, keyboard layouts or a target for your own machines, can be developed on request.

#### Undo and backups

- Each change to a file is a block between `# >>> setup-env: <name> >>>` and `# <<< setup-env: <name> <<<` (`"` instead of `#` in `~/.vimrc`), so you can see it.
- `--undo` removes those blocks, with the links and binaries. Homebrew packages and cloned repositories stay.
- Every file is backed up as `<file>.bak-setup-env-<date>` before it is changed.
- PATH changes go to `~/.zprofile` with zsh, so that non-interactive login shells, such as `tailmon sharpness`, see them too.

#### Caveats

- Run it from a normal terminal on the machine itself, from a clone of this repository. It needs Python 3.6 or later.
- With `gnu-tools`, `sed`, `grep`, `find`, `date`... are the GNU ones in your shells. macOS's own stay in `/usr/bin` for scripts that call them by full path.
- Mounts do not survive a reboot: run `tailmon mount` again.
- `user-bin` needs to reach github.com. On a cluster without Internet access that fix fails and the others still apply.
- Not yet tried on IT4I. It only writes to `$HOME`, but check the plan there before `--apply`.

---

## Spotify integration

Two parts tell people what I am listening to:

| Part | Where | What it does |
|---|---|---|
| Commit trailer | `.githooks/commit-msg` | Adds the track playing in the Spotify desktop app, e.g. `Listening-To: Daft Punk - Veridis Quo <https://open.spotify.com/track/...>`. Reads Spotify over D-Bus (MPRIS), so no account setup. Nothing is added when Spotify is closed, paused or playing an ad, and the hook never blocks a commit. |
| README block | `Spotify now playing` GitHub Action | Every 30 minutes, calls the Spotify Web API and rewrites the block between the `SPOTIFY` markers [above](#what-im-listening-to) with the current track and the last 5 played. Commits only when the block changes. |

> **Status:** only the Python helpers in `spotify/` are in the repository so far. The `.githooks/commit-msg` hook and the `.github/workflows/spotify-now-playing.yml` workflow still have to be committed before the steps below work.

#### Setup

**Commit hook**, in each clone (needs `busctl` and `python3`):

```bash
git config core.hooksPath .githooks
SPOTIFY_TRAILER=off git commit ...   # skip it for one commit
```

**README action:**

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

---

## Related projects

- [internet-train-coverage](https://github.com/tjyderrien/internet-train-coverage): measures Wi-Fi and internet quality along train trips with very little test data (about 5 MB/h), on a Mac or an Android phone, and turns each trip into a 1D map along the track. Useful for seeing whether dead zones come from the infrastructure or from the weather.
- [TailScale-Monitor](https://github.com/tjyderrien/TailScale-Monitor) (`tailmon`): agentless monitor for the machines of a Tailscale tailnet; `env-sharpness.py` and `setup-env.py` build on it.

## License

MIT, see [LICENSE](LICENSE).
