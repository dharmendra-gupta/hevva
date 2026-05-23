# Configuration

## Environment variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `STRAVA_CLIENT_ID` | Yes | — | From your Strava app |
| `STRAVA_CLIENT_SECRET` | Yes | — | From your Strava app |
| `STRAVA_VERIFY_TOKEN` | Yes | — | Any random string — used to verify webhook ownership |
| `HEVY_API_KEY` | Yes | — | From Hevy |
| `WEBHOOK_CALLBACK_URL` | Yes | — | Public URL Strava posts events to |
| `STRAVA_REDIRECT_URI` | Yes | — | Must match your Strava app settings exactly |
| `DASHBOARD_USERNAME` | Yes | — | Username for the web dashboard |
| `DASHBOARD_PASSWORD` | Yes | — | Password for the web dashboard |
| `DOMAIN` | Caddy only | — | Your domain — used by the `:caddy` image for auto-HTTPS |
| `SYNC_WINDOW_SECONDS` | No | `1800` | How close in time (seconds) a Hevy workout must be to a Strava activity to be matched |

---

## Web dashboard

Once the container is running and Strava is authorized, the dashboard is available at:

```
https://hevva.yourdomain.com/
```

It is protected by HTTP Basic Auth using `DASHBOARD_USERNAME` and `DASHBOARD_PASSWORD`.

### What you can change

| Setting | Description |
|---------|-------------|
| **Sync window** | How close in time (in seconds) a Hevy workout must be to the Strava activity's start time to be considered a match. Default is 1800 (30 min). |

Changes take effect immediately — no container restart needed.

!!! note "Sensitive settings stay in .env"
    API keys, OAuth secrets, and credentials are never configurable through the dashboard. Those live in `.env` only.

---

## Endpoints

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/` | Required | Web configuration dashboard |
| `POST` | `/api/config` | Required | Update a runtime setting |
| `GET` | `/auth/login` | — | Start Strava OAuth — visit once to authorize |
| `GET` | `/auth/callback` | — | OAuth callback — Strava redirects here |
| `GET` | `/webhook` | — | Strava webhook verification |
| `POST` | `/webhook` | — | Receives Strava activity events |
| `GET` | `/health` | — | Health check |

---

## Notes

- Tokens are stored in `./data/Hevva.db` (SQLite) and refreshed automatically — you never need to re-authorize unless you revoke access on Strava.
- Activities that don't match a Hevy workout within the sync window are left unchanged and marked processed (no re-processing on the next event).
- Only `WeightTraining` and `Workout` sport types are processed. Runs, rides, swims, and all other types are ignored.
