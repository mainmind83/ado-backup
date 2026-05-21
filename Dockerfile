FROM python:3.12-slim

# git is required for repo mirroring; tzdata lets the scheduler honour TZ.
RUN apt-get update && apt-get install -y --no-install-recommends git tzdata \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/

# Directories for mounted volumes.
RUN mkdir -p /backup /logs

VOLUME ["/backup", "/logs"]

CMD ["python", "src/main.py"]
