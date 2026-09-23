#!/bin/sh
# M25 hardening: generates a self-signed TLS cert on first container start
# if one doesn't already exist in the mounted certs volume, so nginx has
# something to load for its additive :443 listener without ever committing
# key material to the repo. The nginx image runs every executable script
# under /docker-entrypoint.d/ automatically before starting nginx -- this
# is that mechanism, not a custom entrypoint override.
#
# Self-signed only: browsers will show a trust warning on first visit.
# That's expected for local/dev use; swap in a real certificate (e.g. via
# Let's Encrypt) for an actual deployment by replacing the two files below.
set -e

CERT_DIR=/etc/nginx/certs
CERT_FILE="$CERT_DIR/ibvap.crt"
KEY_FILE="$CERT_DIR/ibvap.key"

if [ -f "$CERT_FILE" ] && [ -f "$KEY_FILE" ]; then
    echo "nginx: existing self-signed cert found in $CERT_DIR, reusing it"
    exit 0
fi

mkdir -p "$CERT_DIR"

if ! command -v openssl >/dev/null 2>&1; then
    apk add --no-cache openssl >/dev/null
fi

echo "nginx: generating a self-signed TLS cert for local/dev use"
openssl req -x509 -nodes -newkey rsa:2048 -days 825 \
    -keyout "$KEY_FILE" -out "$CERT_FILE" \
    -subj "/CN=127.0.0.1" \
    -addext "subjectAltName=IP:127.0.0.1,DNS:localhost" \
    2>/dev/null

chmod 600 "$KEY_FILE"
echo "nginx: cert written to $CERT_FILE"
