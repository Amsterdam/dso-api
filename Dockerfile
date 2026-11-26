FROM ghcr.io/astral-sh/uv:0.13-python3.14-trixie-slim AS builder
LABEL org.opencontainers.image.authors="datapunt@amsterdam.nl"

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv

RUN apt update && apt install --no-install-recommends -y \
    build-essential \
    libgeos-dev \
    libpq-dev
WORKDIR /app
COPY pyproject.toml uv.lock ./
ARG UV_SYNC_ARGS="--no-dev"
RUN uv sync --locked --no-install-project $UV_SYNC_ARGS
COPY src/ ./src/
RUN uv sync --locked $UV_SYNC_ARGS

# Start runtime image
FROM ghcr.io/astral-sh/uv:0.13-python3.14-trixie-slim AS runtime
RUN useradd -U -r --create-home dsoapi
RUN apt update && apt install --no-install-recommends -y \
    curl \
    libgdal36 \
    libgeos-c1t64 \
    libproj25 \
    libpq5 \
    media-types \
    netcat-openbsd

# Copy python build artifacts from builder image
COPY --from=builder /opt/venv /opt/venv
ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH"

WORKDIR /app
COPY --from=builder /app /app

ENV DJANGO_SETTINGS_MODULE=dso_api.settings DJANGO_DEBUG=false DSO_STATIC_DIR=/static
RUN python src/manage.py collectstatic --noinput

EXPOSE 8000

# Give dsoapi the same UID as github actions runner.
USER root
RUN usermod --uid 1001 dsoapi

USER dsoapi
ENTRYPOINT []
CMD ["uwsgi"]
