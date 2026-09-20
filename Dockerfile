# Multi-Agent Research Assistant - Hugging Face Spaces (Docker SDK) image.
#
# Stage 1 builds the React frontend; stage 2 runs the FastAPI app and serves that
# build from the same origin, so the deployed Space needs no CORS configuration.

# ---------- Stage 1: build the frontend ----------
FROM node:20-slim AS frontend

WORKDIR /build

# Install dependencies from the lockfile first so this layer caches across source edits.
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci --no-audit --no-fund || npm install --no-audit --no-fund

COPY frontend/ ./
RUN npm run build


# ---------- Stage 2: runtime ----------
FROM python:3.13-slim

# Hugging Face Spaces runs the container as a non-root user with uid 1000.
RUN useradd -m -u 1000 appuser

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    API_HOST=0.0.0.0 \
    API_PORT=7860 \
    FRONTEND_DIST_DIR=frontend/dist

WORKDIR /app

COPY --chown=appuser:appuser requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY --chown=appuser:appuser src/ ./src/
COPY --chown=appuser:appuser main.py serve.py ./
COPY --chown=appuser:appuser --from=frontend /build/dist ./frontend/dist

# The app writes a generated JWT secret to .jwt_secret when JWT_SECRET_KEY is unset.
# On a Space that file is lost on every restart, invalidating all issued tokens, so
# JWT_SECRET_KEY should be set as a Space secret - see DEPLOYMENT.md.
RUN mkdir -p /app/logs && chown -R appuser:appuser /app

USER appuser

EXPOSE 7860

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:7860/api/health', timeout=4).status == 200 else 1)"

CMD ["python", "serve.py"]
