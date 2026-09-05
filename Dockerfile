# --- Exam Seat & Hall Allocation System: backend image ---
FROM python:3.11-slim

# Prevents Python from buffering stdout/stderr (so `docker logs` is live)
# and from writing .pyc files into the image.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# System deps needed to build bcrypt/cryptography wheels on slim images.
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

# SQLite database file lives here. On Render, mount a persistent disk at
# this path (see render.yaml) so data survives deploys/restarts.
RUN mkdir -p /data
ENV DATABASE_URL=sqlite:////data/exam_allocation.db

EXPOSE 8000

# Runs the seed script (idempotent - safe to run every boot) then starts
# the API. Render/Docker both set $PORT; default to 8000 for plain `docker run`.
CMD sh -c "python seed.py && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"
