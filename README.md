# USRG ROSBAG Manager

A self-hosted web application for uploading, managing, converting, and visualizing ROS bag files (`.bag`, `.db3`, `.mcap`). Built by the [Unmanned Systems Research Group](https://unmanned.kaist.ac.kr) at KAIST.

Bags are converted to Rerun `.rrd` format and streamed directly in the browser via the Rerun web viewer — no desktop app required.

## Features

- Upload ROS1 `.bag`, ROS2 `.db3`, and MCAP files
- Automatic conversion to `.rrd` via background Celery workers with live progress
- In-browser 3D visualization powered by [Rerun](https://rerun.io) (self-hosted, no CDN)
- Local RRD viewer — drag-and-drop any `.rrd` file without uploading to the server
- Tag, search, and filter bag library
- Draft/publish workflow — bags are hidden from the library until explicitly published
- Edit bag name, description, and tags after upload
- Synology NAS upload — send bags to NAS on demand with per-upload folder selection
- Role-based access: admin and regular users; per-user NAS upload privilege
- HTTPS support via Let's Encrypt with automatic certificate renewal
- Dark-themed responsive UI

## Stack

| Component | Technology |
|-----------|------------|
| Backend   | FastAPI + SQLAlchemy (async) + Alembic |
| Workers   | Celery + Redis |
| Database  | PostgreSQL 16 |
| Frontend  | Jinja2 templates + HTMX |
| Viewer    | Rerun web viewer (self-hosted) |
| Proxy     | nginx |

## Quick Start (LAN / HTTP)

**Prerequisites:** Docker and Docker Compose v2.

```bash
git clone <repo-url>
cd rosbag-manager
cp .env.example .env
# Edit .env — at minimum set POSTGRES_PASSWORD, SECRET_KEY, PUBLIC_HOST
docker compose up --build -d
docker compose exec backend alembic upgrade head
```

Open `http://<PUBLIC_HOST>` in your browser and log in with the admin credentials set in `.env`.

## HTTPS Deployment (public internet)

**Prerequisites:** A domain with an A record pointing to your server's public IP, and ports 80 + 443 forwarded to the server.

```bash
# 1. Add to .env:
#    DOMAIN=yourdomain.com
#    CERTBOT_EMAIL=admin@yourdomain.com
#    PUBLIC_HOST=yourdomain.com

# 2. Run the one-time certificate bootstrap:
chmod +x init-letsencrypt.sh
./init-letsencrypt.sh

# 3. Start the full stack with automatic certificate renewal:
docker compose --profile https up -d
```

On subsequent restarts, nginx automatically detects the certificate and uses HTTPS. Without a certificate it falls back to HTTP, so LAN deployments are unaffected.

## Configuration

| Variable | Required | Description |
|----------|----------|-------------|
| `POSTGRES_PASSWORD` | Yes | PostgreSQL password |
| `SECRET_KEY` | Yes | Random secret for sessions and password encryption. Generate: `python3 -c "import secrets; print(secrets.token_hex(32))"` |
| `PUBLIC_HOST` | Yes | Hostname or IP shown to users (e.g. `192.168.1.10` or `yourdomain.com`) |
| `INITIAL_ADMIN_PASSWORD` | First boot | Admin password — remove from `.env` after first login |
| `DOMAIN` | HTTPS only | Domain name for Let's Encrypt certificate |
| `CERTBOT_EMAIL` | HTTPS only | Email for Let's Encrypt renewal failure alerts |
| `DATA_DIR` | No | Host path for bag data volume (default: `./data`) |
| `MAX_UPLOAD_SIZE_GB` | No | Upload size limit in GB (default: `50`) |
| `WORKER_CONCURRENCY` | No | Parallel conversion workers (default: `2`) |

## Ports

| Port | Service |
|------|---------|
| 80   | nginx — HTTP (redirects to HTTPS when cert is present) |
| 443  | nginx — HTTPS |
| 5555 | Flower — Celery task monitor |

## Updating

```bash
git pull
docker compose build
docker compose up -d
docker compose exec backend alembic upgrade head
```

## Development

```bash
# Hot-reload for backend and frontend changes
docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build
```

## Data & Backups

All persistent data lives under `DATA_DIR` (default `./data`):

| Path | Contents |
|------|----------|
| `data/uploads/` | Original uploaded bag files |
| `data/rrd/` | Converted Rerun `.rrd` files |
| `data/thumb/` | Thumbnail images |
| `data/certbot/` | TLS certificates (HTTPS deployments) |

Back up the `data/` directory and the PostgreSQL volume (`docker volume ls`) to preserve all bag data.
