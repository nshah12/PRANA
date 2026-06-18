FROM python:3.12-slim

WORKDIR /app

# System deps for argon2, cryptography, asyncpg
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libffi-dev libssl-dev libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8000

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
