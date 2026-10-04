#!/usr/bin/env bash
set -euxo pipefail

export DEBIAN_FRONTEND=noninteractive

apt-get update
apt-get install -y --no-install-recommends \
    automake \
    autoconf \
    build-essential \
    ca-certificates \
    curl \
    dpkg-dev \
    git \
    libcurl4-openssl-dev \
    libgeoip-dev \
    liblmdb-dev \
    libmodsecurity-dev \
    libpcre2-dev \
    libssl-dev \
    libtool \
    libxml2 \
    libxml2-dev \
    libyajl-dev \
    lsb-release \
    pkgconf \
    zlib1g \
    zlib1g-dev

curl -fsSL https://nginx.org/keys/nginx_signing.key | tee /usr/share/keyrings/nginx-keyring.asc

echo "deb [signed-by=/usr/share/keyrings/nginx-keyring.asc] http://nginx.org/packages/debian $(lsb_release -cs) nginx" > /etc/apt/sources.list.d/nginx.list
echo "deb-src [signed-by=/usr/share/keyrings/nginx-keyring.asc] http://nginx.org/packages/debian $(lsb_release -cs) nginx" >> /etc/apt/sources.list.d/nginx.list

cd /tmp/
git clone --depth 1 --branch "${MODSECURITY_TAG}" https://github.com/owasp-modsecurity/ModSecurity-nginx.git

apt-get update
nginx_version="$(apt-cache policy nginx | awk '/Candidate:/ {print $2}')"
if [ -z "${nginx_version}" ] || [ "${nginx_version}" = "(none)" ]; then
    echo "Unable to resolve nginx candidate version from apt cache" >&2
    exit 1
fi

mkdir -p /tmp/nginx-build
cd /tmp/nginx-build
apt-get source "nginx=${nginx_version}"
nginx_source_dir="$(find /tmp/nginx-build -mindepth 1 -maxdepth 1 -type d -name 'nginx-*' | head -n 1)"
if [ -z "${nginx_source_dir}" ]; then
    echo "Unable to find unpacked nginx source directory" >&2
    exit 1
fi

cd "${nginx_source_dir}"
./configure --with-compat --add-dynamic-module=/tmp/ModSecurity-nginx
make -j"$(nproc)" modules

mkdir -p /out
cp objs/ngx_http_modsecurity_module.so /out/ngx_http_modsecurity_module.so
