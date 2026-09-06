# Backend Dockerfile -- Multi-Agent Options Trading Platform (FastAPI)
#
# Portable across PaaS providers: Railway, Render, Fly.io, etc. all inject
# a PORT environment variable and expect the app to bind to 0.0.0.0:$PORT
# -- this Dockerfile handles that generically via shell-expanded ${PORT},
# so no per-platform changes are needed. (Render specifically defaults
# PORT to 10000 if unset; Railway assigns a different port per deploy --
# both work identically here.)

FROM python:3.12-slim

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

EXPOSE 8000
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
