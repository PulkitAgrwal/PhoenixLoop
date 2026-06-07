# PhoenixLoop — Deployment Guide

## Docker Compose (Local / VM)

### Prerequisites

| Tool | Version | Check |
|---|---|---|
| Docker | 24+ | `docker --version` |
| Docker Compose | v2+ | `docker compose version` |

### Quick Start

```bash
# 1. Clone the repo
git clone https://github.com/PulkitAgrwal/PhoenixLoop.git
cd PhoenixLoop

# 2. Set up environment variables
cp .env.example .env
nano .env   # Add your GOOGLE_API_KEY and PHOENIX_API_KEY

# 3. Build and run
docker compose up --build
```

Backend: [http://localhost:8000](http://localhost:8000) | Frontend: [http://localhost:3000](http://localhost:3000)

### What Happens

1. **Backend container** (Python 3.13-slim):
   - Installs pip dependencies from `requirements.txt`
   - Runs FastAPI via uvicorn on port 8000
   - Initializes SQLite database on a persistent Docker volume
   - Mounts `data/` directory (policies, tickets, customers) as read-only

2. **Frontend container** (Node 20-alpine, multi-stage):
   - Stage 1: Installs npm dependencies
   - Stage 2: Builds Next.js with `output: "standalone"`
   - Stage 3: Runs the optimized standalone server on port 3000
   - Bakes `NEXT_PUBLIC_API_URL=http://localhost:8000` at build time

3. **Health check**: Backend exposes `/api/health` — frontend container waits for it before starting.

4. **Persistent data**: SQLite database lives on a named Docker volume (`db-data`), so data survives container restarts and rebuilds.

### Seed and Run

Once both containers are up:

```bash
# Seed 68 demo tickets
curl -X POST http://localhost:8000/api/demo/seed

# Run the agent on the first 5 tickets
curl -X POST http://localhost:8000/api/demo/run-all
```

Or use the frontend: open [http://localhost:3000](http://localhost:3000) and click **"Seed Demo Data"**.

---

## Container Architecture

```
┌─────────────────────────────────────────────────────┐
│  Host machine                                       │
│                                                     │
│  ┌──────────────────┐    ┌──────────────────┐       │
│  │  backend:8000    │    │  frontend:3000   │       │
│  │  Python 3.13     │    │  Node 20         │       │
│  │  FastAPI+uvicorn │    │  Next.js standalone│      │
│  │                  │    │                  │       │
│  │  /app/src/       │    │  /app/           │       │
│  │  /app/db/ (vol)  │    │  .next/standalone│       │
│  │  /data/ (bind)   │    │                  │       │
│  └──────────────────┘    └──────────────────┘       │
│         │                        │                  │
│    ┌────┴────┐              ┌────┴────┐             │
│    │ db-data │              │ browser │             │
│    │ (volume)│              │ calls   │             │
│    └─────────┘              │ :8000   │             │
│                             └─────────┘             │
│                                                     │
│  External:                                          │
│    → Gemini API (GOOGLE_API_KEY)                    │
│    → Phoenix Cloud (PHOENIX_API_KEY)                │
└─────────────────────────────────────────────────────┘
```

---

## Deploy to Google Cloud Run

Two Cloud Run services in `us-central1`, ephemeral SQLite, Vertex AI via
Application Default Credentials. Verified end-to-end on `phoenixloop` GCP
project on 2026-06-07.

### Prerequisites

- A GCP project with billing enabled.
- gcloud CLI authenticated as a principal with the following roles on the
  project: `roles/run.admin`, `roles/artifactregistry.admin`,
  `roles/secretmanager.admin`, `roles/iam.serviceAccountUser`,
  `roles/serviceusage.serviceUsageConsumer`.
- A runtime service account (e.g. `phoenixloop-runtime@PROJECT.iam.gserviceaccount.com`)
  with `roles/aiplatform.user` so it can call Vertex AI.
- Docker with buildx (for cross-building amd64 images from Apple Silicon).

### One-time setup

```bash
PROJECT=YOUR_PROJECT_ID
REGION=us-central1
RUNTIME_SA=phoenixloop-runtime@$PROJECT.iam.gserviceaccount.com

# 1. Enable required APIs
gcloud services enable \
  run.googleapis.com \
  artifactregistry.googleapis.com \
  secretmanager.googleapis.com \
  aiplatform.googleapis.com \
  --project=$PROJECT

# 2. Create the Artifact Registry repo
gcloud artifacts repositories create phoenixloop \
  --repository-format=docker --location=$REGION --project=$PROJECT

# 3. Configure docker auth for the registry
gcloud auth configure-docker $REGION-docker.pkg.dev --quiet

# 4. Store secrets
printf '%s' "$PHOENIX_API_KEY" | gcloud secrets create phoenix-api-key --data-file=- --project=$PROJECT
printf '%s' "$GOOGLE_API_KEY"  | gcloud secrets create google-api-key  --data-file=- --project=$PROJECT

# 5. Grant the runtime SA access to the secrets
for SECRET in phoenix-api-key google-api-key; do
  gcloud secrets add-iam-policy-binding $SECRET \
    --member="serviceAccount:$RUNTIME_SA" \
    --role=roles/secretmanager.secretAccessor \
    --project=$PROJECT --quiet
done
```

### Deploy the backend

```bash
# Cross-build amd64 from Apple Silicon and push
cd backend
docker buildx build --platform=linux/amd64 --push \
  -t $REGION-docker.pkg.dev/$PROJECT/phoenixloop/backend:latest .

# Deploy (PHOENIX_BASE_URL is your workspace URL, e.g. https://app.phoenix.arize.com/s/YOUR_WORKSPACE)
gcloud run deploy phoenixloop-backend \
  --image=$REGION-docker.pkg.dev/$PROJECT/phoenixloop/backend:latest \
  --region=$REGION --project=$PROJECT \
  --service-account=$RUNTIME_SA \
  --min-instances=1 --max-instances=1 \
  --timeout=900 --memory=1Gi --cpu=1 --port=8000 \
  --allow-unauthenticated \
  --set-env-vars="GOOGLE_GENAI_USE_VERTEXAI=true,GOOGLE_CLOUD_PROJECT=$PROJECT,GOOGLE_CLOUD_LOCATION=$REGION,SKIP_AUTOSEED=true,DEMO_FORCE_PENDING_REVIEW=true,DEMO_FORCE_FAILURE=true,PHOENIX_BASE_URL=$PHOENIX_BASE_URL,PHOENIX_COLLECTOR_ENDPOINT=$PHOENIX_BASE_URL,PHOENIX_PROJECT_NAME=phoenixloop,APP_ENV=production,DATABASE_URL=sqlite:////tmp/phoenixloop.db" \
  --set-secrets="PHOENIX_API_KEY=phoenix-api-key:latest,GOOGLE_API_KEY=google-api-key:latest"
```

Note the backend URL Cloud Run prints. Smoke-test:

```bash
curl -sf $BACKEND_URL/api/health | jq .
```

### Deploy the frontend

```bash
cd ../frontend
docker buildx build --platform=linux/amd64 --push \
  --build-arg NEXT_PUBLIC_API_URL=$BACKEND_URL \
  --build-arg NEXT_PUBLIC_PHOENIX_URL=$PHOENIX_BASE_URL \
  -t $REGION-docker.pkg.dev/$PROJECT/phoenixloop/frontend:latest .

gcloud run deploy phoenixloop-frontend \
  --image=$REGION-docker.pkg.dev/$PROJECT/phoenixloop/frontend:latest \
  --region=$REGION --project=$PROJECT \
  --min-instances=1 --max-instances=1 \
  --memory=512Mi --cpu=1 --port=3000 \
  --allow-unauthenticated
```

### Wire CORS

The backend's CORS allowlist reads `FRONTEND_URL`. After the frontend deploy
returns its public URL, set it on the backend:

```bash
gcloud run services update phoenixloop-backend \
  --region=$REGION --project=$PROJECT \
  --update-env-vars=FRONTEND_URL=$FRONTEND_URL
```

### Caveats

- **Ephemeral SQLite.** The DB lives at `/tmp/phoenixloop.db` inside the
  container. Every cold start, redeploy, or instance restart wipes it. With
  `--min-instances=1` the warm instance persists for hours but is not
  guaranteed across deploys. Acceptable for the demo because each "Watch
  it heal" cycle generates its own state.
- **Single instance.** `--max-instances=1` is intentional — SQLite + file
  locks can't be shared across containers. If you need horizontal scaling
  you also need to migrate to Cloud SQL.
- **Vertex ADC.** The runtime SA carries `roles/aiplatform.user` so the
  Python `google-genai` SDK constructs `Client(vertexai=True)` and the
  Cloud Run-injected metadata server provides credentials. No SA-key file
  needed at runtime.
- **Redeploy on code changes.** Re-run the buildx + `gcloud run deploy`
  block; Cloud Run swaps revisions with zero downtime. Frontend changes
  need the rebuild (env vars are baked at build time). Or wire up CI/CD
  below so every push to `main` redeploys automatically.

---

## Auto-deploy from GitHub Actions (Workload Identity Federation)

The `.github/workflows/ci.yml` workflow runs validation jobs on every push
and PR, then on push to `main` (and only after every check passes) builds
+ pushes both images to Artifact Registry and rolls a new Cloud Run
revision. Authentication uses Workload Identity Federation (WIF) — no
long-lived service-account keys live in GitHub secrets.

### One-time GCP setup (project owner runs once)

```bash
PROJECT=phoenixloop
PROJECT_NUMBER=$(gcloud projects describe $PROJECT --format='value(projectNumber)')
RUNTIME_SA=phoenixloop-runtime@$PROJECT.iam.gserviceaccount.com
GITHUB_REPO=PulkitAgrwal/PhoenixLoop

# 1. Enable IAM Credentials API (needed for WIF impersonation)
gcloud services enable iamcredentials.googleapis.com --project=$PROJECT

# 2. Grant the runtime SA the extra roles needed for deploy
for ROLE in roles/run.admin roles/artifactregistry.writer; do
  gcloud projects add-iam-policy-binding $PROJECT \
    --member="serviceAccount:$RUNTIME_SA" \
    --role="$ROLE" --condition=None --quiet
done

# Allow the runtime SA to "act as" itself when attached to a Cloud Run service
gcloud iam service-accounts add-iam-policy-binding $RUNTIME_SA \
  --member="serviceAccount:$RUNTIME_SA" \
  --role=roles/iam.serviceAccountUser \
  --project=$PROJECT --quiet

# 3. Create the Workload Identity Pool + GitHub OIDC provider, locked to this repo
gcloud iam workload-identity-pools create github-pool \
  --project=$PROJECT --location=global --display-name="GitHub Actions Pool"

gcloud iam workload-identity-pools providers create-oidc github \
  --project=$PROJECT --location=global \
  --workload-identity-pool=github-pool --display-name="GitHub Actions" \
  --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository,attribute.ref=assertion.ref" \
  --attribute-condition="assertion.repository == '$GITHUB_REPO'" \
  --issuer-uri=https://token.actions.githubusercontent.com

# 4. Let GitHub Actions for this repo impersonate the runtime SA
gcloud iam service-accounts add-iam-policy-binding $RUNTIME_SA \
  --project=$PROJECT \
  --role=roles/iam.workloadIdentityUser \
  --member="principalSet://iam.googleapis.com/projects/$PROJECT_NUMBER/locations/global/workloadIdentityPools/github-pool/attribute.repository/$GITHUB_REPO"

# 5. Print the two values to paste into GitHub repo secrets
echo "GCP_WIF_PROVIDER=projects/$PROJECT_NUMBER/locations/global/workloadIdentityPools/github-pool/providers/github"
echo "GCP_DEPLOY_SA=$RUNTIME_SA"
```

### GitHub repo secrets

Add these two secrets at **Settings → Secrets and variables → Actions → New repository secret** (or via gh CLI):

```bash
gh secret set GCP_WIF_PROVIDER --body "projects/856079316421/locations/global/workloadIdentityPools/github-pool/providers/github"
gh secret set GCP_DEPLOY_SA --body "phoenixloop-runtime@phoenixloop.iam.gserviceaccount.com"
```

The exact `GCP_WIF_PROVIDER` value is what step 5 above prints.

### Workflow shape

The pipeline is structured for fail-fast feedback and parallelism:

```
secret-scan ─┐
backend-tests ├──┐
backend-lint   │  │
frontend-lint  ├──┼─► docker-build-pr  (PRs only, verify-only)
frontend-tc    │  │
frontend-build ┘  │
                   └─► deploy-backend  ┐  (push to main only,
                       deploy-frontend ┴   parallel after checks)
```

All 6 validation jobs run fully in parallel; on push to `main` the two
deploy jobs run in parallel after every check passes. Caches:

| Cache | Key | What it speeds up |
|---|---|---|
| `actions/setup-python cache: pip` | `backend/requirements.txt` hash | pip installs |
| `actions/setup-node cache: npm` | `frontend/package-lock.json` hash | npm ci |
| `actions/cache` for Next.js | lockfile + sha, restore-keys fall back | `next build` incremental |
| `actions/cache` for Gitleaks binary | version-pinned | Gitleaks install |
| `cache-from/cache-to: type=gha` | per-scope (`backend`, `frontend`) | Docker layer reuse for both PR verify and prod deploys |

Backend tests (~2.5 min) are the long pole; everything else finishes
inside that window.

### Branch protection (run once as the repo owner)

To require PRs and passing checks instead of direct pushes to `main`:

```bash
gh api -X PUT "repos/PulkitAgrwal/PhoenixLoop/branches/main/protection" \
  --input - <<'EOF'
{
  "required_status_checks": {
    "strict": true,
    "contexts": [
      "Secret Scan",
      "Backend Tests",
      "Backend Lint",
      "Frontend Lint",
      "Frontend Typecheck",
      "Frontend Build",
      "Docker Build (PR verification)"
    ]
  },
  "enforce_admins": true,
  "required_pull_request_reviews": {
    "required_approving_review_count": 0,
    "dismiss_stale_reviews": false,
    "require_code_owner_reviews": false
  },
  "restrictions": null,
  "allow_force_pushes": false,
  "allow_deletions": false,
  "required_linear_history": false,
  "required_conversation_resolution": false
}
EOF
```

This forces every change through a PR, blocks force pushes and branch
deletion, and gates merges on the 7 listed CI jobs. `enforce_admins:true`
applies the rule to repo admins too (set `false` to let admins bypass).
`required_approving_review_count: 0` means you can self-merge — useful
for a solo project; raise to `1` if you bring contributors on.

---

## Legacy / alternative platforms

For local dev or Railway deploy, see the sections below.

---

## Deploy to Railway (Recommended for Cloud)

Railway is the recommended cloud platform — no cold starts, auto-deploy from GitHub, persistent volumes, and $5 free credit/month.

### Step 1: Create a Railway account

1. Go to [railway.app](https://railway.app) and sign up with GitHub
2. Create a new project → **"Deploy from GitHub Repo"**
3. Select your `PulkitAgrwal/PhoenixLoop` repository

### Step 2: Set up the backend service

1. In your Railway project, click **"New Service"** → **"GitHub Repo"**
2. Select the PhoenixLoop repo
3. Railway auto-detects the Dockerfile. Set the **root directory** to `backend`
4. Go to the service **Settings**:
   - **Root Directory**: `backend`
   - **Builder**: Dockerfile
   - **Port**: `8000`
5. Railway generates a public URL like `phoenixloop-backend-production.up.railway.app`

### Step 3: Set up the frontend service

1. Click **"New Service"** → **"GitHub Repo"** again
2. Select the same PhoenixLoop repo
3. Set the **root directory** to `frontend`
4. Go to **Settings**:
   - **Root Directory**: `frontend`
   - **Builder**: Dockerfile
   - **Port**: `3000`
   - **Build Args**: `NEXT_PUBLIC_API_URL=https://<your-backend-url>.up.railway.app`
5. Railway generates a public URL for the frontend too

### Step 4: Add API keys (environment variables)

This is where you add your secrets. **Never commit API keys to code.**

#### Backend service variables

Go to your **backend service** → **Variables** tab → click **"New Variable"** and add:

| Variable | Value | Where to get it |
|---|---|---|
| `GOOGLE_API_KEY` | Your Gemini API key | [aistudio.google.com/apikey](https://aistudio.google.com/apikey) → Create API Key |
| `PHOENIX_API_KEY` | Your Phoenix API key | [app.phoenix.arize.com](https://app.phoenix.arize.com) → Settings → API Keys |
| `PHOENIX_BASE_URL` | `https://app.phoenix.arize.com` | Your Phoenix space URL |
| `APP_ENV` | `production` | — |
| `FRONTEND_URL` | `https://<your-frontend-url>.up.railway.app` | Copy from frontend service settings |

#### Frontend service variables

Go to your **frontend service** → **Variables** tab:

| Variable | Value |
|---|---|
| `NEXT_PUBLIC_API_URL` | `https://<your-backend-url>.up.railway.app` |

#### Important notes about API keys

- Railway encrypts all variables at rest — they are never exposed in logs or builds
- Variables set in the dashboard override anything in `.env`
- You can use **Railway's shared variables** to share values between services (like the backend URL)
- Never add `GOOGLE_API_KEY` or `PHOENIX_API_KEY` to the frontend — they are backend-only secrets

### Step 5: Add a persistent volume (for SQLite)

1. Go to your **backend service** → **Volumes**
2. Click **"New Volume"**
3. Set **mount path** to `/app/db`
4. Add a variable: `DATABASE_URL=sqlite:////app/db/phoenixloop.db`

This ensures your database survives redeployments.

### Step 6: Deploy

Railway auto-deploys when you push to `main`. Your first deploy starts as soon as you finish setup.

Verify it's working:
```bash
# Health check
curl https://<your-backend-url>.up.railway.app/api/health

# Seed data
curl -X POST https://<your-backend-url>.up.railway.app/api/demo/seed
```

Then open your frontend URL in a browser.

### Railway Architecture

```
┌── Railway Project ──────────────────────────────────┐
│                                                     │
│  ┌─────────────────────┐  ┌──────────────────────┐  │
│  │  Backend Service    │  │  Frontend Service    │  │
│  │  Dockerfile: backend│  │  Dockerfile: frontend│  │
│  │                     │  │                      │  │
│  │  Env vars:          │  │  Build args:         │  │
│  │  - GOOGLE_API_KEY   │  │  - NEXT_PUBLIC_API_  │  │
│  │  - PHOENIX_API_KEY  │  │    URL → backend URL │  │
│  │  - DATABASE_URL     │  │                      │  │
│  │                     │  │  Public URL:         │  │
│  │  Volume: /app/db    │  │  *.up.railway.app    │  │
│  │  Public URL:        │  │                      │  │
│  │  *.up.railway.app   │  │                      │  │
│  └─────────────────────┘  └──────────────────────┘  │
│                                                     │
│  Auto-deploys on push to main                       │
└─────────────────────────────────────────────────────┘
```

---

## CI/CD Pipeline (GitHub Actions)

Every push to `main` and every pull request triggers automated checks. The pipeline is defined in `.github/workflows/ci.yml`.

### What the pipeline checks

```
Push / PR to main
      │
      ├── Backend Checks (parallel)
      │     ├── Install Python 3.13 + dependencies
      │     ├── Run pytest (7 test files)
      │     └── Verify main.py compiles
      │
      ├── Frontend Checks (parallel)
      │     ├── Install Node 20 + dependencies
      │     ├── ESLint (code quality)
      │     ├── TypeScript type check (tsc --noEmit)
      │     └── Next.js production build
      │
      └── Docker Build (after both pass)
            ├── Build backend Docker image
            └── Build frontend Docker image
```

### Pipeline stages

| Stage | What it checks | Fails if |
|---|---|---|
| **Backend Tests** | `pytest tests/ -v` | Any test fails |
| **Backend Compile** | `py_compile src/main.py` | Syntax error or broken import |
| **Frontend Lint** | `next lint` | ESLint errors |
| **Frontend Types** | `tsc --noEmit` | TypeScript type errors |
| **Frontend Build** | `next build` | Build fails (broken imports, missing deps) |
| **Docker Build** | Builds both Dockerfiles | Dockerfile or dependency issue |

### How it works with Railway

```
Developer pushes code
       │
       ▼
GitHub Actions runs CI
       │
       ├── ❌ Checks fail → PR blocked, no deploy
       │
       └── ✅ Checks pass
              │
              ▼
       Railway auto-deploys from main
```

- **Pull requests**: CI runs checks. If any fail, the PR shows a red X and you know not to merge.
- **Push to main**: CI runs checks AND Railway auto-deploys. If CI fails, you get notified but Railway still deploys (it watches the branch, not CI). To gate deploys on CI, enable **"Wait for CI"** in Railway settings.

### Enabling "Wait for CI" on Railway

1. Go to your Railway project → **Settings**
2. Under **Deployments**, enable **"Check suites"**
3. Now Railway waits for GitHub Actions to pass before deploying

This means: broken code never reaches production.

---

## Environment Variables Reference

### How to set them in each environment

| Environment | Where to set |
|---|---|
| **Local (no Docker)** | `.env` file in project root |
| **Docker Compose** | `.env` file in project root (loaded via `env_file`) |
| **Railway** | Service → Variables tab in dashboard |
| **Render** | Service → Environment tab in dashboard |
| **VM** | `.env` file on the server |

### Full variable list

| Variable | Required | Default | Used by | Description |
|---|---|---|---|---|
| `GOOGLE_API_KEY` | Yes | — | Backend | Gemini API key for agent + LLM judge evaluators |
| `PHOENIX_API_KEY` | Yes | — | Backend | Arize Phoenix Cloud API key |
| `PHOENIX_BASE_URL` | No | `https://app.phoenix.arize.com` | Backend | Phoenix Cloud space URL |
| `PHOENIX_COLLECTOR_ENDPOINT` | No | `https://app.phoenix.arize.com` | Backend | OpenTelemetry collector endpoint |
| `PHOENIX_PROJECT_NAME` | No | `phoenixloop` | Backend | Phoenix project name for trace grouping |
| `APP_ENV` | No | `development` | Backend | `development` or `production` |
| `DATABASE_URL` | No | `sqlite:///phoenixloop.db` | Backend | SQLite path (override in Docker/Railway) |
| `FRONTEND_URL` | No | `http://localhost:3000` | Backend | Allowed CORS origin |
| `NEXT_PUBLIC_API_URL` | No | `http://localhost:8000` | Frontend | Backend URL for API calls (baked at build time) |

### Getting your API keys

**GOOGLE_API_KEY:**
1. Go to [aistudio.google.com/apikey](https://aistudio.google.com/apikey)
2. Sign in with Google
3. Click **"Create API Key"**
4. Copy the key

**PHOENIX_API_KEY:**
1. Go to [app.phoenix.arize.com](https://app.phoenix.arize.com)
2. Sign up (free) and create a space
3. Go to **Settings** → **API Keys**
4. Click **"Create API Key"**
5. Copy the key and note your space URL (this is your `PHOENIX_BASE_URL`)

---

## Deploying New Changes

### Local Docker

```bash
# Pull latest code and rebuild
git pull
docker compose up --build
```

### Railway

Push to `main` — Railway auto-deploys:
```bash
git add -A
git commit -m "your changes"
git push origin main
```

If "Wait for CI" is enabled, Railway waits for GitHub Actions to pass first.

### Manual redeploy on Railway

Go to your service → **Deployments** → click **"Redeploy"** on any previous deployment.

### Rollback on Railway

Go to your service → **Deployments** → find the previous working deployment → click **"Rollback"**. Takes effect in seconds.

---

## Deploying to a Cloud VM

For production on a VPS (DigitalOcean, EC2, GCP):

### 1. Provision a VM

- Ubuntu 22.04+ recommended
- Minimum: 2 vCPU, 4 GB RAM
- Open ports 80 and 443

### 2. Install Docker

```bash
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
```

### 3. Clone and configure

```bash
git clone https://github.com/PulkitAgrwal/PhoenixLoop.git
cd PhoenixLoop
cp .env.example .env
nano .env   # Add production API keys, set APP_ENV=production
```

### 4. Run in detached mode

```bash
docker compose up --build -d
```

### 5. Add a reverse proxy (optional but recommended)

Use Caddy for automatic HTTPS:

```
yourdomain.com {
    handle /api/* {
        reverse_proxy localhost:8000
    }
    handle {
        reverse_proxy localhost:3000
    }
}
```

---

## Common Operations

### View logs

```bash
# Docker Compose
docker compose logs -f
docker compose logs -f backend
docker compose logs -f frontend

# Railway
railway logs   # via Railway CLI
# or: Service → Deployments → click deployment → View Logs
```

### Reset the database

```bash
# Docker Compose
docker compose down -v && docker compose up --build

# Railway
# Delete the volume in Service → Volumes, then redeploy
```

### Shell into a running container

```bash
docker compose exec backend bash
docker compose exec frontend sh
```

---

## Troubleshooting

| Problem | Fix |
|---|---|
| Backend container exits immediately | Check `docker compose logs backend` — likely a missing API key in `.env` |
| Frontend shows "Failed to fetch" | Backend isn't running or CORS issue. Check `NEXT_PUBLIC_API_URL` matches the backend URL |
| Database errors after update | Reset: `docker compose down -v && docker compose up --build` |
| Port already in use | `lsof -i :8000` then kill it, or change ports in `docker-compose.yml` |
| Build fails on ARM Mac (M1/M2/M3) | Docker Desktop handles this natively |
| Frontend blank after deploy | `NEXT_PUBLIC_API_URL` is baked at build time — rebuild frontend if backend URL changed |
| Railway deploy fails | Check build logs in Railway dashboard. Usually a missing env var or Dockerfile issue |
| CI fails on PR | Check the Actions tab on GitHub — click the failed job to see which step broke |
| API keys not working | Verify keys are set in the right service (backend, not frontend). Check for extra spaces/newlines |
