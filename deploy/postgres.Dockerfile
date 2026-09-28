FROM postgres:16.15-alpine3.24
RUN apk add --no-cache openssl python3 \
    && mkdir -p /srv/private-evidence /var/lib/greencity-backups \
    && chown postgres:10001 /srv/private-evidence \
    && chmod 0750 /srv/private-evidence \
    && chown postgres:postgres /var/lib/greencity-backups \
    && chmod 2770 /var/lib/greencity-backups
COPY deploy/postgres-entrypoint.sh /usr/local/bin/greencity-postgres-entrypoint
COPY deploy/backup_loop.py /opt/greencity/backup_loop.py
RUN chmod 0555 /usr/local/bin/greencity-postgres-entrypoint /opt/greencity/backup_loop.py
ENTRYPOINT ["/usr/local/bin/greencity-postgres-entrypoint"]
CMD ["postgres", "-c", "ssl=on", "-c", "ssl_cert_file=/var/lib/postgresql/server.crt", "-c", "ssl_key_file=/var/lib/postgresql/server.key"]
