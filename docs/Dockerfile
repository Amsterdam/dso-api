FROM python:3.9-bullseye as builder

RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      graphviz \
      fonts-liberation \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /docs
COPY requirements.txt /docs
RUN pip install -r requirements.txt

COPY . /docs/

# Added arg here, so build step is invalidated each time
ARG BUILD_NUMBER=unknown
RUN mkdir -p /docs/_static \
 && SPHINXOPTS="-j $(nproc)" make html

# Static serving runtime
FROM nginx
RUN mkdir -p /usr/share/nginx/html/v1/docs/
COPY --from=builder /docs/build/html/ /usr/share/nginx/html/v1/docs/
