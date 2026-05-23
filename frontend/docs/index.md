# Hevva

**The event-driven sync engine for hybrid athletes.**

Inject your high-fidelity Hevy gym logs directly into your sensor-rich wearable activities on Strava. No background tasks, no data compromise, zero configuration bloat.

---

## The Problem

As a multi-sport athlete, you probably track your lifting sessions in two places:

1. **On your wrist** (Garmin, Whoop, Polar, Coros) — to capture strain, heart rate curves, and metabolic metrics.
2. **On your phone** (Hevy) — because inputting exercises, sets, weights, and reps on a smartwatch screen is tedious.

When you save both, they independently push to Strava. You end up with a duplicate mess:

- A **wearable activity** with rich biometrics but a blank description named "Weight Training"
- A **Hevy activity** with your full workout log but no sensor data

Turning off either sync leaves your feed incomplete.

---

## The Solution

Hevva acts as a reactive webhook router. When your wearable sends its biometric activity to Strava, Hevva catches the event, finds the matching Hevy workout using a time-delta window, and updates the Strava activity with your full exercise breakdown — title, sets, reps, weight, and RPE.

Your biometric data stays intact. Your workout log is injected. No duplicates.

---

## Before vs. After

=== "Before (standard wearable sync)"

    **Title:** Weight Training

    **Description:** *(empty)*

=== "After (Hevva)"

    **Title:** Push Day — Hypertrophy Tier 1

    **Description:**
    ```
    Updated by Hevva

    Barbell Bench Press
    - Set 1: 8 reps @ 80kg RPE: 8
    - Set 2: 8 reps @ 80kg RPE: 8
    - Set 3: 6 reps @ 82.5kg RPE: 9

    Standing Dumbbell Press
    - Set 1: 10 reps @ 22kg
    - Set 2: 10 reps @ 22kg
    ```

---

## How it works

```
Gym session logged in Hevy
        ↓
Wearable auto-creates a WeightTraining activity on Strava
        ↓
Strava POSTs webhook event to Hevva
        ↓
Hevva fetches both activities and time-matches them
        ↓
Strava activity updated with Hevy title and exercise detail
```

Hevva spends 99% of its life completely idle. It only runs for a few seconds when a Strava webhook wakes it up.

---

## Quick start

```bash
cp Hevva/.env.example Hevva/.env
# fill in your credentials
docker compose up -d
```

Then visit `https://hevva.yourdomain.com/auth/login` to authorize Strava.

See the [Setup guide](setup.md) for the full walkthrough.

---

## Who is this for?

Hevva is for athletes who use **a non-Apple wearable** (Garmin, Polar, Coros, Whoop, etc.) alongside Hevy for detailed workout tracking. Apple Watch users have native integrations that handle this differently.

---

## Self-hosted, lightweight

- Runs as a single Docker container
- SQLite database — no external dependencies
- Under 30 MB RAM at idle — works on a Raspberry Pi or home NAS
- No polling, no cron jobs — purely event-driven
