FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/
# COPY knowledge/ ./knowledge/
COPY skills/ ./skills_builtin/

COPY docker-entrypoint.sh /
RUN chmod +x /docker-entrypoint.sh

ENV PYTHONPATH=/app/app
WORKDIR /app/app

EXPOSE 8765

ENTRYPOINT ["/docker-entrypoint.sh"]
CMD ["python", "-m", "main"]
