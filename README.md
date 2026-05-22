# Hevva

Hevva syncs your [Hevy](https://www.hevyapp.com) workout data into Strava automatically. When Garmin (or the Strava app) creates a `WeightTraining` activity, Hevva finds the matching Hevy workout and updates the Strava activity with your full exercise breakdown — sets, reps, weight, and RPE.

---

## Docker images

Two images are published to [GitHub Container Registry](https://ghcr.io/dharmendra-gupta/hevva):

| Image | Description |
|-------|-------------|
| `ghcr.io/dharmendra-gupta/hevva:latest` | Standalone — uvicorn on port 8000. Put your own reverse proxy in front. |
| `ghcr.io/dharmendra-gupta/hevva:caddy` | Bundled with Caddy — auto-HTTPS via Let's Encrypt on ports 80/443. Good if you have no existing reverse proxy. |

---

## Before you start

You need:

- A [Strava API application](https://www.strava.com/settings/api) — free to create
- A Hevy account with API access
- Docker on your server
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

#### Option A — Caddy bundled image (no existing proxy)

The `:caddy` image runs Caddy alongside the app and handles HTTPS automatically. Add `DOMAIN` to your `.env`:

```env
DOMAIN=hevva.yourdomain.com
```

Then run:

```bash
docker run -d \
  --name hevva \
  -p 80:80 \
  -p 443:443 \
  --env-file .env \
  -v ./data:/app/data \
  -v caddy_data:/data \
  --restart unless-stopped \
  ghcr.io/dharmendra-gupta/hevva:caddy
```

Caddy stores Let's Encrypt certificates in `/data` — mount a named volume so they survive restarts. Ports 80 and 443 must be reachable from the internet for the ACME challenge to succeed.

Or with compose:

```yaml
services:
  hevva:
    image: ghcr.io/dharmendra-gupta/hevva:caddy
    ports:
      - "80:80"
      - "443:443"
    env_file: .env
    volumes:
      - ./data:/app/data
      - caddy_data:/data
    restart: unless-stopped

volumes:
  caddy_data:
```

---

#### Option B — Existing nginx (standalone image)

Use the `:latest` image and proxy to it from your existing nginx. Put Hevva on the same Docker network as nginx.

Find your nginx network name:

```bash
docker network ls
```

`docker-compose.yml`:

```yaml
services:
  hevva:
    image: ghcr.io/dharmendra-gupta/hevva:latest
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

Then reload nginx:

```bash
nginx -t && nginx -s reload
```

> If you host multiple services under a single domain (e.g. `yourdomain.com/hevva/`), see `nginx/hevva.path.conf` for a path-based config.

---

#### Option C — Existing nginx + Cloudflare

Same as Option B, but Cloudflare terminates SSL so your nginx config is simpler (no cert paths needed if you use Cloudflare Origin CA certs or Flexible mode).

In Cloudflare DNS, add an A record for `hevva.yourdomain.com` pointing to your server IP with the proxy enabled (orange cloud). Set SSL/TLS mode to **Full** or **Full (strict)** — the same as your other services.

---

### Step 4 — Start the container

```bash
docker compose up -d
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
docker compose logs -f
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
| `DOMAIN` | Caddy only | — | Your domain — used by the `:caddy` image for auto-HTTPS |
| `SYNC_WINDOW_SECONDS` | No | `1800` | How close in time (seconds) a Hevy workout must be to a Strava activity to be matched |

---

## Notes

- Tokens are stored in `./data/Hevva.db` (SQLite) and refreshed automatically — you never need to re-authorize unless you revoke access on Strava.
- Activities that don't match a Hevy workout within the sync window are left unchanged.
- Only `WeightTraining` and `Workout` sport types are processed. All other activity types (runs, rides, walks) are ignored.
- Want to run OAuth from your local machine instead of the browser flow? Use `python setup.py` — see comments in that file.

---

## Legal

Hevva is an independent open-source project and is **not affiliated with, endorsed by, or officially connected to Strava, Inc. or Hevy**. Use of their APIs is subject to their respective terms:

- [Strava API Agreement](https://www.strava.com/legal/api)
- [Hevy Terms of Service](https://hevy.com/terms)

Strava is a trademark of Strava, Inc. & Hevy is a trademark of Hevy Inc. All trademarks are the property of their respective owners.

This software is provided under the [MIT License](./LICENSE).

---

## Contributors

- [Dharmendra Gupta](https://github.com/dharmendra-gupta) — author
- [Claude](https://claude.ai) by [Anthropic](https://anthropic.com) — AI co-contributor
