FROM python:3.12.14-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/srv/backend

RUN groupadd --system --gid 10001 greencity \
    && useradd --system --uid 10001 --gid 10001 --create-home --home-dir /home/greencity greencity \
    && install --directory --owner=greencity --group=greencity --mode=0750 /srv/private-evidence \
    && install --directory --owner=greencity --group=greencity /srv/backend

WORKDIR /srv/backend
COPY backend/requirements.lock.txt ./requirements.lock.txt
RUN python -m pip install --no-cache-dir -r requirements.lock.txt

COPY backend/app ./app
COPY backend/alembic ./alembic
COPY backend/alembic.ini ./alembic.ini
COPY backend/scripts ./scripts
COPY deploy/backend-entrypoint.sh /usr/local/bin/backend-entrypoint
RUN chmod 0555 /usr/local/bin/backend-entrypoint \
    && chown -R greencity:greencity /srv/backend /srv/private-evidence

USER greencity:greencity
EXPOSE 8000
ENTRYPOINT ["/usr/local/bin/backend-entrypoint"]
CMD ["uvicorn", "app.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
