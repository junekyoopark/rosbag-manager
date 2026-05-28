#!/bin/sh
# Use HTTPS config when certificates exist, otherwise fall back to HTTP-only.
CERT="/etc/letsencrypt/live/${DOMAIN}/fullchain.pem"

if [ -f "$CERT" ]; then
    echo "Certificate found — starting nginx with HTTPS"
    envsubst '${DOMAIN}' < /etc/nginx/nginx.conf.template > /etc/nginx/nginx.conf
else
    echo "No certificate found — starting nginx in HTTP-only mode"
    cp /etc/nginx/nginx.conf.http /etc/nginx/nginx.conf
fi

exec nginx -g 'daemon off;'
