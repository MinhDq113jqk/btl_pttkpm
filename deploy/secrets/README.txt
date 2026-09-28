Create these six one-line files locally before `docker compose -f deploy/compose.yml up`:

* `postgres_password` — disposable PostgreSQL bootstrap password.
* `migration_database_url` — migration DSN using the dedicated migrator role, for example `postgresql://greencity_migrator:[REDACTED]@db:5432/greencity?sslmode=require`.
* `runtime_database_url` — backend DSN using the DML-only runtime role, for example `postgresql://greencity_runtime:[REDACTED]@db:5432/greencity?sslmode=require`.
* `migrator_password` and `runtime_password` — must match the respective DSNs.
* `secret_key` — random value of at least 32 bytes.

The setup job reads the admin and role passwords from mounted files and creates
`greencity_owner` (`NOLOGIN`), `greencity_migrator` (`NOINHERIT`, `SET ROLE`
membership), and `greencity_runtime` (`NOINHERIT`, DML only). The migration DSN
and runtime DSN must use the generated migrator/runtime passwords respectively.

Never commit the files or paste their values into logs. Production must replace
the local PostgreSQL service with the approved managed database, use
`sslmode=verify-full`, and mount its CA as `database_ssl_root_cert`.
