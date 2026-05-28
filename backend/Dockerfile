FROM python:3.11-slim

RUN apt-get update && apt-get install -y \
    libpq-dev \
    gcc \
    curl \
    tar \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir \
    rerun-sdk==0.32.0 \
    "fastapi>=0.115" \
    "uvicorn[standard]>=0.30" \
    "sqlalchemy[asyncio]>=2.0" \
    "asyncpg>=0.29" \
    "alembic>=1.13" \
    "pydantic-settings>=2.3" \
    "celery[redis]>=5.4" \
    "redis>=5.0" \
    "python-multipart>=0.0.9" \
    "jinja2>=3.1" \
    "aiofiles>=23.2" \
    "rosbags>=0.11" \
    "mcap>=1.1" \
    "mcap-ros1-support>=0.7" \
    "mcap-ros2-support>=0.5" \
    "Pillow>=10.3" \
    "numpy>=1.26" \
    "pyyaml>=6.0" \
    "python-slugify>=8.0" \
    "psycopg2-binary>=2.9" \
    "flower>=2.0" \
    "bcrypt>=4.0" \
    "itsdangerous>=2.1" \
    "httpx>=0.27" \
    "cryptography>=42.0" \
    "websockets>=12.0" \
    "paramiko>=3.0"

WORKDIR /app

COPY backend/ .
COPY frontend/ /app/frontend/

# Download @rerun-io/web-viewer and serve it locally so no CDN is needed at runtime
ARG RERUN_VERSION=0.32.0
RUN mkdir -p /app/frontend/static/vendor/rerun && \
    curl -sL "https://registry.npmjs.org/@rerun-io/web-viewer/-/web-viewer-${RERUN_VERSION}.tgz" \
    | tar -xz -C /tmp && \
    cp -r /tmp/package/* /app/frontend/static/vendor/rerun/ && \
    sed -i 's|import("./re_viewer")|import("./re_viewer.js")|g' /app/frontend/static/vendor/rerun/index.js

# Download HTMX and serve it locally so no CDN is needed at runtime
ARG HTMX_VERSION=1.9.12
RUN mkdir -p /app/frontend/static/vendor/htmx && \
    curl -sL "https://unpkg.com/htmx.org@${HTMX_VERSION}/dist/htmx.min.js" \
    -o /app/frontend/static/vendor/htmx/htmx.min.js

RUN useradd -m appuser && chown -R appuser /app
USER appuser

EXPOSE 8000
