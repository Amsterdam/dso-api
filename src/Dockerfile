FROM amsterdam/python:3.8-buster AS builder
MAINTAINER datapunt@amsterdam.nl

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Start runtime image,
FROM amsterdam/python:3.8-slim-buster

# Copy python build artifacts from builder image
COPY --from=builder /usr/local/bin/ /usr/local/bin/
COPY --from=builder /usr/local/lib/python3.8/site-packages/ /usr/local/lib/python3.8/site-packages/

RUN mkdir /static && chown datapunt:datapunt /static

WORKDIR /app
COPY . ./

ENV DJANGO_SETTINGS_MODULE=dso_api.settings DJANGO_DEBUG=false
RUN python manage.py collectstatic --noinput

EXPOSE 8000
USER datapunt
CMD ["uwsgi"]
