import asyncio
import logging
import httpx
from fastapi import Depends, FastAPI, Form, Request, HTTPException
from fastapi.responses import RedirectResponse, HTMLResponse
from pydantic import BaseModel
from core.config import settings
from core.processing import process_strava_activity
from core.webhook import register_webhook
from core.database import get_config, get_strava_tokens, set_config, update_strava_tokens
from core.strava_oauth import exchange_code_for_tokens
from core.auth import require_auth

logger = logging.getLogger(__name__)
app = FastAPI()

CONFIGURABLE_KEYS = {"SYNC_WINDOW_SECONDS"}


def _dashboard_html(saved: bool = False, error: str | None = None) -> str:
    authorized = bool(get_strava_tokens())
    sync_window = get_config("SYNC_WINDOW_SECONDS") or str(settings.SYNC_WINDOW_SECONDS)
    status_color = "#d1fae5" if authorized else "#fef3c7"
    status_text_color = "#065f46" if authorized else "#92400e"
    status_label = "Strava authorized" if authorized else "Not authorized"
    auth_hint = "" if authorized else '<p style="margin-top:.5rem;font-size:.8rem"><a href="/auth/login">Authorize Strava</a></p>'
    msg = ""
    if saved:
        msg = '<p style="margin-top:.75rem;font-size:.8rem;color:#065f46">Settings saved.</p>'
    if error:
        msg = f'<p style="margin-top:.75rem;font-size:.8rem;color:#b91c1c">{error}</p>'
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Hevva</title>
  <style>
    *{{box-sizing:border-box;margin:0;padding:0}}
    body{{font-family:system-ui,sans-serif;background:#f5f5f5;color:#222;padding:2rem}}
    .wrap{{max-width:480px;margin:0 auto}}
    h1{{font-size:1.3rem;margin-bottom:.2rem}}
    .sub{{color:#666;font-size:.85rem;margin-bottom:1.75rem}}
    .card{{background:#fff;border-radius:8px;padding:1.5rem;margin-bottom:1rem;box-shadow:0 1px 3px rgba(0,0,0,.08)}}
    .card h2{{font-size:.95rem;font-weight:600;margin-bottom:.75rem}}
    .badge{{display:inline-block;padding:.2rem .65rem;border-radius:4px;font-size:.78rem;font-weight:600;background:{status_color};color:{status_text_color}}}
    label{{display:block;font-size:.85rem;font-weight:500;margin-bottom:.35rem;margin-top:.75rem}}
    input[type=number]{{width:100%;padding:.45rem .7rem;border:1px solid #ddd;border-radius:6px;font-size:.85rem}}
    .hint{{font-size:.75rem;color:#999;margin-top:.3rem}}
    button{{margin-top:1rem;background:#fc4c02;color:#fff;border:none;padding:.55rem 1.1rem;border-radius:6px;font-size:.85rem;font-weight:600;cursor:pointer}}
    button:hover{{background:#e04400}}
  </style>
</head>
<body>
  <div class="wrap">
    <h1>Hevva</h1>
    <p class="sub">Strava ↔ Hevy sync dashboard</p>
    <div class="card">
      <h2>Status</h2>
      <span class="badge">{status_label}</span>
      {auth_hint}
    </div>
    <div class="card">
      <h2>Settings</h2>
      <form method="post" action="/api/config">
        <input type="hidden" name="key" value="SYNC_WINDOW_SECONDS">
        <label for="sw">Sync window (seconds)</label>
        <input type="number" id="sw" name="value" value="{sync_window}" min="60" max="86400">
        <p class="hint">How close in time a Hevy workout must be to a Strava activity to be matched. Default: 1800 (30 min)</p>
        <button type="submit">Save</button>
      </form>
      {msg}
    </div>
  </div>
</body>
</html>"""


@app.on_event("startup")
async def startup():
    asyncio.create_task(_deferred_webhook_registration())


async def _deferred_webhook_registration():
    # Wait for the app to be fully serving before calling Strava,
    # so the verification GET /webhook can be handled normally.
    await asyncio.sleep(2)
    await register_webhook()


class WebhookEvent(BaseModel):
    aspect_type: str
    event_time: int
    object_id: int
    object_type: str
    owner_id: int
    subscription_id: int
    updates: dict


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request, saved: str = "", _: None = Depends(require_auth)):
    return _dashboard_html(saved=saved == "1")


@app.post("/api/config")
async def update_config(key: str = Form(...), value: str = Form(...), _: None = Depends(require_auth)):
    if key not in CONFIGURABLE_KEYS:
        return HTMLResponse(_dashboard_html(error=f"Unknown config key: {key}"), status_code=400)
    if key == "SYNC_WINDOW_SECONDS":
        try:
            v = int(value)
            if not (60 <= v <= 86400):
                raise ValueError
        except ValueError:
            return HTMLResponse(_dashboard_html(error="Sync window must be between 60 and 86400 seconds."), status_code=400)
    set_config(key, value)
    return RedirectResponse("/?saved=1", status_code=303)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/auth/login")
async def auth_login():
    if get_strava_tokens():
        return HTMLResponse("<h2>Already authorized. Hevva is running.</h2>")
    auth_url = (
        f"https://www.strava.com/oauth/authorize"
        f"?client_id={settings.STRAVA_CLIENT_ID}"
        f"&redirect_uri={settings.STRAVA_REDIRECT_URI}"
        f"&response_type=code"
        f"&scope=activity:read_all,activity:write"
        f"&approval_prompt=auto"
    )
    return RedirectResponse(auth_url)


@app.get("/auth/callback")
async def auth_callback(code: str):
    try:
        tokens = await exchange_code_for_tokens(code)
    except httpx.HTTPStatusError:
        raise HTTPException(status_code=400, detail="Failed to exchange authorization code. Try /auth/login again.")
    update_strava_tokens(tokens["access_token"], tokens["refresh_token"], tokens["expires_at"])
    set_config("athlete_id", str(tokens["athlete"]["id"]))
    return HTMLResponse("<h2>Authorization successful. Hevva is ready.</h2>")


@app.get("/webhook")
async def strava_webhook_verification(request: Request):
    if request.query_params.get("hub.mode") == "subscribe" and \
       request.query_params.get("hub.verify_token") == settings.STRAVA_VERIFY_TOKEN:
        return {"hub.challenge": request.query_params.get("hub.challenge")}
    raise HTTPException(status_code=403, detail="Forbidden")


@app.post("/webhook")
async def strava_webhook_event(event: WebhookEvent):
    expected_subscription_id = get_config("subscription_id")
    expected_owner_id = get_config("athlete_id")

    if expected_subscription_id and str(event.subscription_id) != expected_subscription_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    if expected_owner_id and str(event.owner_id) != expected_owner_id:
        raise HTTPException(status_code=403, detail="Forbidden")

    if event.object_type == "activity" and event.aspect_type == "create":
        await process_strava_activity(event.object_id)
    return {"status": "ok"}

