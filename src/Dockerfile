FROM python:3.11-slim-bullseye AS builder
MAINTAINER datapunt@amsterdam.nl

RUN apt update && apt install --no-install-recommends -y \
    build-essential \
    libgeos-dev \
    libpq-dev
COPY requirements* ./
ARG PIP_REQUIREMENTS=requirements.txt
RUN python -m pip install uwsgi
# The `--no-deps` has been added because of a pip bug with --require-hashes
# The dependencies have already been resolved during the generation of
# the requirements.txt, so adding `--no-deps` can safely be done.
RUN python -m pip install --no-cache-dir --no-deps -r $PIP_REQUIREMENTS

# Start runtime image,
FROM python:3.11-slim-bullseye
RUN useradd -U -r dsoapi
RUN apt update && apt install --no-install-recommends -y \
    curl \
    libgdal28 \
    libgeos-c1v5 \
    libpq5 \
    media-types \
    netcat-openbsd

# Copy python build artifacts from builder image
COPY --from=builder /usr/local/bin/ /usr/local/bin/
COPY --from=builder /usr/local/lib/python3.11/site-packages/ /usr/local/lib/python3.11/site-packages/

WORKDIR /app
COPY . ./

ENV DJANGO_SETTINGS_MODULE=dso_api.settings DJANGO_DEBUG=false DSO_STATIC_DIR=/static
RUN python manage.py collectstatic --noinput

EXPOSE 8000
USER dsoapi
CMD ["uwsgi"]
