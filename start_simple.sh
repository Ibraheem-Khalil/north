#!/bin/bash

# For now, just start the API without Tailscale
# We'll use a different approach for Weaviate connectivity

echo "Starting NORTH API..."
echo "Weaviate URL: ${WEAVIATE_URL}"
echo "Weaviate API Key is set: $([ -n "$WEAVIATE_API_KEY" ] && echo "Yes" || echo "No")"

# Start the API
uvicorn api:app --host 0.0.0.0 --port $PORT