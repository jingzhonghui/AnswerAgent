FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/
COPY knowledge/ ./knowledge/

ENV PYTHONPATH=/app/app
WORKDIR /app/app

EXPOSE 8765

CMD ["python", "-m", "main"]
