# Networking

Pick the option that matches your setup.

---

## Option A — Caddy bundled image (no existing proxy)

The `:caddy` image bundles Caddy and handles HTTPS automatically via Let's Encrypt. Best if you have no existing reverse proxy.

Add `DOMAIN` to your `.env`:

```env
DOMAIN=hevva.yourdomain.com
```

=== "docker compose"

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

=== "docker run"

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

---

## Option B — Existing nginx

Use the `:latest` (standalone) image and proxy to it from your existing nginx setup. Put Hevva on the same Docker network as nginx.

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

### Subdomain config

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

### Path-based config

If you host multiple services under a single domain (e.g. `yourdomain.com/hevva/`), see `nginx/hevva.path.conf` in the repo for the path-based template.

Reload nginx after any config change:

```bash
nginx -t && nginx -s reload
```

---

## Option C — Existing nginx + Cloudflare

Same as Option B, but Cloudflare terminates SSL so your nginx config is simpler — no cert paths needed if you use Cloudflare Origin CA certs.

In Cloudflare DNS, add an **A record** for `hevva.yourdomain.com` pointing to your server IP with the proxy enabled (orange cloud). Set SSL/TLS mode to **Full** or **Full (strict)**.
