# BorderlineComputing
Suite of tools that are necessary to prolong lifetime of computers to infinite.

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
