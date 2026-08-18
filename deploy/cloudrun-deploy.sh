#!/usr/bin/env bash
# Deploy the EDI-Converter API to Google Cloud Run.
#
# Cloud Run is the cheapest option that can also be made HIPAA-compliant: it
# scales to zero (no traffic, no bill), and Google will sign a BAA covering it.
# See deploy/README.md for how that compares to a flat-rate VPS.
#
#   ./cloudrun-deploy.sh my-gcp-project us-central1
#
# The static frontend is NOT deployed here — host it free on Cloudflare Pages or
# Firebase Hosting and point FRONTEND_ORIGIN at it.
set -euo pipefail

PROJECT="${1:?usage: cloudrun-deploy.sh <gcp-project-id> [region]}"
REGION="${2:-us-central1}"
SERVICE="${SERVICE:-edi-converter-api}"
FRONTEND_ORIGIN="${FRONTEND_ORIGIN:-https://edi-converter.pages.dev}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "Project   $PROJECT"
echo "Region    $REGION"
echo "Service   $SERVICE"
echo "Frontend  $FRONTEND_ORIGIN"
echo

# Cloud Run builds from source, but our image is already lean and reproducible —
# push it instead so what runs in production is exactly what was tested locally.
IMAGE="${REGION}-docker.pkg.dev/${PROJECT}/edi-converter/api:$(git -C "$REPO_ROOT" rev-parse --short HEAD)"

gcloud artifacts repositories describe edi-converter \
  --project "$PROJECT" --location "$REGION" >/dev/null 2>&1 || \
gcloud artifacts repositories create edi-converter \
  --project "$PROJECT" --location "$REGION" --repository-format docker \
  --description "EDI-Converter images"

echo "Building $IMAGE"
docker build -t "$IMAGE" "$REPO_ROOT/backend"
docker push "$IMAGE"

gcloud run deploy "$SERVICE" \
  --project "$PROJECT" \
  --region "$REGION" \
  --image "$IMAGE" \
  --platform managed \
  --allow-unauthenticated \
  --port 5080 \
  --cpu 1 \
  --memory 512Mi \
  --min-instances 0 \
  --max-instances 4 \
  --concurrency 8 \
  --timeout 120s \
  --set-env-vars "EDI_CORS_ORIGINS=${FRONTEND_ORIGIN},EDI_MAX_FILE_MB=10" \
  --execution-environment gen2

URL="$(gcloud run services describe "$SERVICE" --project "$PROJECT" --region "$REGION" --format 'value(status.url)')"
echo
echo "Deployed: $URL"
echo
echo "Verify it before sending anyone to it:"
echo "  python \"$REPO_ROOT/deploy/smoke_test.py\" \"$URL\" --api-path '' --no-tls"
echo
echo "Notes:"
echo "  * --allow-unauthenticated makes this PUBLIC. The app has no auth of its"
echo "    own, so anyone with the URL can convert files. For PHI, drop that flag"
echo "    and put IAP or an API gateway in front."
echo "  * --concurrency 8 matches the measured CPU-bound throughput; raising it"
echo "    increases latency without increasing req/s."
