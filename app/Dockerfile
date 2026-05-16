FROM python:3.12-slim

WORKDIR /app

# Install deps as a separate layer (cache-friendly)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .

# Data volume for SQLite persistence
RUN mkdir -p /data

# Non-root user
RUN adduser --disabled-password --gecos '' appuser && \
    chown -R appuser /data
USER appuser

EXPOSE 5000

ENV FLASK_ENV=production \
    DB_PATH=/data/habits.db \
    APP_VERSION=dev

# gunicorn: 1 worker so APScheduler runs in a single process
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "1", \
     "--access-logfile", "-", "--error-logfile", "-", "app:app"]
