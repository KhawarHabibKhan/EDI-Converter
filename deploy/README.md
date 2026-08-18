# Deployment runbook

Everything needed to put EDI-Converter in front of real users, and to prove it
works once it is there.

| File | What it is |
|------|------------|
| `docker-compose.prod.yml` | Production stack: Caddy edge → SPA + API on one origin |
| `Caddyfile` | TLS, security headers, `/api` routing, upload ceiling |
| `.env.production.example` | Copy to `.env` and fill in (contains no secrets) |
| `smoke_test.py` | 17 post-deployment checks against any URL — **run after every deploy** |
| `load_test.py` | Throughput/latency measurement, exits non-zero above an error budget |
| `fly.toml` | Fly.io API deployment (scale-to-zero) |
| `cloudrun-deploy.sh` | Google Cloud Run API deployment (scale-to-zero, BAA-eligible) |

---

## The one decision that changes everything: real PHI or not?

This app processes claims — patient names, member IDs, diagnoses. That is PHI,
and it splits the deployment options into two tracks that cost very different
amounts.

**It also has no authentication.** Anyone who can reach the URL can convert
files. That is fine for an internal tool on a private network or behind a VPN;
it is not acceptable for a public deployment handling real patient data. Decide
this before picking a host, not after.

| | Track A — demo / synthetic data | Track B — real PHI |
|---|---|---|
| Data | Test files, de-identified samples | Live claims |
| Host requirement | Anything | Vendor will sign a **BAA** |
| Auth | Optional | Mandatory (not built yet) |
| Audit logging | Optional | Mandatory (not built yet) |
| Realistic cost | **$0–6/month** | **$25–70/month** |

Track B needs work that does not exist in the codebase yet — see
"Before Track B" below. Do not put real PHI behind this until that lands.

---

## Cost comparison

Prices are list rates checked against vendor pricing pages in early 2026 and
move over time — confirm before committing. Assumes light usage: a few thousand
conversions a month, one small container.

| Option | Monthly | Scale-to-zero | BAA | Notes |
|--------|---------|---------------|-----|-------|
| **Oracle Cloud Always Free** | **$0** | no | no | 4 ARM cores / 24 GB, genuinely free tier; capacity can be hard to get |
| **Hetzner CX22 + Caddy** | **~$4.50** | no | no | 2 vCPU / 4 GB. Cheapest reliable always-on box. Use `docker-compose.prod.yml` as-is |
| **Fly.io** (`fly.toml`) | **~$0–3** | yes | no | Suspends when idle; ~1–2 s cold start |
| **Google Cloud Run** (`cloudrun-deploy.sh`) | **~$0–5** | yes | **yes** | 2M free requests/month; the cheapest HIPAA-capable path |
| **Cloudflare Pages** (frontend) | **$0** | n/a | no | Static hosting, generous free tier — pair with Fly/Cloud Run |
| AWS App Runner / ECS Fargate | ~$25–45 | partial | yes | Convenient if you are already on AWS; not the cheap option |

**Cheapest overall:** Cloudflare Pages (frontend, $0) + Fly.io or Cloud Run
(API, ~$0–5). **Simplest:** one Hetzner box running `docker-compose.prod.yml` —
one machine, one file, automatic TLS, ~$4.50/month. **Cheapest with a BAA:**
Cloud Run + Cloudflare Pages.

---

## Deploy: single box (recommended starting point)

Any Ubuntu/Debian host with Docker. One machine serves both the SPA and the API,
with automatic Let's Encrypt certificates.

```bash
# 1. Point an A record at the box first — Caddy proves domain control to
#    Let's Encrypt, and certificate issuance fails without working DNS.
# 2. On the box:
git clone <your-repo> && cd EDI-Converter/deploy
cp .env.production.example .env
nano .env                      # SITE_ADDRESS + ACME_EMAIL
docker compose -f docker-compose.prod.yml up -d --build

# 3. Verify from your laptop — never trust a deploy you have not tested:
python smoke_test.py https://edi.example.com
```

The API is deliberately **not** published to the host: only Caddy binds ports,
so the backend cannot be reached except through TLS and the security headers.

