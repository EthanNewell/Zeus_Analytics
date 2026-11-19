FROM python:3.12-slim-bookworm AS builder
ENV PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_NO_CACHE_DIR=1
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential default-libmysqlclient-dev pkg-config \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /build
COPY requirements.txt requirements-mysql.txt ./
RUN python -m pip wheel --wheel-dir /wheels -r requirements-mysql.txt

FROM python:3.12-slim-bookworm AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    DJANGO_SETTINGS_MODULE=config.settings.staging MEDIA_ROOT=/app/media
RUN apt-get update && apt-get install -y --no-install-recommends libmariadb3 \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10001 app && useradd --uid 10001 --gid app --create-home app
COPY --from=builder /wheels /wheels
WORKDIR /app
COPY requirements.txt requirements-mysql.txt ./
RUN python -m pip install --no-cache-dir --no-index --find-links=/wheels -r requirements-mysql.txt \
    && rm -rf /wheels
COPY --chown=app:app . .
RUN DB_ENGINE=sqlite DJANGO_SETTINGS_MODULE=config.settings.local \
    python manage.py collectstatic --noinput \
    && mkdir -p /app/media && chown app:app /app/media
USER app
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "from urllib.request import urlopen; urlopen('http://127.0.0.1:8000/health/live/', timeout=3)"
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "2", "--timeout", "60", "--error-logfile", "-"]
