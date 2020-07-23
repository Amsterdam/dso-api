FROM python:3.8-buster as builder

RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      graphviz \
      fonts-liberation \
 && rm -rf /var/lib/apt/lists/* \
 && pip install Sphinx==3.1.2 Pillow sphinx-rtd-theme psycopg2-binary python-string-utils

WORKDIR /docs
COPY . /docs
RUN make html

# Static serving runtime
FROM nginx
RUN mkdir -p /usr/share/nginx/html/v1/docs/
COPY --from=builder /docs/build/html/ /usr/share/nginx/html/v1/docs/
