# Deployment Guide — host sizing

An analysis of what this stack actually needs, from the two compose files and the
two Dockerfiles. Every figure below is **measured on the running stack**, not
estimated — configured ceilings are shown alongside real usage, because they differ
by roughly 10×.

The production stack is three containers: `caddy` (TLS edge), `backend`
(FastAPI/uvicorn), `frontend` (static bundle on nginx). There is **no database, no
cache and no worker** — files are parsed in memory and discarded, which is what
makes the sizing so modest.

## Memory: configured vs actually used

| Service | Limit | Reservation | Idle | Under load |
|---|---|---|---|---|
| caddy | 128 MB | — | 10.7 MB | 17.7 MB |
| backend | 512 MB | 128 MB | 43.4 MB | 48.9 MB |
| frontend | 128 MB | 32 MB | 9.5 MB | 12.5 MB |
| **Total** | **768 MB** | **160 MB** | **~64 MB** | **~79 MB** |

"Under load" is 32 concurrent validation requests sustained for 20 seconds. Serving
traffic barely moves the needle — the frontend is static files, and Caddy is just
proxying.

**The real memory driver is upload size, not request rate.** Four concurrent 9 MB
uploads took the backend to **176 MB** (34% of its limit). That is the number the
512 MB limit is sized against: roughly ten simultaneous maximum-size uploads before
it becomes tight. Note that `/tmp` is a **memory-backed tmpfs** (64 MB), because the
root filesystem is read-only and Starlette spools multipart uploads over ~1 MB to
disk — so upload buffers count against the container's memory limit.

**Recommended: 2 GB RAM.** The stack itself needs well under 1 GB, but Docker engine
plus OS overhead is ~400–600 MB, and `docker compose build` needs materially more
than running does (see flag 1 below). 1 GB technically runs it; 2 GB means you never
think about it.

## CPU

Summed limits: 0.5 + 1.0 + 0.5 = **2.0 vCPU** of ceiling, and unlike memory these do
get used.

| Scenario | backend | caddy |
|---|---|---|
| 32 concurrent validations | 60% | 23% |
| 4 concurrent 9 MB uploads | **99.6%** (pegged) | — |

Parsing is CPU-bound and synchronous, so the backend is the bottleneck by design.
Measured throughput on its 1.0 CPU limit: **152 req/s** at concurrency 8 (p95 94 ms)
and 213 req/s at concurrency 32 (p95 231 ms) — a 40% throughput gain for triple the
latency, which is why both platform configs cap concurrency at 8.

**Recommended: 2 vCPU.** One core for the backend under sustained parsing, one for
the edge and the OS. Scale by **adding CPU before adding replicas** — the workload
is compute, not I/O.

## Storage

- **Images: 284 MB total** for all three, with layer sharing (backend 127 MB,
  frontend 81.7 MB, `caddy:2-alpine` 88.7 MB — the two app images share the Alpine
  base).
- **Volumes: under 1 MB.** Only `caddy_data` and `caddy_config` exist, holding TLS
  certificates. There is no `pgdata` equivalent because there is no database.
- **Build cache is the only thing that grows.** On the machine this was measured on
  it had reached 21 GB across projects, 99% reclaimable. If you build on the host,
  `docker builder prune` belongs in a cron job.

**Recommended: 20 GB SSD.** Comfortable for images, logs and cache churn. 10 GB
works if you build elsewhere and pull the image.

## Bandwidth

Negligible. The frontend bundle is **62.8 KB gzipped**, cached after first load;
requests are single EDI files (typically a few KB) with JSON responses. Any standard
VPS allowance is orders of magnitude more than needed. There are **no outbound API
calls** — the engine has no third-party dependencies at runtime. The one external
request is the browser fetching Google Fonts, which is a privacy consideration
rather than a bandwidth one (see flag 6).

## Suggested starting spec

**2 vCPU / 2 GB RAM / 20 GB SSD** — comfortably covers this stack with room to grow.
A Hetzner CX22 (2 vCPU / 4 GB / 40 GB, ~€3.79/month) exceeds this on every axis and
is the cheapest sensible fit. For scale-to-zero hosting the equivalent is 1 vCPU /
512 MB per instance, which is what `fly.toml` and the Cloud Run script both request.

## Things worth flagging before you deploy

1. **Building needs more than running.** The backend image compiles `uvloop` and
   `httptools` from source (no musl wheels exist), which pulls in a ~200 MB gcc
   toolchain and spikes CPU and memory during the build. On a 1 GB box the build can
   OOM even though the running container uses 43 MB. Build in CI and pull the image,
   or size the host for the build rather than the runtime.

2. **Do not deploy the root `docker-compose.yml`.** It is the development stack: it
   publishes the backend directly on port 5080 with no TLS and no security headers.
   Production is `deploy/docker-compose.prod.yml`, where only Caddy binds ports and
   the API is unreachable except through the edge.

3. **Persist the `caddy_data` volume.** It holds the issued TLS certificates.
   Deleting it on every deploy means re-issuing from Let's Encrypt, and their rate
   limits will lock you out of new certificates for that domain.

4. **Raising the upload cap has three knobs, not one.** `EDI_MAX_FILE_MB`,
   Caddy's `MAX_UPLOAD_SIZE`, and the tmpfs `size=64m` all have to move together —
   and because the tmpfs is RAM, so does the container's memory limit.

5. **The backend has no dependency lock file.** `requirements.txt` uses `>=` ranges,
   so a rebuild months from now can pull a different FastAPI than was tested, and
   Python CVE scanners have nothing to scan. Pin before you rely on rebuilding.

6. **The UI loads fonts from Google's CDN**, so every user's IP reaches a third
   party. Harmless for an internal tool; worth vendoring the three fonts before any
   deployment handling real patient data, which also tightens the CSP to `'self'`.

7. **ARM hosts build slower.** On Oracle's free ARM tier the same compile runs
   natively but takes noticeably longer, and multi-arch builds have not been tested
   here. Verify the image runs before committing to that host.

8. **The limits are deliberately loose.** Measured peak is 176 MB against a 512 MB
   ceiling. That headroom absorbs concurrent large uploads; do not tighten it to the
   idle figure or the first busy minute will OOM-kill the parser.

---

*Deployment steps, platform options and cost comparison live in
[`deploy/README.md`](../deploy/README.md). Verify any deployment with
`python deploy/smoke_test.py <url>` and re-measure with
`python deploy/load_test.py <url>`.*
