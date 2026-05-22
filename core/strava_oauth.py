import httpx
import time
from core.config import settings
from core.database import get_strava_tokens, update_strava_tokens

STRAVA_API_BASE_URL = settings.STRAVA_API_BASE_URL
OAUTH_URL = settings.STRAVA_OAUTH_URL


async def refresh_strava_token():
    tokens = get_strava_tokens()
    if not tokens:
        # This would typically be handled by an initial OAuth flow
        # For this project, we assume tokens are pre-filled in .env or via an initial setup
        print("No Strava tokens found in DB. Please ensure initial OAuth setup is complete or .env is populated.")
        return False

    access_token, refresh_token, expires_at = tokens

    # Check if token needs refreshing (e.g., within 5 minutes of expiration)
    if expires_at - 300 < time.time():
        print("Refreshing Strava token...")
        async with httpx.AsyncClient() as client:
            response = await client.post(
                OAUTH_URL,
                data={
                    "client_id": settings.STRAVA_CLIENT_ID,
                    "client_secret": settings.STRAVA_CLIENT_SECRET,
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                },
            )
            response.raise_for_status()
            new_tokens = response.json()
            update_strava_tokens(
                new_tokens["access_token"],
                new_tokens["refresh_token"],
                new_tokens["expires_at"],
            )
            settings.STRAVA_ACCESS_TOKEN = new_tokens["access_token"]
            settings.STRAVA_REFRESH_TOKEN = new_tokens["refresh_token"]
            settings.STRAVA_EXPIRES_AT = new_tokens["expires_at"]
            print("Strava token refreshed successfully.")
            return True
    return False


async def get_strava_headers():
    await refresh_strava_token()
    tokens = get_strava_tokens()
    if not tokens:
        raise Exception("Strava tokens not available.")
    access_token, _, _ = tokens
    return {"Authorization": f"Bearer {access_token}"}


async def exchange_code_for_tokens(code: str) -> dict:
    async with httpx.AsyncClient() as client:
        response = await client.post(
            OAUTH_URL,
            data={
                "client_id": settings.STRAVA_CLIENT_ID,
                "client_secret": settings.STRAVA_CLIENT_SECRET,
                "code": code,
                "grant_type": "authorization_code",
            },
        )
        response.raise_for_status()
        return response.json()
