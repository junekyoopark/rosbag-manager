#!/bin/bash
# Run once on first deployment to obtain a Let's Encrypt certificate.
# After this, docker compose handles automatic renewal via the certbot service.
#
# Usage:
#   chmod +x init-letsencrypt.sh
#   ./init-letsencrypt.sh

set -e

# Load .env
if [ -f .env ]; then
    set -a; source .env; set +a
fi

if [ -z "$DOMAIN" ]; then
    echo "Error: DOMAIN is not set. Add DOMAIN=yourdomain.com to .env"
    exit 1
fi
if [ -z "$CERTBOT_EMAIL" ]; then
    echo "Error: CERTBOT_EMAIL is not set. Add CERTBOT_EMAIL=you@example.com to .env"
    exit 1
fi

CERT_DIR="./data/certbot/conf"
WWW_DIR="./data/certbot/www"

mkdir -p "$CERT_DIR/live/$DOMAIN" "$WWW_DIR"

# ── Step 1: Download recommended TLS parameters ───────────────────
echo "==> Downloading recommended TLS parameters..."
if [ ! -f "$CERT_DIR/options-ssl-nginx.conf" ]; then
    curl -fsSL \
      "https://raw.githubusercontent.com/certbot/certbot/master/certbot-nginx/certbot_nginx/_internal/tls_configs/options-ssl-nginx.conf" \
      -o "$CERT_DIR/options-ssl-nginx.conf"
fi
if [ ! -f "$CERT_DIR/ssl-dhparams.pem" ]; then
    curl -fsSL \
      "https://raw.githubusercontent.com/certbot/certbot/master/certbot/certbot/ssl-dhparams.pem" \
      -o "$CERT_DIR/ssl-dhparams.pem"
fi

# ── Step 2: Create a temporary self-signed certificate ───────────
# nginx needs certificate files to exist before it will start with the HTTPS block.
echo "==> Creating temporary self-signed certificate..."
openssl req -x509 -nodes -newkey rsa:2048 -days 1 \
    -keyout "$CERT_DIR/live/$DOMAIN/privkey.pem" \
    -out    "$CERT_DIR/live/$DOMAIN/fullchain.pem" \
    -subj   "/CN=$DOMAIN" 2>/dev/null

# ── Step 3: Start nginx with the dummy certificate ───────────────
echo "==> Starting nginx..."
docker compose up -d nginx
echo "Waiting for nginx to be ready..."
sleep 5

# ── Step 4: Obtain real certificate via ACME webroot ─────────────
echo "==> Requesting Let's Encrypt certificate for $DOMAIN..."
docker compose run --rm certbot certonly \
    --webroot \
    --webroot-path=/var/www/certbot \
    --email "$CERTBOT_EMAIL" \
    --agree-tos \
    --no-eff-email \
    -d "$DOMAIN"

# ── Step 5: Reload nginx with the real certificate ───────────────
echo "==> Reloading nginx..."
docker compose exec nginx nginx -s reload

echo ""
echo "Done! HTTPS is configured for https://$DOMAIN"
echo "Start the full stack with:  docker compose --profile https up -d"
