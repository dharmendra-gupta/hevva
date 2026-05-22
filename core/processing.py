import httpx
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List

from core.config import settings
from core.database import is_activity_processed, record_processed_activity, update_strava_tokens
from core.strava_oauth import get_strava_headers

logger = logging.getLogger(__name__)

# Base URLs are now sourced from settings
STRAVA_API_BASE_URL = settings.STRAVA_API_BASE_URL
HEVY_API_BASE_URL = settings.HEVY_API_BASE_URL


async def fetch_strava_activity(activity_id: int) -> Dict[str, Any]:
    headers = await get_strava_headers()
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{STRAVA_API_BASE_URL}/activities/{activity_id}", headers=headers)
        response.raise_for_status()
        return response.json()


async def fetch_hevy_workouts() -> List[Dict[str, Any]]:
    headers = {"api-key": settings.HEVY_API_KEY}
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{HEVY_API_BASE_URL}/v1/workouts", headers=headers)
        response.raise_for_status()
        return response.json()["workouts"]


def format_hevy_workout(workout: Dict[str, Any]) -> str:
    description = "Updated by Hevva\n\n"
    for exercise in workout["exercises"]:
        superset_id = exercise.get("superset_id")
        header = exercise['title']
        if superset_id is not None:
            header += f" [superset:{superset_id}]"
        description += header + "\n"
        for s_idx, s in enumerate(exercise["sets"]):
            if s.get("reps") is not None:
                set_info = f"- Set {s_idx + 1}: {s['reps']} reps"
            elif s.get("duration_seconds") is not None:
                set_info = f"- Set {s_idx + 1}: {s['duration_seconds']}s"
            else:
                set_info = f"- Set {s_idx + 1}"
            if s.get("weight_kg") is not None:
                set_info += f" @ {s['weight_kg']}kg"
            if s.get("rpe") is not None:
                set_info += f" RPE: {s['rpe']}"
            description += set_info + "\n"
        description += "\n"
    return description


async def update_strava_activity(activity_id: int, title: str, description: str):
    headers = await get_strava_headers()
    async with httpx.AsyncClient() as client:
        response = await client.put(
            f"{STRAVA_API_BASE_URL}/activities/{activity_id}",
            headers=headers,
            json={
                "name": title,
                "description": description
            },
        )
        response.raise_for_status()
        return response.json()


async def process_strava_activity(activity_id: int):
    if is_activity_processed(activity_id):
        logger.info(f"Activity {activity_id} already processed. Skipping.")
        return

    try:
        strava_activity = await fetch_strava_activity(activity_id)

        # FR-2: Categorical Type Isolation Engine
        sport_type = strava_activity.get("sport_type")
        if sport_type not in ["WeightTraining", "Workout"]:
            logger.info(f"Activity {activity_id} is of type {sport_type}. Dropping.")
            record_processed_activity(activity_id)
            return

        strava_start_date_str = strava_activity["start_date"]
        strava_start_date = datetime.fromisoformat(strava_start_date_str.replace("Z", "+00:00"))

        hevy_workouts = await fetch_hevy_workouts()

        matching_hevy_workout = None
        for workout in hevy_workouts:
            hevy_end_time_str = workout.get("end_time") or workout.get("start_time")
            if hevy_end_time_str:
                hevy_time = datetime.fromisoformat(hevy_end_time_str.replace("Z", "+00:00"))
                time_delta = abs((strava_start_date - hevy_time).total_seconds())
                if time_delta <= settings.SYNC_WINDOW_SECONDS:
                    matching_hevy_workout = workout
                    break
        
        if matching_hevy_workout:
            title = matching_hevy_workout['title']
            description = format_hevy_workout(matching_hevy_workout)
            await update_strava_activity(activity_id, title, description)
            logger.info(f"Successfully updated Strava activity {activity_id} with Hevy workout data.")
            record_processed_activity(activity_id)
        else:
            logger.info(f"No matching Hevy workout found for Strava activity {activity_id}.")
            record_processed_activity(activity_id)

    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error processing activity {activity_id}: {e}")
        # Optionally, handle specific HTTP error codes (e.g., 401 for token issues)
    except Exception as e:
        logger.error(f"Error processing activity {activity_id}: {e}")

