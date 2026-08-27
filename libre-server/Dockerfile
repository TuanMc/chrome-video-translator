# CPU-only image — this server only runs faster-whisper locally (translation
# is a separate LibreTranslate container, see docker-compose.yml), so unlike
# nllb-server there's no torch/CUDA consideration here at all.
FROM python:3.11-slim

WORKDIR /app

# System deps: faster-whisper/av need libgomp1 (OpenMP) and ffmpeg's codecs
# are handled by PyAV's own wheel, but libsndfile-adjacent audio decode paths
# can need libgomp1 at runtime on slim images.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

# Whisper's model downloads here on first run (see README) — mount a volume
# at this path so it persists across container restarts instead of
# re-downloading every time.
ENV HF_HOME=/data/hf-cache
RUN mkdir -p /data/hf-cache

# Off by default already in code (see app/config/settings.py) — restated here
# for visibility, not because the default changes.
ENV SAVE_DEBUG_AUDIO=false

# 8001, not 8000 — nllb-server takes 8000 so both can run at the same time
# (see README.md).
EXPOSE 8001

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]
