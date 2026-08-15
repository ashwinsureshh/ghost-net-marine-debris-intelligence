# The deployed operator console (PRD §9.1) — one image, both halves.
#
#   docker build -t ghostnet-console .
#   docker run --rm -p 8000:8000 ghostnet-console
#
# Stage 1 builds the React frontend; stage 2 runs FastAPI and serves the built
# assets from the same process, so a free-tier host needs one service rather
# than a web service plus a static site.
#
# Host-agnostic on purpose: it honours $PORT (Render, Railway, Koyeb, Fly all
# set it) and defaults to 8000 so `docker run` works with no environment at all.
# See DEPLOY.md.

# --------------------------------------------------------------------------
# Stage 1 — frontend
# --------------------------------------------------------------------------
FROM node:24-alpine AS frontend

WORKDIR /build

# Dependencies first, so editing a component does not re-run npm ci.
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./
RUN npm run build


# --------------------------------------------------------------------------
# Stage 2 — server
# --------------------------------------------------------------------------
FROM python:3.11-slim AS server

# 3.11 to match both development machines (see MACHINE-WORKFLOW.md).
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PORT=8000 \
    # ghostnet is run from source rather than installed: config.REPO_ROOT is
    # derived from the package's own path, and it must resolve to /app so that
    # config/, eval/ and webapp_data/ are found. An installed copy in
    # site-packages would point somewhere else entirely.
    PYTHONPATH=/app/src

WORKDIR /app

COPY requirements-deploy.txt ./
RUN python -m pip install --no-cache-dir -r requirements-deploy.txt

# Only what the server actually reads. No data/ — MARIDA and the Sentinel-2
# tiles are workstation-only and could never fit a free tier anyway; that
# constraint is the whole reason artefacts are precomputed (PRD §9.1).
COPY src/ ./src/
COPY config/ ./config/
COPY eval/ ./eval/
COPY webapp_data/ ./webapp_data/
COPY --from=frontend /build/dist ./frontend/dist

# Fail the BUILD, not the first request, if requirements-deploy.txt has drifted
# behind the server's import graph. Also proves the run artefact and the
# measured results are readable from inside the image.
RUN python -c "\
from ghostnet.webapp.app import app;\
from ghostnet.benchmark import cached_benchmark;\
from ghostnet.webapp.store import ArtefactStore;\
report = cached_benchmark();\
runs = ArtefactStore().run_ids();\
assert report.available, report.unavailable_reason;\
assert runs, 'no run artefacts in the image — the console would boot empty';\
print(f'ok: {len(runs)} run(s), benchmark from {report.source_file}')"

EXPOSE 8000

# A shell is needed to expand ${PORT}, but `exec` hands the process back to
# PID 1 so the host's SIGTERM reaches uvicorn — without it the shell swallows
# the signal and every redeploy waits out the kill timeout.
#
# One worker: the free tier gives ~512 MB and planning is cheap, so a second
# would buy nothing and risk the OOM killer.
CMD ["sh", "-c", "exec uvicorn ghostnet.webapp.app:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]
