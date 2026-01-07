FROM python:3.13-bookworm AS builder
LABEL org.opencontainers.image.authors="datapunt@amsterdam.nl"

RUN apt update && apt install --no-install-recommends -y \
    build-essential \
    libgeos-dev \
    libpq-dev
COPY requirements* ./
ARG PIP_REQUIREMENTS=requirements.txt
RUN python -m pip install -U pip \
 && python -m pip install uwsgi
# The `--no-deps` has been added because of a pip bug with --require-hashes
# The dependencies have already been resolved during the generation of
# the requirements.txt, so adding `--no-deps` can safely be done.
RUN python -m pip -v install --no-cache-dir --no-deps -r $PIP_REQUIREMENTS

# Start runtime image
FROM python:3.13-slim-bookworm AS runtime
RUN useradd -U -r dsoapi
RUN apt update && apt install --no-install-recommends -y \
    curl \
    libgdal32 \
    libgeos-c1v5 \
    libproj25 \
    libpq5 \
    media-types \
    netcat-openbsd

# Copy python build artifacts from builder image
COPY --from=builder /usr/local/bin/ /usr/local/bin/
COPY --from=builder /usr/local/lib/python3.13/site-packages/ /usr/local/lib/python3.13/site-packages/

WORKDIR /app
COPY . ./

ENV DJANGO_SETTINGS_MODULE=dso_api.settings DJANGO_DEBUG=false DSO_STATIC_DIR=/static
RUN python manage.py collectstatic --noinput

EXPOSE 8000

# Give dsoapi the same UID as github actions runner.
USER root
RUN usermod --uid 1001 dsoapi

USER dsoapi
CMD ["uwsgi"]
