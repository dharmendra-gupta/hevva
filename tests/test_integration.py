import json
import os
import pytest
import httpx
from fastapi.testclient import TestClient
from unittest.mock import patch, AsyncMock, MagicMock
from datetime import datetime, timedelta

from main import app
from core.config import settings


@pytest.fixture(autouse=True)
def mock_db_functions_integration():
    with (
        patch("core.processing.is_activity_processed", return_value=False) as mock_is_processed,
        patch("core.processing.record_processed_activity", return_value=None) as mock_record_processed,
        patch("core.strava_oauth.get_strava_tokens", return_value=("access_token_123", "refresh_token_456", 9999999999)) as mock_get_tokens,
        patch("core.strava_oauth.update_strava_tokens", return_value=None) as mock_update_tokens,
        patch("main.get_config", return_value=None),
        patch("main.set_config", return_value=None),
        patch("main.update_strava_tokens", return_value=None),
    ):
        yield mock_is_processed, mock_record_processed, mock_get_tokens, mock_update_tokens


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def mock_strava_activity_weight_training():
    return {
        "id": 12345,
        "sport_type": "WeightTraining",
        "start_date": (datetime.utcnow() - timedelta(minutes=15)).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


@pytest.fixture
def mock_hevy_workouts_integration():
    now = datetime.utcnow()
    return [
        {
            "title": "Integration Test Workout",
            "end_time": (now - timedelta(minutes=10)).isoformat(timespec="seconds") + "Z",
            "exercises": [
                {
                    "title": "Test Exercise",
                    "sets": [
                        {"reps": 5, "weight_kg": 50, "rpe": 8},
                    ],
                },
            ],
        },
    ]


@pytest.mark.asyncio
async def test_webhook_post_triggers_processing(client, mock_strava_activity_weight_training, mock_hevy_workouts_integration, mock_db_functions_integration):
    mock_is_processed, mock_record_processed, mock_get_tokens, mock_update_tokens = mock_db_functions_integration

    with (
        patch("core.processing.fetch_strava_activity", new_callable=AsyncMock, return_value=mock_strava_activity_weight_training) as mock_fetch_strava,
        patch("core.processing.fetch_hevy_workouts", new_callable=AsyncMock, return_value=mock_hevy_workouts_integration) as mock_fetch_hevy,
        patch("core.processing.update_strava_activity", new_callable=AsyncMock, return_value={"id": 12345, "name": "Updated"}) as mock_update_strava,
        patch("core.strava_oauth.refresh_strava_token", new_callable=AsyncMock, return_value=False),
    ):
        response = client.post(
            "/webhook",
            json={
                "aspect_type": "create",
                "event_time": int(datetime.now().timestamp()),
                "object_id": mock_strava_activity_weight_training["id"],
                "object_type": "activity",
                "owner_id": 123,
                "subscription_id": 456,
                "updates": {},
            },
        )

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    mock_fetch_strava.assert_called_once_with(mock_strava_activity_weight_training["id"])
    mock_fetch_hevy.assert_called_once()
    mock_update_strava.assert_called_once()
    mock_record_processed.assert_called_once_with(mock_strava_activity_weight_training["id"])


def test_webhook_get_verification(client):
    settings.STRAVA_VERIFY_TOKEN = "TEST_VERIFY_TOKEN"
    response = client.get(
        "/webhook",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": "TEST_VERIFY_TOKEN",
            "hub.challenge": "challenge_accepted",
        },
    )
    assert response.status_code == 200
    assert response.json() == {"hub.challenge": "challenge_accepted"}


def test_webhook_get_verification_invalid_token(client):
    settings.STRAVA_VERIFY_TOKEN = "TEST_VERIFY_TOKEN"
    response = client.get(
        "/webhook",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": "WRONG_TOKEN",
            "hub.challenge": "challenge_accepted",
        },
    )
    assert response.status_code == 403


