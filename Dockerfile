FROM python:3.12-slim

WORKDIR /app

# System dependencies + SPIRE prerequisites
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install SPIRE binaries (sidecar mode for cloud deployment)
ARG SPIRE_VERSION=1.9.6
RUN curl -sL "https://github.com/spiffe/spire/releases/download/v${SPIRE_VERSION}/spire-${SPIRE_VERSION}-linux-amd64-musl.tar.gz" \
    -o /tmp/spire.tar.gz \
    && mkdir -p /opt/spire \
    && tar xzf /tmp/spire.tar.gz -C /opt/spire --strip-components=1 \
    && rm /tmp/spire.tar.gz \
    && mkdir -p /opt/spire/conf /opt/spire/data/server /opt/spire/data/agent /opt/spire/logs \
    && mkdir -p /tmp/spire-agent/public /tmp/spire-server/private

# Copy SPIRE sidecar configs
COPY infra/spire/sidecar/server.conf /opt/spire/conf/server.conf
COPY infra/spire/sidecar/agent.conf /opt/spire/conf/agent.conf
COPY infra/spire/sidecar/start-spire.sh /opt/spire/start-spire.sh
RUN chmod +x /opt/spire/start-spire.sh

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PORT=8080
EXPOSE 8080

CMD ["bash", "/opt/spire/start-spire.sh"]
