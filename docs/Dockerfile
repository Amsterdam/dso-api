FROM nginx

WORKDIR /docs
RUN apt-get update \
 && apt-get install -y \
      graphviz \
      imagemagick \
      make \
      python3 \
      python3-pip \
 && apt-get autoremove \
 && apt-get clean \
 && rm -rf /var/lib/apt/lists/*

RUN python3 -m pip install -U pip
RUN python3 -m pip install Sphinx==3.1.1 Pillow sphinx-rtd-theme psycopg2-binary python-string-utils

COPY . /docs
# RUN make html
RUN mkdir -p /usr/share/nginx/html/v1/docs/
# RUN cp -rf /docs/build/html/* /usr/share/nginx/html/v1/docs/
