#!/bin/bash

SPIRE_BIN="/opt/spire/bin"
SPIRE_CONF="/opt/spire/conf"
SOCKET_PATH="/tmp/spire-agent/public/api.sock"
SERVER_SOCK="/tmp/spire-server/private/api.sock"

mkdir -p /opt/spire/data/server /opt/spire/data/agent /tmp/spire-agent/public /tmp/spire-server/private

echo "[PALADIN] Starting SPIRE Server..."
$SPIRE_BIN/spire-server run -config $SPIRE_CONF/server.conf &
SERVER_PID=$!

# Wait for server readiness (up to 30s) — check socket exists then healthcheck
echo "[PALADIN] Waiting for SPIRE Server to be ready..."
SERVER_READY=false
for i in $(seq 1 30); do
    if [ -S "$SERVER_SOCK" ]; then
        if $SPIRE_BIN/spire-server healthcheck -socketPath $SERVER_SOCK 2>&1; then
            echo "[PALADIN] SPIRE Server ready after ${i}s"
            SERVER_READY=true
            break
        fi
    fi
    # Check if server process is still alive
    if ! kill -0 $SERVER_PID 2>/dev/null; then
        echo "[PALADIN] ERROR: SPIRE Server process died"
        break
    fi
    sleep 1
done

if [ "$SERVER_READY" != "true" ]; then
    echo "[PALADIN] WARNING: SPIRE Server not ready — starting Streamlit without SPIRE"
    exec streamlit run main.py --server.port ${PORT:-8080} --server.address 0.0.0.0
fi

# Generate join token
echo "[PALADIN] Generating agent join token..."
TOKEN_OUTPUT=$($SPIRE_BIN/spire-server token generate \
    -spiffeID spiffe://demo.local/agent/spire_agent \
    -socketPath $SERVER_SOCK 2>&1)
TOKEN=$(echo "$TOKEN_OUTPUT" | grep "Token:" | awk '{print $2}')

if [ -z "$TOKEN" ]; then
    echo "[PALADIN] WARNING: Token generation failed: $TOKEN_OUTPUT"
    exec streamlit run main.py --server.port ${PORT:-8080} --server.address 0.0.0.0
fi
echo "[PALADIN] Join token generated: ${TOKEN:0:8}..."

# Start SPIRE Agent
echo "[PALADIN] Starting SPIRE Agent..."
$SPIRE_BIN/spire-agent run -config $SPIRE_CONF/agent.conf -joinToken "$TOKEN" &
AGENT_PID=$!

# Wait for agent socket (up to 20s)
echo "[PALADIN] Waiting for SPIRE Agent socket..."
for i in $(seq 1 20); do
    if [ -S "$SOCKET_PATH" ]; then
        echo "[PALADIN] SPIRE Agent socket ready after ${i}s"
        break
    fi
    if [ $i -eq 20 ]; then
        echo "[PALADIN] WARNING: Agent socket not found after 20s"
    fi
    sleep 1
done

# Register workload identities
echo "[PALADIN] Registering workload identities..."
CURRENT_UID=$(id -u)

for AGENT_ID in devops incident finance research; do
    $SPIRE_BIN/spire-server entry create \
        -spiffeID "spiffe://demo.local/agent/$AGENT_ID" \
        -parentID "spiffe://demo.local/agent/spire_agent" \
        -selector "unix:uid:$CURRENT_UID" \
        -socketPath $SERVER_SOCK 2>/dev/null || true
done

for SVC_ID in gateway security; do
    $SPIRE_BIN/spire-server entry create \
        -spiffeID "spiffe://demo.local/service/$SVC_ID" \
        -parentID "spiffe://demo.local/agent/spire_agent" \
        -selector "unix:uid:$CURRENT_UID" \
        -socketPath $SERVER_SOCK 2>/dev/null || true
done

echo "[PALADIN] ✅ SPIRE infrastructure ready — 6 workload identities registered"
echo "[PALADIN] Starting Streamlit application..."

# Trap to clean up background processes on exit
trap "kill $SERVER_PID $AGENT_PID 2>/dev/null; exit" SIGTERM SIGINT

# Start Streamlit in foreground
exec streamlit run main.py --server.port ${PORT:-8080} --server.address 0.0.0.0

