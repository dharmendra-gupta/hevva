"""
First-time setup: Strava OAuth flow.
Run this once from the Hevva/ directory before starting the app.

    python setup.py

Requires STRAVA_CLIENT_ID, STRAVA_CLIENT_SECRET, and STRAVA_REDIRECT_URI in .env.
STRAVA_REDIRECT_URI must also be registered in your Strava app's allowed redirect URIs.
Default: http://localhost:8888/callback
"""
import asyncio
import os
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

import httpx

from core.config import settings
from core.database import get_strava_tokens, update_strava_tokens, set_config

CALLBACK_PORT = int(settings.STRAVA_REDIRECT_URI.split(":")[-1].split("/")[0])

_auth_code: str | None = None
_auth_event = threading.Event()


class _CallbackHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        global _auth_code
        params = parse_qs(urlparse(self.path).query)
        if "code" in params:
            _auth_code = params["code"][0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"<h2>Authorization successful. You can close this tab.</h2>")
            _auth_event.set()
        elif "error" in params:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b"<h2>Authorization denied.</h2>")
            _auth_event.set()

    def log_message(self, *args):
        pass


def _is_inside_container() -> bool:
    return os.path.exists("/.dockerenv") or os.environ.get("DOCKER", "") == "1"


async def run_oauth():
    existing = get_strava_tokens()
    if existing:
        print("Strava tokens already present in database. Skipping OAuth.")
        return True

    auth_url = (
        f"https://www.strava.com/oauth/authorize"
        f"?client_id={settings.STRAVA_CLIENT_ID}"
        f"&redirect_uri={settings.STRAVA_REDIRECT_URI}"
        f"&response_type=code"
        f"&scope=activity:read_all,activity:write"
        f"&approval_prompt=auto"
    )

    server = HTTPServer(("localhost", CALLBACK_PORT), _CallbackHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    if _is_inside_container():
        print(f"\nOpen this URL in your browser to authorize:\n\n  {auth_url}\n")
    else:
        print("Opening browser for Strava authorization...")
        print(f"If it doesn't open, visit:\n  {auth_url}\n")
        webbrowser.open(auth_url)

    print("Waiting for authorization (timeout: 120s)...")
    _auth_event.wait(timeout=120)
    server.shutdown()

    if not _auth_code:
        print("Authorization timed out or was denied.")
        return False

    async with httpx.AsyncClient() as client:
        response = await client.post(
            settings.STRAVA_OAUTH_URL,
            data={
                "client_id": settings.STRAVA_CLIENT_ID,
                "client_secret": settings.STRAVA_CLIENT_SECRET,
                "code": _auth_code,
                "grant_type": "authorization_code",
            },
        )
        response.raise_for_status()
        tokens = response.json()
        update_strava_tokens(
            tokens["access_token"],
            tokens["refresh_token"],
            tokens["expires_at"],
        )
        athlete_id = str(tokens["athlete"]["id"])
        set_config("athlete_id", athlete_id)
        print(f"Tokens saved. Authorized as athlete id={athlete_id}.")
    return True


async def main():
    print("=== Hevva Setup ===\n")

    ok = await run_oauth()
    if not ok:
        print("\nSetup failed. Fix the error above and re-run.")
        sys.exit(1)

    print(
        "\nOAuth complete.\n"
        "Next: start the app with  docker-compose up  (or  uvicorn main:app).\n"
        "The webhook subscription will be registered automatically on first startup\n"
        "as long as WEBHOOK_CALLBACK_URL is set in .env and the app is publicly accessible."
    )


if __name__ == "__main__":
    asyncio.run(main())
