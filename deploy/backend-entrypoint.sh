#!/bin/sh
set -eu
export GREENCITY_DISABLE_DOTENV=1

read_secret() {
    secret_path="$1"
    if [ ! -r "$secret_path" ]; then
        echo "required secret is missing: $secret_path" >&2
        exit 78
    fi
    # Secret files are single-line values. Strip only the final CR/LF so a
    # Windows-created secret file remains usable without changing its value.
    tr -d '\r\n' < "$secret_path"
}

database_secret="${DATABASE_URL_SECRET_FILE:-/run/secrets/runtime_database_url}"
if [ -r "$database_secret" ]; then
    export DATABASE_URL="$(read_secret "$database_secret")"
fi
if [ -r /run/secrets/secret_key ]; then
    export SECRET_KEY="$(read_secret /run/secrets/secret_key)"
fi

if [ -r /run/secrets/database_ssl_root_cert ]; then
    export DATABASE_SSL_ROOT_CERT=/run/secrets/database_ssl_root_cert
fi

exec "$@"
