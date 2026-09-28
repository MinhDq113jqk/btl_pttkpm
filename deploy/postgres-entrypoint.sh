#!/bin/sh
set -eu

if [ "$(id -u)" = "0" ]; then
    if [ ! -s /var/lib/postgresql/server.crt ] || [ ! -s /var/lib/postgresql/server.key ]; then
        openssl req -new -x509 -days 3650 -nodes \
            -out /var/lib/postgresql/server.crt \
            -keyout /var/lib/postgresql/server.key \
            -subj "/CN=greencity-postgres"
        chmod 600 /var/lib/postgresql/server.key
        chown postgres:postgres /var/lib/postgresql/server.crt /var/lib/postgresql/server.key
    fi
fi

exec /usr/local/bin/docker-entrypoint.sh "$@"
