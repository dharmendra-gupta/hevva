import json
import os
import time
import pytest
import httpx
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from core.processing import process_strava_activity, format_hevy_workout
from core.strava_oauth import exchange_code_for_tokens, refresh_strava_token, get_strava_headers
from core.webhook import register_webhook, get_existing_subscription
from core.config import settings


@pytest.fixture(autouse=True)
def mock_db_functions():
    with (
        patch("core.processing.is_activity_processed", return_value=False) as mock_is_processed,
        patch("core.processing.record_processed_activity", return_value=None) as mock_record_processed,
        patch("core.strava_oauth.get_strava_tokens", return_value=("access_token", "refresh_token", 9999999999)) as mock_get_tokens,
        patch("core.strava_oauth.update_strava_tokens", return_value=None) as mock_update_tokens,
        patch("core.database.set_config", return_value=None),
    ):
        yield mock_is_processed, mock_record_processed, mock_get_tokens, mock_update_tokens


@pytest.fixture
def mock_strava_activity_weight_training():
    return {
        "id": 12345,
        "sport_type": "WeightTraining",
        "start_date": (datetime.utcnow() - timedelta(minutes=15)).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


@pytest.fixture
def mock_strava_activity_running():
    return {
        "id": 67890,
        "sport_type": "Running",
        "start_date": (datetime.utcnow() - timedelta(minutes=15)).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


@pytest.fixture
def mock_hevy_workouts():
    now = datetime.utcnow()
    return [
        {
            "title": "Push Day - Hypertrophy Tier 1",
            "end_time": (now - timedelta(minutes=10)).isoformat(timespec="seconds") + "Z",
            "exercises": [
                {
                    "title": "Barbell Bench Press",
                    "sets": [
                        {"reps": 8, "weight_kg": 100, "rpe": 7},
                        {"reps": 8, "weight_kg": 100, "rpe": 7.5},
                    ],
                },
                {
                    "title": "Dumbbell Shoulder Press",
                    "sets": [
                        {"reps": 10, "weight_kg": 30, "rpe": None},
                    ],
                },
            ],
        },
        {
            "title": "Leg Day",
            "end_time": (now - timedelta(hours=2)).isoformat(timespec="seconds") + "Z",
            "exercises": [],
        },
    ]


# ---------------------------------------------------------------------------
# process_strava_activity — dedup
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_already_processed_activity_skips():
    with (
        patch("core.processing.is_activity_processed", return_value=True),
        patch("core.processing.fetch_strava_activity", new_callable=AsyncMock) as mock_fetch,
    ):
        await process_strava_activity(12345)
        mock_fetch.assert_not_called()


# ---------------------------------------------------------------------------
# process_strava_activity — sport type filtering
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_webhook_rejects_non_strength_training_activity(mock_strava_activity_running, mock_db_functions):
    mock_is_processed, mock_record_processed, _, _ = mock_db_functions

    with (
        patch("core.processing.fetch_strava_activity", new_callable=AsyncMock, return_value=mock_strava_activity_running),
        patch("core.processing.fetch_hevy_workouts", new_callable=AsyncMock) as mock_fetch_hevy,
        patch("core.processing.update_strava_activity", new_callable=AsyncMock) as mock_update_strava,
    ):
        await process_strava_activity(mock_strava_activity_running["id"])

        mock_record_processed.assert_called_once_with(mock_strava_activity_running["id"])
        mock_fetch_hevy.assert_not_called()
        mock_update_strava.assert_not_called()


@pytest.mark.asyncio
async def test_workout_sport_type_is_processed(mock_hevy_workouts, mock_db_functions):
    mock_is_processed, mock_record_processed, _, _ = mock_db_functions
    now = datetime.utcnow()
    activity = {
        "id": 99,
        "sport_type": "Workout",
        "start_date": (now - timedelta(minutes=10)).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    with (
        patch("core.processing.fetch_strava_activity", new_callable=AsyncMock, return_value=activity),
        patch("core.processing.fetch_hevy_workouts", new_callable=AsyncMock, return_value=mock_hevy_workouts),
        patch("core.processing.update_strava_activity", new_callable=AsyncMock) as mock_update,
    ):
        await process_strava_activity(99)
        mock_update.assert_called_once()


# ---------------------------------------------------------------------------
# process_strava_activity — time matching
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_time_delta_matching_within_window(mock_strava_activity_weight_training, mock_hevy_workouts, mock_db_functions):
    mock_is_processed, mock_record_processed, _, _ = mock_db_functions

    strava_time = datetime.fromisoformat(mock_hevy_workouts[0]["end_time"].replace("Z", "+00:00")) + timedelta(seconds=settings.SYNC_WINDOW_SECONDS - 60)
    mock_strava_activity_weight_training["start_date"] = strava_time.strftime("%Y-%m-%dT%H:%M:%SZ")

    with (
        patch("core.processing.fetch_strava_activity", new_callable=AsyncMock, return_value=mock_strava_activity_weight_training),
        patch("core.processing.fetch_hevy_workouts", new_callable=AsyncMock, return_value=mock_hevy_workouts) as mock_fetch_hevy,
        patch("core.processing.update_strava_activity", new_callable=AsyncMock) as mock_update_strava,
    ):
        await process_strava_activity(mock_strava_activity_weight_training["id"])

        mock_fetch_hevy.assert_called_once()
        mock_update_strava.assert_called_once()
        mock_record_processed.assert_called_once_with(mock_strava_activity_weight_training["id"])


@pytest.mark.asyncio
async def test_time_delta_matching_outside_window(mock_strava_activity_weight_training, mock_hevy_workouts, mock_db_functions):
    mock_is_processed, mock_record_processed, _, _ = mock_db_functions

    strava_time = datetime.fromisoformat(mock_hevy_workouts[0]["end_time"].replace("Z", "+00:00")) + timedelta(seconds=settings.SYNC_WINDOW_SECONDS + 60)
    mock_strava_activity_weight_training["start_date"] = strava_time.strftime("%Y-%m-%dT%H:%M:%SZ")

    with (
        patch("core.processing.fetch_strava_activity", new_callable=AsyncMock, return_value=mock_strava_activity_weight_training),
        patch("core.processing.fetch_hevy_workouts", new_callable=AsyncMock, return_value=mock_hevy_workouts) as mock_fetch_hevy,
        patch("core.processing.update_strava_activity", new_callable=AsyncMock) as mock_update_strava,
    ):
        await process_strava_activity(mock_strava_activity_weight_training["id"])

        mock_fetch_hevy.assert_called_once()
        mock_update_strava.assert_not_called()
        mock_record_processed.assert_called_once_with(mock_strava_activity_weight_training["id"])


@pytest.mark.asyncio
async def test_hevy_workout_uses_start_time_fallback(mock_db_functions):
    mock_is_processed, mock_record_processed, _, _ = mock_db_functions
    now = datetime.utcnow()
    activity = {
        "id": 55,
        "sport_type": "WeightTraining",
        "start_date": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    workouts = [{
        "title": "Morning Lift",
        "end_time": None,
        "start_time": (now - timedelta(minutes=5)).isoformat(timespec="seconds") + "Z",
        "exercises": [{"title": "Squat", "sets": [{"reps": 5, "weight_kg": 100, "rpe": None}]}],
    }]
    with (
        patch("core.processing.fetch_strava_activity", new_callable=AsyncMock, return_value=activity),
        patch("core.processing.fetch_hevy_workouts", new_callable=AsyncMock, return_value=workouts),
        patch("core.processing.update_strava_activity", new_callable=AsyncMock) as mock_update,
    ):
        await process_strava_activity(55)
        mock_update.assert_called_once()


@pytest.mark.asyncio
async def test_empty_hevy_workout_list(mock_strava_activity_weight_training, mock_db_functions):
    mock_is_processed, mock_record_processed, _, _ = mock_db_functions
    with (
        patch("core.processing.fetch_strava_activity", new_callable=AsyncMock, return_value=mock_strava_activity_weight_training),
        patch("core.processing.fetch_hevy_workouts", new_callable=AsyncMock, return_value=[]),
        patch("core.processing.update_strava_activity", new_callable=AsyncMock) as mock_update,
    ):
        await process_strava_activity(mock_strava_activity_weight_training["id"])
        mock_update.assert_not_called()
        mock_record_processed.assert_called_once_with(mock_strava_activity_weight_training["id"])


@pytest.mark.asyncio
async def test_multiple_workouts_in_window_picks_first(mock_strava_activity_weight_training, mock_db_functions):
    mock_is_processed, mock_record_processed, _, _ = mock_db_functions
    now = datetime.utcnow()
    mock_strava_activity_weight_training["start_date"] = (now - timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%SZ")

    workouts = [
        {"title": "First Workout", "end_time": (now - timedelta(minutes=3)).isoformat(timespec="seconds") + "Z", "exercises": []},
        {"title": "Second Workout", "end_time": (now - timedelta(minutes=4)).isoformat(timespec="seconds") + "Z", "exercises": []},
    ]
    with (
        patch("core.processing.fetch_strava_activity", new_callable=AsyncMock, return_value=mock_strava_activity_weight_training),
        patch("core.processing.fetch_hevy_workouts", new_callable=AsyncMock, return_value=workouts),
        patch("core.processing.update_strava_activity", new_callable=AsyncMock) as mock_update,
    ):
        await process_strava_activity(mock_strava_activity_weight_training["id"])
        mock_update.assert_called_once()
        title_arg = mock_update.call_args[0][1]
        assert "First Workout" in title_arg


# ---------------------------------------------------------------------------
# process_strava_activity — HTTP errors do not mark activity as processed
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_strava_fetch_http_error_activity_not_marked_processed(mock_strava_activity_weight_training, mock_db_functions):
    mock_is_processed, mock_record_processed, _, _ = mock_db_functions
    error = httpx.HTTPStatusError("401", request=MagicMock(), response=MagicMock())
    with patch("core.processing.fetch_strava_activity", new_callable=AsyncMock, side_effect=error):
        await process_strava_activity(mock_strava_activity_weight_training["id"])
    mock_record_processed.assert_not_called()


@pytest.mark.asyncio
async def test_hevy_fetch_http_error_activity_not_marked_processed(mock_strava_activity_weight_training, mock_db_functions):
    mock_is_processed, mock_record_processed, _, _ = mock_db_functions
    error = httpx.HTTPStatusError("500", request=MagicMock(), response=MagicMock())
    with (
        patch("core.processing.fetch_strava_activity", new_callable=AsyncMock, return_value=mock_strava_activity_weight_training),
        patch("core.processing.fetch_hevy_workouts", new_callable=AsyncMock, side_effect=error),
    ):
        await process_strava_activity(mock_strava_activity_weight_training["id"])
    mock_record_processed.assert_not_called()


@pytest.mark.asyncio
async def test_process_real_strava_activity_response(mock_db_functions):
    mock_is_processed, mock_record_processed, _, _ = mock_db_functions
    sample_path = os.path.join(os.path.dirname(__file__), "strava_sample_json", "activities_{activity_id}.json")
    with open(sample_path) as f:
        activity = json.load(f)

    with (
        patch("core.processing.fetch_strava_activity", new_callable=AsyncMock, return_value=activity),
        patch("core.processing.fetch_hevy_workouts", new_callable=AsyncMock, return_value=[]) as mock_fetch_hevy,
        patch("core.processing.update_strava_activity", new_callable=AsyncMock) as mock_update,
    ):
        await process_strava_activity(activity["id"])

    mock_fetch_hevy.assert_called_once()
    mock_update.assert_not_called()
    mock_record_processed.assert_called_once_with(activity["id"])


# ---------------------------------------------------------------------------
# format_hevy_workout_to_markdown
# ---------------------------------------------------------------------------

def test_text_composition_rendering(mock_hevy_workouts):
    workout = mock_hevy_workouts[0]
    expected = (
        "Updated by Hevva\n\n"
        "Push Day - Hypertrophy Tier 1\n\n"
        "Barbell Bench Press\n"
        "- Set 1: 8 reps @ 100kg RPE: 7\n"
        "- Set 2: 8 reps @ 100kg RPE: 7.5\n\n"
        "Dumbbell Shoulder Press\n"
        "- Set 1: 10 reps @ 30kg\n\n"
    )
    assert format_hevy_workout(workout) == expected


def test_format_markdown_exercise_with_empty_sets():
    workout = {"title": "Quick Session", "exercises": [{"title": "Plank", "sets": []}]}
    result = format_hevy_workout(workout)
    assert "Plank" in result
    assert "Set 1" not in result


def test_format_markdown_workout_with_no_exercises():
    workout = {"title": "Empty Session", "exercises": []}
    result = format_hevy_workout(workout)
    assert result.startswith("Updated by Hevva\n\n")
    assert "Empty Session" in result


def test_format_real_hevy_response():
    import json
    import os
    sample_path = os.path.join(os.path.dirname(__file__), "hevy_sample_json", "v1_workouts_{workoutId}.json")
    with open(sample_path) as f:
        workout = json.load(f)

    result = format_hevy_workout(workout)
    print("\n--- Real Hevy Workout Description Output ---")
    print(result)
    print("---")

    assert result.startswith("Updated by Hevva\n\n")
    assert "Reactivation Workout 5" in result
    assert "Seated Chest Press (Cable)" in result
    assert "Face Pull" in result
    assert "Leg Press (Machine) [superset:0]" in result
    assert "Seated Cable Row - V Grip (Cable) [superset:0]" in result
    assert "Lying Leg Curl (Machine) [superset:1]" in result
    assert "Plank [superset:1]" in result
    assert "Single Leg Decline Squats" in result
    assert "60s" in result
    assert "@ 45kg" in result
    assert "12 reps" in result


def test_format_markdown_superset_label():
    workout = {
        "title": "Superset Session",
        "exercises": [
            {
                "title": "Squat",
                "superset_id": 0,
                "sets": [{"reps": 10, "weight_kg": 80, "rpe": None}],
            },
            {
                "title": "Leg Press",
                "superset_id": 0,
                "sets": [{"reps": 12, "weight_kg": 60, "rpe": None}],
            },
            {
                "title": "Plank",
                "superset_id": None,
                "sets": [{"reps": None, "duration_seconds": 45, "weight_kg": None, "rpe": None}],
            },
        ],
    }
    result = format_hevy_workout(workout)
    assert "Squat [superset:0]" in result
    assert "Leg Press [superset:0]" in result
    assert "Plank\n" in result  # no superset label
    assert "[superset:" not in result.split("Plank")[1].split("\n")[0]


# ---------------------------------------------------------------------------
# refresh_strava_token
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_refresh_token_no_tokens_in_db():
    with (
        patch("core.strava_oauth.get_strava_tokens", return_value=None),
        patch("core.strava_oauth.httpx.AsyncClient") as mock_client_cls,
    ):
        result = await refresh_strava_token()
        assert result is False
        mock_client_cls.assert_not_called()


@pytest.mark.asyncio
async def test_refresh_token_still_valid():
    future_expiry = int(time.time()) + 3600
    with (
        patch("core.strava_oauth.get_strava_tokens", return_value=("access", "refresh", future_expiry)),
        patch("core.strava_oauth.httpx.AsyncClient") as mock_client_cls,
    ):
        result = await refresh_strava_token()
        assert result is False
        mock_client_cls.assert_not_called()


@pytest.mark.asyncio
async def test_refresh_token_expired(mock_db_functions):
    mock_is_processed, mock_record_processed, mock_get_tokens, mock_update_tokens = mock_db_functions
    past_expiry = int(time.time()) - 100
    new_tokens = {"access_token": "new_access", "refresh_token": "new_refresh", "expires_at": int(time.time()) + 21600}

    mock_response = MagicMock()
    mock_response.json.return_value = new_tokens
    mock_response.raise_for_status = MagicMock()

    with (
        patch("core.strava_oauth.get_strava_tokens", return_value=("old_access", "old_refresh", past_expiry)),
        patch("core.strava_oauth.httpx.AsyncClient") as mock_client_cls,
    ):
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client_cls.return_value.__aenter__.return_value = mock_client

        result = await refresh_strava_token()

    assert result is True
    mock_update_tokens.assert_called_once_with("new_access", "new_refresh", new_tokens["expires_at"])


# ---------------------------------------------------------------------------
# get_strava_headers
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_strava_headers_raises_when_no_tokens():
    with (
        patch("core.strava_oauth.refresh_strava_token", new_callable=AsyncMock),
        patch("core.strava_oauth.get_strava_tokens", return_value=None),
    ):
        with pytest.raises(Exception, match="Strava tokens not available"):
            await get_strava_headers()


# ---------------------------------------------------------------------------
# exchange_code_for_tokens
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_exchange_code_for_tokens_returns_token_data():
    fake_response = {
        "access_token": "abc",
        "refresh_token": "def",
        "expires_at": 9999999999,
        "athlete": {"id": 42},
    }
    mock_response = MagicMock()
    mock_response.json.return_value = fake_response
    mock_response.raise_for_status = MagicMock()

    with patch("core.strava_oauth.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client_cls.return_value.__aenter__.return_value = mock_client

        result = await exchange_code_for_tokens("test_code")

    assert result["access_token"] == "abc"
    assert result["athlete"]["id"] == 42
    call_data = mock_client.post.call_args[1]["data"]
    assert call_data["code"] == "test_code"
    assert call_data["grant_type"] == "authorization_code"


@pytest.mark.asyncio
async def test_exchange_code_http_error():
    mock_response = MagicMock()
    mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "400", request=MagicMock(), response=MagicMock()
    )
    with patch("core.strava_oauth.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client_cls.return_value.__aenter__.return_value = mock_client

        with pytest.raises(httpx.HTTPStatusError):
            await exchange_code_for_tokens("bad_code")


# ---------------------------------------------------------------------------
# register_webhook
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_register_webhook_skips_without_callback_url():
    with patch.object(settings, "WEBHOOK_CALLBACK_URL", None):
        with patch("core.webhook.get_existing_subscription") as mock_get:
            await register_webhook()
            mock_get.assert_not_called()


@pytest.mark.asyncio
async def test_register_webhook_skips_if_already_registered():
    with (
        patch.object(settings, "WEBHOOK_CALLBACK_URL", "https://hevva.example.com/webhook"),
        patch("core.webhook.get_existing_subscription", new_callable=AsyncMock, return_value={"id": 99}),
        patch("core.webhook.httpx.AsyncClient") as mock_client_cls,
    ):
        await register_webhook()
        mock_client_cls.assert_not_called()


@pytest.mark.asyncio
async def test_register_webhook_registers_when_no_subscription():
    mock_response = MagicMock()
    mock_response.status_code = 201
    mock_response.json.return_value = {"id": 77}

    with (
        patch.object(settings, "WEBHOOK_CALLBACK_URL", "https://hevva.example.com/webhook"),
        patch("core.webhook.get_existing_subscription", new_callable=AsyncMock, return_value=None),
        patch("core.webhook.httpx.AsyncClient") as mock_client_cls,
    ):
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client_cls.return_value.__aenter__.return_value = mock_client

        await register_webhook()

        mock_client.post.assert_called_once()
        call_data = mock_client.post.call_args[1]["data"]
        assert call_data["callback_url"] == "https://hevva.example.com/webhook"


@pytest.mark.asyncio
async def test_register_webhook_registration_fails_logs_error():
    mock_response = MagicMock()
    mock_response.status_code = 400
    mock_response.text = "Bad Request"

    with (
        patch.object(settings, "WEBHOOK_CALLBACK_URL", "https://hevva.example.com/webhook"),
        patch("core.webhook.get_existing_subscription", new_callable=AsyncMock, return_value=None),
        patch("core.webhook.httpx.AsyncClient") as mock_client_cls,
    ):
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client_cls.return_value.__aenter__.return_value = mock_client

        await register_webhook()  # must not raise


@pytest.mark.asyncio
async def test_register_webhook_network_error_logs_error():
    with (
        patch.object(settings, "WEBHOOK_CALLBACK_URL", "https://hevva.example.com/webhook"),
        patch("core.webhook.get_existing_subscription", new_callable=AsyncMock, side_effect=Exception("connection refused")),
    ):
        await register_webhook()  # must not raise


# ---------------------------------------------------------------------------
# get_existing_subscription
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_existing_subscription_empty_list_returns_none():
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = []

    with patch("core.webhook.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client_cls.return_value.__aenter__.return_value = mock_client

        result = await get_existing_subscription()
        assert result is None
