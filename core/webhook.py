import logging
import httpx
from core.config import settings
from core.database import set_config

logger = logging.getLogger(__name__)


async def get_existing_subscription() -> dict | None:
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{settings.STRAVA_API_BASE_URL}/push_subscriptions",
            params={
                "client_id": settings.STRAVA_CLIENT_ID,
                "client_secret": settings.STRAVA_CLIENT_SECRET,
            },
        )
        if response.status_code == 200:
            subs = response.json()
            return subs[0] if subs else None
    return None


async def register_webhook():
    if not settings.WEBHOOK_CALLBACK_URL:
        logger.warning("WEBHOOK_CALLBACK_URL not set — skipping webhook registration.")
        return

    try:
        existing = await get_existing_subscription()
        if existing:
            set_config("subscription_id", str(existing["id"]))
            logger.info(f"Webhook subscription already active (id={existing['id']}). Skipping.")
            return

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{settings.STRAVA_API_BASE_URL}/push_subscriptions",
                data={
                    "client_id": settings.STRAVA_CLIENT_ID,
                    "client_secret": settings.STRAVA_CLIENT_SECRET,
                    "callback_url": settings.WEBHOOK_CALLBACK_URL,
                    "verify_token": settings.STRAVA_VERIFY_TOKEN,
                },
            )
            if response.status_code == 201:
                sub = response.json()
                set_config("subscription_id", str(sub["id"]))
                logger.info(f"Webhook subscription registered (id={sub['id']}).")
            else:
                logger.error(f"Webhook registration failed: {response.status_code} {response.text}")

    except Exception as e:
        logger.error(f"Webhook registration error: {e}")
