# SentinelAI production image.
#
# Two stages: the dashboard is built with Node and its static output is copied
# into the Python runtime, so the shipped image carries no Node toolchain and
# the API serves the UI from a single container.

# ---- Stage 1: build the dashboard ----------------------------------------
FROM node:20-slim AS dashboard

WORKDIR /build

# Copy manifests first so dependency install is cached independently of source.
COPY dashboard/package.json dashboard/package-lock.json ./
RUN npm ci

COPY dashboard/ ./
RUN npm run build


# ---- Stage 2: Python runtime ---------------------------------------------
FROM python:3.12-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY ingestion/       ./ingestion/
COPY observability/   ./observability/
COPY rag_service/     ./rag_service/
COPY sentinel_core/   ./sentinel_core/
COPY api/             ./api/
COPY config/          ./config/
COPY data/            ./data/

COPY --from=dashboard /build/dist ./dashboard/dist

# Run unprivileged. The landing zone is the only path the app writes to.
RUN useradd --create-home --uid 10001 sentinel \
    && mkdir -p /app/data/landing \
    && chown -R sentinel:sentinel /app/data
USER sentinel

EXPOSE 8000

# Hits the one route exempt from API-key auth, so a configured key does not
# make the container look unhealthy.
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4).status==200 else 1)"

CMD ["uvicorn", "api.server:app", "--host", "0.0.0.0", "--port", "8000"]
