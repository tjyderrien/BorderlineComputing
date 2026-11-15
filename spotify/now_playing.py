#!/usr/bin/env python3
"""Rewrite the Spotify block of a README with what is playing now and what played recently.

Usage: now_playing.py README.md

Needs SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET and SPOTIFY_REFRESH_TOKEN in the
environment (see spotify/get_refresh_token.py). If any is missing it prints a
warning and exits 0, so the scheduled workflow does not fail before setup.
The block lives between the START and END markers below; the file is only
written when the block's content changes.
"""
import base64
import json
import os
import sys
import urllib.parse
import urllib.request

START = "<!-- SPOTIFY:START -->"
END = "<!-- SPOTIFY:END -->"
RECENT = 5
VARS = ("SPOTIFY_CLIENT_ID", "SPOTIFY_CLIENT_SECRET", "SPOTIFY_REFRESH_TOKEN")


def access_token(client_id, client_secret, refresh_token):
    auth = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
    data = urllib.parse.urlencode(
        {"grant_type": "refresh_token", "refresh_token": refresh_token}
    ).encode()
    req = urllib.request.Request(
        "https://accounts.spotify.com/api/token",
        data=data,
        headers={"Authorization": f"Basic {auth}",
                 "Content-Type": "application/x-www-form-urlencoded"},
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)["access_token"]


def api(token, path):
    req = urllib.request.Request(
        "https://api.spotify.com/v1" + path,
        headers={"Authorization": f"Bearer {token}"},
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        body = r.read()
        return json.loads(body) if r.status != 204 and body else None


def md(text):
    """Escape characters that would break Markdown links and tables."""
    for ch in "\\`*_[]<>|":
        text = text.replace(ch, "\\" + ch)
    return " ".join(text.split())


def describe(item):
    """Return (title link, artist/show) for a track or podcast episode."""
    url = item.get("external_urls", {}).get("spotify", "")
    title = md(item.get("name", "?"))
    link = f"[{title}]({url})" if url else title
    if item.get("type") == "episode":
        who = item.get("show", {}).get("name", "")
    else:
        who = ", ".join(a.get("name", "") for a in item.get("artists", []))
    return link, md(who)


def render(now, recent):
    lines = []
    if now and now.get("is_playing") and now.get("item"):
        link, who = describe(now["item"])
        lines.append(f"**Now playing:** {link} by {who}" if who else f"**Now playing:** {link}")
        lines.append("")
    items = (recent or {}).get("items", [])
    if items:
        lines += ["**Recently played**", "", "| Track | Artist | Played (UTC) |", "|---|---|---|"]
        for entry in items[:RECENT]:
            link, who = describe(entry["track"])
            played = entry["played_at"][:16].replace("T", " ")  # "2026-11-03T12:34:56.789Z", UTC
            lines.append(f"| {link} | {who} | {played} |")
    if not lines:
        lines.append("Nothing played recently.")
    return "\n".join(lines).rstrip()


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    readme = sys.argv[1]
    missing = [v for v in VARS if not os.environ.get(v)]
    if missing:
        print(f"::warning::Spotify not configured, missing: {', '.join(missing)}")
        return

    token = access_token(*(os.environ[v] for v in VARS))
    now = api(token, "/me/player/currently-playing?additional_types=episode")
    recent = api(token, f"/me/player/recently-played?limit={RECENT}")
    block = render(now, recent)

    with open(readme, encoding="utf-8") as f:
        text = f.read()
    if START not in text or END not in text:
        sys.exit(f"{readme}: markers {START} and {END} not found")
    head, rest = text.split(START, 1)
    _, tail = rest.split(END, 1)
    new = f"{head}{START}\n{block}\n{END}{tail}"
    if new == text:
        print("No change.")
        return
    with open(readme, "w", encoding="utf-8") as f:
        f.write(new)
    print("Updated:\n" + block)


if __name__ == "__main__":
    main()
