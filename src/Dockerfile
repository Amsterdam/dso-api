FROM amsterdam/python:3.9-bullseye AS builder
MAINTAINER datapunt@amsterdam.nl

COPY requirements* ./
ARG PIP_REQUIREMENTS=requirements.txt
RUN pip install --no-cache-dir -r $PIP_REQUIREMENTS

# Start runtime image,
FROM amsterdam/python:3.9-slim-bullseye
RUN apt update && apt install --no-install-recommends -y curl

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
CMD ["uwsgi"]
