FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /srv

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY app ./app
COPY main.py .
COPY knowledge_base/vector_index ./knowledge_base/vector_index

# One worker (the index lives in memory once), several threads. Cloud Run sets $PORT.
# The timeout covers a full batch of Gemini calls; keep it below the Pub/Sub ack deadline.
CMD exec gunicorn --bind :${PORT:-8080} --workers 1 --threads 4 --timeout 300 main:app
