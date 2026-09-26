# syntax=docker/dockerfile:1

FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# WeasyPrint runtime libs only (mysql-connector is pure Python -> no build deps)
RUN apt-get update && apt-get install -y --no-install-recommends \
      libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz-subset0 \
      libcairo2 libgdk-pixbuf-2.0-0 libffi8 \
      libjpeg62-turbo libopenjp2-7 \
      shared-mime-info fonts-dejavu-core \
      curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /code

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

RUN useradd --create-home --uid 1000 appuser \
    && chown -R appuser:appuser /code
USER appuser

EXPOSE 8080

# 1 worker + 8 threads is deliberate:
#   Flask-Limiter + Flask-Caching are in-process -> N workers = Nx effective rate limit
CMD ["gunicorn", "app:app", \
     "--bind", "0.0.0.0:8080", \
     "--workers", "1", "--threads", "8", \
     "--timeout", "120", "--graceful-timeout", "30", \
     "--access-logfile", "-", "--error-logfile", "-", \
     "--log-level", "info"]
