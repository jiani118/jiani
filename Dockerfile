FROM python:3.12-slim

# ffmpeg 用于合并音视频（1080p 及以上必需）
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py index.html manifest.json sw.js icon-192.png icon-512.png ./

EXPOSE 8000

# 任务状态保存在内存里，所以只能用 1 个 worker，并发靠线程
CMD ["gunicorn", "-w", "1", "--threads", "8", "--timeout", "0", "-b", "0.0.0.0:8000", "app:app"]
