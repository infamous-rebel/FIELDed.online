#!/usr/bin/env bash
# Map Groq secrets to Cloud Run environment variables.
# Preserves all existing env vars and secretKeyRef entries.
# Uses gcloud run services update with --set-secrets to add new bindings
# while keeping existing ones intact.
set -euo pipefail

PROJECT="fielded-online"
SERVICE="fielded-api"
REGION="us-central1"

echo "=== Mapping Groq secrets to Cloud Run env vars ==="
echo "Service: $SERVICE  Project: $PROJECT  Region: $REGION"
echo ""

# Verify all three secrets exist in Secret Manager
for secret in BRAIN_AI_API_KEY DISCOVERY_AI_API_KEY CALL_AGENT_AI_API_KEY; do
  if ! gcloud secrets describe "$secret" --project="$PROJECT" --format='value(name)' &>/dev/null; then
    echo "✗ Secret $secret does not exist in Secret Manager. Run create-groq-secrets.sh first."
    exit 1
  fi
  echo "✓ Secret $secret exists"
done

echo ""
echo "Updating Cloud Run service with new secret env var mappings..."
echo "  BRAIN_AI_API_KEY       -> Secret Manager: BRAIN_AI_API_KEY"
echo "  DISCOVERY_AI_API_KEY   -> Secret Manager: DISCOVERY_AI_API_KEY"
echo "  CALL_AGENT_AI_API_KEY  -> Secret Manager: CALL_AGENT_AI_API_KEY"
echo ""

# Update the Cloud Run service, adding the three new secret env vars.
# --set-secrets adds/replaces individual entries without touching existing ones.
# The existing APP_SECRET_KEY, JWT_SECRET_KEY, DATABASE_URL bindings are preserved.
gcloud run services update "$SERVICE" \
  --project="$PROJECT" \
  --region="$REGION" \
  --set-secrets="BRAIN_AI_API_KEY=BRAIN_AI_API_KEY:latest,DISCOVERY_AI_API_KEY=DISCOVERY_AI_API_KEY:latest,CALL_AGENT_AI_API_KEY=CALL_AGENT_AI_API_KEY:latest" \
  2>&1

echo ""
echo "=== Verifying secret mappings ==="
gcloud run services describe "$SERVICE" \
  --project="$PROJECT" \
  --region="$REGION" \
  --format=json 2>/dev/null | python3 -c "
import json, sys
svc = json.load(sys.stdin)
revision = svc.get('status', {}).get('latestReadyRevisionName', 'unknown')
print(f'Latest ready revision: {revision}')
for container in svc.get('spec', {}).get('template', {}).get('spec', {}).get('containers', []):
    for e in container.get('env', []):
        if 'valueFrom' in e:
            sr = e['valueFrom'].get('secretKeyRef', {})
            print(f\"  {e['name']} -> secret={sr.get('name','?')} key={sr.get('key','?')}\")
"

echo ""
echo "=== Waiting for new revision to become ready ==="
gcloud run services wait "$SERVICE" \
  --project="$PROJECT" \
  --region="$REGION" \
  --timeout=300 2>&1

echo ""
echo "=== Health checks ==="
URL=$(gcloud run services describe "$SERVICE" --project="$PROJECT" --region="$REGION" --format='value(status.url)')
echo "Service URL: $URL"
echo ""
echo "GET /api/v1/health"
curl -sf "$URL/api/v1/health" 2>&1 || echo "(failed)"
echo ""
echo ""
echo "GET /api/v1/health/ready"
curl -sf "$URL/api/v1/health/ready" 2>&1 || echo "(failed)"
echo ""
echo ""
echo "=== Done ==="
