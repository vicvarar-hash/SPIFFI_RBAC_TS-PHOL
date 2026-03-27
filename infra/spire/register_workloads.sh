#!/bin/bash
# Registers the persona workload identities in the SPIRE Server

if ! command -v docker &> /dev/null
then
    echo "Docker is required but not installed."
    exit 1
fi

echo "Registering SPIFFE workloads..."

# Register DevOps Agent
docker compose exec spire-server /opt/spire/bin/spire-server entry create \
    -spiffeID spiffe://demo.local/agent/devops \
    -parentID spiffe://demo.local/agent/spire_agent \
    -selector unix:user:root

# Register Incident Agent
docker compose exec spire-server /opt/spire/bin/spire-server entry create \
    -spiffeID spiffe://demo.local/agent/incident \
    -parentID spiffe://demo.local/agent/spire_agent \
    -selector unix:user:root

# Register Finance Agent
docker compose exec spire-server /opt/spire/bin/spire-server entry create \
    -spiffeID spiffe://demo.local/agent/finance \
    -parentID spiffe://demo.local/agent/spire_agent \
    -selector unix:user:root

# Register Research Agent
docker compose exec spire-server /opt/spire/bin/spire-server entry create \
    -spiffeID spiffe://demo.local/agent/research \
    -parentID spiffe://demo.local/agent/spire_agent \
    -selector unix:user:root

# Register Automation Gateway
docker compose exec spire-server /opt/spire/bin/spire-server entry create \
    -spiffeID spiffe://demo.local/service/gateway \
    -parentID spiffe://demo.local/agent/spire_agent \
    -selector unix:user:root

# Register Security Engine
docker compose exec spire-server /opt/spire/bin/spire-server entry create \
    -spiffeID spiffe://demo.local/service/security \
    -parentID spiffe://demo.local/agent/spire_agent \
    -selector unix:user:root

echo "Workloads registered successfully."
