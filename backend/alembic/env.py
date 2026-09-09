from alembic import context
from sqlalchemy import inspect

from app.core.config import Settings
from app.core.database import Database
from app.models import Base
from app.models.base import SCHEMA


def include_name(name, type_, parent_names):
    if type_ == "schema":
        return name == SCHEMA
    return True


def configure(**kwargs):
    context.configure(target_metadata=Base.metadata, include_schemas=True,
                      include_name=include_name, version_table_schema=SCHEMA,
                      compare_type=True, **kwargs)


if context.is_offline_mode():
    configure(url="postgresql+psycopg://", literal_binds=True)
    with context.begin_transaction():
        context.execute('CREATE SCHEMA IF NOT EXISTS "greencity"')
        context.run_migrations()
else:
    database = Database(Settings())
    try:
        with database.engine.connect() as connection:
            # Version table needs its namespace before Alembic can initialize.
            # CREATE SCHEMA is transactional and belongs to the migration runner.
            if SCHEMA not in inspect(connection).get_schema_names():
                command = getattr(context.config.cmd_opts, "cmd", (None,))[0]
                if getattr(command, "__name__", "") not in {"upgrade", "revision"}:
                    raise RuntimeError("Run the reviewed initial migration first")
                connection.exec_driver_sql('CREATE SCHEMA "greencity"')
                connection.commit()
            else:
                # Inspection starts a transaction; finish it before Alembic owns one.
                connection.rollback()
            configure(connection=connection)
            with context.begin_transaction():
                context.run_migrations()
    finally:
        database.close()
