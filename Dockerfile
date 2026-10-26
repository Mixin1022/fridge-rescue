FROM python:3.12-slim
WORKDIR /app
ENV PLAYWRIGHT_BROWSERS_PATH=/opt/playwright PYTHONUNBUFFERED=1 HOST=0.0.0.0 PORT=8080 FRIDGE_DATA_DIR=/data HF_HOME=/data/models/huggingface
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg libgomp1 && rm -rf /var/lib/apt/lists/*
COPY requirements-cloud.txt .
RUN pip install --no-cache-dir -r requirements-cloud.txt
RUN python -m playwright install --with-deps chromium
COPY . .
RUN useradd --uid 10001 --create-home fridge && mkdir -p /data && chown fridge:fridge /data
USER fridge
EXPOSE 8080
CMD ["python", "cloud_server.py"]
