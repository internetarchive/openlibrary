#!/bin/bash

machine=$(uname -m)

if [[ "${machine}" == "aarch64" || "${machine}" == "arm64" ]]; then
    echo "Running on ARM64 architecture (e.g., Apple M1)"
    echo "openresty still doesn't work on arm see https://github.com/openresty/openresty/issues/840 and \
    https://github.com/internetarchive/openlibrary/issues/6316"
else
    wget -O - https://openresty.org/package/pubkey.gpg | apt-key add -
    echo "deb http://openresty.org/package/debian $(lsb_release -sc) openresty" \
        | tee /etc/apt/sources.list.d/openresty.list
    apt-get update && apt-get -y install --no-install-recommends openresty
fi
