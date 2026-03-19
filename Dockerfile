FROM python:3.12-slim

WORKDIR /app

# Enable bytecode compilation
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Install required system dependencies (if any)
RUN apt-get update && apt-get install -y --no-install-recommends \
    sqlite3 \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY ./app ./app

# Create directory for persistent data (sqlite db and cache)
RUN mkdir -p /app/data /app/cache_data

# Ensure main starts the app properly
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
