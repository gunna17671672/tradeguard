# TradeGuard — single self-hosted container.
#
#   docker build -t tradeguard .
#   docker run -p 8080:8080 -v tradeguard_data:/data tradeguard
#
# Everything mutable (the SQLite database and your live rules.yaml) lives on
# the /data volume; the image itself is stateless. On first start rules.yaml
# is seeded from the shipped rules.example.yaml template.

# --- Stage 1: build the static frontend -------------------------------------
FROM node:22-alpine AS frontend
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
# Built with an empty API base so every request is same-origin relative:
# FastAPI serves the pages and /api from one port.
ENV NEXT_PUBLIC_API_URL=""
RUN npm run build

# --- Stage 2: runtime — FastAPI serving the API + the built frontend --------
FROM python:3.12-slim
WORKDIR /app

COPY backend/pyproject.toml ./
COPY backend/app ./app
# Install as a real package, then drop the source copy: uvicorn imports the
# site-packages install, so /app holds only the template and the static site.
RUN pip install --no-cache-dir . && rm -rf ./app ./pyproject.toml

# The rules template (bootstrapped to /data/rules.yaml on first start) and
# the frontend export.
COPY rules.example.yaml ./
COPY --from=frontend /build/out ./static

ENV TRADEGUARD_DB=/data/tradeguard.db \
    TRADEGUARD_RULES=/data/rules.yaml \
    TRADEGUARD_STATIC=/app/static

RUN useradd --create-home tradeguard && mkdir /data && chown tradeguard /data
USER tradeguard
VOLUME /data
EXPOSE 8080
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
