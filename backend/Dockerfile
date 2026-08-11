# EDI-Converter backend image — multi-stage, Alpine runtime, non-root.
#
# Stage 1 compiles the dependencies into a self-contained virtualenv; stage 2 is
# a clean runtime that copies just that venv plus the application source. The
# compiler toolchain, pip's cache and the test framework never reach the final
# image (pytest lives in requirements-dev.txt, which only CI and local
# development install).
#
# Measured: 260 MB single-stage slim -> 127 MB. See docx/6-memory.md.

# --------------------------------------------------------------------------- #
#  Stage 1 — build dependencies
# --------------------------------------------------------------------------- #
FROM python:3.11-alpine AS build

ENV PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# uvloop and httptools (from uvicorn[standard]) publish no musl wheels, so they
# are compiled here. This toolchain is ~200 MB and stays in the build stage.
RUN apk add --no-cache build-base libffi-dev

# A venv keeps everything we ship inside one directory to copy over.
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /app
COPY requirements.txt .

# Install, then strip what only the installer needed: pip/setuptools/wheel are
# ~15 MB of dead weight at runtime and bytecode caches rebuild on demand.
# One RUN, so the removals actually shrink the layer instead of shadowing it.
RUN pip install --no-cache-dir -r requirements.txt \
    && pip uninstall --yes pip setuptools wheel \
    && find /opt/venv -type d -name '__pycache__' -prune -exec rm -rf {} + \
    && find /opt/venv -type d -name 'tests' -prune -exec rm -rf {} +

# --------------------------------------------------------------------------- #
#  Stage 2 — runtime
# --------------------------------------------------------------------------- #
FROM python:3.11-alpine AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:$PATH"

# Runtime support for the compiled extensions (uvloop links libgcc), plus an
# unprivileged user: nothing here needs root and the container writes no files —
# uploads are processed in memory and discarded.
#
# The base image also ships pip/setuptools/wheel in its own site-packages, which
# nothing uses at runtime (the app runs from /opt/venv) but which Trivy flags —
# they were the image's only HIGH CVEs (CVE-2026-24049 wheel, CVE-2026-23949
# jaraco.context, both installer-only path-traversal/code-execution issues).
# Removing them takes the image to zero HIGH/CRITICAL findings.
RUN apk add --no-cache libgcc libstdc++ \
    && rm -rf /usr/local/lib/python3.11/site-packages/pip* \
              /usr/local/lib/python3.11/site-packages/setuptools* \
              /usr/local/lib/python3.11/site-packages/wheel* \
              /usr/local/lib/python3.11/site-packages/pkg_resources \
              /usr/local/lib/python3.11/ensurepip \
    && addgroup -S -g 1001 app \
    && adduser -S -u 1001 -G app -h /app -s /sbin/nologin app

WORKDIR /app

# Dependencies first so the layer is reused when only application code changes.
COPY --from=build --chown=app:app /opt/venv /opt/venv
COPY --chown=app:app . .

USER app

EXPOSE 5080

# Container healthcheck hitting the /health endpoint. 127.0.0.1 rather than
# localhost, which resolves to ::1 first while uvicorn is bound to IPv4.
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:5080/health').status==200 else 1)"

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "5080"]
