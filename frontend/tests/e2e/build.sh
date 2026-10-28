#!/bin/sh
# Builds a copy of frontend/ against the suite's fake origins and serves it on $E2E_PORT.
# Never touches frontend/.next (a `next dev` may be running there) and never copies .env* files:
# the only env the build sees is the fake values below.
set -eu

FRONTEND_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
WORK_DIR="${E2E_WORK_DIR:-${TMPDIR:-/tmp}/ttths-e2e}"
PORT="${E2E_PORT:-3011}"
COPY_DIR="$WORK_DIR/fe"

pkill -f "next start -p $PORT" 2>/dev/null || true
mkdir -p "$COPY_DIR"
rsync -a --delete --exclude node_modules --exclude .next --exclude '.env*' --exclude tsconfig.tsbuildinfo \
  "$FRONTEND_DIR/" "$COPY_DIR/"
ln -sfn "$FRONTEND_DIR/node_modules" "$COPY_DIR/node_modules"

cd "$COPY_DIR"
# Placeholders, not credentials: the suite answers every request to these origins itself.
export NEXT_PUBLIC_SUPABASE_URL="http://supabase.e2e.test"
export NEXT_PUBLIC_SUPABASE_ANON_KEY="e2e-placeholder-anon-key"
export NEXT_PUBLIC_API_BASE_URL="http://api.e2e.test"
export NEXT_TELEMETRY_DISABLED=1
npx next build > "$WORK_DIR/build.log" 2>&1 || { tail -40 "$WORK_DIR/build.log"; exit 1; }
nohup npx next start -p "$PORT" > "$WORK_DIR/server.log" 2>&1 &
echo $! > "$WORK_DIR/server.pid"

i=0
until curl -fsS -o /dev/null "http://localhost:$PORT/login" 2>/dev/null; do
  i=$((i + 1))
  [ "$i" -gt 60 ] && { echo "server did not start, see $WORK_DIR/server.log"; exit 1; }
  sleep 1
done
echo "e2e build served on http://localhost:$PORT (copy: $COPY_DIR)"
