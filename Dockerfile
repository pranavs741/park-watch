FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    YOLO_CONFIG_DIR=/root/.config/Ultralytics

# OpenCV needs these runtime libraries even though ParkWatch has no GUI.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libglib2.0-0 libgl1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
# Use the official ARM64 CPU wheels. The default PyPI ARM wheel currently
# advertises CUDA libraries, which are unnecessary for this CPU-only service.
RUN sed '/^ultralytics>=/d' requirements.txt > /tmp/requirements-base.txt \
    && pip install --no-cache-dir -r /tmp/requirements-base.txt \
    && pip install --no-cache-dir --no-deps \
        --index-url https://download.pytorch.org/whl/cpu \
        torch==2.0.1 torchvision==0.15.2 \
    && pip install --no-cache-dir filelock typing_extensions sympy networkx jinja2 fsspec \
    && pip install --no-cache-dir --no-deps ultralytics \
    && pip install --no-cache-dir \
        matplotlib pillow pyyaml requests psutil polars nvidia-ml-py httpx \
    && pip install --no-cache-dir --no-deps ultralytics-thop ultralytics-platform

COPY parkwatch ./parkwatch
COPY scripts ./scripts

RUN chmod +x scripts/run_polling.sh

CMD ["./scripts/run_polling.sh"]
