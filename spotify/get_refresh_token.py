#!/usr/bin/env python3
"""One-time setup: let this repo read your Spotify playback, and print a refresh token.

1. Create an app at https://developer.spotify.com/dashboard and add the
   redirect URI  http://127.0.0.1:8888/callback  to it.
2. Run:  python3 spotify/get_refresh_token.py
   It asks for the app's Client ID and secret, opens Spotify's consent page in
   your browser, and prints the refresh token once you accept.

Only read access is requested: what is playing now and what played recently.
"""
import base64
import getpass
import json
import os
import secrets
import sys
import urllib.parse
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer

REDIRECT = "http://127.0.0.1:8888/callback"
SCOPES = "user-read-currently-playing user-read-recently-played"


def main():
    client_id = os.environ.get("SPOTIFY_CLIENT_ID") or input("Client ID: ").strip()
    client_secret = os.environ.get("SPOTIFY_CLIENT_SECRET") or getpass.getpass("Client secret: ").strip()
    state = secrets.token_urlsafe(16)
    url = "https://accounts.spotify.com/authorize?" + urllib.parse.urlencode({
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": REDIRECT,
        "scope": SCOPES,
        "state": state,
    })

    result = {}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            parsed = urllib.parse.urlparse(self.path)
            if parsed.path != "/callback":
                self.send_error(404)
                return
            result.update({k: v[0] for k, v in urllib.parse.parse_qs(parsed.query).items()})
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"Done. You can close this tab and go back to the terminal.")

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 8888), Handler)
    print("Opening Spotify's consent page. If no browser opens, visit:\n" + url)
    webbrowser.open(url)
    while "code" not in result and "error" not in result:
        server.handle_request()
    server.server_close()

    if "error" in result:
        sys.exit(f"Spotify refused: {result['error']}")
    if result.get("state") != state:
        sys.exit("State mismatch; aborting.")

    auth = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
    req = urllib.request.Request(
        "https://accounts.spotify.com/api/token",
        data=urllib.parse.urlencode({
            "grant_type": "authorization_code",
            "code": result["code"],
            "redirect_uri": REDIRECT,
        }).encode(),
        headers={"Authorization": f"Basic {auth}",
                 "Content-Type": "application/x-www-form-urlencoded"},
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        tokens = json.load(r)
    print("\nRefresh token (keep it secret):\n" + tokens["refresh_token"])


if __name__ == "__main__":
    main()
