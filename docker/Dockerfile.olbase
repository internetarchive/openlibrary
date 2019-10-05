FROM ubuntu:xenial

ENV LANG en_US.UTF-8

# required for postgres
ENV LC_ALL POSIX

# add openlibrary users
RUN groupadd --system openlibrary \
  && useradd --no-log-init --system --gid openlibrary openlibrary \
  && useradd --no-log-init --system --gid openlibrary solrupdater

RUN apt-get -qq update && apt-get install -y \
    nginx \
    authbind \
    postgresql \
    build-essential \
    git-core \
    libpq-dev \
    libxml2-dev \
    libxslt-dev \
    libffi-dev \
    curl \
    screen \
    python-dev \
    python-pip \
    libgeoip-dev \
    python-lxml \
    python-psycopg2 \
    python-yaml

# Install LTS version of node.js
RUN curl -sL https://deb.nodesource.com/setup_8.x | bash - \
    && apt-get install -y nodejs

# enable users to bind to port 80
RUN touch /etc/authbind/byport/80 && chmod 777 /etc/authbind/byport/80

# Setup nginx
RUN ln -s /openlibrary/conf/nginx/sites-available/openlibrary.conf /etc/nginx/sites-available/ \
    && ln -s /etc/nginx/sites-available/openlibrary.conf /etc/nginx/sites-enabled/

RUN mkdir -p /var/log/openlibrary /var/lib/openlibrary \
    && chown openlibrary:openlibrary /var/log/openlibrary /var/lib/openlibrary

RUN mkdir /openlibrary && chown openlibrary:openlibrary /openlibrary
WORKDIR /openlibrary

COPY requirements*.txt ./
RUN pip install --disable-pip-version-check --default-timeout=100 -r requirements_common.txt

COPY package*.json ./
RUN npm install && npm install -g less

COPY --chown=openlibrary:openlibrary . /openlibrary

USER openlibrary
RUN ln -s vendor/infogami/infogami infogami
# run make to initialize git submodules, build css and js files
RUN make

# Expose Open Library and Infobase
EXPOSE 80 7000
CMD authbind --deep scripts/openlibrary-server conf/openlibrary.yml \
    --gunicorn --workers 4 --timeout 180 --bind :80
