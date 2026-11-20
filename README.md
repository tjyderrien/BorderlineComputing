# BorderlineComputing

Suite of tools that are necessary to prolong lifetime of computers to infinite.

Two ideas behind it:

1. **Old computers stay useful.** A ten-year-old laptop is still a perfectly good machine for a shell, an editor and a remote desktop. What makes people replace it is rarely the hardware: it is a full disk, a network quirk, a device that won't stay connected, a keyboard that half works.
2. **Every machine on your network feels the same, whichever Unix it runs.** An old Ubuntu laptop, a new Mac, a lab server running another distribution, an account on a computing centre: on each one the same tools, the same shell habits and the same SSH setup should just work, and each should reach and mount the others without a password. Then it no longer matters which machine you happen to sit at, and the old one is as good a door into your work as the new one.

The scripts are small, readable, and change nothing without telling you.

> *Inspiration: in 2024, after a memory chip failed in Voyager 1's 1970s flight computer, NASA engineers moved its code to other parts of memory, from 24 billion km away. Every command took 22.5 hours to arrive. I wish I could bring back Voyager I to Earth with that code.*

## Contents

- [Which tool do I need?](#which-tool-do-i-need)
- [One environment on every machine](#one-environment-on-every-machine)
  - [`env-sharpness.py`](#env-sharpnesspy): score how well a machine fits into your network, with the fix for each gap
  - [`setup-env.py`](#setup-envpy): apply the fewest fixes that bring it up to standard
- [Keeping old machines usable](#keeping-old-machines-usable)
  - [`free-disk-space.sh`](#free-disk-spacesh): reclaim several GB on a full Ubuntu root partition
  - [`TurnOffIPv6.sh`](#turnoffipv6sh): turn off IPv6 on Wi-Fi when sites such as Google Scholar hang
  - [`bluetooth-switch.sh`](#bluetooth-switchsh): Bluetooth on/off in one command, devices reconnected automatically
  - [`mac-printscreen.sh`](#mac-printscreensh): Print Screen on a Mac with a PC keyboard
- [Spotify: what I'm listening to](#spotify-what-im-listening-to)
- [Related projects](#related-projects)
- [License](#license)

## Which tool do I need?

| Your problem | Tool | Runs on | Changes your system? |
|---|---|---|---|
| One of your machines is more painful to work from than the others: passwords at every login, dropped connections, commands that behave differently, other machines you can't browse | [`env-sharpness.py`](#env-sharpnesspy) to see why | Linux, macOS | No, read-only |
| … and you want it brought up to the same standard | [`setup-env.py`](#setup-envpy) | Linux, macOS | Only with `--apply`; `--undo` reverts |
| Ubuntu says the disk is full and you can't install or update anything | [`free-disk-space.sh`](#free-disk-spacesh) | Ubuntu/Debian | Only with `--apply` |
| Google Scholar or other sites hang on Wi-Fi while the rest of the web works | [`TurnOffIPv6.sh`](#turnoffipv6sh) | Linux | Yes, until the next reboot |
| Bluetooth audio devices keep disconnecting | [`bluetooth-switch.sh`](#bluetooth-switchsh) | Linux (BlueZ) | Yes (starts/stops the service) |
| The Print Screen key of your PC keyboard does nothing on a Mac | [`mac-printscreen.sh`](#mac-printscreensh) | macOS + Karabiner-Elements | Yes; `--remove` reverts |
| You want your README to show what you're listening to | [Spotify integration](#spotify-what-im-listening-to) | GitHub Actions, Linux | Commits to this repository |

---

## One environment on every machine

Two scripts that work as a pair: **`env-sharpness.py` measures how far a machine is from your common standard, `setup-env.py` closes the gap.** Run them on each machine of your network, old or new, and they all end up with the same tools, shell and SSH setup, each able to reach and mount the others.

**Where they run.** Linux (any distribution) and macOS, on 64-bit Intel/AMD or ARM processors, including old laptops and Intel Macs. They need only Python 3.6 or later and its standard library. The fix hints for Linux are written with `apt` (Debian/Ubuntu); on other distributions use the equivalent package. Other Unixes (FreeBSD...) and 32-bit machines are untested.

### `env-sharpness.py`

**The problem.** Machines drift apart. One has your SSH keys and aliases, another asks for a password every time; one has GNU `sed` and bash 5, another has BSD `sed` and bash 3.2, so a command that works on one fails on the next; one can browse the others' files, another can't; one keeps its connection, another drops it when you stop typing. Each difference costs seconds, every day, and they are easy to stop noticing.

**What it does.** On the machine it runs on, it makes 44 checks (with two other machines to reach; the per-machine checks scale with `--hosts`) in 7 categories: reaching the other machines, logging in without a password, SSH settings, remote files, tools, shell and your own toolkit. Each category is scored 0–100 %, and the overall score is compared with a target that depends on what the machine is for. Then it lists every gap with the exact command that closes it, biggest gain first. It changes nothing.

**When to use it.** When you set up or revive a machine; after an OS upgrade; when one machine "feels worse" than another (`--compare` shows exactly why).

#### Usage

```bash
./env-sharpness.py --hosts biatri-1,biatri-2,luzicka   # the other machines to check against (default: online Linux tailnet machines)
./env-sharpness.py --role server                        # judge it as a server (default: guessed)
./env-sharpness.py --check                              # exit status 1 if not above the target (for scripts)
./env-sharpness.py -v                                   # also list the checks that pass
./env-sharpness.py --offline                            # no network checks
./env-sharpness.py --json asus.json                     # save the results
./env-sharpness.py --compare asus.json mac.json         # differences between two machines, largest first
```

- Without `--hosts`, it checks against the online Linux machines of your tailnet, or the hosts in `~/.ssh/config` when Tailscale is not running.
- `--json -` prints only the JSON; [`tailmon sharpness`](https://github.com/tjyderrien/TailScale-Monitor) uses it to score every machine of the tailnet at once, in one table.
- **Comparing two machines:** run it on each one with the same `--hosts` and `--json`, copy one JSON file to the other machine, and run `--compare`.
- Run it from a normal terminal, not through `ssh`, so it sees your real ssh-agent, PATH and mounts.

#### Example output

A Mac mini checked against two Ubuntu machines of the same network (shortened):

```
Environment sharpness: mac-mini (Darwin 27.0.0)
Role: workstation (target 90)   Hosts checked: bumblefoot, luzicka

Reaching the servers                 ####################  98.9
Logging in without friction          ###################.  97.2
     76%  luzicka: time to shell  [1.01 s]
SSH ergonomics                       ##################..  90.0
      0%  X server for `ssh -X` graphics  [missing]
Remote files                         #################...  85.0
     40%  rsync 3.x  [openrsync]
Toolchain parity with the servers    ############........  59.3
     17%  GNU coreutils/sed/grep/find (as on the servers)  [GNU: 1/6 (BSD versions behave differently: sed -i, date -d...)]
      0%  bash >= 4 (as on the servers)  [bash 3]
Shell                                #################...  82.9
Your toolkit (TailMon & co.)         #################### 100.0

OVERALL                              ##################..  87.6 / 100   below target 90

Biggest gains first:
   1. `brew install coreutils gnu-sed grep findutils` and put their `gnubin` dirs first in PATH, so commands copied from the servers work unchanged.
   2. `brew install bash` (macOS ships bash 3.2 from 2007: no associative arrays, no `mapfile`, `${x,,}`...).
   3. `brew install rsync` (macOS ships an old rsync/openrsync lacking --info=progress2, -A, -X...).
```

#### What it measures

Each check is weighted inside its category; the overall score is the mean of the 7 categories.

| Category | Checks |
|---|---|
| Reaching the other machines | Tailscale/VPN running; TCP connect time to each machine |
| Logging in without friction | SSH key, key permissions, agent; `ssh -o BatchMode=yes <host> true` works with no password, and how long it takes |
| SSH ergonomics | Host aliases for every machine, ControlMaster, ServerAliveInterval, tmux/screen/mosh, X server, VNC viewer |
| Remote files | sshfs, rsync 3.x, each machine mounted locally and how fast the mount answers |
| Toolchain parity | git, vim, python3, conda, gnuplot, rg, jq, htop, gh, claude; GNU (not BSD) sed/grep/find/date; bash 4 or later |
| Shell | bash as login shell, history size, ssh commands in history, personal aliases, fzf, vim with colours |
| Your toolkit | tailmon, claude-explorer, env-sharpness on the PATH; `/media/tailscale` ready for `tailmon mount`; the same keyboard layouts everywhere (French AZERTY PC first, Czech) and, on macOS, an ISO keyboard type |

The network checks only open a TCP connection and run `true` on each machine.

#### Roles and targets

Machines don't need to be identical, only equally comfortable for what they are used for, so each is judged on its role:

| Role | What it is | Judged on | Target |
|---|---|---|---|
| `workstation` | a machine you sit at: desktop, laptop, old or new | everything, including reaching, logging in to and mounting the other machines | 90 |
| `server` | a machine you work *on*, through SSH | SSH settings, keys, tools, shell; not VNC, X or mounts | 80 |
| `hpc` | a shared computing centre you don't administer (IT4I...) | only what one user can set up in `$HOME`: no Tailscale, no conda/gnuplot (they come from modules) | 70 |

The role is guessed, and `--role` / `--target` override it:

- a Mac, or a machine running a display manager → `workstation`;
- a machine with modules or a batch scheduler (`sbatch`, `qsub`) where you are not in `sudo`/`wheel` → `hpc`;
- anything else → `server`.

#### Typical gaps, by system

| System | Typical gaps | What goes wrong |
|---|---|---|
| macOS | BSD `sed`/`date`/`find`, bash 3.2, openrsync; no sshfs without macFUSE or FUSE-T; zsh by default | commands from the Linux machines fail (`sed -i`, `date -d`); the other machines can't be opened as folders; your bash aliases are missing |
| An older or minimal Linux | no `fzf` or `rg` in its packages; short shell history; no SSH multiplexing | slow searching, Ctrl+R finds nothing, every `ssh` and `scp` logs in from scratch |
| A computing-centre account | no sudo, tools from `module load`, no VPN | only your home directory can be fixed: `setup-env.py --layers core` does exactly that |
| A freshly installed or revived machine | no SSH key or agent, no host aliases, empty history | passwords and full host names at every login |

### `setup-env.py`

**The problem.** `env-sharpness.py` tells you what differs, but a dozen fixes by hand is tedious and easy to get slightly wrong, and you'll do it again on the next machine. Making every machine strictly identical is not the goal either: a laptop and a server need different things.

**What it does.** Measures the machine with `env-sharpness.py` (which must sit next to it), then picks among its 13 known fixes the **smallest set** that lifts the score above the role's target, biggest gain first, and stops there. A machine already above its target is left alone. Every change is marked, backed up and reversible with `--undo`.

**When to use it.** On every machine of your network, once, right after `env-sharpness.py` says *below target*; again after an OS reinstall; on a computing-centre account with `--layers core` (home directory only, no sudo).

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

Nothing changes without `--apply`. Fixes that ask for a password are skipped, with a note, when the script is not run from a terminal.

#### The 13 fixes

They come in three layers. All are allowed by default; `--layers` restricts them.

**Layer `core`**, for every machine: your home directory only, no sudo, no background service, so it is safe on old machines and shared computing centres alike.

| Fix | What it does |
|---|---|
| `ssh-defaults` | `Host *` block at the end of `~/.ssh/config`: ControlMaster, ControlPersist 10m, ServerAliveInterval 30 (plus keychain on macOS) |
| `history` | 100,000-line shell history |
| `user-bin` | fzf 0.56.3 and ripgrep 14.1.1 in `~/.local/bin`, with the fzf key bindings, even where the system's packages are too old to have them. Downloaded from their GitHub releases (Linux and macOS, x86_64 and ARM) and checked against pinned SHA-256 sums |
| `aliases` | ten portable aliases (`ll`, `la`, `..`, `h`, `path`...) |
| `vim` | `~/.vimrc` with `syntax on` and Vim's own defaults (incremental search, ruler, filetype indent), as on Ubuntu |

**Layer `macos`**, to make a Mac behave like the Linux machines. Needs [Homebrew](https://brew.sh), which asks for your password once when you install it.

| Fix | What it does |
|---|---|
| `gnu-tools` | GNU coreutils, sed, grep and findutils, first in PATH |
| `bash` | bash 5 (macOS ships 3.2) |
| `rsync` | rsync 3 (macOS ships openrsync) |
| `fuse-sshfs` | FUSE-T and its sshfs: no kernel extension, no reboot. Asks for your password |
| `xquartz` | XQuartz, for `ssh -X`. Asks for your password |

**Layer `workstation`**, for the machines you sit at.

| Fix | What it does |
|---|---|
| `toolkit` | clones TailScale-Monitor and ClaudeXplorer into `~/Documents` (if missing) and links `tailmon`, `claude-explorer` and `env-sharpness` into `~/.local/bin` |
| `mounts` | `tailmon mount`: every other machine under `/media/tailscale` (`~/tailscale` on macOS). Brings in `toolkit`, and `fuse-sshfs` on macOS |
| `keyboard` | French AZERTY (PC) as default layout, plus Czech, the same on every machine. GNOME input sources on Linux; on macOS the *French – PC* input source, not Apple's *French*, which places symbols differently |

Customizations, such as other fixes, keyboard layouts or a target for your own machines, can be developed on request.

#### Undo and backups

- Each change to a file is a block between `# >>> setup-env: <name> >>>` and `# <<< setup-env: <name> <<<` (`"` instead of `#` in `~/.vimrc`), so you can see it.
- `--undo` removes those blocks, with the links and binaries. Homebrew packages and cloned repositories stay.
- Every file is backed up as `<file>.bak-setup-env-<date>` before it is changed.
- PATH changes go to `~/.zprofile` with zsh, so that non-interactive login shells, such as `tailmon sharpness`, see them too.

#### Caveats

- Run it from a normal terminal on the machine itself, from a clone of this repository.
- With `gnu-tools`, `sed`, `grep`, `find`, `date`... are the GNU ones in your shells. macOS's own stay in `/usr/bin` for scripts that call them by full path.
- Mounts do not survive a reboot: run `tailmon mount` again.
- `user-bin` needs to reach github.com. On a cluster without Internet access that fix fails and the others still apply.
- Not yet tried on IT4I. It only writes to `$HOME`, but check the plan there before `--apply`.

---

## Keeping old machines usable

Small fixes for the problems that make a working computer feel finished: a full disk, a network quirk, devices that won't stay connected, a keyboard that half works.

### `free-disk-space.sh`

**The problem.** Old laptops often have small disks. When the Ubuntu root partition fills up, updates and installs fail and the machine looks too small, although most of the space is taken by data the system can regenerate.

**What it does.** Removes only that data, in 6 steps (package caches, logs, old snap revisions and kernels, conda and pip caches, the Trash), typically several GB, and lists the bigger items it leaves to your judgement. It never touches `~/Documents` or `~/Downloads`.

**When to use it.** When `df -h /` shows the root partition almost full.

#### Usage

```bash
./free-disk-space.sh           # dry run: shows sizes and what would be removed
./free-disk-space.sh --apply   # actually do it (asks for your sudo password once)
```

Always start with the dry run. It prints the root filesystem usage, each step with its current size, and the exact command it would run. Nothing is deleted without `--apply`.

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

#### What it leaves to you

At the end it lists bigger items it does not remove, because deleting them is a judgement call:

- Browser caches under `~/snap/firefox/common` and `~/snap/chromium/common`. Clear them from each browser, or with `rm -rf ~/snap/*/common/.cache`.
- Old installers in `~/Downloads/Softwares`.
- The Android emulator in `~/Android/Sdk/emulator`, if you don't use it.
- Old Claude Code versions in `~/.local/share/claude/versions` (keep the newest).

#### Requirements and caveats

- Ubuntu/Debian with `apt`, `systemd` and `snap`. Steps whose tools are missing print an error and the script carries on.
- Needs `sudo` for the apt, journal and snap steps.
- Step 4 removes any package apt considers unused, including old kernels. Check the list in the dry run first; the running kernel (`uname -r`) is never removed.
- Emptying the Trash is permanent.
- Some sizes, paths and notes (the `/dev/sda6` root, `/media/thibault/Data`, the 5.15 kernel) are specific to the machine the script was written for. Adjust them before using it elsewhere.

### `TurnOffIPv6.sh`

**The problem.** On some Wi-Fi networks IPv6 is announced but doesn't really work. The browser tries IPv6 first, and sites such as Google Scholar hang or refuse to load while the rest of the web looks fine, which is easily mistaken for a slow, worn-out laptop.

**What it does.** Turns IPv6 off on the `wlan0` interface, so everything goes over IPv4. It runs:

```bash
sudo sysctl -w net.ipv6.conf.wlan0.disable_ipv6=1
```

**When to use it.** When a site loads on your phone's mobile data but hangs on the Wi-Fi.

#### Usage

```bash
bash TurnOffIPv6.sh   # asks for your sudo password
```

#### Caveats

- The interface name is hard-coded to `wlan0`. Check yours with `ip link` and edit the script if it differs.
- The change lasts until the next reboot. To turn IPv6 back on before that:

  ```bash
  sudo sysctl -w net.ipv6.conf.wlan0.disable_ipv6=0
  ```

### `bluetooth-switch.sh`

**The problem.** Bluetooth audio devices (here an Alesis MultiMix mixer and a CMO-3110 speaker) drop their connection and don't come back by themselves, and turning Bluetooth on and off on Linux takes several commands.

**What it does.**

- **Run without options**, it toggles Bluetooth:
  - **if on**: blocks the radio with `rfkill`, stops the `bluetooth` service and closes blueman;
  - **if off**: unblocks the radio, starts the service, powers the adapter on and opens `blueman-manager`. While blueman stays open, every 15 s it reconnects each device of its list that has dropped.
- **`--monitor`** powers Bluetooth on and only runs the reconnect loop, with no window (e.g. at login).

**When to use it.** Bound to a keyboard shortcut, as an on/off switch; `--monitor` in your startup applications if devices drop often.

#### Usage

```bash
./bluetooth-switch.sh             # toggle on/off
./bluetooth-switch.sh --monitor   # power on and keep the devices connected
```

#### Caveats

- Linux with BlueZ (`bluetoothctl`), `rfkill`, systemd and blueman. Needs `sudo` to start or stop the service.
- The devices are listed by MAC address in `DEVICES` at the top of the script, and the interval in `RECONNECT_INTERVAL`: edit both for your own devices.

### `mac-printscreen.sh`

**The problem.** Keyboards outlive computers. On a Mac, the Print Screen key of a PC keyboard does nothing: macOS takes screenshots with ⌘⇧3 / ⌘⇧4 and has no action for that key.

**What it does.** Adds two rules to [Karabiner-Elements](https://karabiner-elements.pqrs.org) so the key does what it does on Windows and Linux:

| Key | Takes | Sends |
|---|---|---|
| Print Screen | the whole screen | ⌘⇧3 |
| Shift + Print Screen | an area (drag a rectangle), or a window (press Space, then click the app) | ⌘⇧4 |

Screenshots go where macOS puts them: the Desktop by default (⌘⇧5 → Options to change it).

**When to use it.** Once, on any Mac used with a PC keyboard.

#### Usage

```bash
./mac-printscreen.sh            # add the two rules
./mac-printscreen.sh --remove   # take them out again
```

- The rules go into the selected profile of `~/.config/karabiner/karabiner.json`, which Karabiner reloads by itself.
- The file is copied to `karabiner.json.<date>.bak` first.
- Running it twice does not add the rules twice: they are tagged `[BorderlineComputing print screen]`, and old copies are replaced.

#### Requirements

- Karabiner-Elements, installed and opened once (driver and input monitoring allowed): `brew install --cask karabiner-elements`.
- `python3` (comes with the Xcode command line tools).

> **Geek corner.** On the Mac this was written on, the Karabiner profile held **4,034 rules but only 65 distinct ones**: the 63 Windows-style shortcuts (Ctrl+C, Home/End, Win+L…) were each present exactly **64 = 2⁶ times**, plus the 2 Print Screen rules. That was 98.4 % duplicates in a 10.9 MB `karabiner.json`: a rule set imported again and again, apparently doubling each time. Karabiner didn't mind, since the first matching rule wins and the other 63 copies were never reached. Keeping only the first copy of each rule, in order, shrank the file to 173 KB (63× smaller) with exactly the same behaviour.

---

## Spotify: what I'm listening to

<!-- SPOTIFY:START -->
Nothing played recently.
<!-- SPOTIFY:END -->

**What it does.** Tells people what I'm listening to, in two places:

| Part | Where | How |
|---|---|---|
| This README | the block just above | A GitHub Action (`Spotify now playing`) runs every 30 minutes, calls the Spotify Web API and rewrites the block between the `SPOTIFY` markers with the current track and the last 5 played. It commits only when the block changes. |
| Commit messages | `.githooks/commit-msg` | Adds the track playing in the Spotify desktop app, e.g. `Listening-To: Daft Punk - Veridis Quo <https://open.spotify.com/track/...>`. Reads Spotify over D-Bus (MPRIS), so no account setup. Nothing is added when Spotify is closed, paused or playing an ad, and the hook never blocks a commit. |

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
- GitHub may delay scheduled runs by several minutes, so "now playing" can lag.
- Until the secrets are set, the action only logs a warning.

---

## Related projects

- [TailScale-Monitor](https://github.com/tjyderrien/TailScale-Monitor) (`tailmon`): the other half of "one environment on every machine". An agentless CPU/GPU/RAM/disk monitor, web htop and volume mixer for every machine of a Tailscale tailnet, plus `tailmon mount`, `search` and `grep` across all of them. `env-sharpness.py` and `setup-env.py` use it to find and mount the other machines.
- [internet-train-coverage](https://github.com/tjyderrien/internet-train-coverage): measures Wi-Fi and internet quality along train trips with very little test data (about 5 MB/h), on a Mac or an Android phone, and turns each trip into a 1D map along the track. Useful for seeing whether dead zones come from the infrastructure or from the weather.

## License

MIT, see [LICENSE](LICENSE).
