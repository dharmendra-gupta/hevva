# Hevva

Hevva syncs your [Hevy](https://www.hevyapp.com) workout data into Strava automatically. When Garmin (or the Strava app) creates a `WeightTraining` activity, Hevva finds the matching Hevy workout and updates the Strava activity with your full exercise breakdown — sets, reps, weight, and RPE.

---

## Before you start

You need:

- A [Strava API application](https://www.strava.com/settings/api) — free to create
- A Hevy account with API access
- Docker + Docker Compose on your server
- A domain pointed at your server (required — Strava webhooks only work over HTTPS)

---

## Setup

### Step 1 — Create a Strava app

Go to [strava.com/settings/api](https://www.strava.com/settings/api) and create an app. Note your **Client ID** and **Client Secret**.

In the **Authorization Callback Domain** field, enter your domain (e.g. `hevva.yourdomain.com`).

---

### Step 2 — Configure environment

```bash
cp .env.example .env
```

Edit `.env` and fill in your values:

```env
STRAVA_CLIENT_ID=...
STRAVA_CLIENT_SECRET=...
STRAVA_VERIFY_TOKEN=pick_any_random_string
HEVY_API_KEY=...
WEBHOOK_CALLBACK_URL=https://hevva.yourdomain.com/webhook
STRAVA_REDIRECT_URI=https://hevva.yourdomain.com/auth/callback
```

---

### Step 3 — Reverse proxy

Pick the setup that matches your situation.

#### I don't have a reverse proxy yet

The simplest option is [Caddy](https://caddyserver.com) — it handles HTTPS automatically with no certificate config needed.

`docker-compose.yml` addition:

```yaml
services:
  caddy:
    image: caddy:2-alpine
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./Caddyfile:/etc/caddy/Caddyfile
      - caddy_data:/data
    networks:
      - hevva_net

  hevva:
    build: .
    env_file: .env
    volumes:
      - ./data:/app/data
    networks:
      - hevva_net
    restart: unless-stopped

networks:
  hevva_net:

volumes:
  caddy_data:
```

`Caddyfile`:

```
hevva.yourdomain.com {
    reverse_proxy hevva:8000
}
```

#### I already have nginx running

Add to your nginx config (see `nginx/hevva.subdomain.conf` for the full template):

```nginx
upstream hevva {
  zone hevva 64k;
  server hevva:8000;
  keepalive 2;
}

server {
    listen 443 ssl http2;
    server_name hevva.yourdomain.com;

    ssl_certificate /path/to/fullchain.pem;
    ssl_certificate_key /path/to/privkey.pem;

    location / {
        proxy_http_version 1.1;
        proxy_set_header "Connection" "";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_pass http://hevva;
    }
}
```

Then put Hevva on the same Docker network as your nginx container. Find your nginx network name:

```bash
docker network ls
```

Add to `docker-compose.yml`:

```yaml
services:
  hevva:
    build: .
    env_file: .env
    volumes:
      - ./data:/app/data
    networks:
      - your_nginx_network_name
    restart: unless-stopped

networks:
  your_nginx_network_name:
    external: true
```

> If you host multiple services under a single domain (e.g. `yourdomain.com/hevva/`), see `nginx/hevva.path.conf` for a path-based config.

---

### Step 4 — Start the container

```bash
docker-compose up -d --build
```

---

### Step 5 — Authorize Strava

Open in your browser:

```
https://hevva.yourdomain.com/auth/login
```

This redirects you to Strava to authorize the app. After you approve, you're sent back to `/auth/callback` and tokens are saved automatically.

---

### Step 6 — Done

On startup, Hevva registers the Strava webhook automatically (you'll see it in the logs). From this point, every new `WeightTraining` or `Workout` activity on Strava will be enriched with your Hevy data.

```bash
docker-compose logs -f
```

Look for:
```
Webhook subscription registered (id=XXXXX)
```

---

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/auth/login` | Start Strava OAuth — visit this once to authorize |
| `GET` | `/auth/callback` | OAuth callback — Strava redirects here after authorization |
| `GET` | `/webhook` | Strava webhook verification (used automatically during registration) |
| `POST` | `/webhook` | Receives Strava activity events |
| `GET` | `/health` | Health check |

---

## Configuration reference

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `STRAVA_CLIENT_ID` | Yes | — | From your Strava app |
| `STRAVA_CLIENT_SECRET` | Yes | — | From your Strava app |
| `STRAVA_VERIFY_TOKEN` | Yes | — | Any random string — used to verify webhook ownership |
| `HEVY_API_KEY` | Yes | — | From Hevy |
| `WEBHOOK_CALLBACK_URL` | Yes | — | Public URL Strava posts events to |
| `STRAVA_REDIRECT_URI` | Yes | — | Must match your Strava app settings exactly |
| `SYNC_WINDOW_SECONDS` | No | `1800` | How close in time (seconds) a Hevy workout must be to a Strava activity to be matched |

---

## Notes

- Tokens are stored in `./data/Hevva.db` (SQLite) and refreshed automatically — you never need to re-authorize unless you revoke access on Strava.
- Activities that don't match a Hevy workout within the sync window are left unchanged.
- Only `WeightTraining` and `Workout` sport types are processed. All other activity types (runs, rides, walks) are ignored.
- Want to run OAuth from your local machine instead of the browser flow? Use `python setup.py` — see comments in that file.
