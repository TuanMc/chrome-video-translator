# Lightest of the three servers — no local model, no faster-whisper/torch,
# so no libgomp1 or CUDA considerations at all. Soniox does STT+translation
# entirely on their end, over an outbound WebSocket (see
# app/providers/soniox_client.py).
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

# SONIOX_API_KEY is required at runtime but deliberately NOT declared here —
# pass it with `-e SONIOX_API_KEY=...` at `docker run` time (see
# run-server.bat / README.md) so it never ends up baked into an image layer.
# The app itself defaults to "" and logs a warning if it's missing (see
# app/main.py) rather than refusing to start.

# Off by default already in code (see app/config/settings.py) — restated here
# for visibility, not because the default changes.
ENV SAVE_DEBUG_AUDIO=false

# 8002 — nllb-server takes 8000, libre-server takes 8001.
EXPOSE 8002

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8002"]
