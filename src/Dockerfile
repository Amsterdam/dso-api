FROM amsterdam/python:3.9-buster AS builder
MAINTAINER datapunt@amsterdam.nl

COPY requirements* ./
ARG PIP_REQUIREMENTS=requirements.txt
RUN pip install --no-cache-dir -r $PIP_REQUIREMENTS

# Start runtime image,
FROM amsterdam/python:3.9-slim-buster
RUN apt update \
 && apt install --no-install-recommends -y curl \
 && rm -rf /var/lib/apt/lists/* /var/cache/debconf/*-old

# Copy python build artifacts from builder image
COPY --from=builder /usr/local/bin/ /usr/local/bin/
COPY --from=builder /usr/local/lib/python3.9/site-packages/ /usr/local/lib/python3.9/site-packages/

RUN mkdir /static && chown datapunt:datapunt /static

WORKDIR /app
COPY . ./

ENV DJANGO_SETTINGS_MODULE=dso_api.settings DJANGO_DEBUG=false
RUN python manage.py collectstatic --noinput

EXPOSE 8000
USER datapunt
# Uwsing gunicorn instead of uWSGI to avoid memory leaking issues
CMD ["gunicorn", "--bind=0.0.0.0:8000", "--worker-tmp-dir=/dev/shm", "--workers=1", "--threads=4", "--access-logfile=-", "dso_api.wsgi:application"]
