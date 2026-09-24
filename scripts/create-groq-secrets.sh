#!/usr/bin/env bash
# Secure Groq credential provisioning for FIELDed production.
# Run this script locally — it prompts for each key with hidden input
# and creates Google Secret Manager secrets in project fielded-online.
set -euo pipefail

PROJECT="fielded-online"

create_secret() {
  local name="$1"
  printf "\n▶  Enter %s (paste, then press Enter): " "$name"
  read -rs value
  echo ""
  if [ -z "$value" ]; then
    echo "  ✗  Empty value — skipping $name"
    return 1
  fi
  printf "%s" "$value" | gcloud secrets create "$name" \
    --project="$PROJECT" \
    --replication-policy=automatic \
    --data-file=- 2>&1
  local digest
  digest=$(printf "%s" "$value" | shasum -a 256 | awk '{print $1}')
  local byte_count
  byte_count=$(printf "%s" "$value" | wc -c | tr -d ' ')
  echo "  ✓  $name created — SHA-256: ${digest:0:16}…  bytes: $byte_count"
  unset value
}

echo "=== FIELDed Groq credential provisioning ==="
echo "Project: $PROJECT"
echo ""

create_secret "BRAIN_AI_API_KEY"
create_secret "DISCOVERY_AI_API_KEY"
create_secret "CALL_AGENT_AI_API_KEY"

echo ""
echo "=== All three secrets created. Verifying ==="
gcloud secrets list --project="$PROJECT" \
  --filter="name:BRAIN_AI_API_KEY OR name:DISCOVERY_AI_API_KEY OR name:CALL_AGENT_AI_API_KEY" \
  --format="table(name,createTime)"

echo ""
echo "Next step: map these secrets to Cloud Run env vars."
echo "Run the companion script: ./scripts/map-groq-secrets.sh"
