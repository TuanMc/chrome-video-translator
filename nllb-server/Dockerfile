# CPU-only image — matches the dev setup (server/README.md). No GPU support
# here; if you have an NVIDIA GPU and want to use it, you'd need a CUDA base
# image and the NVIDIA Container Toolkit on the host, not covered here.
FROM python:3.11-slim

WORKDIR /app

# System deps: faster-whisper/av need libgomp1 (OpenMP) and ffmpeg's codecs
# are handled by PyAV's own wheel, but libsndfile-adjacent audio decode paths
# can need libgomp1 at runtime on slim images.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# CPU-only torch wheel first, same reasoning as server/README.md's manual
# setup — a plain `pip install torch` (or listing it in requirements.txt)
# pulls the much larger CUDA-bundled build.
RUN pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu torch

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

# Models download here on first run (see README) — mount a volume at this
# path so they persist across container restarts instead of re-downloading
# ~2.5GB every time.
ENV HF_HOME=/data/hf-cache
RUN mkdir -p /data/hf-cache

# Off by default already in code (see app/config/settings.py) — restated here
# for visibility, not because the default changes.
ENV SAVE_DEBUG_AUDIO=false

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