### Rehearse the production topology locally

Test the real compose file, edge routing and headers before touching a domain:

```bash
cd deploy
SITE_ADDRESS=":80" ACME_EMAIL="test@example.com" HTTP_PORT=8088 HTTPS_PORT=9443 \
  docker compose -f docker-compose.prod.yml up -d --build
python smoke_test.py http://localhost:8088 --no-tls
```

`SITE_ADDRESS=":80"` tells Caddy to serve plain HTTP, so no certificate is
needed. Everything else — routing, `/api` prefix stripping, headers, upload
limits — is exactly what production runs.

## Deploy: split (static frontend + scale-to-zero API)

Cheapest at low traffic, because the API costs nothing while idle.

```bash
# Frontend -> Cloudflare Pages (free)
cd frontend
VITE_API_URL=https://your-api-host npm run build
npx wrangler pages deploy dist

# API -> Fly.io
fly deploy --config deploy/fly.toml --dockerfile backend/Dockerfile
#   ...or Google Cloud Run
FRONTEND_ORIGIN=https://your-pages-url ./deploy/cloudrun-deploy.sh my-project us-central1

# Verify (the API is its own origin here, so there is no /api prefix)
python deploy/smoke_test.py https://your-api-host --api-path '' 
```

Two origins means CORS is live: set `EDI_CORS_ORIGINS` to the **exact** frontend
URL. Never `*` — it would let any site drive the converter with a user's data.

---

## Measured performance (sizing input)

Taken with `load_test.py` against `docker-compose.prod.yml` on a 1-CPU-limited
container, 765-byte 837P claim, through the Caddy edge:

| Endpoint | Concurrency | Throughput | p50 | p95 | p99 | Errors |
|----------|-------------|-----------|-----|-----|-----|--------|
| `/edi/validate` (SNIP L1–5) | 8 | **152 req/s** | 47 ms | 94 ms | 125 ms | 0 |
| `/edi/validate` (SNIP L1–5) | 32 | **213 req/s** | 132 ms | 231 ms | 276 ms | 0 |
| `/edi/fhir` | 8 | **233 req/s** | 32 ms | 51 ms | 58 ms | 0 |

Reading: one small container absorbs ~150 claims/second with sub-100 ms p95.
Throughput is CPU-bound — going from 8 to 32 concurrent requests raises
throughput only 40% while tripling latency, which is why `fly.toml` and the
Cloud Run script both cap concurrency at 8. A single $4.50 box comfortably
covers hundreds of thousands of conversions a day; scale by adding CPU before
adding replicas.

Re-measure after any parser change:

```bash
python load_test.py https://edi.example.com --concurrency 8 --requests 400
```

---

## Before Track B (real PHI)

Blockers that are **not** in the codebase today. Each is a real piece of work,
not a config flag:

1. **Authentication.** No login, no API keys, no sessions. Everything is open to
   whoever reaches the URL.
2. **Rate limiting.** Nothing throttles requests. Parsing is CPU-bound, so a
   single client can saturate the service.
3. **Audit logging.** HIPAA expects a record of who accessed what, when. The app
   logs nothing today (deliberately — that also means no PHI leaks into logs).
4. **Self-hosted fonts.** `index.html` loads Sora/Manrope/JetBrains Mono from
   Google Fonts, so every user's IP reaches Google. Vendor the fonts into
   `frontend/src/styles/` and tighten the CSP `style-src`/`font-src` to `'self'`.
5. **A signed BAA** with the hosting vendor, and encryption at rest confirmed
   (the app stores nothing, but the host's disks still matter).

What is already in place and does count toward compliance: TLS everywhere,
security headers, in-memory-only processing with no persistence, errors that
never echo file contents, non-root read-only containers, and images with zero
HIGH/CRITICAL CVEs.

---

## Rollback

Images are tagged by commit SHA in the Cloud Run path, so rollback is a redeploy
of the previous tag. For compose, `git checkout <previous-sha> && docker compose
-f docker-compose.prod.yml up -d --build`. Certificates live in the `caddy_data`
volume and survive both — do not delete that volume, or Let's Encrypt rate
limits will bite on repeated re-issuance.
