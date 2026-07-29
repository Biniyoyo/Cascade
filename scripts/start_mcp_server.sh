#!/bin/sh
# Persistent DataHub MCP server (HTTP transport) for CASCADE's agent runs.
cd "$(dirname "$0")/.."
DATAHUB_GMS_URL="${DATAHUB_GMS_URL:-http://localhost:8080}" \
DATAHUB_GMS_TOKEN="${DATAHUB_GMS_TOKEN:-dummy-local}" \
TOOLS_IS_MUTATION_ENABLED=true \
DATAHUB_TELEMETRY_ENABLED=false \
exec .venv/bin/mcp-server-datahub --transport sse
