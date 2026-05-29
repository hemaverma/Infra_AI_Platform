#!/usr/bin/env bash
set -euo pipefail
# Start Azurite for local storage emulation
# Run this when developing offline (no VPN)

azurite --silent \
    --location /workspace/.azurite \
    --blobHost 0.0.0.0 --blobPort 10000 \
    --queueHost 0.0.0.0 --queuePort 10001 \
    --tableHost 0.0.0.0 --tablePort 10002 &

echo "Azurite running:"
echo "  Blob:  http://127.0.0.1:10000"
echo "  Queue: http://127.0.0.1:10001"
echo "  Table: http://127.0.0.1:10002"
echo ""
echo "Use connection string:"
echo "  DefaultEndpointsProtocol=http;AccountName=devstoreaccount1;AccountKey=Eby8vdM02xNOcqFlqUwJPLlmEtlCDXJ1OUzFT50uSRZ6IFsuFq2UVErCz4I6tq/K1SZFPTOtr/KBHBeksoGMGw==;BlobEndpoint=http://127.0.0.1:10000/devstoreaccount1;QueueEndpoint=http://127.0.0.1:10001/devstoreaccount1;TableEndpoint=http://127.0.0.1:10002/devstoreaccount1;"