def test_health_endpoint(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_webhook_post_rejects_wrong_subscription_id(client):
    with patch("main.get_config", side_effect=lambda k: {"subscription_id": "999", "athlete_id": None}.get(k)):
        response = client.post(
            "/webhook",
            json={
                "aspect_type": "create",
                "event_time": int(datetime.now().timestamp()),
                "object_id": 12345,
                "object_type": "activity",
                "owner_id": 123,
                "subscription_id": 456,
                "updates": {},
            },
        )
    assert response.status_code == 403


def test_webhook_post_rejects_wrong_owner_id(client):
    with patch("main.get_config", side_effect=lambda k: {"subscription_id": None, "athlete_id": "999"}.get(k)):
        response = client.post(
            "/webhook",
            json={
                "aspect_type": "create",
                "event_time": int(datetime.now().timestamp()),
                "object_id": 12345,
                "object_type": "activity",
                "owner_id": 123,
                "subscription_id": 456,
                "updates": {},
            },
        )
    assert response.status_code == 403


def test_webhook_post_passes_with_matching_ids(client, mock_strava_activity_weight_training, mock_hevy_workouts_integration):
    with (
        patch("main.get_config", side_effect=lambda k: {"subscription_id": "456", "athlete_id": "123"}.get(k)),
        patch("core.processing.fetch_strava_activity", new_callable=AsyncMock, return_value=mock_strava_activity_weight_training),
        patch("core.processing.fetch_hevy_workouts", new_callable=AsyncMock, return_value=mock_hevy_workouts_integration),
        patch("core.processing.update_strava_activity", new_callable=AsyncMock),
        patch("core.strava_oauth.refresh_strava_token", new_callable=AsyncMock, return_value=False),
    ):
        response = client.post(
            "/webhook",
            json={
                "aspect_type": "create",
                "event_time": int(datetime.now().timestamp()),
                "object_id": mock_strava_activity_weight_training["id"],
                "object_type": "activity",
                "owner_id": 123,
                "subscription_id": 456,
                "updates": {},
            },
        )
    assert response.status_code == 200


def test_auth_login_redirects_to_strava(client):
    with patch("main.get_strava_tokens", return_value=None):
        response = client.get("/auth/login", follow_redirects=False)
    assert response.status_code in (302, 307)
    assert "strava.com/oauth/authorize" in response.headers["location"]


def test_auth_login_already_authorized(client):
    with patch("main.get_strava_tokens", return_value=("tok", "ref", 9999999999)):
        response = client.get("/auth/login")
    assert response.status_code == 200
    assert "already authorized" in response.text.lower()


def test_auth_callback_saves_tokens(client):
    fake_tokens = {
        "access_token": "new_access",
        "refresh_token": "new_refresh",
        "expires_at": 9999999999,
        "athlete": {"id": 42},
    }
    with (
        patch("main.exchange_code_for_tokens", new_callable=AsyncMock, return_value=fake_tokens) as mock_exchange,
        patch("main.update_strava_tokens") as mock_update,
        patch("main.set_config") as mock_set_config,
    ):
        response = client.get("/auth/callback", params={"code": "test_code"})

    assert response.status_code == 200
    assert "successful" in response.text.lower()
    mock_exchange.assert_called_once_with("test_code")
    mock_update.assert_called_once_with("new_access", "new_refresh", 9999999999)
    mock_set_config.assert_called_once_with("athlete_id", "42")


def test_auth_callback_missing_code(client):
    response = client.get("/auth/callback")
    assert response.status_code == 422


def test_auth_callback_exchange_fails(client):
    error = httpx.HTTPStatusError("400", request=MagicMock(), response=MagicMock())
    with patch("main.exchange_code_for_tokens", new_callable=AsyncMock, side_effect=error):
        response = client.get("/auth/callback", params={"code": "bad_code"})
    assert response.status_code == 400


def test_webhook_get_missing_hub_mode(client):
    settings.STRAVA_VERIFY_TOKEN = "TEST_VERIFY_TOKEN"
    response = client.get(
        "/webhook",
        params={
            "hub.verify_token": "TEST_VERIFY_TOKEN",
            "hub.challenge": "challenge",
        },
    )
    assert response.status_code == 403


def test_webhook_post_non_create_aspect_type(client):
    with patch("main.process_strava_activity", new_callable=AsyncMock) as mock_process:
        response = client.post(
            "/webhook",
            json={
                "aspect_type": "update",
                "event_time": int(datetime.now().timestamp()),
                "object_id": 12345,
                "object_type": "activity",
                "owner_id": 123,
                "subscription_id": 456,
                "updates": {"title": "New Name"},
            },
        )
    assert response.status_code == 200
    mock_process.assert_not_called()


def test_webhook_post_non_activity_object_type(client):
    with patch("main.process_strava_activity", new_callable=AsyncMock) as mock_process:
        response = client.post(
            "/webhook",
            json={
                "aspect_type": "create",
                "event_time": int(datetime.now().timestamp()),
                "object_id": 12345,
                "object_type": "athlete",
                "owner_id": 123,
                "subscription_id": 456,
                "updates": {},
            },
        )
    assert response.status_code == 200
    mock_process.assert_not_called()


def test_webhook_post_no_ids_stored_passes(client):
    with (
        patch("main.get_config", return_value=None),
        patch("main.process_strava_activity", new_callable=AsyncMock),
    ):
        response = client.post(
            "/webhook",
            json={
                "aspect_type": "create",
                "event_time": int(datetime.now().timestamp()),
                "object_id": 12345,
                "object_type": "activity",
                "owner_id": 123,
                "subscription_id": 456,
                "updates": {},
            },
        )
    assert response.status_code == 200


def test_webhook_post_real_strava_payload(client):
    sample_path = os.path.join(os.path.dirname(__file__), "strava_sample_json", "webhook_request.json")
    with open(sample_path) as f:
        payload = json.load(f)

    with patch("main.process_strava_activity", new_callable=AsyncMock) as mock_process:
        response = client.post("/webhook", json=payload)

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    mock_process.assert_called_once_with(payload["object_id"])
