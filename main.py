import asyncio
import logging
import httpx
from fastapi import Depends, FastAPI, Form, Request, HTTPException
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader
from pydantic import BaseModel
from core.config import settings
from core.processing import process_strava_activity
from core.webhook import register_webhook
from core.database import get_config, get_strava_tokens, set_config, update_strava_tokens
from core.strava_oauth import exchange_code_for_tokens
from core.auth import require_auth

logger = logging.getLogger(__name__)
app = FastAPI()
app.mount("/static", StaticFiles(directory="frontend/static"), name="static")
_templates = Environment(loader=FileSystemLoader("frontend/templates"), autoescape=True)


def _render(name: str, status_code: int = 200, **ctx) -> HTMLResponse:
    return HTMLResponse(_templates.get_template(name).render(**ctx), status_code=status_code)

CONFIGURABLE_KEYS = {"SYNC_WINDOW_SECONDS"}


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


@app.get("/")
async def dashboard(saved: str = "", _: None = Depends(require_auth)):
    return _render("dashboard.html",
        authorized=bool(get_strava_tokens()),
        sync_window=get_config("SYNC_WINDOW_SECONDS") or str(settings.SYNC_WINDOW_SECONDS),
        saved=saved == "1",
        error=None,
    )


@app.post("/api/config")
async def update_config(key: str = Form(...), value: str = Form(...), _: None = Depends(require_auth)):
    def _error(msg: str):
        return _render("dashboard.html",
            status_code=400,
            authorized=bool(get_strava_tokens()),
            sync_window=get_config("SYNC_WINDOW_SECONDS") or str(settings.SYNC_WINDOW_SECONDS),
            saved=False,
            error=msg,
        )

    if key not in CONFIGURABLE_KEYS:
        return _error(f"Unknown config key: {key}")
    if key == "SYNC_WINDOW_SECONDS":
        try:
            v = int(value)
            if not (60 <= v <= 86400):
                raise ValueError
        except ValueError:
            return _error("Sync window must be between 60 and 86400 seconds.")
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
