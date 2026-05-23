# Setup

## Before you start

You need:

- A [Strava API application](https://www.strava.com/settings/api) — free to create
- A Hevy account with API access
- Docker on your server
- A domain pointed at your server (required — Strava webhooks only work over HTTPS)

---

## Step 1 — Create a Strava app

Go to [strava.com/settings/api](https://www.strava.com/settings/api) and create an app. Note your **Client ID** and **Client Secret**.

In the **Authorization Callback Domain** field, enter your domain (e.g. `hevva.yourdomain.com`).

---

## Step 2 — Configure environment

```bash
cp Hevva/.env.example Hevva/.env
```

Edit `.env` and fill in your values:

```env
STRAVA_CLIENT_ID=...
STRAVA_CLIENT_SECRET=...
STRAVA_VERIFY_TOKEN=pick_any_random_string
HEVY_API_KEY=...
WEBHOOK_CALLBACK_URL=https://hevva.yourdomain.com/webhook
STRAVA_REDIRECT_URI=https://hevva.yourdomain.com/auth/callback
DASHBOARD_USERNAME=admin
DASHBOARD_PASSWORD=your_secure_password
```

---

## Step 3 — Reverse proxy

See the [Networking guide](networking.md) for setup options (Caddy, nginx, Cloudflare).

---

## Step 4 — Start the container

```bash
docker compose up -d
```

---

## Step 5 — Authorize Strava

Open in your browser:

```
https://hevva.yourdomain.com/auth/login
```

This redirects you to Strava to authorize the app. After you approve, tokens are saved automatically.

---

## Step 6 — Disable Hevy's native Strava sync

!!! warning "Important — prevents duplicate activities"
    Hevva updates your **wearable activity** with Hevy data. If Hevy's own Strava sync is still enabled, Hevy will also push a separate activity to Strava for the same session — giving you two entries per workout.

To fix this, turn off Hevy's Strava integration:

1. Open the Hevy app
2. Go to **Profile → Settings → Connected Apps**
3. Disconnect **Strava**

Hevva does not delete activities on your behalf — this step is yours to do once.

!!! note
    If you don't use a separate wearable and only track in Hevy, leave Hevy's sync enabled and skip Hevva — it's designed for athletes tracking the same session in both a wearable and Hevy.

---

## Step 7 — Done

On startup, Hevva registers the Strava webhook automatically. Check the logs:

```bash
docker compose logs -f
```

Look for:
```
Webhook subscription registered (id=XXXXX)
```

From this point, every new `WeightTraining` or `Workout` activity on Strava will be enriched with your Hevy data.
