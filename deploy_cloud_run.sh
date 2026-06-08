#!/usr/bin/env bash
# PhoenixLoop — one-shot Cloud Run deploy for both backend and frontend.
#
# Usage:
#   ./deploy_cloud_run.sh [PROJECT_ID] [REGION]
#
# Defaults match the CI workflow values. Requires gcloud, docker, and
# Application Default Credentials. Mirrors .github/workflows/ci.yml so a
# judge can replicate the hosted deploy.

set -euo pipefail

PROJECT_ID="${1:-phoenixloop}"
REGION="${2:-us-central1}"
AR_REPO="phoenixloop"
BACKEND_SERVICE="phoenixloop-backend"
FRONTEND_SERVICE="phoenixloop-frontend"
RUNTIME_SA="phoenixloop-runtime@${PROJECT_ID}.iam.gserviceaccount.com"

SHA="$(git rev-parse --short HEAD)"
BACKEND_IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${AR_REPO}/backend:${SHA}"
FRONTEND_IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${AR_REPO}/frontend:${SHA}"

log() { printf "\033[1;32m▶ %s\033[0m\n" "$*"; }

log "Configuring Artifact Registry docker auth"
gcloud auth configure-docker "${REGION}-docker.pkg.dev" --quiet

log "Building + pushing backend image: ${BACKEND_IMAGE}"
docker buildx build --platform=linux/amd64 --push \
  -t "${BACKEND_IMAGE}" \
  -t "${REGION}-docker.pkg.dev/${PROJECT_ID}/${AR_REPO}/backend:latest" \
  ./backend

log "Deploying backend Cloud Run revision"
gcloud run deploy "${BACKEND_SERVICE}" \
  --image="${BACKEND_IMAGE}" \
  --region="${REGION}" \
  --project="${PROJECT_ID}" \
  --service-account="${RUNTIME_SA}" \
  --update-env-vars=SKIP_AUTOSEED=false,LIGHTWEIGHT_DEMO=false \
  --quiet

BACKEND_URL="$(gcloud run services describe "${BACKEND_SERVICE}" --region="${REGION}" --project="${PROJECT_ID}" --format='value(status.url)')"

log "Building + pushing frontend image with NEXT_PUBLIC_API_URL=${BACKEND_URL}"
docker buildx build --platform=linux/amd64 --push \
  --build-arg "NEXT_PUBLIC_API_URL=${BACKEND_URL}" \
  -t "${FRONTEND_IMAGE}" \
  -t "${REGION}-docker.pkg.dev/${PROJECT_ID}/${AR_REPO}/frontend:latest" \
  ./frontend

log "Deploying frontend Cloud Run revision"
gcloud run deploy "${FRONTEND_SERVICE}" \
  --image="${FRONTEND_IMAGE}" \
  --region="${REGION}" \
  --project="${PROJECT_ID}" \
  --service-account="${RUNTIME_SA}" \
  --quiet

log "Smoke-testing /api/health"
curl -fsS "${BACKEND_URL}/api/health" | tee /dev/stderr | grep -q '"ok":true'
log "Done. Backend: ${BACKEND_URL}"
