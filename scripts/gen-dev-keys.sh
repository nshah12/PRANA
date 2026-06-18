#!/usr/bin/env bash
# Generates RS256 JWT key pair for local dev. Run once before `docker compose up`.
# Keys are mounted read-only into all prana-* containers via docker-compose.yml.
set -euo pipefail

KEYS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/keys"
mkdir -p "$KEYS_DIR"

if [ -f "$KEYS_DIR/jwt_private.pem" ]; then
  echo "Keys already exist at $KEYS_DIR — skipping. Delete the directory to regenerate."
  exit 0
fi

echo "Generating RS256 key pair in $KEYS_DIR ..."

openssl genrsa -out "$KEYS_DIR/jwt_private.pem" 2048
openssl rsa -in "$KEYS_DIR/jwt_private.pem" -pubout -out "$KEYS_DIR/jwt_public.pem"

chmod 600 "$KEYS_DIR/jwt_private.pem"
chmod 644 "$KEYS_DIR/jwt_public.pem"

echo "Done."
echo "  Private key : keys/jwt_private.pem"
echo "  Public  key : keys/jwt_public.pem"
echo ""
echo "Add keys/ to .gitignore if not already present."
