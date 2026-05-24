# USRG ROSBAG Manager

A self-hosted web application for managing, converting, and visualizing ROS bag files (`.bag`, `.db3`, `.mcap`). Bags are converted to Rerun `.rrd` format and streamed directly in the browser via the Rerun web viewer.

## Features

- Upload ROS1 `.bag`, ROS2 `.db3`, and MCAP files
- Automatic conversion to `.rrd` via Celery workers
- In-browser 3D visualization powered by [Rerun](https://rerun.io)
- Local RRD viewer (drag-and-drop, no server needed)
- Tag, search, and filter bag library
- Draft/publish workflow
- Synology NAS upload integration
- Role-based access (admin / user with optional NAS privilege)
- Dark-themed responsive UI

## Stack

| Component | Technology |
|-----------|-----------|
| Backend   | FastAPI + SQLAlchemy (async) + Alembic |
| Workers   | Celery + Redis |
| Database  | PostgreSQL |
| Frontend  | Jinja2 templates + HTMX |
| Viewer    | Rerun web viewer (self-hosted, no CDN) |
| Proxy     | nginx |

## Quick Start

**Prerequisites:** Docker and Docker Compose.

```bash
git clone https://github.com/junekyoopark/rosbag-manager
cd rosbag-manager
cp .env.example .env
# Edit .env — set POSTGRES_PASSWORD, SECRET_KEY, PUBLIC_HOST
docker compose up --build -d
docker compose exec backend alembic upgrade head
```

Open `http://<PUBLIC_HOST>` in your browser. Log in with the admin credentials set in `.env`.

## Configuration

Copy `.env.example` to `.env` and fill in:

| Variable | Description |
|----------|-------------|
| `POSTGRES_PASSWORD` | Database password |
| `SECRET_KEY` | Random secret for session signing and encryption. Generate with: `python3 -c "import secrets; print(secrets.token_hex(32))"` |
| `PUBLIC_HOST` | Hostname or IP address of the server (used to build URLs) |
| `INITIAL_ADMIN_PASSWORD` | Admin password on first boot — remove from `.env` after first login |
| `MAX_UPLOAD_SIZE_GB` | Maximum upload size in GB (default: 50) |
| `DATA_DIR` | Host path for persistent bag data (default: `./data`) |
| `WORKER_CONCURRENCY` | Number of parallel Celery workers (default: 2) |

## Development

```bash
# Hot-reload backend + frontend
docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build
```

## Updating

```bash
git pull
docker compose build
docker compose up -d
docker compose exec backend alembic upgrade head
```

## Ports

| Port | Service |
|------|---------|
| 80   | nginx (main app) |
| 5555 | Flower (Celery task monitor) |
